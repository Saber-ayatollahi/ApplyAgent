#!/usr/bin/env python3
"""
fit_scorer.py — Smart fit-scoring for scan results.

Takes a scraper-output JSON (scan_v4.json) and scores every candidate against Saber's
Master Repository profile. Outputs a scored JSON with per-role:

  - fit_score (1-10)
  - fit_verdict ("apply_now" | "tailor_and_apply" | "watch" | "skip")
  - top_3_reasons (why this matches)
  - skill_gaps (what Saber lacks for this role)
  - osfi_hook (which OSFI angle to lead the cover letter with)
  - tier (1-4)
  - summary (30-word pitch of why to apply)

Uses a 2-stage pipeline:
  Stage 1: fast rule-based triage (title + company + keywords) → drop junk, cheap.
  Stage 2: LLM scoring for surviving candidates, with JD fetched, 1 call per role.

JD fetch is cached to disk (jd_cache/) so re-runs on the same scan are free.

Usage:
    python fit_scorer.py                              # score latest scan
    python fit_scorer.py --scan scan_v4.json
    python fit_scorer.py --scan scan_v4.json --limit 50
    python fit_scorer.py --dry-run                    # rule-stage only, no API calls
    python fit_scorer.py --only "Director" --only "VP"  # regex filter titles
    python fit_scorer.py --rescore                    # ignore cache, re-call LLM

Outputs:
    automation/outputs/scan_v4_scored.json            # full scored list
    automation/outputs/scan_v4_scored.md              # human-readable report
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
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
JD_CACHE = OUT_DIR / "jd_cache"
FIT_CACHE = OUT_DIR / "fit_cache"
MASTER_REPO = ROOT / "Saber_Ayatollahi_Master_Repository.md"
PROGRESS_PATH = OUT_DIR / "fit_scorer_progress.json"

MODEL = os.environ.get("FIT_SCORER_MODEL", "claude-haiku-4-5-20251001")
FALLBACK_MODEL = "claude-haiku-4-5-20251001"


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
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        serializable = dict(_progress_state)
        serializable["recent"] = list(_progress_state["recent"])
        PROGRESS_PATH.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    except Exception:
        pass  # progress is best-effort; don't break scoring on IO hiccup


def progress_begin(scan_name: str, total: int):
    with _progress_lock:
        _progress_state.update({
            "state": "running",
            "scan": scan_name,
            "total": total,
            "current": 0,
            "cache_hits": 0,
            "errors": 0,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
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
        _progress_state["updated_at"] = datetime.utcnow().isoformat() + "Z"
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
        _progress_state["finished_at"] = datetime.utcnow().isoformat() + "Z"
        _write_progress()


# ---------------------------------------------------------------------------
# Cost telemetry — captures token usage per successful LLM call and sums into
# the progress JSON so the UI can show live $ spend.
# ---------------------------------------------------------------------------
_cost_state = {
    "llm_calls": 0,
    "cache_hits": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_create_tokens": 0,
    "cache_read_tokens": 0,
    "estimated_cost_usd": 0.0,
    "per_model": {},  # model -> {"calls": n, "in_tokens": n, "out_tokens": n, "cost_usd": f}
}


def _cost_tick(model: str | None = None, in_tokens: int = 0, out_tokens: int = 0,
               cache_create: int = 0, cache_read: int = 0, cache_hit: bool = False):
    with _progress_lock:
        if cache_hit:
            _cost_state["cache_hits"] += 1
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

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
    # French equivalents for QC postings
    "validation des modèles", "gestion de l'actif", "gestion des risques",
    "risque de crédit", "risque de marché", "analytique", "modélisation",
]

WEAK_POS = [  # +1 each — noisy tokens, require combos
    "risk", "capital", "liquidity",
    "quant", "analytics", "modeling", "modelling",
    "model", "reporting",
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


def rule_triage(title: str) -> dict:
    """Weighted stage-1 triage. Passes if total score >= STAGE1_THRESHOLD.

    Returns {stage1_pass, rough_tier, score, rule_reasons, hits_breakdown}.
    """
    t = (title or "").lower()
    # Hard-fail on negative term
    for n in NEG_TITLE_TERMS:
        if n in t:
            return {"stage1_pass": False, "rough_tier": 5, "score": 0,
                    "rule_reasons": [f"neg:{n}"], "hits_breakdown": {}}

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
    if strong: reasons.append(f"strong={strong[:3]}")
    if medium: reasons.append(f"medium={medium[:3]}")
    if weak: reasons.append(f"weak={weak[:3]}")
    if level: reasons.append(f"level={level[:2]}")

    # Pass rules (OR'd):
    #   - any STRONG hit                      -> pass (core lane term)
    #   - any MEDIUM hit                      -> pass (domain-specific)
    #   - any WEAK hit + level                -> pass ("Senior Manager, Liquidity Management")
    #   - >=2 WEAK hits                       -> pass ("Capital Risk Analyst")
    # A pure LEVEL-only match does NOT pass — too noisy. The LLM will still see the
    # role title and can make the call; but we don't want to LLM-score every "VP, Strategy".
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
def _url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


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

# Section-header hints — lines starting with these get +score during section scoring
_KEEP_SECTION_HINTS = (
    "responsibilities", "key responsibilities", "what you'll do", "what you will do",
    "your role", "in this role", "the role", "duties",
    "qualifications", "requirements", "what you'll bring", "what you bring",
    "must have", "must-have", "experience required", "skills",
    "about the team", "about the role", "position summary", "job summary",
    "we're looking for", "we are looking for", "ideal candidate",
    # French
    "responsabilités", "exigences", "profil recherché", "qualifications requises",
)


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
    """If we can identify responsibilities/qualifications sections, prefer those.
    Fall back to a head-of-document truncation otherwise."""
    if not cleaned or len(cleaned) <= max_chars:
        return cleaned
    lower = cleaned.lower()
    # Find the earliest section header hit
    earliest = len(cleaned)
    for hint in _KEEP_SECTION_HINTS:
        idx = lower.find(hint)
        if 0 <= idx < earliest:
            earliest = idx
    if earliest < len(cleaned) and earliest < max_chars * 2:
        # We found a section start — grab from there
        return cleaned[earliest:earliest + max_chars]
    # Fall back to head of document
    return cleaned[:max_chars]


def fetch_jd(url: str, max_chars: int = 8000) -> str:
    """Fetch, strip HTML, clean boilerplate, prefer responsibilities section.

    Caching: we cache the CLEANED text (not raw HTML), so a cache bump is needed
    when the cleaner logic changes. Use a versioned cache filename."""
    JD_CACHE.mkdir(parents=True, exist_ok=True)
    # Cache filename versioned — bump when cleaner changes
    cache_path = JD_CACHE / f"{_url_hash(url)}.v2.txt"
    legacy_cache = JD_CACHE / f"{_url_hash(url)}.txt"
    if cache_path.exists():
        return _extract_sections(cache_path.read_text(encoding="utf-8"), max_chars)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return ""
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
        # Legacy cache cleanup
        if legacy_cache.exists():
            try: legacy_cache.unlink()
            except Exception: pass
        cache_path.write_text(cleaned, encoding="utf-8")
        return _extract_sections(cleaned, max_chars)
    except Exception as e:
        print(f"  [fetch_jd] err {url}: {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Stage 2 — LLM scoring (cached)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a hard-nosed senior finance career strategist assessing job fit for Saber Ayatollahi.\n"
    "\n"
    "Saber's profile (do not over-interpret — stick to this):\n"
    "- CFA charterholder. Dual MSc (Financial Modelling + Chemical Engineering).\n"
    "- ~7.3 years experience: Moody's Analytics (May 2022-present, Assistant Director Modelling Services),\n"
    "  EY (Sep 2021-Apr 2022, Sr Consultant IFRS 17/9), Ortec Finance (Feb 2019-Sep 2021, ALM/LDI).\n"
    "- Core competencies: ALM, IRRBB, Model Validation/Governance, Cash-Flow Projection, LDI,\n"
    "  Derivatives Pricing, Stochastic Scenario Generation, IFRS 17/9, Python, agentic AI workflows.\n"
    "- Formal sign-off authority on multi-asset institutional portfolios $5-25bn.\n"
    "- TARGET POSITIONING: (1) Primary = ALM/IRRBB/Model Governance Director/VP; \n"
    "  (2) Secondary = Vendor-Platform / Client Solutions (Aladdin, Bloomberg, MSCI, S&P Global).\n"
    "- RETIRED from outbound: pure Product Manager, Project Manager, generalist PM, pure asset-management\n"
    "  quant-research at boutique HFs. If a role is primarily in these lanes, it's NOT a fit.\n"
    "- Toronto-based, not relocating.\n"
    "\n"
    "Regulatory tailwinds relevant to this search:\n"
    "- OSFI E-23 Model Risk Management (eff. 2027-05-01, AI/ML scope).\n"
    "- OSFI B-12 IRRBB revision (Q1 2026 consultations).\n"
    "- OSFI LAR 2026 Liquidity Adequacy.\n"
    "- IFRS 17/9 (insurers/banks).\n"
    "\n"
    "You score each role. Return ONLY valid JSON matching the schema given, no prose, no markdown.\n"
)

SCHEMA = """{
  "fit_score": 1-10 integer,
  "fit_verdict": "apply_now" | "tailor_and_apply" | "watch" | "skip",
  "top_3_reasons": ["...", "...", "..."],
  "skill_gaps": ["..."],   // can be empty
  "osfi_hook": "E-23 Model Risk Management" | "B-12 IRRBB revision" | "LAR 2026 Liquidity Adequacy" | "IFRS 17" | "None",
  "tier": 1-4 integer (1=top tier apply-this-week; 4=watch-only),
  "summary": "30-word-ish pitch for Saber of why to apply (or why not)"
}"""


def _cache_path_fit(url: str) -> Path:
    FIT_CACHE.mkdir(parents=True, exist_ok=True)
    return FIT_CACHE / f"{_url_hash(url)}.json"


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


def score_with_llm(client, role: dict, jd_text: str) -> dict:
    """Call Claude with role+JD, cached by URL hash. Returns parsed dict.

    Retry policy per model:
      - Transient errors (429, 5xx, timeouts): retry up to 3 times w/ exponential backoff (1s, 3s, 9s)
      - Fatal errors (billing/auth): set global abort event; stop pending jobs
      - Parse errors: 1 retry on same model, then fall through to fallback model
    Cost telemetry is accumulated into _cost_state on each successful call.
    """
    cache = _cache_path_fit(role["link"])
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            _cost_tick(cache_hit=True)
            return cached
        except Exception:
            pass

    if _abort_event.is_set():
        return {"fit_score": 0, "fit_verdict": "error", "top_3_reasons": ["aborted"],
                "skill_gaps": [], "osfi_hook": "None", "tier": 4,
                "summary": "Aborted due to fatal earlier error."}

    user = (
        f"# ROLE\n"
        f"Company: {role['company']}\n"
        f"Sector: {role.get('sector', '')}\n"
        f"Title: {role['title']}\n"
        f"Location: {role.get('location', '')}\n"
        f"URL: {role['link']}\n"
        f"Source: {role.get('source', '')}\n"
        f"\n# JOB DESCRIPTION (may be partial)\n"
        f"{jd_text[:6000] if jd_text else '(JD not available — score from title/company only.)'}\n"
        f"\n# YOUR OUTPUT\n"
        f"Return ONLY valid JSON, no prose, matching this schema:\n"
        f"{SCHEMA}\n"
    )

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0  # seconds

    for model in (MODEL, FALLBACK_MODEL):
        for attempt in range(MAX_RETRIES):
            if _abort_event.is_set():
                break
            try:
                resp = client.messages.create(
                    model=model,
                    max_tokens=400,
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
                m = re.search(r"\{.*\}", text, flags=re.S)
                if not m:
                    # Parse miss — try next attempt
                    continue
                parsed = json.loads(m.group(0))
                parsed.setdefault("fit_score", 1)
                parsed.setdefault("fit_verdict", "skip")
                parsed.setdefault("top_3_reasons", [])
                parsed.setdefault("skill_gaps", [])
                parsed.setdefault("osfi_hook", "None")
                parsed.setdefault("tier", 4)
                parsed.setdefault("summary", "")
                cache.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
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
                            "osfi_hook": "None", "tier": 4,
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
            "skill_gaps": [], "osfi_hook": "None", "tier": 4,
            "summary": "LLM scoring failed after all retries."}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default="scan_v4.json",
                    help="Filename in automation/outputs/ of the scraper output to score.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Limit to N roles after stage 1 triage (0=all).")
    ap.add_argument("--only", action="append", default=[],
                    help="Only score titles matching this regex (can pass multiple).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Stage 1 only; don't call LLM.")
    ap.add_argument("--rescore", action="store_true",
                    help="Ignore fit cache; re-call LLM for every role.")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Parallel LLM calls (default 4).")
    args = ap.parse_args()

    scan_path = OUT_DIR / args.scan
    if not scan_path.exists():
        print(f"ERROR: {scan_path} not found", file=sys.stderr)
        return 1

    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    roles = scan.get("results", [])
    print(f"[fit_scorer] Loaded {len(roles)} roles from {scan_path.name}", file=sys.stderr)

    # Stage 1 — rule triage
    triaged = []
    skipped = 0
    for r in roles:
        tri = rule_triage(r["title"])
        r["_triage"] = tri
        if not tri["stage1_pass"]:
            skipped += 1
            continue
        if args.only and not any(re.search(p, r["title"], re.I) for p in args.only):
            continue
        triaged.append(r)

    print(f"[fit_scorer] Stage 1: {len(triaged)} pass / {skipped} drop / "
          f"{len(roles) - len(triaged) - skipped} filtered by --only", file=sys.stderr)

    if args.limit:
        triaged = triaged[: args.limit]
        print(f"[fit_scorer] Limiting to {len(triaged)} for this run.", file=sys.stderr)

    if args.dry_run:
        out = {"scan_date": scan.get("scan_date"), "stage1_only": True,
               "total_input": len(roles), "stage1_passed": len(triaged),
               "results": triaged}
        (OUT_DIR / (Path(args.scan).stem + "_scored.json")).write_text(
            json.dumps(out, indent=2), encoding="utf-8")
        print(f"[fit_scorer] DRY RUN complete. Wrote {args.scan} "
              f"-> {Path(args.scan).stem}_scored.json", file=sys.stderr)
        return 0

    # Stage 2 — LLM scoring (parallel)
    if anthropic is None:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    if args.rescore:
        # Nuke fit cache for each triaged role
        for r in triaged:
            p = _cache_path_fit(r["link"])
            if p.exists():
                p.unlink()

    client = anthropic.Anthropic()
    t0 = time.time()
    progress_begin(args.scan, len(triaged))

    def score_one(r):
        # Short-circuit immediately if a fatal API error was already detected
        if _abort_event.is_set():
            r["fit"] = {"fit_score": 0, "fit_verdict": "skip",
                        "top_3_reasons": ["aborted_fatal_api_error"],
                        "skill_gaps": [], "osfi_hook": "None", "tier": 4,
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
        "scored_at": datetime.utcnow().isoformat() + "Z",
        "total_input": len(roles),
        "stage1_passed": len(triaged),
        "stage2_scored": len(scored),
        "api_error": api_error,
        "results": scored,
    }
    if api_error:
        print(f"\n[fit_scorer] ⚠️  Run aborted early — results are incomplete.\n"
              f"  Fix: {api_error[:200]}", file=sys.stderr)
    json_out = OUT_DIR / (Path(args.scan).stem + "_scored.json")
    json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")

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
                 "| Score | Verdict | Tier | Sector | Company | Title | OSFI hook | Summary | Link |",
                 "|---|---|---|---|---|---|---|---|---|"]
    for r in scored[:40]:
        f = r["fit"]
        title = r["title"].replace("|", "/")
        summary = f.get("summary", "").replace("|", "/").replace("\n", " ")[:140]
        md_lines.append(
            f"| {f.get('fit_score')} | {f.get('fit_verdict')} | {f.get('tier')} | "
            f"{r.get('sector', '')} | {r['company']} | {title} | "
            f"{f.get('osfi_hook', '')} | {summary} | [open]({r['link']}) |"
        )

    md_out = OUT_DIR / (Path(args.scan).stem + "_scored.md")
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[fit_scorer] Wrote {json_out}", file=sys.stderr)
    print(f"[fit_scorer] Wrote {md_out}", file=sys.stderr)
    print(f"[fit_scorer] Verdict counts: {by_verdict}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
