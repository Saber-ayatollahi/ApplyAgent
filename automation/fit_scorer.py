#!/usr/bin/env python3
"""
fit_scorer.py — Smart fit-scoring for scan results.

Takes a scraper-output JSON (scan_YYYYMMDD.json) and scores every candidate against
Saber's Master Repository profile. Outputs a scored JSON with per-role:

  - fit_score (1-10)
  - fit_verdict ("apply_now" | "tailor_and_apply" | "watch" | "skip")
  - top_3_reasons (why this matches)
  - skill_gaps (what Saber lacks for this role)
  - tier (1-4)
  - summary (30-word pitch of why to apply)

Uses a 2-stage pipeline:
  Stage 1: fast rule-based triage (title + company + keywords) → drop junk, cheap.
  Stage 2: LLM scoring for surviving candidates, with JD fetched, 1 call per role.

JD fetch is cached to disk (jd_cache/) so re-runs on the same scan are free.

Usage:
    python fit_scorer.py                              # score latest scan
    python fit_scorer.py --scan scan_20260512.json
    python fit_scorer.py --scan scan_20260512.json --limit 50
    python fit_scorer.py --dry-run                    # rule-stage only, no API calls
    python fit_scorer.py --only "Director" --only "VP"  # regex filter titles
    python fit_scorer.py --rescore                    # ignore cache, re-call LLM

Outputs:
    automation/outputs/scan_<date>_scored.json        # full scored list
    automation/outputs/scan_<date>_scored.md          # human-readable report
    automation/outputs/jd_cache/<url-hash>.txt        # cached JD text (persistent)
    automation/outputs/fit_cache/<url-hash>.json      # cached fit scores (persistent)
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import time

# Force UTF-8 stdio so emoji + ∪ symbols don't crash cp1252 Windows
# consoles. errors="replace" so a print of an unencodable char becomes
# '?' instead of a fatal exception.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Event
from typing import Optional

# Set by score_with_llm when a fatal (billing/auth) API error is detected.
# All pending jobs short-circuit once this is set.
_abort_event = Event()
_abort_reason: list[str] = []  # mutable so threads can write

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    print("ERROR: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

try:
    import anthropic  # type: ignore
except ImportError:
    anthropic = None  # type: ignore

# Deterministic JD → skill / variant / gap analysis. Runs BEFORE the LLM call so
# the LLM gets pre-computed facts injected into its prompt. Optional — if the
# master_repo YAMLs or loader aren't available, we silently fall back to
# LLM-only scoring (legacy behavior).
try:
    from jd_skill_extract import extract as _jd_extract  # type: ignore
except ImportError:
    try:
        from .jd_skill_extract import extract as _jd_extract  # type: ignore
    except Exception:
        _jd_extract = None  # type: ignore

# Central error log. Replaces `except Exception: pass` on best-effort paths so
# silent failures (progress writes, cache reads, etc.) land in logs/errors.jsonl.
try:
    from error_log import log_error as _log_error  # type: ignore
except ImportError:
    try:
        from .error_log import log_error as _log_error  # type: ignore
    except Exception:
        _log_error = None  # type: ignore

# Cost guardrail: daily + per-run USD caps. Lazy-constructed in main() so
# `--dry-run` (which never calls the LLM) bypasses it entirely.
try:
    from cost_guard import CostGuard as _CostGuard  # type: ignore
except ImportError:
    try:
        from .cost_guard import CostGuard as _CostGuard  # type: ignore
    except Exception:
        _CostGuard = None  # type: ignore

# Outcome feedback — pipeline conversion data injected into the system prompt
# once the tracker starts accumulating Applied/Interview/Offer transitions.
# Returns "" until there's real signal, so pre-application runs see no change.
try:
    from outcome_feedback import prompt_snippet as _outcome_prompt_snippet  # type: ignore
except ImportError:
    try:
        from .outcome_feedback import prompt_snippet as _outcome_prompt_snippet  # type: ignore
    except Exception:
        _outcome_prompt_snippet = None  # type: ignore

# The guard is a process-global so _cost_tick can accumulate spend without
# threading through every function signature. main() sets it before spawning
# workers; None means "no guard active" (legacy behavior).
_cost_guard: "Optional[_CostGuard]" = None  # type: ignore

# Lifetime cost ledger (never-reset, cumulative across sessions).
try:
    from cost_ledger import record as _ledger_record  # type: ignore
except ImportError:
    # Same-package relative import fallback
    try:
        from .cost_ledger import record as _ledger_record  # type: ignore
    except Exception:
        _ledger_record = None  # type: ignore

# Suppression registry — sector/company mutes consulted at triage. Dormant when
# the live file is empty (default state); short-circuits with no extra work.
try:
    import suppressions as _suppressions  # type: ignore
except ImportError:
    try:
        from . import suppressions as _suppressions  # type: ignore
    except Exception:
        _suppressions = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
JD_CACHE = OUT_DIR / "jd_cache"
FIT_CACHE = OUT_DIR / "fit_cache"
MASTER_REPO = ROOT / "docs" / "Saber_Ayatollahi_Master_Repository.md"
PROGRESS_PATH = OUT_DIR / "fit_scorer_progress.json"

MODEL = os.environ.get("FIT_SCORER_MODEL", "claude-haiku-4-5-20251001")
# Fallback must be a DIFFERENT model — otherwise score_with_llm's retry loop
# burns 2× attempts against the same model on any non-transient failure.
# Sonnet is a stronger model that a rare Haiku parse-failure on a weird JD is
# very unlikely to repeat on. Cost impact is ~$0.01 per fallback, rare.
FALLBACK_MODEL = os.environ.get("FIT_SCORER_FALLBACK_MODEL", "claude-sonnet-4-6")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to `path` via tempfile + os.replace.

    A raw write_text() opens with 'w' which truncates immediately — a crash
    or external-reader between truncate and write sees an empty/partial file.
    fit_cache and jd_cache use this helper so the cache files are always
    either old-and-complete or new-and-complete, never mid-write."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                                prefix=path.name + ".",
                                suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def _atomic_write_json(path: Path, data: dict) -> None:
    """tmp-file-and-replace JSON write so a concurrent reader (UI Action
    Plan) never sees a missing or half-written `worklist_scored.json`.
    Mirrors `worklist._atomic_write_json` — kept local so importing the
    sibling module isn't a hard dep at this call site."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".",
                                suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Per-cache-path lock dict. The lock is acquired ONLY around the cache write
# (see the double-checked-locking block in score_with_llm). Two concurrent
# workers scoring the same URL still both make the LLM call — we don't hold
# the lock through the call (would head-of-line-block sibling threads on a
# 5-30s API round-trip). The lock just guarantees that whichever response
# lands first wins the cache file, and the second writer reads-and-returns
# rather than overwriting. Cost impact: in the rare case of duplicate URLs
# in the scan input, one extra Haiku call per duplicate (~$0.001).
# ---------------------------------------------------------------------------
_fit_cache_locks_guard = Lock()
_fit_cache_locks: dict[str, Lock] = {}

# Prior-run scored fit index, keyed by canonical URL. Populated once at
# main() startup from worklist_scored.json. score_with_llm consults this on
# cache miss when the worklist marked the row as is_new_since_last_score=False
# (i.e. the same URL was already scored in the previous run) — saves a Haiku
# call when the fit-cache file was orphaned by a key-canonicalization bump or
# a manual cache wipe.
_prev_fit_index: dict[str, dict] = {}

_FIT_CACHE_LOCK_CAP = 1024


def _fit_cache_lock(path: Path) -> Lock:
    """Get-or-create the per-cache-path lock. Capped to prevent unbounded
    growth in long-running processes (Streamlit-hosted scorer over many
    sessions). When the dict exceeds the cap, evict the oldest insertion —
    the worst case is a single redundant LLM call for a path whose lock
    we forgot, which is the same blast radius as the bug this lock was
    added to fix in the first place."""
    key = str(path)
    with _fit_cache_locks_guard:
        lock = _fit_cache_locks.get(key)
        if lock is None:
            if len(_fit_cache_locks) >= _FIT_CACHE_LOCK_CAP:
                # Drop oldest. Python 3.7+ dicts preserve insertion order.
                _oldest_key = next(iter(_fit_cache_locks))
                _fit_cache_locks.pop(_oldest_key, None)
            lock = Lock()
            _fit_cache_locks[key] = lock
        return lock


# ---------------------------------------------------------------------------
# Live progress — writes outputs/fit_scorer_progress.json after each candidate
# so the Streamlit UI can show a progress bar, ETA, and the last-N results.
# ---------------------------------------------------------------------------
_progress_lock = Lock()
_progress_state: dict = {
    "state": "idle",
    "scan": None,
    "total": 0,
    "current": 0,
    "cache_hits": 0,
    "errors": 0,
    "started_at": None,
    "updated_at": None,
    "elapsed_sec": 0.0,
    "eta_sec": None,
    "verdict_counts": {},
    "recent": deque(maxlen=8),  # last-N scored candidates
}


def _write_progress():
    """Snapshot under _progress_lock then write atomically outside it.

    The previous implementation held _progress_lock during the file write,
    so every progress_tick / _cost_tick serialized on disk IO. With 6-worker
    concurrency this throttles scoring on slow disks (especially Windows
    machines with antivirus scanning the JSON file).

    Snapshotting is cheap and stays under the lock. The disk write itself
    happens outside the lock — but uses tempfile + os.replace so two
    concurrent writers can't truncate-tear the same file (which a raw
    write_text WOULD do, since 'w' mode truncates).
    """
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with _progress_lock:
            serializable = dict(_progress_state)
            serializable["recent"] = list(_progress_state["recent"])
        # Atomic write: tempfile in same directory + os.replace. Multiple
        # workers may call this concurrently; each write is self-consistent
        # and os.replace is atomic on POSIX + Win32, so a reader never sees
        # a partial JSON. Last-writer-wins for the contents — fine since
        # each snapshot is complete.
        import tempfile
        fd, tmp = tempfile.mkstemp(
            dir=str(PROGRESS_PATH.parent),
            prefix=PROGRESS_PATH.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
            os.replace(tmp, PROGRESS_PATH)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
    except Exception as e:
        if _log_error is not None:
            _log_error("progress_write", e, module="fit_scorer")


def progress_begin(scan_name: str, total: int):
    with _progress_lock:
        _progress_state.update({
            "state": "running",
            "scan": scan_name,
            "total": total,
            "current": 0,
            "cache_hits": 0,
            "errors": 0,
            "started_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "elapsed_sec": 0.0,
            "eta_sec": None,
            "verdict_counts": {},
            "recent": deque(maxlen=8),
        })
    _write_progress()


def progress_tick(candidate: dict, from_cache: bool, error: bool, t0: float):
    with _progress_lock:
        _progress_state["current"] += 1
        if from_cache:
            _progress_state["cache_hits"] += 1
        if error:
            _progress_state["errors"] += 1
        cur = _progress_state["current"]
        total = _progress_state["total"] or 1
        elapsed = time.time() - t0
        _progress_state["elapsed_sec"] = round(elapsed, 1)
        remaining = total - cur
        rate = cur / elapsed if elapsed > 0 else 0
        _progress_state["eta_sec"] = round(remaining / rate, 1) if rate > 0 else None
        _progress_state["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        f = candidate.get("fit") or {}
        verdict = f.get("fit_verdict", "?")
        _progress_state["verdict_counts"][verdict] = (
            _progress_state["verdict_counts"].get(verdict, 0) + 1
        )
        _progress_state["recent"].append({
            "company": candidate.get("company", ""),
            "title": (candidate.get("title") or "")[:80],
            "score": f.get("fit_score"),
            "verdict": verdict,
            "from_cache": from_cache,
            "error": error,
        })
    _write_progress()


def progress_end(state: str = "finished"):
    with _progress_lock:
        _progress_state["state"] = state
        _progress_state["finished_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    _write_progress()


# ---------------------------------------------------------------------------
# Cost telemetry — captures token usage per successful LLM call and sums into
# the progress JSON so the UI can show live $ spend.
# ---------------------------------------------------------------------------
_cost_state = {
    "llm_calls": 0,
    "cache_hits": 0,
    # Subset of cache_hits attributable to the prev-fit second-chance reuse
    # path (worklist_scored.json index hit on cache miss). Surfaces how often
    # we avoid paying for a re-score when fit_cache is orphaned.
    "prev_fit_reuses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_create_tokens": 0,
    "cache_read_tokens": 0,
    "estimated_cost_usd": 0.0,
    "per_model": {},  # model -> {"calls": n, "in_tokens": n, "out_tokens": n, "cost_usd": f}
}


def _cost_tick(model: str | None = None, in_tokens: int = 0, out_tokens: int = 0,
               cache_create: int = 0, cache_read: int = 0, cache_hit: bool = False,
               prev_fit_reuse: bool = False):
    cost = 0.0
    with _progress_lock:
        if cache_hit:
            _cost_state["cache_hits"] += 1
            if prev_fit_reuse:
                _cost_state["prev_fit_reuses"] += 1
        else:
            _cost_state["llm_calls"] += 1
            _cost_state["input_tokens"] += in_tokens
            _cost_state["output_tokens"] += out_tokens
            _cost_state["cache_create_tokens"] += cache_create
            _cost_state["cache_read_tokens"] += cache_read
            cost = _estimate_cost_usd(model or "?", in_tokens, out_tokens)
            _cost_state["estimated_cost_usd"] += cost
            m = _cost_state["per_model"].setdefault(
                model or "?", {"calls": 0, "in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0})
            m["calls"] += 1
            m["in_tokens"] += in_tokens
            m["out_tokens"] += out_tokens
            m["cost_usd"] += cost
        # Mirror to progress state so the UI sees it
        _progress_state["cost"] = dict(_cost_state)
    _write_progress()

    # Cost guardrail: record this call and trip the abort event if either
    # cap is exceeded. Outside the progress lock so the ledger-based daily
    # cap check doesn't hold up progress writers.
    if _cost_guard is not None and not cache_hit and cost > 0:
        _cost_guard.record(cost)
        if _cost_guard.exceeded():
            _cost_guard.trigger_abort(_abort_event, _abort_reason)

    # Append to the lifetime ledger outside the progress lock so a slow
    # disk write on the ledger file never blocks the scorer's progress
    # writes. The ledger has its own internal lock for concurrent ticks.
    if _ledger_record is not None:
        try:
            _ledger_record(
                model=model or "?",
                in_tokens=in_tokens,
                out_tokens=out_tokens,
                cost_usd=cost,
                cache_create=cache_create,
                cache_read=cache_read,
                cache_hit=cache_hit,
            )
        except Exception as e:
            # Ledger write is best-effort — the session-level telemetry in
            # _cost_state is still accurate for this run.
            if _log_error is not None:
                _log_error("ledger_record", e, module="fit_scorer")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Input-token rate limiter — Anthropic org cap is 50k input TPM. Keep a 60s
# sliding window of recent (timestamp, tokens) entries; before each call,
# block until the window has room. Cap is set ~10% under the org limit so
# concurrent telemetry/preflight traffic doesn't tip us over.
# ---------------------------------------------------------------------------
_TPM_CAP = int(os.environ.get("FIT_SCORER_INPUT_TPM_CAP", "45000"))
_TPM_WINDOW_SEC = 60.0
_tpm_lock = Lock()
_tpm_log: deque[tuple[float, int]] = deque()


def _tpm_reserve(tokens: int) -> None:
    """Block until `tokens` will fit under _TPM_CAP within the next 60s window.

    Single-call payload larger than the cap is admitted anyway — refusing it
    would deadlock; the API will 429 and our existing retry loop handles it.
    """
    if tokens <= 0:
        return
    while True:
        with _tpm_lock:
            now = time.monotonic()
            cutoff = now - _TPM_WINDOW_SEC
            while _tpm_log and _tpm_log[0][0] < cutoff:
                _tpm_log.popleft()
            in_window = sum(t for _, t in _tpm_log)
            if in_window + tokens <= _TPM_CAP or not _tpm_log:
                _tpm_log.append((now, tokens))
                return
            wait = max(0.05, _tpm_log[0][0] + _TPM_WINDOW_SEC - now)
        time.sleep(min(wait, 1.0))


def _estimate_input_tokens(system_text: str, user_text: str) -> int:
    """Cheap char-based estimate (~4 chars/token). Good enough for budgeting;
    actual usage is reconciled into _cost_state from resp.usage."""
    return max(1, (len(system_text) + len(user_text)) // 4 + 32)

# ---------------------------------------------------------------------------
# Stage 1 — rule-based triage.
# ---------------------------------------------------------------------------
NEG_TITLE_TERMS = [
    # Junior / student roles
    "intern", "internship", "co-op", "coop", "student", "graduate program",
    "analyst program", "associate program", "leadership program",
    "fall 2026", "spring 2026", "summer 2026", "winter 2026",
    "fall 2027", "spring 2027", "summer 2027",
    "new grad", "new graduate", "rotational program",
    # Retail / consumer-facing banking
    "retail branch", "teller", "branch manager", "customer service",
    "personal banker", "personal banking associate", "mobile mortgage",
    "financial advisor", "financial planner", "wealth advisor",
    "investment advisor", "investment advisor i", "advisor trainee",
    "insurance advisor", "sun life financial advisor",
    # Sales / BD / marketing
    "sales representative", "account executive", "business development representative",
    "marketing", "social media", "content writer", "communications",
    "public relations",
    # Facilities / admin / ops
    "cleaning", "security guard", "janitor", "facilities",
    "receptionist", "administrative assistant", "executive assistant",
    # Wrong engineering disciplines
    "scientist, chemistry", "mechanical engineer", "electrical engineer",
    "civil engineer", "materials engineer", "chemical engineer",
    # Pure software roles (Saber is finance-quant, not dev)
    "web developer", "front end developer", "frontend developer",
    "full stack developer", "full-stack developer", "full stack engineer",
    "backend developer", "ui/ux", "ux designer", "ui designer",
    "mobile developer", "android developer", "ios developer",
    "software developer (junior)", "junior developer",
    "sdet", "qa analyst", "qa engineer", "qa automation",
    "quality engineer", "automation tester", "test engineer",
    "java developer", ".net developer", "python developer",
    "devops engineer", "site reliability", "platform engineer",
    "application support", "production support",
    # Software engineering variants — Saber is not a SWE even when the role is
    # "risk-adjacent". These burn LLM budget to always return verdict=skip.
    "software engineer", "staff engineer", "principal engineer",
    "staff software", "senior software engineer",
    "data engineer", "senior data engineer", "machine learning engineer",
    "ml engineer", "ai engineer", "cloud engineer", "network engineer",
    "security engineer", "infrastructure engineer",
    "technical lead", "tech lead", "lead engineer",
    "database administrator", "dba,", "sre ",
    "scrum master", "agile coach",
    "penetration tester", "pentester",
    # Legal / audit-only / generic
    "senior counsel", "junior counsel", "legal counsel",
    "registered supervisor",
]


# Weighted positive signals. score ≥ 3 passes stage 1.
# Matched longest-first; each distinct phrase contributes its weight once.
STRONG_POS = [  # +3 each — unambiguous lane hits
    "alm", "asset liability", "asset-liability",
    "irrbb", "interest rate risk",
    "model validation", "model risk", "model vetting", "model governance",
    "model oversight", "model development",
    "treasury risk", "balance sheet",
    "funds transfer pricing", "fund transfer pricing", "ftp",
    "ldi", "liability driven", "liability-driven",
    "fixed income", "liquidity risk", "market risk",
    "credit risk model", "credit risk analytics",
    "ifrs 17", "ifrs17", "ifrs 9", "ifrs9",
    "capital model", "stress test", "stress testing",
    "enterprise risk", "aladdin", "bloomberg risk",
    "actuarial", "actuary",
    "stochastic", "monte carlo",
    "e-23", "b-12", "basel",
    "regulatory capital", "economic capital", "capital adequacy",
    "counterparty credit", "cva", "xva",
    "risk officer", "chief risk", "head of risk",
    "risk director", "risk vp",
    "derivatives pricing", "derivatives valuation",
    "scenario generation", "scenario analysis",
    # Rates / fixed-income strong terms (restored)
    "rates trading", "rates strategy", "rates strategist",
    "rates structuring", "rates desk", "linear rates", "exotic rates",
    "swaps trader", "swap desk", "g10 rates",
    # Structured / capital markets
    "securitization", "structured credit", "structured finance",
    "credit structuring", "debt structuring", "rates structuring",
    "collateralized", "clo ", "abs trader",
    # OSFI-adjacent emerging
    "climate risk", "climate financial", "b-15",
    "crypto treasury", "digital asset", "digital assets",
    "model risk management", "mrm",
]

MEDIUM_POS = [  # +2 each — domain-adjacent signals; a single hit passes stage 1
    "quantitative", "valuation",
    "portfolio risk", "risk analytics", "portfolio analytics",
    "total portfolio", "investment finance",
    "risk modeling", "risk modelling",
    "financial modeling", "financial modelling",
    "financial risk", "investment risk",
    "treasury", "capital risk", "capital governance",
    "liquidity reporting", "capital reporting",
    "regulatory reporting", "financial reporting",
    "credit risk", "operational risk",
    "risk governance", "risk management",
    "model governance", "ai governance", "model risk governance",
    "reserving", "pricing actuary",
    "forecasting model", "forecasting models",
    "derivatives", "securitization", "structured credit",
    "hedge accounting", "hedging",
    "osfi", "lcr", "nsfr", "lar",
    "insurance investment", "insurance solutions",
    # Resolution/recovery planning (OSFI reg)
    "resolution planning", "recovery and resolution", "erm",
    # Balance-sheet-adjacent senior-role vocab that wasn't covered
    "balance sheet strategy", "treasury strategy", "capital strategy",
    "liquidity strategy", "risk strategy",
    "capital planning", "liquidity planning", "stress planning",
    # Strategy-flavored roles with a finance/risk noun attached are worth the LLM look
    "risk transformation", "finance transformation", "risk framework",
    # French equivalents for QC postings
    "validation des modèles", "gestion de l'actif", "gestion des risques",
    "risque de crédit", "risque de marché", "analytique", "modélisation",
]

WEAK_POS = [  # +1 each — noisy tokens, require combos
    "risk", "capital", "liquidity",
    "quant", "analytics", "modeling", "modelling",
    "model", "reporting",
    # Strategy / planning / advisory / transformation — noisy on their own, but
    # at Director+ seniority they're often risk/ALM/treasury roles in disguise.
    # These pass stage-1 only when combined with a level term (see pass rules).
    "strategy", "strategic", "planning", "advisory",
    "framework", "transformation", "governance",
    "enterprise", "corporate development",
    # Finance-domain nouns that often accompany strategy/planning roles
    "finance", "financial", "investment", "portfolio",
    "balance sheet", "fixed income", "derivative",
]

LEVEL_TERMS = [  # +1 each — target seniority
    "director", "senior director", "vp", "vice president", "avp",
    "head of", "principal", "managing director", "associate director",
    "senior vice", "senior manager", "sr manager", "sr. manager",
    "senior consultant", "chief", "lead",
    "manager", "senior",
]

DIR_LEVEL_TERMS = (  # for tier classification
    "director", "vp", "vice president", "head of",
    "principal", "managing director", "associate director",
    "chief", "avp",
)
MGR_LEVEL_TERMS = (
    "senior manager", "sr manager", "sr. manager",
)

STAGE1_THRESHOLD = 2  # lowered from 3 — see stage1_pass() for combo rules


def _distinct_hits(title_lower: str, phrases: list[str]) -> list[str]:
    """Return phrases found in title_lower, longest-first, with substring
    suppression (so "risk analytics" matching blocks the shorter "risk" hit)."""
    hits: list[str] = []
    taken_spans: list[tuple[int, int]] = []
    for p in sorted(phrases, key=len, reverse=True):
        idx = title_lower.find(p)
        if idx < 0:
            continue
        end = idx + len(p)
        # Skip if overlaps an already-taken span
        if any(start < end and idx < e for start, e in taken_spans):
            continue
        hits.append(p)
        taken_spans.append((idx, end))
    return hits


# Module-level cache for the suppression snapshot — loaded once per process so
# a 1,400-row scoring run reads the registry exactly once. Sentinel `_UNSET`
# distinguishes "not yet loaded" from "loaded as None" (env var unset).
_UNSET = object()
_suppression_snapshot_cache: object = _UNSET


def _load_suppression_snapshot() -> dict | None:
    """Read the suppression snapshot pointed to by APPLYAGENT_SUPPRESSIONS_SNAPSHOT.

    Returns the parsed dict on success; None when the env var is unset OR the
    file is missing/unreadable — graceful degradation, never crashes the run.
    Cached module-level so a 1,400-row scoring loop reads the registry once."""
    global _suppression_snapshot_cache
    if _suppression_snapshot_cache is not _UNSET:
        return _suppression_snapshot_cache  # type: ignore[return-value]
    path_str = os.environ.get("APPLYAGENT_SUPPRESSIONS_SNAPSHOT")
    if not path_str:
        _suppression_snapshot_cache = None
        return None
    p = Path(path_str)
    if not p.exists():
        _suppression_snapshot_cache = None
        return None
    try:
        snap = json.loads(p.read_text(encoding="utf-8"))
        _suppression_snapshot_cache = snap if isinstance(snap, dict) else None
    except Exception as _e:
        if _log_error is not None:
            _log_error("suppression_snapshot_load", _e, module="fit_scorer")
        _suppression_snapshot_cache = None
    return _suppression_snapshot_cache  # type: ignore[return-value]


def _snapshot_has_entries(snap: dict | None) -> bool:
    """True if the snapshot contains any active sector or company entries."""
    if not snap:
        return False
    return bool(snap.get("sectors")) or bool(snap.get("companies"))


def rule_triage(title: str,
                row: dict | None = None,
                suppression_snapshot: dict | None = None,
                only_url_override: bool = False) -> dict:
    """Weighted stage-1 triage. Passes if total score >= STAGE1_THRESHOLD.

    Returns {stage1_pass, rough_tier, score, rule_reasons, hits_breakdown}.

    Triage ordering: negative_term -> suppression -> keyword/level. Suppression
    consults `suppression_snapshot` (or live state if None and the suppressions
    module is available); when `only_url_override` is True, a suppressed match
    is recorded as `override_reason: manual_only_url` in `rule_reasons` instead
    of dropping the row.
    """
    t = (title or "").lower()
    # Hard-fail on negative term
    for n in NEG_TITLE_TERMS:
        if n in t:
            return {"stage1_pass": False, "rough_tier": 5, "score": 0,
                    "rule_reasons": [f"neg:{n}"], "hits_breakdown": {}}

    # Suppression check — applied after neg-term (correctness) but before the
    # keyword/level scoring (taste). Short-circuits cleanly when the snapshot
    # is empty so the dormant default state stays byte-identical to legacy.
    suppression_override_reason: str | None = None
    if row is not None and _suppressions is not None:
        snap = suppression_snapshot
        if snap is None:
            # Caller didn't pre-load a snapshot; consult the env-var path or
            # fall back to live state once (live load itself is cheap; the
            # caller is expected to pass the result into per-row calls so we
            # don't reload 1,400 times — main() does this).
            snap = _load_suppression_snapshot()
        if _snapshot_has_entries(snap):
            try:
                suppressed, drop_reason = _suppressions.is_suppressed(row, snapshot=snap)
            except Exception as _e:
                if _log_error is not None:
                    _log_error("suppression_check", _e, module="fit_scorer")
                suppressed, drop_reason = False, None
            if suppressed and drop_reason:
                if only_url_override:
                    # Record the override; row continues into keyword scoring.
                    suppression_override_reason = drop_reason
                else:
                    return {"stage1_pass": False, "rough_tier": 5, "score": 0,
                            "rule_reasons": [drop_reason], "hits_breakdown": {}}

    strong = _distinct_hits(t, STRONG_POS)
    # Medium and weak are matched against the remaining (post-strong) title
    # to avoid double-counting "risk" inside "liquidity risk", etc.
    remaining = t
    for s in strong:
        remaining = remaining.replace(s, " ")
    medium = _distinct_hits(remaining, MEDIUM_POS)
    for m in medium:
        remaining = remaining.replace(m, " ")
    weak = _distinct_hits(remaining, WEAK_POS)
    level = _distinct_hits(t, LEVEL_TERMS)

    score = 3 * len(strong) + 2 * len(medium) + 1 * len(weak) + 1 * min(len(level), 2)
    breakdown = {"strong": strong, "medium": medium, "weak": weak, "level": level}
    reasons = []
    # Audit trail for --only-url overriding a would-be suppression drop.
    if suppression_override_reason is not None:
        reasons.append("override_reason:manual_only_url")
        reasons.append(f"would_have_dropped:{suppression_override_reason}")
    if strong: reasons.append(f"strong={strong[:3]}")
    if medium: reasons.append(f"medium={medium[:3]}")
    if weak: reasons.append(f"weak={weak[:3]}")
    if level: reasons.append(f"level={level[:2]}")

    # Pass rules (OR'd):
    #   - any STRONG hit                      -> pass (core lane term)
    #   - any MEDIUM hit                      -> pass (domain-specific)
    #   - any WEAK hit + level                -> pass ("Senior Manager, Liquidity Management")
    #   - >=2 WEAK hits                       -> pass ("Capital Risk Analyst")
    #   - Director/VP/Head/Principal/MD level + ANY weak hit -> pass
    #     ("VP, Strategy" alone still drops; "VP, Strategy & Corporate Development"
    #     now passes — 'strategy' + 'corporate development' = 2 weak hits; "Director,
    #     Treasury Strategy" passes via the multi-weak rule too.)
    #     This deliberately widens the funnel for senior roles since the LLM cost is
    #     cheap (~$0.001/role at Haiku) and false-positives get scored=skip.
    # A pure LEVEL-only match does NOT pass — too noisy.
    pass_reason = None
    if strong:
        pass_reason = "strong_hit"
    elif medium:
        pass_reason = "medium_hit"
    elif weak and level:
        pass_reason = "weak+level"
    elif len(weak) >= 2:
        pass_reason = "multi_weak"

    if not pass_reason:
        return {"stage1_pass": False, "rough_tier": 5, "score": score,
                "rule_reasons": reasons or ["insufficient_signal"],
                "hits_breakdown": breakdown}
    reasons.append(f"pass:{pass_reason}")

    # Tier classification
    has_dir = any(l in t for l in DIR_LEVEL_TERMS)
    has_mgr = any(l in t for l in MGR_LEVEL_TERMS)
    if strong and has_dir:
        rough = 1
    elif strong and has_mgr:
        rough = 2
    elif strong:
        rough = 3
    elif has_dir and (medium or weak):
        rough = 3  # Director of something-adjacent; LLM can judge
    elif medium:
        rough = 3
    else:
        rough = 4

    return {"stage1_pass": True, "rough_tier": rough, "score": score,
            "rule_reasons": reasons, "hits_breakdown": breakdown}


# ---------------------------------------------------------------------------
# JD fetching (cached to disk)
# ---------------------------------------------------------------------------
def _canonicalize_url(url: str) -> str:
    """Canonicalize a JD URL before hashing so ?utm_source=…, trailing slash,
    scheme/host case, and LinkedIn tracking-redirect variants all collapse to
    the same cache key. Mirrors worklist.norm_url so the scorer's per-URL cache
    matches the worklist's dedup key."""
    if not url:
        return ""
    try:
        from worklist import norm_url  # type: ignore
    except ImportError:
        try:
            from .worklist import norm_url  # type: ignore
        except Exception:
            norm_url = None  # type: ignore
    if norm_url is not None:
        n = norm_url({"link": url})
        if n:
            return n
    base = str(url).split("#", 1)[0].split("?", 1)[0]
    return base.rstrip("/").lower()


def _url_hash(url: str) -> str:
    return hashlib.sha1(_canonicalize_url(url).encode("utf-8")).hexdigest()[:16]


# Boilerplate regexes — applied AFTER HTML stripping, before we send to the LLM.
# Order matters: we strip the biggest noise first (paragraphs), then single lines.
_BOILERPLATE_PATTERNS = [
    # EEO / diversity statements — common phrasings
    re.compile(r"(?is)(?:is\s+)?(?:an\s+)?equal opportunity employer[^\n]*?\n.*?"
               r"(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)(?:we are\s+)?committed to (?:fostering|building|creating|providing)\s+"
               r"(?:a\s+)?(?:diverse|inclusive|welcoming).*?(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)qualified applicants will receive consideration.*?(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)accommodation(?:s)? (?:is|are) available.*?(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)persons with disabilities.*?(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)aoda[^\n]*\n.*?(?=\n\s*\n|\Z)"),
    # Cookie / privacy notices
    re.compile(r"(?is)this (?:website|site) uses cookies.*?(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)by clicking\s+[\"']?accept[\"']?.*?(?=\n\s*\n|\Z)"),
    re.compile(r"(?is)privacy (?:policy|notice|statement)[^\n]*\n.*?(?=\n\s*\n|\Z)"),
    # Marketing fluff
    re.compile(r"(?is)follow us on[^\n]*\n?"),
    re.compile(r"(?im)^\s*(?:share|apply|save|print|email)\s+(?:this|to)?\s*(?:job|link|posting|role|offer)?\s*$\n?"),
    re.compile(r"(?im)^\s*(?:apply now|save job|back to results|return to search|job details|full job description|share this role)\s*$\n?"),
    # Careers-page nav leftovers
    re.compile(r"(?is)job (?:alerts|search|openings|category|function|family)[^\n]*\n"),
]

# Section-header hints — tiered by signal value. P1 hints tell the LLM what the
# job ACTUALLY IS (responsibilities/duties); P2 hints tell it about required
# background; P3 hints describe the role context; P4 hints are marketing fluff.
# _extract_sections walks tiers in order and returns the first tier with a hit
# whose position is reasonable. Before this change, we picked the EARLIEST hit
# regardless of tier — so "About Us" at pos 200 beat "Responsibilities" at pos
# 5000, sending 6 KB of marketing text to the LLM instead of the job content.
_SECTION_HINTS_P1 = (  # Job content (highest signal)
    "responsibilities", "key responsibilities", "what you'll do", "what you will do",
    "your role", "in this role", "the role", "duties", "core duties",
    "role overview", "job description", "job responsibilities",
    # French
    "responsabilités",
)
_SECTION_HINTS_P2 = (  # Required profile
    "qualifications", "requirements", "what you'll bring", "what you bring",
    "must have", "must-have", "experience required", "required experience",
    "required qualifications", "skills we're looking for",
    "we're looking for", "we are looking for", "ideal candidate",
    # French
    "exigences", "profil recherché", "qualifications requises",
)
_SECTION_HINTS_P3 = (  # Role framing
    "about the team", "about the role", "position summary", "job summary",
    "summary", "skills",
)
_SECTION_HINTS_P4 = (  # Low-signal boilerplate — only as last resort before head-of-doc
    "about us", "about the company", "our company", "who we are",
    "benefits", "why join",
)

# Kept for backward compat; unions of the above.
_KEEP_SECTION_HINTS = _SECTION_HINTS_P1 + _SECTION_HINTS_P2 + _SECTION_HINTS_P3


def _clean_jd(raw_text: str) -> str:
    """Strip boilerplate and repeated legal text from a JD. Keeps the high-signal
    sections (responsibilities, qualifications, summary) intact."""
    if not raw_text:
        return ""
    t = raw_text
    for pat in _BOILERPLATE_PATTERNS:
        t = pat.sub("", t)
    # Collapse repeated whitespace
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    # Drop lines that are just punctuation / single words / pure noise
    lines = []
    for ln in t.split("\n"):
        s = ln.strip()
        if not s:
            lines.append("")
            continue
        # Drop pure-nav lines (all caps, <4 words)
        if s.isupper() and len(s.split()) <= 4 and len(s) < 50:
            continue
        # Drop "Apply" / "Save Job" buttons leaked as text
        if s.lower() in ("apply", "apply now", "save", "save job", "print",
                         "share", "back to results", "return to search",
                         "job details", "full job description"):
            continue
        lines.append(ln)
    t = "\n".join(lines)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def _extract_sections(cleaned: str, max_chars: int) -> str:
    """Priority-tiered JD windowing. Walk tiers from highest-signal (P1:
    responsibilities/duties) to lowest (P4: about-us). The first tier with any
    hit wins, and we return max_chars starting from that tier's EARLIEST hit.

    Before this change the function picked the earliest hit across ALL tiers,
    which meant "About Us" at pos 200 beat "Responsibilities" at pos 5000 on
    many JDs — the LLM then got 6 KB of marketing fluff with the actual job
    description truncated off the end.
    """
    if not cleaned or len(cleaned) <= max_chars:
        return cleaned
    lower = cleaned.lower()

    def _earliest_hit(hints: tuple[str, ...]) -> int:
        best = len(cleaned)
        for hint in hints:
            idx = lower.find(hint)
            if 0 <= idx < best:
                best = idx
        return best

    for tier in (_SECTION_HINTS_P1, _SECTION_HINTS_P2,
                  _SECTION_HINTS_P3, _SECTION_HINTS_P4):
        start = _earliest_hit(tier)
        if start < len(cleaned):
            return cleaned[start:start + max_chars]
    # No section header found anywhere — head-of-document fallback.
    return cleaned[:max_chars]


def fetch_jd(url: str, max_chars: int = 8000) -> str:
    """Fetch, strip HTML, clean boilerplate, prefer responsibilities section.

    Caching: we cache the CLEANED text (not raw HTML), so a cache bump is needed
    when the cleaner logic changes. Use a versioned cache filename.

    Empty/short results (common when the page is JS-shell, 404, or blocked by
    anti-bot) are NOT cached, so a later re-run can try again. A short JD is
    flagged to stderr so Saber can see JS-SPA domains that are silently losing
    roles to title-only scoring.
    """
    JD_CACHE.mkdir(parents=True, exist_ok=True)
    # Cache filename versioned — bump when cleaner changes
    cache_path = JD_CACHE / f"{_url_hash(url)}.v2.txt"
    legacy_cache = JD_CACHE / f"{_url_hash(url)}.txt"
    if cache_path.exists():
        return _extract_sections(cache_path.read_text(encoding="utf-8"), max_chars)
    # Retrying GET: handles transient 5xx/429 + Retry-After, logs terminal
    # failures to logs/errors.jsonl. Returns None when retries are exhausted.
    try:
        from http_retry import retry_get  # type: ignore
        r = retry_get(url, headers=HEADERS, timeout=25,
                      max_tries=3, context="fetch_jd")
    except ImportError:
        # Fallback: legacy single-shot GET.
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code != 200:
                r = None
        except Exception as e:
            print(f"  [fetch_jd] err {url}: {e}", file=sys.stderr)
            return ""

    if r is None:
        # http_retry already logged the failure reason + URL to the error log.
        return ""

    # Defense against pathological JD pages (CMS bugs, infinite scroll
    # mirrors, malware-injected megapages). 5 MB is far beyond any real
    # job description; anything larger is an alarm.
    if len(r.text) > 5_000_000:
        if _log_error is not None:
            try:
                raise ValueError(f"JD response too large: {len(r.text)} bytes")
            except Exception as _e:
                _log_error("fetch_jd_oversize", _e, module="fit_scorer",
                           extra={"url": url, "size": len(r.text)})
        print(f"  [fetch_jd] response {len(r.text)} bytes for {url} "
              f"— skipping (over 5 MB cap)", file=sys.stderr)
        return ""

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "button", "form",
                         "aside", "iframe", "noscript"]):
            tag.decompose()
        # Prefer <main> / <article> content if present (most ATS pages have it)
        main = soup.select_one("main, article, .job-description, #job-description, "
                               "[class*='JobDescription'], [class*='job-details']")
        body = main if main else soup
        raw_text = body.get_text("\n")
        cleaned = _clean_jd(raw_text)
        # Don't cache suspiciously-empty results — the page is either JS-shell
        # (needs headless browser) or blocked. Caching would poison future runs.
        if len(cleaned) < 300:
            print(f"  [fetch_jd] short ({len(cleaned)} chars) for {url} "
                  f"— likely JS-SPA; not caching", file=sys.stderr)
            return cleaned  # return what we have but don't persist
        # Legacy cache cleanup
        if legacy_cache.exists():
            try:
                legacy_cache.unlink()
            except Exception as e:
                if _log_error is not None:
                    _log_error("jd_cache_legacy_unlink", e, module="fit_scorer")
        _atomic_write_text(cache_path, cleaned)
        return _extract_sections(cleaned, max_chars)
    except Exception as e:
        if _log_error is not None:
            _log_error("fetch_jd_parse", e, module="fit_scorer",
                        extra={"url": url})
        print(f"  [fetch_jd] parse err {url}: {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Stage 2 — LLM scoring (cached)
# ---------------------------------------------------------------------------

# Resume variants mirror Saber_Ayatollahi_Master_Repository.md §10.
# The scorer picks 1-3 of these per role so the UI + tailor know which to lead with.
RESUME_VARIANTS = ["ALM", "VAL", "VEN", "QUANT", "CON"]

# ---------------------------------------------------------------------------
# Shared strategy text — SINGLE SOURCE OF TRUTH for the scoring rubric.
#
# Both the live prompt (_build_system_prompt) and the dead-path fallback
# (_FALLBACK_SYSTEM_PROMPT) interpolate these blocks, so the strategy can never
# drift between them again. Edit strategy HERE, not in two places.
# (Previously the VEN/QUANT-PRIMARY, opportunistic-stretch, and trading-desk
# rules lived only in the fallback and silently never reached production.)
# ---------------------------------------------------------------------------
_STRATEGY_VARIANTS = (
    "Resume variants Saber can lead with (pick the best-fit 1-3 in your output):\n"
    "- ALM    — Asset-Liability Management, IRRBB, Treasury & Balance-Sheet Risk\n"
    "- VAL    — Model Risk, Validation & Governance\n"
    "- VEN    — Vendor-Platform / Solutions Engineering & Client Solutions\n"
    "           (Aladdin SE, MSCI, S&P, Bloomberg, SS&C)\n"
    "- QUANT  — Investment & Market Risk Analytics (VaR/CVaR, risk decomposition,\n"
    "           portfolio optimization, LDI, stochastic/Monte Carlo)\n"
    "- CON    — Consulting / Advisory (Big 4 FSRM, Mercer, WTW, Oliver Wyman)\n"
    "Vendor-Platform (VEN) and Investment & Market Risk (QUANT) are PRIMARY lanes,\n"
    "co-equal with ALM and VAL — do not treat them as secondary or fallback variants.\n"
)

_STRATEGY_OPPORTUNISTIC = (
    "OPPORTUNISTIC STRETCH — market-risk CAPITAL / methodology roles:\n"
    "Market-risk-CAPITAL and methodology roles (FRTB, CCR / xVA, CCAR, market risk\n"
    "capital methodology) are OPPORTUNISTIC stretch targets worth pursuing — Saber has\n"
    "the metrics (VaR/ES, scenario & reverse-stress testing, derivatives valuation) but\n"
    "not the trading-desk capital machinery. Score these as a stretch worth pursuing:\n"
    "verdict 'watch' or 'tailor_and_apply' (NOT 'skip'), and flag cover-letter framing\n"
    "to bridge the gap. Keep this DISTINCT from pure trading-DESK roles below: a\n"
    "'market risk capital / methodology' role is IN-SCOPE (opportunistic), whereas a\n"
    "'rates trading desk' role is OUT-OF-SCOPE (skip).\n"
)

_STRATEGY_CAPABILITIES = (
    "Reasons MUST cite concrete capabilities Saber demonstrably has: ALM/IRRBB\n"
    "modelling, cash-flow projection engines, delegated sign-off authority, LDI\n"
    "strategy, model validation/governance, VaR/CVaR portfolio optimization, risk\n"
    "decomposition, solutions-engineering / platform client-solutions delivery,\n"
    "vendor-platform implementation (Aladdin/Bloomberg/MSCI/S&P/PFaroe),\n"
    "Python/agentic-AI workflows, or sector experience (pension/insurer/Big 6/vendor).\n"
)

_STRATEGY_OUT_OF_SCOPE = (
    "HARD OUT-OF-SCOPE (score 1-3, verdict=skip):\n"
    "- Pure software engineering (web/mobile/backend/devops/SRE/QA)\n"
    "- Retail banking (teller, personal banker, branch manager, mobile mortgage)\n"
    "- Sales / marketing / communications / PR\n"
    "- Internships, co-ops, student programs, new-grad rotational\n"
    "- Generalist Product Manager / Project Manager (non-risk/non-ALM scope)\n"
    "- Boutique HF quant-research as PRIMARY focus (Saber is buy-side adjacent, not HF)\n"
    "- Pure trading-DESK roles (rates trading, rates strategy/strategist, market-making,\n"
    "  trading desk) — these are out-of-scope/skip. Do NOT confuse these with the\n"
    "  market-risk-capital/methodology roles above, which ARE in-scope (opportunistic).\n"
)

_FALLBACK_SYSTEM_PROMPT = (
    "You are a hard-nosed senior finance career strategist assessing job fit for Saber Ayatollahi.\n"
    "\n"
    "Saber's profile:\n"
    "- CFA charterholder. Dual MSc (Financial Modelling + Chemical Engineering).\n"
    "- ~7.3 years finance experience at Moody's Analytics (ALM/model governance sign-off),\n"
    "  EY (insurance-accounting transformation), Ortec Finance (pension ALM + LDI).\n"
    "- Core competencies: ALM, IRRBB, Market Risk, Model Validation/Governance, Cash-Flow\n"
    "  Projection, LDI, Derivatives valuation & sensitivity validation, VaR/CVaR &\n"
    "  portfolio optimization, risk decomposition, Stochastic Scenario Generation,\n"
    "  Python, agentic AI workflows, enterprise risk-platform delivery,\n"
    "  platform / solutions-engineering client delivery.\n"
    "- Delegated sign-off authority on multi-asset institutional portfolios\n"
    "  ($5-25bn per engagement; $50bn+ cumulative).\n"
    "- Toronto-based, not relocating.\n"
    "\n"
    + _STRATEGY_VARIANTS +
    "\n"
    "Score each role on CAPABILITY FIT against the skill inventory above. Judge whether\n"
    "Saber can do the job and whether the role advances his trajectory. Strategy, market\n"
    "risk, treasury, balance-sheet, valuations, and adjacent lanes are in-scope when\n"
    "seniority is Director / VP / Head / Principal / AVP / Senior Manager at a target\n"
    "Toronto finance employer and the JD has substantive quantitative, risk, or\n"
    "platform-delivery content.\n"
    "\n"
    + _STRATEGY_OPPORTUNISTIC +
    "\n"
    "HARD RULE — top_3_reasons and fit drivers:\n"
    "ABSOLUTE PROHIBITION: top_3_reasons strings MUST NOT contain ANY of these tokens\n"
    "(case-insensitive): 'OSFI', 'E-23', 'B-12', 'LAR', 'IFRS', 'Basel', 'ECL',\n"
    "'guideline', 'regulatory-calendar', 'regulatory tailwind', 'regulatory posture',\n"
    "'regulatory awareness', 'regulatory familiarity'. These are background context\n"
    "only and read as generic. "
    + _STRATEGY_CAPABILITIES +
    "\n"
    + _STRATEGY_OUT_OF_SCOPE +
    "\n"
    "Return ONLY valid JSON matching the schema given, no prose, no markdown.\n"
)


def _extract_repo_sections(repo_text: str) -> str:
    """Extract §4 (Skills Inventory), §7 (Positioning), §10 (Resume Variants) from the
    Master Repository markdown. We keep these sections only — sending the whole 433-line
    repo would cost ~5k input tokens per scan (once, with caching) for noise the scorer
    doesn't need. Section headers in the repo use '## 4.', '## 7.', '## 10.' form.
    """
    if not repo_text:
        return ""

    def _grab(start_marker: str, next_markers: list[str]) -> str:
        idx = repo_text.find(start_marker)
        if idx < 0:
            return ""
        end = len(repo_text)
        for nm in next_markers:
            i = repo_text.find(nm, idx + len(start_marker))
            if 0 <= i < end:
                end = i
        return repo_text[idx:end].strip()

    # Each section is bounded by the next top-level ## heading.
    s4 = _grab("## 4. SKILLS INVENTORY",
                ["## 5.", "## 6.", "## 7.", "## 10."])
    s7 = _grab("## 7. TARGET ROLE POSITIONING",
                ["## 8.", "## 9.", "## 10."])
    s10 = _grab("## 10. RESUME VARIANTS",
                 ["## 11.", "---"])

    parts = [p for p in (s4, s7, s10) if p]
    if not parts:
        return ""
    return "\n\n".join(parts)


def _build_system_prompt() -> str:
    """Build the scorer system prompt.

    Strategy: boilerplate frame + extracted Master Repo sections (Skills §4, Positioning §7,
    Variants §10) + outcome feedback (pipeline conversion data, once there's signal).
    Prompt-cached — the per-scan cost is paid once, the per-role cost is ~$0.
    Falls back to a constant prompt if the repo file is missing or sectioning fails.
    """
    if not MASTER_REPO.exists():
        return _FALLBACK_SYSTEM_PROMPT
    try:
        repo_text = MASTER_REPO.read_text(encoding="utf-8")
    except Exception:
        return _FALLBACK_SYSTEM_PROMPT
    sections = _extract_repo_sections(repo_text)
    if not sections:
        return _FALLBACK_SYSTEM_PROMPT

    outcome_block = ""
    if _outcome_prompt_snippet is not None:
        try:
            snippet = _outcome_prompt_snippet()
            if snippet:
                outcome_block = (
                    "\n# Pipeline-outcome feedback (actual Saber results — weight accordingly)\n\n"
                    f"{snippet}\n"
                    "\nWhen scoring, treat hot-lane slices as slight positive signal and\n"
                    "cold-lane slices as a yellow flag worth noting in `top_3_reasons`.\n"
                )
        except Exception:
            outcome_block = ""

    return (
        "You are a hard-nosed senior finance career strategist assessing job fit for\n"
        "Saber Ayatollahi. Below is Saber's canonical skills inventory, positioning angles,\n"
        "and active resume variants (extracted from the Master Career Repository).\n"
        "\n"
        "# Saber's Master Repository (evidenced skills, positioning, resume variants)\n"
        "\n"
        f"{sections}\n"
        f"{outcome_block}"
        "\n"
        "# How to score\n"
        "\n"
        "Score each role on CAPABILITY FIT against the skill inventory above. Judge\n"
        "whether Saber can do the job and whether the role advances his trajectory.\n"
        "Strategy, market risk, treasury, balance-sheet, valuations, and adjacent lanes\n"
        "are IN SCOPE when the seniority is Director / VP / Head / Principal / AVP /\n"
        "Senior Manager at a target Toronto finance employer and the JD has substantive\n"
        "quantitative, risk, or platform-delivery content.\n"
        "\n"
        "# " + _STRATEGY_OPPORTUNISTIC +
        "\n"
        "# HARD RULE — top_3_reasons and fit drivers\n"
        "\n"
        "ABSOLUTE PROHIBITION: top_3_reasons strings MUST NOT contain ANY of these tokens\n"
        "(case-insensitive): 'OSFI', 'E-23', 'B-12', 'LAR', 'IFRS', 'Basel', 'ECL',\n"
        "'guideline', 'regulatory-calendar', 'regulatory tailwind', 'regulatory posture',\n"
        "'regulatory awareness', 'regulatory familiarity'. The §4.9 Master Repo block\n"
        "lists these as background knowledge only — do NOT echo them back. If a reason\n"
        "would mention any of these, rewrite it to cite the underlying CAPABILITY:\n"
        "  - Instead of 'OSFI B-12 / IRRBB awareness' → say 'IRRBB modelling, EVE/NII\n"
        "    sensitivity, parallel and non-parallel rate-shock analytics'\n"
        "  - Instead of 'OSFI E-23 / model risk awareness' → say 'delegated sign-off\n"
        "    authority on institutional models, independent model review, assumption\n"
        "    validation'\n"
        "  - Instead of 'OSFI LAR / liquidity awareness' → say 'liquidity-gap and\n"
        "    cash-flow projection modelling (T+1 to multi-year)'\n"
        "  - Instead of 'IFRS 17 / IFRS 9 awareness' → say 'EY-delivered insurance-\n"
        "    accounting transformation programs' (only when EY/insurer context fits)\n"
        "  - Instead of 'Canadian regulatory alignment' → say 'sector experience at\n"
        "    Canadian Big 6 / pension / insurer / vendor'\n"
        + _STRATEGY_CAPABILITIES +
        "\n"
        "For every role also pick the 1-3 resume variants best suited (from this set):\n"
        + _STRATEGY_VARIANTS +
        "If a role leans market-risk, lead with the lane that fits (ALM or QUANT) and\n"
        "list VAL where model-review overlaps; if it leans strategy, list CON + relevant\n"
        "others; etc.\n"
        "\n"
        + _STRATEGY_OUT_OF_SCOPE +
        "\n"
        "Return ONLY valid JSON matching the schema given. No prose, no markdown.\n"
    )


# Computed once at import. Cheap enough.
SYSTEM_PROMPT = _build_system_prompt()

SCHEMA = """{
  "fit_score": 1-10 integer,
  "fit_verdict": "apply_now" | "tailor_and_apply" | "watch" | "skip",
  "top_3_reasons": ["...", "...", "..."],
  "skill_gaps": ["..."],                 // can be empty
  "tier": 1-4 integer (1=top tier apply-this-week; 4=watch-only),
  "applicable_resume_variants": ["ALM" | "VAL" | "VEN" | "QUANT" | "CON", ...],  // 1-3 items, best-fit first
  "summary": "30-word-ish pitch for Saber of why to apply (or why not)"
}"""


def _cache_path_fit(url: str) -> Path:
    """Fit-cache path. Versioned — v2 introduced deterministic JD analysis
    injection; older v1 caches don't have `deterministic` block and we'd
    rather re-score than back-fill. Old cache files are left in place (cheap
    on disk) but never read."""
    FIT_CACHE.mkdir(parents=True, exist_ok=True)
    return FIT_CACHE / f"{_url_hash(url)}.v2.json"


# Per-1M-token prices (USD) for each supported model. Source: Anthropic pricing
# (Oct 2025). Used ONLY for the cost-telemetry display — not authoritative for
# billing; trust your Anthropic invoice for that.
_MODEL_PRICES = {
    "claude-haiku-4-5-20251001": {"input": 1.0,  "output": 5.0},
    "claude-haiku-4-5":          {"input": 1.0,  "output": 5.0},
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0},
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0},
}


def _estimate_cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _MODEL_PRICES.get(model) or _MODEL_PRICES.get(model.split("-2025")[0])
    if not p:
        return 0.0
    return (in_tokens * p["input"] + out_tokens * p["output"]) / 1_000_000


def _is_fatal_error(err_str: str) -> bool:
    """Errors that mean 'don't bother retrying anything' — billing or auth failures."""
    em = err_str.lower()
    return any(phrase in em for phrase in (
        "credit balance", "billing", "insufficient", "invalid_api_key",
        "authentication", "permission_denied",
    ))


def _is_transient_error(err_str: str) -> bool:
    """Errors worth retrying: rate limits, server errors, transient network blips."""
    em = err_str.lower()
    return any(phrase in em for phrase in (
        "rate_limit", "429", "overloaded_error", "529",
        "internal_server_error", "500", "502", "503", "504",
        "timeout", "timed out", "connection", "read error",
    ))


def _compute_deterministic_analysis(jd_text: str) -> Optional[dict]:
    """Run JD → skills/variants/gaps extraction. Returns a small serializable
    dict, or None if the extractor is unavailable / JD is empty.

    The LLM gets this as text in its prompt; the UI gets it as structured
    JSON alongside the LLM output."""
    if _jd_extract is None or not jd_text:
        return None
    try:
        ex = _jd_extract(jd_text)
    except Exception as e:
        print(f"  [jd_extract] err: {e}", file=sys.stderr)
        return None
    return {
        "coverage_pct": ex.coverage_pct,
        "skill_ids_matched": ex.skill_ids_matched,
        "primary_hit_ids": [h.skill_id for h in ex.primary_hits],
        "gap_phrases": [g.matched_phrase for g in ex.gaps_flagged],
        "suggested_variants": [
            {"variant": v.variant, "bullets": v.bullets_supporting,
             "skills": v.skills_supporting, "score": v.rank_score}
            for v in ex.suggested_variants[:5]
        ],
        "_prompt_block": ex.as_prompt_block(),
    }


def _load_prev_fit_index() -> dict[str, dict]:
    """Map canonical URL -> prior `fit` dict from worklist_scored.json. Used as
    a second-chance lookup when the per-URL fit cache misses but the worklist
    says is_new_since_last_score=False (so the role definitely was scored
    before, only the cache key changed).

    Skips rows whose `fit_verdict` is `error`, `needs_rescore`, or any other
    sentinel that indicates the prior run never produced a real score —
    otherwise score_with_llm would copy these placeholders into fit_cache and
    we'd silently skip the LLM call for URLs that have never actually been
    scored.

    Falls back to `worklist_scored.prev.json` if the live file is missing —
    a `--rescore` run interrupted between the prev-snapshot and the rewrite
    would otherwise leave the next normal run with no prior index, forcing
    paid re-scoring for everything."""
    scored = OUT_DIR / "worklist_scored.json"
    if not scored.exists():
        # Fall back to the .prev.json snapshot — a `--rescore` interrupted
        # between the snapshot copy and the rewrite would otherwise leave
        # the next normal run thinking nothing was scored before.
        scored = OUT_DIR / "worklist_scored.prev.json"
        if not scored.exists():
            return {}
    try:
        data = json.loads(scored.read_text(encoding="utf-8"))
    except Exception:
        return {}
    real_verdicts = {"apply_now", "tailor_and_apply", "watch", "skip"}
    # Sentinel reason strings written by score_one's abort path or score_with_llm's
    # fatal/parse-fail returns. These rows carry a real-looking verdict (often
    # `skip`) so the verdict filter alone misses them — checking the reasons
    # blocklist catches the cases where a row was never actually LLM-scored.
    abort_markers = {"aborted_fatal_api_error", "aborted",
                     "fatal_api", "LLM_failure"}
    idx: dict[str, dict] = {}
    for r in data.get("results", []) or []:
        url = (r.get("link") or "").strip()
        fit = r.get("fit")
        if not url or not isinstance(fit, dict):
            continue
        if fit.get("fit_verdict") not in real_verdicts:
            continue
        reasons = fit.get("top_3_reasons") or []
        if any(m in reasons for m in abort_markers):
            continue
        canon = _canonicalize_url(url)
        if canon:
            idx[canon] = fit
    return idx


def score_with_llm(client, role: dict, jd_text: str) -> dict:
    """Call Claude with role+JD, cached by URL hash. Returns parsed dict.

    Retry policy per model:
      - Transient errors (429, 5xx, timeouts): retry up to 3 times w/ exponential backoff (1s, 3s, 9s)
      - Fatal errors (billing/auth): set global abort event; stop pending jobs
      - Parse errors: 1 retry on same model, then fall through to fallback model
    Cost telemetry is accumulated into _cost_state on each successful call.

    Before the LLM call, a deterministic JD → skill extraction runs over the
    Master Repo YAMLs and is injected into the user prompt + persisted in
    the result under `deterministic`. The LLM references it instead of
    re-parsing the JD from scratch, which both reduces hallucination and
    gives callers a structured coverage number independent of the LLM.
    """
    cache = _cache_path_fit(role["link"])
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            _cost_tick(cache_hit=True)
            return cached
        except Exception as e:
            # Corrupt cache entry — re-score. Surface so a pattern of
            # corruption (disk full? concurrent writer?) is visible.
            if _log_error is not None:
                _log_error("fit_cache_read", e, module="fit_scorer",
                            extra={"url": role.get("link")})

    # Second-chance hit: worklist diff says this URL was already scored in the
    # prior run. Reuse that fit instead of paying for another LLM call when
    # the per-URL cache file is orphaned (cache-key bump, manual wipe).
    if _prev_fit_index and role.get("is_new_since_last_score") is False:
        canon = _canonicalize_url(role.get("link") or "")
        prev_fit = _prev_fit_index.get(canon)
        if prev_fit:
            # Block reuse on any signal the prior fit was a model parse-miss
            # or default-fallback (verdict in {error, skip, None}, score==0,
            # empty top_3_reasons). Otherwise we'd re-stamp a placeholder
            # into fit_cache and skip a real LLM call indefinitely.
            bad_verdict = prev_fit.get("fit_verdict") in ("error", None, "skip")
            bad_score = (prev_fit.get("fit_score") or 0) == 0
            bad_reasons = not prev_fit.get("top_3_reasons")
            if not (bad_verdict or bad_score or bad_reasons):
                try:
                    _atomic_write_text(cache, json.dumps(prev_fit, indent=2))
                except Exception:
                    pass
                _cost_tick(cache_hit=True, prev_fit_reuse=True)
                return prev_fit

    if _abort_event.is_set():
        return {"fit_score": 0, "fit_verdict": "error", "top_3_reasons": ["aborted"],
                "skill_gaps": [], "tier": 4,
                "summary": "Aborted due to fatal earlier error."}

    # Deterministic pre-analysis. Always runs; costs ~1ms; may return None if
    # extractor or JD is unavailable.
    det = _compute_deterministic_analysis(jd_text)
    det_block = det.get("_prompt_block") if det else ""

    user = (
        f"# ROLE\n"
        f"Company: {role['company']}\n"
        f"Sector: {role.get('sector', '')}\n"
        f"Title: {role['title']}\n"
        f"Location: {role.get('location', '')}\n"
        f"URL: {role['link']}\n"
        f"Source: {role.get('source', '')}\n"
        + (f"\n{det_block}\n" if det_block else "")
        + f"\n# JOB DESCRIPTION (may be partial)\n"
        f"{jd_text[:6000] if jd_text else '(JD not available — score from title/company only.)'}\n"
        f"\n# YOUR OUTPUT\n"
        f"Return ONLY valid JSON, no prose, matching this schema:\n"
        f"{SCHEMA}\n"
        f"\nReminder: top_3_reasons MUST NOT contain 'OSFI', 'E-23', 'B-12', 'LAR',\n"
        f"'IFRS', 'Basel', 'ECL', 'guideline', or any 'regulatory-...' phrasing.\n"
        f"Cite concrete capabilities (ALM/IRRBB, cash-flow engines, sign-off authority,\n"
        f"LDI, model validation/governance, vendor platforms, sector experience).\n"
    )

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0  # seconds

    for model in (MODEL, FALLBACK_MODEL):
        for attempt in range(MAX_RETRIES):
            if _abort_event.is_set():
                break
            try:
                _tpm_reserve(_estimate_input_tokens(SYSTEM_PROMPT, user))
                resp = client.messages.create(
                    model=model,
                    # 800 — 400 truncated mid-JSON when the model emitted
                    # ```json fences plus full schema (3 reasons + gaps +
                    # summary), causing the closing-brace regex to miss.
                    max_tokens=800,
                    system=[{"type": "text", "text": SYSTEM_PROMPT,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user}],
                )
                # Token telemetry
                try:
                    usage = resp.usage
                    in_t = getattr(usage, "input_tokens", 0) or 0
                    out_t = getattr(usage, "output_tokens", 0) or 0
                    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
                    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                    _cost_tick(model=model, in_tokens=in_t, out_tokens=out_t,
                               cache_create=cache_create, cache_read=cache_read)
                except Exception:
                    pass

                text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
                # Strip ```json / ``` fences if the model wrapped its output —
                # SYSTEM_PROMPT forbids this but both Haiku and Sonnet do it
                # intermittently, so we tolerate it instead of parse-missing.
                stripped = text.strip()
                if stripped.startswith("```"):
                    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
                    stripped = re.sub(r"\s*```\s*$", "", stripped)
                m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped, flags=re.S)
                if not m:
                    m = re.search(r"\{.*\}", stripped, flags=re.S)
                if not m:
                    # Parse miss — model returned text but no JSON. Log it
                    # (so a recurring pattern is visible) and break out of
                    # this model's retry loop to fall through to the
                    # fallback model. Retrying the same model on parse-miss
                    # almost never helps; the prompt is the issue.
                    if _log_error is not None:
                        try:
                            raise ValueError("LLM returned no JSON")
                        except Exception as _pme:
                            _log_error("score_parse_miss", _pme,
                                       module="fit_scorer",
                                       extra={"model": model,
                                              "url": role.get("link"),
                                              "preview": text[:200]})
                    print(f"  [score_llm] {model} parse miss — falling through "
                          f"to fallback model", file=sys.stderr)
                    break  # exit attempt loop, try next model
                parsed = json.loads(m.group(0))
                parsed.setdefault("fit_score", 1)
                parsed.setdefault("fit_verdict", "skip")
                parsed.setdefault("top_3_reasons", [])
                parsed.setdefault("skill_gaps", [])
                parsed.setdefault("tier", 4)
                parsed.setdefault("summary", "")
                # Drop legacy osfi_hook if the LLM still emits one — the field is
                # retired. Older cache entries may still have it; downstream code
                # doesn't read it anymore so leaving stale cache is harmless.
                parsed.pop("osfi_hook", None)
                # Sanitize resume variants — LLM sometimes invents tokens ("FI", "BS").
                # Keep only the recognized set; cap at 3; preserve order (primary first).
                raw_variants = parsed.get("applicable_resume_variants") or []
                if isinstance(raw_variants, str):
                    raw_variants = [raw_variants]
                seen: set[str] = set()
                cleaned: list[str] = []
                for v in raw_variants:
                    if not isinstance(v, str):
                        continue
                    key = v.strip().upper()
                    if key in RESUME_VARIANTS and key not in seen:
                        seen.add(key)
                        cleaned.append(key)
                    if len(cleaned) >= 3:
                        break
                parsed["applicable_resume_variants"] = cleaned
                # Attach the deterministic analysis to the persisted result
                # (without `_prompt_block` — that's an LLM-prompt artifact and
                # only adds noise to downstream consumers).
                if det:
                    persisted = {k: v for k, v in det.items() if not k.startswith("_")}
                    parsed["deterministic"] = persisted
                # Double-checked locking on the cache write. Two threads
                # could have both seen a cache miss above and both raced to
                # the LLM; whichever finishes first wins the lock and
                # writes. The second thread re-reads the cache rather than
                # clobbering it, so we keep one canonical result instead
                # of a last-writer-wins corruption window.
                with _fit_cache_lock(cache):
                    if cache.exists():
                        try:
                            return json.loads(cache.read_text(encoding="utf-8"))
                        except Exception:
                            pass  # fall through and overwrite the bad file
                    _atomic_write_text(cache, json.dumps(parsed, indent=2))
                return parsed
            except Exception as e:
                err_str = str(e)
                if _is_fatal_error(err_str):
                    if not _abort_event.is_set():
                        _abort_reason.append(err_str[:300])
                        _abort_event.set()
                        print(
                            f"\n[fit_scorer] FATAL API ERROR — aborting all remaining jobs.\n"
                            f"  Reason: {err_str[:200]}\n",
                            file=sys.stderr,
                        )
                    return {"fit_score": 0, "fit_verdict": "error",
                            "top_3_reasons": ["fatal_api"], "skill_gaps": [],
                            "tier": 4,
                            "summary": f"Fatal: {err_str[:120]}"}
                if _is_transient_error(err_str) and attempt < MAX_RETRIES - 1:
                    backoff = BACKOFF_BASE * (3 ** attempt)
                    print(f"  [score_llm] {model} attempt {attempt+1}/{MAX_RETRIES} "
                          f"transient error, retrying in {backoff:.1f}s: {err_str[:120]}",
                          file=sys.stderr)
                    time.sleep(backoff)
                    continue
                # Non-transient, non-fatal — fall through to next model
                print(f"  [score_llm] {model} failed (attempt {attempt+1}): {err_str[:200]}",
                      file=sys.stderr)
                break
    return {"fit_score": 0, "fit_verdict": "error", "top_3_reasons": ["LLM_failure"],
            "skill_gaps": [], "tier": 4,
            "summary": "LLM scoring failed after all retries."}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=None,
                    help="Filename in automation/outputs/ of the scraper output to score. "
                         "If omitted, scores worklist.json (the deduped pool — "
                         "scrape ∪ recent Gmail). Pass --scan X for legacy "
                         "single-file mode.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Limit to N roles after stage 1 triage (0=all).")
    ap.add_argument("--only", action="append", default=[],
                    help="Only score titles matching this regex (can pass multiple).")
    ap.add_argument("--only-url", action="append", default=None, metavar="URL",
                    help="Score ONLY the row(s) whose canonical URL matches. "
                         "Repeatable. Merges into the existing scored file "
                         "instead of overwriting, and skips the .prev.json "
                         "snapshot so a single-URL rescore doesn't reset the "
                         "Action Plan diff baseline. Pair with --rescore to "
                         "bypass the fit cache.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Stage 1 only; don't call LLM.")
    ap.add_argument("--rescore", action="store_true",
                    help="Ignore fit cache; re-call LLM for every role.")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Parallel LLM calls (default 4).")
    ap.add_argument("--no-cost-guard", action="store_true",
                    help="Disable the daily/per-run USD cap. Use when you "
                         "deliberately want a large run (e.g. full rescore).")
    args = ap.parse_args()

    if not args.scan:
        # Default: score worklist.json. The worklist module unions the
        # latest web scrape with the rolling-30d Gmail pool, dedups, and
        # tags every row with provenance — so scoring it covers every
        # surfaced role exactly once. If worklist.json doesn't exist
        # yet (first-time setup), bootstrap by triggering a rebuild.
        try:
            import worklist  # type: ignore
        except ImportError:
            from . import worklist  # type: ignore
        wpath = worklist.effective_scan()
        if wpath is None:
            # No inputs at all — neither worklist nor a raw scan. Trigger
            # a rebuild in case there are inputs that just haven't been
            # folded yet. Log any failure (used to be silently swallowed,
            # which produced cryptic "no scan_*.json" errors with no clue
            # that rebuild() was actually crashing).
            try:
                worklist.rebuild()
            except Exception as _e:
                print(f"[fit_scorer] worklist.rebuild() bootstrap failed: "
                      f"{type(_e).__name__}: {_e}", file=sys.stderr)
            wpath = worklist.effective_scan()
        if wpath is None:
            print("ERROR: no worklist.json and no scan_*.json in outputs/. "
                  "Run jd_scraper or gmail_fetch first.", file=sys.stderr)
            return 1
        args.scan = wpath.name
        print(f"[fit_scorer] No --scan supplied; using {args.scan} "
              f"(worklist contract — pool = scrape ∪ recent Gmail).",
              file=sys.stderr)
    scan_path = OUT_DIR / args.scan
    if not scan_path.exists():
        print(f"ERROR: {scan_path} not found", file=sys.stderr)
        return 1

    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    roles = scan.get("results", [])
    print(f"[fit_scorer] Loaded {len(roles)} roles from {scan_path.name}", file=sys.stderr)

    # --only-url: filter the input pool down to the supplied URL(s) before
    # stage-1 triage. Uses worklist.norm_url so a LinkedIn tracking-redirect
    # URL still matches its canonical /jobs/view/<id> form. Triage and the
    # cache layer are deliberately untouched — pair with --rescore to also
    # bust the fit cache.
    only_url_targets: set[str] | None = None
    if args.only_url:
        try:
            import worklist  # type: ignore
        except ImportError:
            from . import worklist  # type: ignore
        only_url_targets = {
            worklist.norm_url({"link": u}) for u in args.only_url if u
        }
        only_url_targets.discard("")
        before = len(roles)
        roles = [r for r in roles
                 if worklist.norm_url(r) in only_url_targets]
        print(f"[fit_scorer] --only-url matched {len(roles)}/{before} role(s).",
              file=sys.stderr)
        if not roles:
            print(f"[fit_scorer] --only-url matched 0 rows in {scan_path.name}; "
                  f"nothing to do.", file=sys.stderr)
            return 0

    # Stage 1 — rule triage. We keep the dropped records in a separate list
    # so the UI can show "why didn't this role get scored?" — before this,
    # failed stage-1 roles vanished silently and the user had no way to
    # audit the scoring funnel.
    triaged: list[dict] = []
    triage_drops: list[dict] = []   # compact records of stage-1 failures
    only_filtered: list[dict] = []  # dropped via --only regex
    # Load the suppression snapshot once for the whole run; the helper caches
    # module-level so subsequent calls are no-ops. None when the env var is
    # unset or the file is missing — fall back to live state in that path so
    # per-row triage doesn't re-read the registry 1,400 times.
    _supp_snapshot = _load_suppression_snapshot()
    if _supp_snapshot is None and _suppressions is not None:
        try:
            _supp_snapshot = _suppressions.load_active()
        except Exception as _e:
            if _log_error is not None:
                _log_error("suppression_live_load", _e, module="fit_scorer")
            _supp_snapshot = None
    _only_url_active = bool(only_url_targets)
    for r in roles:
        tri = rule_triage(r["title"], row=r,
                          suppression_snapshot=_supp_snapshot,
                          only_url_override=_only_url_active)
        r["_triage"] = tri
        if not tri["stage1_pass"]:
            triage_drops.append({
                "company": r.get("company", ""),
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "source": r.get("source", ""),
                "rule_reasons": tri.get("rule_reasons", []),
                "hits_breakdown": tri.get("hits_breakdown", {}),
                "score": tri.get("score", 0),
            })
            continue
        if args.only and not any(re.search(p, r["title"], re.I) for p in args.only):
            only_filtered.append({
                "company": r.get("company", ""),
                "title": r.get("title", ""),
                "link": r.get("link", ""),
            })
            continue
        triaged.append(r)

    print(f"[fit_scorer] Stage 1: {len(triaged)} pass / {len(triage_drops)} drop / "
          f"{len(only_filtered)} filtered by --only", file=sys.stderr)

    if args.limit:
        triaged = triaged[: args.limit]
        print(f"[fit_scorer] Limiting to {len(triaged)} for this run.", file=sys.stderr)

    if args.dry_run:
        # --only-url + --dry-run is meaningless and dangerous: dry-run writes
        # only the triaged stage-1 rows to <scan>_scored.json with no `fit`
        # field, which would clobber the live scored file. Refuse instead of
        # silently destroying the user's scored snapshot.
        if only_url_targets:
            print("[fit_scorer] --only-url with --dry-run is unsafe (would "
                  "overwrite the scored file with stage-1-only rows). "
                  "Drop one of the flags.", file=sys.stderr)
            return 2
        out = {"scan_date": scan.get("scan_date"), "stage1_only": True,
               "total_input": len(roles), "stage1_passed": len(triaged),
               "stage1_dropped": len(triage_drops),
               "stage1_only_filtered": len(only_filtered),
               "results": triaged,
               "triage_drops": triage_drops,
               "only_filtered": only_filtered}
        (OUT_DIR / (Path(args.scan).stem + "_scored.json")).write_text(
            json.dumps(out, indent=2), encoding="utf-8")
        print(f"[fit_scorer] DRY RUN complete. Wrote {args.scan} "
              f"-> {Path(args.scan).stem}_scored.json", file=sys.stderr)
        return 0

    # Stage 2 — LLM scoring (parallel)
    if anthropic is None:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 2

    # Real API preflight: do a 1-token messages.create BEFORE spawning the
    # worker pool. Without this, a revoked/stale key (or exhausted billing)
    # lets fit_scorer spin up workers that all fail one-by-one, spamming
    # the error log and making the scorer look broken when the fix is 30
    # seconds of env work. Bypass with APPLYAGENT_SKIP_PREFLIGHT=1.
    try:
        from api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
    except ImportError:
        try:
            from .api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
        except Exception:
            _cli_preflight = None  # type: ignore
    if _cli_preflight is not None:
        _cli_preflight(module="fit_scorer")
    elif not os.environ.get("ANTHROPIC_API_KEY"):
        # Legacy fallback if api_preflight isn't importable.
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    # Module-global persists across main() calls in the same process
    # (Streamlit). Both branches below assign it, so declare global once
    # up-front (Python forbids `global` after a same-name assignment).
    global _prev_fit_index
    if args.rescore:
        # Nuke fit cache for each triaged role
        for r in triaged:
            p = _cache_path_fit(r["link"])
            if p.exists():
                p.unlink()
        # The non-rescore branch sets _prev_fit_index; --rescore must
        # explicitly clear so a second invocation in the same process
        # doesn't reuse stale prior fits the user just asked us to ignore.
        _prev_fit_index = {}
    else:
        # Build the prior-fit index from worklist_scored.json so a row that
        # the worklist marked as is_new_since_last_score=False can short-circuit
        # to the prior fit on cache miss (e.g. when a cache-key canonicalization
        # bump orphaned the fit_cache files). --rescore deliberately bypasses
        # this — that flag exists to force a fresh LLM call.
        _prev_fit_index = _load_prev_fit_index()
        if _prev_fit_index:
            print(f"[fit_scorer] loaded {len(_prev_fit_index)} prior fits "
                  f"from worklist_scored.json (used on cache miss for "
                  f"is_new_since_last_score=False rows).", file=sys.stderr)

    # Activate cost guardrail (daily + per-run USD caps from env). Preflight
    # refuses to start if today's spend is already over cap; in-run checks
    # trip _abort_event once per-run cap is hit. Skip in --no-guard mode.
    global _cost_guard
    if _CostGuard is not None and not args.no_cost_guard:
        _cost_guard = _CostGuard.from_env()
        print(f"[cost_guard] {_cost_guard.summary()}", file=sys.stderr)
        _cost_guard.preflight_or_exit()

    client = anthropic.Anthropic()
    t0 = time.time()
    progress_begin(args.scan, len(triaged))

    def score_one(r):
        # Short-circuit immediately if a fatal API error was already detected
        if _abort_event.is_set():
            r["fit"] = {"fit_score": 0, "fit_verdict": "skip",
                        "top_3_reasons": ["aborted_fatal_api_error"],
                        "skill_gaps": [], "tier": 4,
                        "summary": "Skipped — scorer aborted due to API error."}
            return r, False, True

        # Detect cache hit BEFORE calling (so the UI can show cache-hit rate).
        from_cache = _cache_path_fit(r["link"]).exists()
        error = False
        try:
            jd = fetch_jd(r["link"])
            r["_jd_len"] = len(jd)
            r["fit"] = score_with_llm(client, r, jd)
        except Exception as e:
            error = True
            r["fit"] = {"fit_score": 0, "fit_verdict": "error",
                        "summary": f"scoring error: {e}"[:200]}
        return r, from_cache, error

    scored = []
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = [ex.submit(score_one, r) for r in triaged]
            for i, fut in enumerate(as_completed(futures), 1):
                r, from_cache, error = fut.result()
                scored.append(r)
                progress_tick(r, from_cache, error, t0)
                if i % 10 == 0 or i == len(futures):
                    print(f"  [fit_scorer] scored {i}/{len(futures)} "
                          f"({(time.time() - t0) / 60:.1f} min)", file=sys.stderr)
        progress_end("finished")
    except Exception:
        progress_end("failed")
        raise

    # Sort by (fit_score desc, tier asc)
    scored.sort(key=lambda r: (-r["fit"].get("fit_score", 0), r["fit"].get("tier", 4)))

    api_error = _abort_reason[0] if _abort_reason else None
    out = {
        "scan_date": scan.get("scan_date"),
        "scored_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "total_input": len(roles),
        "stage1_passed": len(triaged),
        "stage1_dropped": len(triage_drops),
        "stage1_only_filtered": len(only_filtered),
        "stage2_scored": len(scored),
        "api_error": api_error,
        "results": scored,
        # Triage audit trail — consumed by the UI's Triage page so the user
        # can answer "why didn't this role get scored?" without re-running
        # rule_triage against the scan by hand.
        "triage_drops": triage_drops,
        "only_filtered": only_filtered,
    }
    if api_error:
        print(f"\n[fit_scorer] ⚠️  Run aborted early — results are incomplete.\n"
              f"  Fix: {api_error[:200]}", file=sys.stderr)
    json_out = OUT_DIR / (Path(args.scan).stem + "_scored.json")
    # Single-URL rescore: merge updated row(s) into the existing scored file
    # instead of overwriting it (otherwise re-scoring one suspicious skip
    # would obliterate the other 500 scored rows in worklist_scored.json).
    # Skip the .prev.json snapshot too — a single-URL touch shouldn't reset
    # the Action Plan diff baseline.
    if only_url_targets and json_out.exists():
        try:
            existing = json.loads(json_out.read_text(encoding="utf-8"))
        except Exception as _merge_err:
            print(f"[fit_scorer] warn: could not read existing "
                  f"{json_out.name} for merge ({_merge_err}); falling back to "
                  f"overwrite.", file=sys.stderr)
        else:
            try:
                import worklist  # type: ignore
            except ImportError:
                from . import worklist  # type: ignore
            updated = {worklist.norm_url(r): r for r in scored}
            merged: list[dict] = []
            for r in existing.get("results", []):
                key = worklist.norm_url(r)
                merged.append(updated.pop(key, r) if key in updated else r)
            merged.extend(updated.values())  # any rescored row not in old file
            merged.sort(key=lambda r: (-(r.get("fit") or {}).get("fit_score", 0),
                                       (r.get("fit") or {}).get("tier", 4)))
            out["results"] = merged
            out["stage2_scored"] = len(scored)  # only this run, not the merged total
            print(f"[fit_scorer] --only-url merge: rewrote {len(scored)} "
                  f"row(s) into {json_out.name}; total rows in file: "
                  f"{len(merged)}.", file=sys.stderr)
            # Atomic replace, not raw write_text — the UI Action Plan reader
            # polls this file every Streamlit rerun. A truncate-then-write
            # window here defeats the whole copy-then-replace hardening
            # introduced for the full-run snapshot.
            _atomic_write_json(json_out, out)
            # Skip the prev-snapshot (it would overwrite the previous full
            # run's baseline with this single-row merge) and skip MD (would
            # render a one-row report over the full one).
            return 0
    # Snapshot the previous scored output so the UI can diff this run vs prior
    # (Action Plan: NEW / UPGRADED / DOWNGRADED / STABLE badges). Best-effort —
    # if the snapshot fails (file in use, perms), we log and proceed; the
    # scoring output is the priority. Only one generation is kept.
    #
    # COPY-then-atomic-replace, not rename-then-write: a 10-min re-score
    # would otherwise leave `worklist_scored.json` missing on disk for the
    # whole run, and the UI Action Plan reading concurrently would see no
    # file. With copy+os.replace the live file is never absent — readers
    # see either old-complete or new-complete.
    if json_out.exists():
        prev_path = json_out.with_suffix(".prev.json")
        try:
            import shutil
            shutil.copy2(json_out, prev_path)
        except Exception as _snap_err:
            print(f"[fit_scorer] warn: could not snapshot {json_out.name} -> "
                  f"{prev_path.name}: {_snap_err}", file=sys.stderr)
    _atomic_write_json(json_out, out)

    # Human-readable MD
    md_lines = [
        f"# Fit-Scored Report -- {scan.get('scan_date')}",
        "",
        f"- Scan source: `{args.scan}`",
        f"- Total candidates input: {len(roles)}",
        f"- Passed rule-triage: {len(triaged)}",
        f"- LLM-scored: {len(scored)}",
        f"- Runtime: {(time.time() - t0) / 60:.1f} min",
        "",
        "## Verdict distribution",
        "",
    ]
    by_verdict = {}
    for r in scored:
        v = r["fit"].get("fit_verdict", "?")
        by_verdict[v] = by_verdict.get(v, 0) + 1
    for v, n in sorted(by_verdict.items(), key=lambda x: -x[1]):
        md_lines.append(f"- **{v}**: {n}")
    md_lines += ["", "## Top 40 by fit score", "",
                 "| Score | Verdict | Tier | Sector | Company | Title | Summary | Link |",
                 "|---|---|---|---|---|---|---|---|"]
    for r in scored[:40]:
        f = r["fit"]
        title = r["title"].replace("|", "/")
        summary = f.get("summary", "").replace("|", "/").replace("\n", " ")[:140]
        md_lines.append(
            f"| {f.get('fit_score')} | {f.get('fit_verdict')} | {f.get('tier')} | "
            f"{r.get('sector', '')} | {r['company']} | {title} | "
            f"{summary} | [open]({r['link']}) |"
        )

    md_out = OUT_DIR / (Path(args.scan).stem + "_scored.md")
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[fit_scorer] Wrote {json_out}", file=sys.stderr)
    print(f"[fit_scorer] Wrote {md_out}", file=sys.stderr)
    print(f"[fit_scorer] Verdict counts: {by_verdict}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
