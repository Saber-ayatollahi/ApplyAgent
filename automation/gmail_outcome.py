#!/usr/bin/env python3
"""
gmail_outcome.py — Recruiter-email outcome ingestion for the job tracker.

Why this exists
---------------
The campaign tracker is write-only today: 96 roles, 0 in any post-Applied
state because manually editing tracker JSON after a recruiter email is
friction nobody pays for. This module turns the loop closed:

    Gmail  →  classify (Haiku)  →  match to tracker  →  propose status

Proposals land in `automation/outputs/outcome_proposals.json` (the same
file `url_check.py` uses) so the UI surfaces them in one queue regardless
of source. We never mutate the tracker without `--commit`, and even then
only auto-apply HIGH-confidence (>=9) classifications. The UI is the
single arbiter for everything in between.

What it does
------------
1. Auths to Gmail via IMAP using the same app-password pattern as
   `gmail_reader.py` (creds in `~/.applyagent/config.json`). Read-only.
2. Pulls last N days (default 7) of emails from a curated allowlist
   (Workday/Greenhouse/Lever/iCIMS/SuccessFactors/Phenom/Avature plus
   any sender previously associated with a tracker entry's company).
3. For each candidate email, fires ONE Haiku classification (~$0.001)
   asking for: category, confidence, extracted_company, extracted_role,
   proposed_status, evidence_quote.
4. Matches to a tracker entry by company token-fuzzy (drops generic
   tokens: bank, group, inc, financial, holdings, capital, ...).
5. Appends matched proposals to `outputs/outcome_proposals.json` via
   `safe_json.mutate_json` (atomic + cross-process; concurrent-safe with
   `url_check.py` which writes the same file).
6. Records each LLM call to `cost_ledger`. Hard cap RUN spend at $0.20.

CLI
---
    python automation/gmail_outcome.py --help
    python automation/gmail_outcome.py --dry-run
    python automation/gmail_outcome.py --limit 3 --days 7
    python automation/gmail_outcome.py --commit            # auto-apply >=9-conf

Constraints
-----------
- DOES NOT modify gmail_reader.py — only imports from it.
- DOES NOT touch existing UI pages — additive only.
- All file writes are atomic via safe_json so a crashed run never leaves
  half a JSON on disk.
- Graceful degradation: if creds missing, prints a clean error and exits
  non-zero. Never crashes the caller.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Project-local imports — support both "run as script" and "run as module".
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
AUTOMATION_DIR = Path(__file__).resolve().parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

try:
    from safe_json import read_json, mutate_json  # type: ignore
except ImportError as e:
    print(f"[gmail_outcome] FATAL: safe_json not importable: {e}", file=sys.stderr)
    raise

# gmail_reader is imported lazily inside fetch_emails(); we only need it
# when actually pulling mail. --dry-run + --help must work without IMAP.
try:
    import gmail_reader as _gr  # type: ignore
except ImportError:
    _gr = None  # type: ignore

# Cost guard + ledger — same wiring as fit_scorer / jd_tailor.
try:
    from cost_guard import CostGuard  # type: ignore
except ImportError:
    CostGuard = None  # type: ignore

try:
    import cost_ledger  # type: ignore
except ImportError:
    cost_ledger = None  # type: ignore

# Best-effort error logging.
try:
    from error_log import log_error as _log_error  # type: ignore
except Exception:
    _log_error = None  # type: ignore

try:
    import anthropic  # type: ignore
except ImportError:
    anthropic = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRACKER_PATH = ROOT / "data" / "job_tracker_data.json"
OUT_DIR = ROOT / "automation" / "outputs"
PROPOSALS_PATH = OUT_DIR / "outcome_proposals.json"

# Senders worth classifying. Anything from here gets a Haiku call. We also
# add per-company senders dynamically from the tracker (any sender who
# previously emailed the user about a tracker company).
ATS_DOMAINS = (
    "myworkdayjobs.com", "myworkday.com", "workday.com",
    "greenhouse.io", "no-reply@greenhouse.io",
    "lever.co", "hire.lever.co",
    "eightfold.ai",
    "icims.com",
    "successfactors.com", "sapsf.com",
    "phenom.com", "phenompeople.com",
    "avature.net",
    "smartrecruiters.com",
    "workable.com",
    "ashbyhq.com",
)

# Subject keywords that suggest "outcome-y" mail even from unknown senders.
SUBJECT_KEYWORDS = (
    "application", "interview", "rejection", "offer", "candidacy",
    "next step", "next steps", "schedule", "screen", "screening",
    "assessment", "take-home", "take home", "onsite", "on-site",
    "decision", "regret", "unfortunately", "thank you for applying",
    "hiring team", "talent acquisition", "recruiter",
)

# Map LLM-emitted categories → tracker status strings. Keys must match the
# enum in `data/job_tracker_data.json::meta.status_enum`.
CATEGORY_TO_STATUS = {
    "interview_invite":          "Phone_Screen",
    "rejection":                 "Rejected",
    "recruiter_screen_invite":   "Recruiter_Screen",
    "take_home_assignment":      "Take_Home",
    "onsite_invite":             "Onsite",
    "offer":                     "Offer",
    "application_acknowledged":  "Applied",   # already Applied → no-op
    "ghost_signal":              "Ghosted",
    "unrelated":                 None,
    "other":                     None,
}

# Statuses we never overwrite (terminal). Same convention as url_check.
TERMINAL_STATUSES = {"Hired", "Withdrawn", "Declined"}

# Generic company-name tokens to drop before fuzzy matching.
GENERIC_TOKENS = {
    "bank", "group", "inc", "incorporated", "financial", "holdings",
    "capital", "corp", "corporation", "co", "company", "ltd", "limited",
    "the", "of", "and", "&", "global", "canada", "canadian", "us", "usa",
    "north", "america", "investments", "investment", "management",
    "services", "solutions", "partners", "advisors", "advisory", "asset",
    "wealth", "trust", "plc",
}

DEFAULT_DAYS = 7
DEFAULT_MIN_CONFIDENCE = 6
HARD_RUN_CAP_USD = 0.20

# Same Haiku model the rest of the project uses by default.
DEFAULT_MODEL = os.environ.get("GMAIL_OUTCOME_MODEL", "claude-haiku-4-5")
# Per-1M-token prices (USD) — matches the table in fit_scorer.
_MODEL_PRICES = {
    "claude-haiku-4-5":          {"input": 1.0,  "output": 5.0},
    "claude-haiku-4-5-20251001": {"input": 1.0,  "output": 5.0},
}


SYSTEM_PROMPT = """You classify recruiter / ATS emails for a Toronto-based job-search tracker.

Your task: read ONE email (sender, subject, body), and emit JSON describing
what kind of recruiter signal it is.

Categories (choose exactly one):
  - interview_invite          : a real interview, panel, or hiring-manager call is being scheduled
  - rejection                 : the candidate has been rejected / not moving forward
  - recruiter_screen_invite   : initial recruiter / talent-acquisition phone screen
  - take_home_assignment      : take-home test / case study / coding assessment
  - onsite_invite             : onsite or final-round invitation
  - offer                     : explicit offer of employment, including verbal-offer follow-ups
  - application_acknowledged  : automated "we received your application" receipts
  - ghost_signal              : explicit "this role is no longer open" / "we have closed the role"
  - unrelated                 : marketing, networking, alerts, newsletters, anything not about the candidate's pipeline
  - other                     : recruiter content but doesn't fit any other bucket

Output a JSON object with exactly these keys:
  category            string  (one of the categories above)
  confidence          int     (1-10, how sure you are; <=5 means "uncertain")
  extracted_company   string  (best-effort company NAME — e.g. "Royal Bank of Canada", "Scotiabank", "Bloomberg")
  extracted_role      string  (best-effort role title; "" if not stated)
  evidence_quote      string  (1-2 short sentences from the email PROVING the classification)

Hard rules:
  * Return ONLY valid JSON, no prose, no markdown fences.
  * Job-alert digests (LinkedIn / Indeed weekly emails) are ALWAYS unrelated.
  * "Thank you for your interest" boilerplate that does NOT mention an
    interview is application_acknowledged, NOT rejection.
  * "Unfortunately" + "decided to move forward with other candidates" is
    rejection.
  * If the email is ambiguous, lower the confidence — do NOT guess high.
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Classification:
    category: str
    confidence: int
    extracted_company: str
    extracted_role: str
    evidence_quote: str
    proposed_status: Optional[str]
    cost_usd: float
    model: str


@dataclass
class ProposalRow:
    job_id: str
    company: str
    current_status: str
    proposed_status: str
    reason: str
    evidence: dict


# ---------------------------------------------------------------------------
# Fuzzy company matching
# ---------------------------------------------------------------------------
# Bidirectional alias map. Each key is a CANONICAL form (lower-case, no
# punctuation); the value is the set of phrasings recruiters / ATS systems
# emit that should resolve to it. The map is consumed both ways:
#   - extracted email name → canonical (so "Royal Bank of Canada" → "rbc")
#   - tracker company name → canonical (so "RBC" tracker entry also → "rbc")
# Two names match iff they collapse to the same canonical key. Pure jaccard
# token overlap on `{royal, bank, canada}` vs `{rbc}` returns 0, which is
# why the legacy code silently dropped Big-Six bank emails.
#
# Keep this list aligned with `automation/jd_scraper.py` TARGETS — same
# companies, same canonical spellings.
_COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    # ── Canadian Big 6 Banks ──
    "rbc":            ("rbc", "royal bank of canada", "royal bank",
                       "rbc royal bank", "rbc capital markets"),
    "bmo":            ("bmo", "bank of montreal", "bmo financial group",
                       "bmo capital markets", "bmo harris"),
    "scotiabank":     ("scotiabank", "scotia", "bank of nova scotia",
                       "scotia bank", "the bank of nova scotia"),
    "td bank":        ("td", "td bank", "toronto-dominion", "toronto dominion",
                       "the toronto-dominion bank", "td bank group",
                       "td canada trust", "td securities"),
    "cibc":           ("cibc", "canadian imperial bank of commerce",
                       "cibc capital markets"),
    "national bank of canada": ("national bank", "national bank of canada",
                       "banque nationale", "banque nationale du canada",
                       "nbc", "banque nationale of canada"),
    # ── Canadian Pension Funds ──
    "hoopp":          ("hoopp", "healthcare of ontario pension plan",
                       "healthcare of ontario pension"),
    "omers":          ("omers", "ontario municipal employees retirement system",
                       "ontario municipal employees retirement"),
    "ontario teachers' pension plan": ("otpp", "ontario teachers",
                       "ontario teachers pension plan",
                       "ontario teachers' pension plan", "otppb"),
    "cpp investments": ("cpp", "cppib", "cpp investments",
                       "canada pension plan investment board",
                       "canada pension plan"),
    # ── Insurers ──
    "manulife":       ("manulife", "manulife financial", "john hancock",
                       "manulife investment management"),
    "sun life":       ("sun life", "sun life financial",
                       "sun life investment management",
                       "sun life asset management"),
    # ── Analytics / vendors ──
    "bloomberg":      ("bloomberg", "bloomberg lp", "bloomberg l.p.",
                       "bloomberg industry group"),
    "blackrock":      ("blackrock", "blackrock inc",
                       "blackrock asset management"),
    "s&p global":     ("s&p", "s&p global", "standard & poor's",
                       "standard and poor's", "spgi"),
    "msci":           ("msci", "msci inc"),
    "morningstar dbrs": ("morningstar dbrs", "dbrs morningstar", "dbrs"),
    # ── US banks (Toronto presence) ──
    "jpmorgan chase": ("jpmorgan", "jpmorgan chase", "jp morgan",
                       "j.p. morgan", "chase"),
    "goldman sachs":  ("goldman sachs", "goldman", "gs"),
    "morgan stanley": ("morgan stanley", "ms"),
}


def _norm_text(s: str) -> str:
    """Unicode-fold + lowercase + collapse punctuation to spaces. Used as
    the canonicalization step before alias / containment lookups so e.g.
    smart-quote 'Ontario Teachers' Pension Plan' matches plain ASCII."""
    if not s:
        return ""
    # Strip combining marks (é → e), unify ligatures.
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    # Drop any apostrophe / quote variant entirely (don't insert a space —
    # "teachers' plan" → "teachers plan", not "teachers  plan").
    s = re.sub(r"['‘’ʼ“”`]", "", s)
    # Replace remaining non-alphanumeric with single spaces.
    s = re.sub(r"[^a-z0-9&]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Pre-compute reverse lookup: any normalized alias → canonical key. Built
# at import time so match_company is O(1) per probe.
def _build_alias_lookup() -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, aliases in _COMPANY_ALIASES.items():
        c_norm = _norm_text(canonical)
        out[c_norm] = c_norm
        for a in aliases:
            out[_norm_text(a)] = c_norm
    return out


_ALIAS_LOOKUP: dict[str, str] = _build_alias_lookup()


def _canonicalize(name: str) -> str:
    """Resolve a free-form company name to its canonical alias key. Falls
    back to the normalized form when no alias is registered."""
    n = _norm_text(name)
    if not n:
        return ""
    return _ALIAS_LOOKUP.get(n, n)


def _normalize_company(name: str) -> set[str]:
    """Return a set of meaningful tokens for fuzzy matching. Drops generic
    corporate-suffix words. Empty set for names that are entirely generic."""
    raw = _norm_text(name)
    tokens = {t for t in raw.split() if t and t not in GENERIC_TOKENS and len(t) >= 2}
    return tokens


def _strip_generic_tokens(name: str) -> str:
    """Return the normalized form with generic tokens removed. Used by the
    substring-containment check so e.g. 'Bloomberg LP' and 'Bloomberg' both
    collapse to 'bloomberg' before testing containment."""
    raw = _norm_text(name)
    keep = [t for t in raw.split() if t not in GENERIC_TOKENS and len(t) >= 2]
    return " ".join(keep).strip()


def match_company(extracted: str, tracker_jobs: list[dict]) -> Optional[dict]:
    """Match an extracted company name to a tracker job. Strategy:

    1. Exact (case-insensitive) match on `company`.
    2. Alias-map canonicalization — collapse both sides to a canonical key
       (e.g., 'Royal Bank of Canada' and 'RBC' both → 'rbc') and match.
    3. Substring containment after stripping generic tokens — handles
       cases like 'Scotia' ⊂ 'Scotiabank' that the alias map didn't catch.
    4. Token-jaccard fallback — keeps the historical permissive behaviour
       for genuinely fuzzy cases (e.g., long marketing names).

    Returns the matched job dict (the FIRST match — caller disambiguates).
    """
    if not extracted:
        return None
    e_low = extracted.strip().lower()
    if not e_low:
        return None

    # 1. Exact match (case-insensitive). Cheap and bullet-proof when the
    # email subject literally repeats the tracker spelling.
    for j in tracker_jobs:
        c = (j.get("company") or "").strip().lower()
        if c and c == e_low:
            return j

    # 2. Alias-map lookup. Both sides go through _canonicalize so e.g.
    # 'Royal Bank of Canada' (extracted) and 'RBC' (tracker) both collapse
    # to 'rbc'. This is the step that fixes the Big-Six silent-drop bug.
    e_canon = _canonicalize(extracted)
    if e_canon:
        for j in tracker_jobs:
            c_canon = _canonicalize(j.get("company") or "")
            if c_canon and c_canon == e_canon:
                return j

    # 3. Substring containment after generic-token strip. Catches short
    # subsets ('Scotia' ⊂ 'Scotiabank') and short supersets. We require
    # the shorter side to be at least 4 chars so single-token nouns like
    # 'tdx' don't accidentally collide.
    e_strip = _strip_generic_tokens(extracted)
    if e_strip and len(e_strip) >= 4:
        for j in tracker_jobs:
            c_strip = _strip_generic_tokens(j.get("company") or "")
            if not c_strip or len(c_strip) < 4:
                continue
            short, long = (e_strip, c_strip) if len(e_strip) <= len(c_strip) \
                          else (c_strip, e_strip)
            # Need a real substring match on a full-token boundary so
            # 'risk' doesn't match 'asterisk'. We re-tokenize and demand
            # one side's tokens be a subsequence prefix/suffix of the other.
            if short == long:
                return j
            if (" " + short + " ") in (" " + long + " "):
                return j
            if long.startswith(short + " ") or long.endswith(" " + short):
                return j

    # 4. Token-jaccard fallback. Same threshold as before so we don't
    # invent new matches; the alias map should cover the high-value cases.
    e_tokens = _normalize_company(extracted)
    if not e_tokens:
        return None

    best: tuple[float, Optional[dict]] = (0.0, None)
    for j in tracker_jobs:
        c_tokens = _normalize_company(j.get("company", ""))
        if not c_tokens:
            continue
        inter = e_tokens & c_tokens
        if not inter:
            continue
        union = e_tokens | c_tokens
        jacc = len(inter) / len(union) if union else 0.0
        if jacc > best[0]:
            best = (jacc, j)

    return best[1] if best[0] >= 0.5 else None


# ---------------------------------------------------------------------------
# Sender allowlist construction
# ---------------------------------------------------------------------------
def is_candidate_sender(sender_email: str, subject: str,
                         allowlist_domains: Iterable[str],
                         per_company_emails: Iterable[str]) -> bool:
    """True if this email is worth classifying. We're permissive on intake
    — Haiku is cheap and false positives just classify as `unrelated`."""
    se = (sender_email or "").lower()
    sub = (subject or "").lower()

    if not se:
        return False

    # Curated ATS allowlist
    for dom in allowlist_domains:
        d = dom.lower()
        if d in se:
            return True

    # Tracker-derived per-company senders
    for known in per_company_emails:
        if known and known.lower() in se:
            return True

    # Subject heuristics — anything that walks like an outcome email.
    if any(kw in sub for kw in SUBJECT_KEYWORDS):
        return True

    return False


def build_per_company_emails(tracker_jobs: list[dict]) -> set[str]:
    """Pull any sender_email previously logged in a tracker entry's
    outreach_log. Today the tracker rarely has these, but the schema
    supports it and gmail_outcome itself can populate it later."""
    out: set[str] = set()
    for j in tracker_jobs:
        for entry in j.get("outreach_log", []) or []:
            se = (entry.get("sender_email") or "").lower().strip()
            if se:
                out.add(se)
        # Also accept any explicit recruiter_emails list on the job
        for se in j.get("recruiter_emails", []) or []:
            if se:
                out.add(se.lower().strip())
    return out


# ---------------------------------------------------------------------------
# Email fetching
# ---------------------------------------------------------------------------
def fetch_emails(days: int, limit: Optional[int],
                  per_company_emails: set[str]) -> list:
    """Pull recent inbox messages relevant to outcome tracking. Returns the
    `gmail_reader.InboxMessage` list (with body included)."""
    if _gr is None:
        print("[gmail_outcome] FATAL: gmail_reader unavailable — install "
              "anthropic-side deps and check automation/gmail_reader.py",
              file=sys.stderr)
        return []

    email_addr, pw = _gr.load_credentials()
    if not email_addr or not pw:
        print("[gmail_outcome] ERROR: Gmail credentials not configured. "
              "Set them in the UI sidebar (📬 Gmail panel) or save to "
              "~/.applyagent/config.json — then retry.", file=sys.stderr)
        return []

    # gmail_reader.fetch_inbox_signals already filters to the recruiter
    # domains it knows about; we want a wider net. Bump `limit` and rely
    # on `is_candidate_sender` to filter post-fetch.
    raw = _gr.fetch_inbox_signals(days=days, limit=400, include_body=True)

    candidates = []
    for msg in raw:
        if is_candidate_sender(msg.sender_email, msg.subject,
                                ATS_DOMAINS, per_company_emails):
            candidates.append(msg)
    if limit:
        candidates = candidates[:limit]
    return candidates


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------
def _estimate_cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _MODEL_PRICES.get(model) or _MODEL_PRICES.get(model.split("-2025")[0])
    if not p:
        return 0.0
    return (in_tokens * p["input"] + out_tokens * p["output"]) / 1_000_000


def _truncate_body(body: str, cap: int = 4000) -> str:
    """Cap the body we feed to Haiku. Most outcome signals are in the
    first ~1000 chars (greeting + verdict + sign-off); 4000 leaves headroom
    for embedded calendar invites without blowing the prompt budget."""
    if not body:
        return ""
    return body[:cap]


def classify_email(client: Any, model: str, msg: Any) -> Classification:
    """One Haiku classification per email. Always returns SOMETHING — on
    parse-miss / API failure we return a low-confidence `other` with the
    error in evidence_quote so the run keeps going."""
    user = (
        f"# EMAIL\n"
        f"From: {msg.sender} <{msg.sender_email}>\n"
        f"Date: {msg.date}\n"
        f"Subject: {msg.subject}\n"
        f"\n"
        f"# BODY\n"
        f"{_truncate_body(msg.snippet)}\n"
        f"\n"
        f"# YOUR OUTPUT\n"
        f"Return ONLY the JSON object described in the system prompt.\n"
    )

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=400,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content
                        if getattr(b, "type", None) == "text")
        usage = resp.usage
        in_t = getattr(usage, "input_tokens", 0) or 0
        out_t = getattr(usage, "output_tokens", 0) or 0
        cost = _estimate_cost_usd(model, in_t, out_t)
        # Record to ledger (best-effort)
        if cost_ledger is not None:
            try:
                cost_ledger.record(model=model, in_tokens=in_t,
                                    out_tokens=out_t, cost_usd=cost)
            except Exception:
                pass

        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return Classification(
                category="other", confidence=1,
                extracted_company="", extracted_role="",
                evidence_quote=f"(parse miss; raw preview: {text[:120]})",
                proposed_status=None, cost_usd=cost, model=model,
            )
        parsed = json.loads(m.group(0))
        cat = str(parsed.get("category", "other")).lower().strip()
        if cat not in CATEGORY_TO_STATUS:
            cat = "other"
        try:
            conf = int(parsed.get("confidence", 1))
        except (TypeError, ValueError):
            conf = 1
        conf = max(1, min(conf, 10))
        return Classification(
            category=cat,
            confidence=conf,
            extracted_company=str(parsed.get("extracted_company", "")).strip(),
            extracted_role=str(parsed.get("extracted_role", "")).strip(),
            evidence_quote=str(parsed.get("evidence_quote", "")).strip()[:500],
            proposed_status=CATEGORY_TO_STATUS.get(cat),
            cost_usd=cost,
            model=model,
        )
    except Exception as e:
        if _log_error is not None:
            try:
                _log_error("gmail_outcome_classify", e,
                            module="gmail_outcome",
                            extra={"sender": msg.sender_email,
                                   "subject": msg.subject[:120]})
            except Exception:
                pass
        return Classification(
            category="other", confidence=1,
            extracted_company="", extracted_role="",
            evidence_quote=f"(LLM call failed: {type(e).__name__})",
            proposed_status=None, cost_usd=0.0, model=model,
        )


# ---------------------------------------------------------------------------
# Proposal merge — concurrent-safe with url_check.py
# ---------------------------------------------------------------------------
def _dedupe_key(p: dict) -> tuple:
    """Two proposals collide if they target the same job with the same
    proposed status from the same source AND (for Gmail) the same email
    UID. This lets gmail_outcome and url_check both write to the same file
    without each clobbering the other's entries."""
    ev = p.get("evidence", {}) or {}
    return (
        p.get("job_id"),
        p.get("proposed_status"),
        ev.get("source", ""),
        ev.get("email_id", ""),  # only set for gmail_outcome rows
    )


def append_proposals(new_props: list[dict]) -> int:
    if not new_props:
        return 0
    PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _merge(current: Any) -> list[dict]:
        if not isinstance(current, list):
            current = []
        new_keys = {_dedupe_key(p) for p in new_props}
        kept = [p for p in current if _dedupe_key(p) not in new_keys]
        return kept + new_props

    mutate_json(PROPOSALS_PATH, _merge, default=[])
    return len(new_props)


# ---------------------------------------------------------------------------
# Optional --commit: apply HIGH-confidence proposals to the tracker
# ---------------------------------------------------------------------------
def commit_high_confidence(proposals: list[dict],
                            min_conf_for_commit: int = 9) -> tuple[int, list[str]]:
    """Apply proposals whose confidence >= `min_conf_for_commit` to the
    tracker. Same locking semantics as url_check.commit_tracker_changes."""
    eligible = []
    for p in proposals:
        ev = p.get("evidence") or {}
        try:
            conf = int(ev.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0
        if conf < min_conf_for_commit:
            continue
        # Also: don't auto-apply offers / rejections silently — they need
        # a human eye even at high confidence. We DO commit the screening
        # transitions (Recruiter_Screen, Phone_Screen, Take_Home, Onsite).
        if p.get("proposed_status") in {"Offer", "Rejected"}:
            continue
        eligible.append(p)

    if not eligible:
        return 0, []

    by_id = {p["job_id"]: p for p in eligible}
    changed_ids: list[str] = []

    def _apply(tracker: Any) -> Any:
        if not isinstance(tracker, dict) or "jobs" not in tracker:
            return tracker
        for j in tracker["jobs"]:
            jid = j.get("id")
            if jid not in by_id:
                continue
            if j.get("status") in TERMINAL_STATUSES:
                continue
            new_status = by_id[jid]["proposed_status"]
            if not new_status:
                continue
            j["status"] = new_status
            j["status_changed_by"] = "gmail_outcome"
            j["status_changed_on"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            changed_ids.append(jid)
        return tracker

    mutate_json(TRACKER_PATH, _apply, default={"jobs": []})
    return len(changed_ids), changed_ids


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="gmail_outcome",
        description="Recruiter-email outcome ingestion — classify Gmail "
                    "messages, propose tracker status transitions.",
    )
    p.add_argument("--days", type=int, default=DEFAULT_DAYS,
                   help=f"Lookback window in days (default {DEFAULT_DAYS}).")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap the number of emails CLASSIFIED (post-filter). "
                        "Useful for smoke tests.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print plan and exit. No IMAP, no LLM, no writes.")
    p.add_argument("--commit", action="store_true",
                   help="Auto-apply HIGH-confidence (>=9) proposals to the "
                        "tracker. Default is propose-only.")
    p.add_argument("--min-confidence", type=int,
                   default=DEFAULT_MIN_CONFIDENCE,
                   help=f"Drop proposals below this confidence (default "
                        f"{DEFAULT_MIN_CONFIDENCE}).")
    p.add_argument("--commit-min-confidence", type=int, default=9,
                   help="Confidence threshold for auto-commit when --commit "
                        "is set (default 9).")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL,
                   help=f"Anthropic model id (default {DEFAULT_MODEL}).")
    return p.parse_args(argv)


def _write_summary_files(today_str: str, summary: dict,
                          proposals: list[dict],
                          unmatched: list[dict]) -> tuple[Path, Path]:
    """Persist the per-run JSON + Markdown digest. Idempotent re-runs on
    the same day overwrite the existing summary."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"gmail_outcome_{today_str}.json"
    md_path = OUT_DIR / f"gmail_outcome_{today_str}.md"

    # JSON: full structured summary
    json_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "proposals": proposals,
        "unmatched": unmatched,
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False),
                          encoding="utf-8")

    # Markdown digest
    lines = [
        f"# Gmail outcome ingestion — {today_str}",
        "",
        f"- Emails fetched: **{summary.get('emails_fetched', 0)}**",
        f"- Classified: **{summary.get('classified', 0)}**",
        f"- Matched to tracker: **{summary.get('matched', 0)}**",
        f"- Proposals written: **{summary.get('proposals_written', 0)}**",
        f"- Unmatched (logged): **{summary.get('unmatched', 0)}**",
        f"- Total LLM cost: **${summary.get('cost_usd', 0.0):.4f}**",
        "",
    ]
    if proposals:
        lines.append("## Proposals")
        lines.append("")
        lines.append("| Company | Role | Current | Proposed | Conf | Source |")
        lines.append("| --- | --- | --- | --- | ---: | --- |")
        for p in proposals:
            ev = p.get("evidence") or {}
            lines.append(
                f"| {p.get('company', '?')} "
                f"| {ev.get('extracted_role', '')[:50]} "
                f"| {p.get('current_status', '')} "
                f"| {p.get('proposed_status', '')} "
                f"| {ev.get('confidence', '?')} "
                f"| {ev.get('source', '')} |"
            )
        lines.append("")
    if unmatched:
        lines.append("## Unmatched (no tracker entry found)")
        lines.append("")
        lines.append("| Sender | Subject | Extracted company | Category |")
        lines.append("| --- | --- | --- | --- |")
        for u in unmatched:
            lines.append(
                f"| {u.get('sender', '')} "
                f"| {u.get('subject', '')[:60]} "
                f"| {u.get('extracted_company', '?')} "
                f"| {u.get('category', '?')} |"
            )
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def _write_unmatched_jsonl(today_str: str, rows: list[dict]) -> Optional[Path]:
    if not rows:
        return None
    p = OUT_DIR / f"gmail_outcome_unmatched_{today_str}.jsonl"
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    today_str = date.today().strftime("%Y%m%d")

    # ---------- Tracker selection ----------
    tracker = read_json(TRACKER_PATH, default={"jobs": []}) or {"jobs": []}
    tracker_jobs = tracker.get("jobs", []) if isinstance(tracker, dict) else []
    per_company_emails = build_per_company_emails(tracker_jobs)

    # ---------- DRY RUN: print plan and exit ----------
    if args.dry_run:
        print(f"[gmail_outcome] DRY RUN — no IMAP, no LLM, no writes")
        print(f"  tracker_path        : {TRACKER_PATH}")
        print(f"  proposals_path      : {PROPOSALS_PATH}")
        print(f"  tracker entries     : {len(tracker_jobs)}")
        print(f"  per-company senders : {len(per_company_emails)}")
        print(f"  ATS allowlist       : {len(ATS_DOMAINS)} domains")
        print(f"  days                : {args.days}")
        print(f"  limit               : {args.limit or '(none)'}")
        print(f"  min-confidence      : {args.min_confidence}")
        print(f"  --commit auto-apply : {args.commit}"
              f"{' (>=' + str(args.commit_min_confidence) + ')' if args.commit else ''}")
        print(f"  model               : {args.model}")
        return 0

    # ---------- Cost guard preflight ----------
    if CostGuard is not None:
        guard = CostGuard.from_env()
        # Tighten per-run cap to our hard $0.20 ceiling for this script.
        guard.per_run_cap_usd = min(guard.per_run_cap_usd, HARD_RUN_CAP_USD)
        guard.preflight_or_exit()
    else:
        guard = None

    # ---------- Anthropic client ----------
    if anthropic is None:
        print("[gmail_outcome] ERROR: pip install anthropic", file=sys.stderr)
        return 2
    # Hydrate the key from any of the project's standard locations so a
    # standalone CLI invocation works without a manual `export`. Order:
    #   1. existing env (highest priority — explicit override wins)
    #   2. .env at repo root (project convention; load_env.py is the same
    #      helper the rest of the project uses)
    #   3. ~/.applyagent/config.json (UI-managed key)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from load_env import load_env as _load_env  # type: ignore
            _load_env()
        except Exception:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        try:
            cfg_path = Path.home() / ".applyagent" / "config.json"
            if cfg_path.exists():
                _cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                _k = (_cfg.get("anthropic_api_key") or "").strip()
                if _k:
                    os.environ["ANTHROPIC_API_KEY"] = _k
        except Exception:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[gmail_outcome] ERROR: ANTHROPIC_API_KEY not in environment, "
              ".env, or ~/.applyagent/config.json. Set it in the UI sidebar "
              "(🔑 panel), the project .env, or your shell.", file=sys.stderr)
        return 2
    client = anthropic.Anthropic()

    # ---------- Fetch ----------
    print(f"[gmail_outcome] fetching last {args.days}d of mail...", flush=True)
    candidates = fetch_emails(args.days, args.limit, per_company_emails)
    print(f"[gmail_outcome] {len(candidates)} candidate emails after filter",
          flush=True)
    if not candidates:
        summary = {
            "emails_fetched": 0, "classified": 0, "matched": 0,
            "proposals_written": 0, "unmatched": 0, "cost_usd": 0.0,
        }
        _write_summary_files(today_str, summary, [], [])
        print(f"[gmail_outcome] nothing to do — exit 0")
        return 0

    # ---------- Classify ----------
    proposals: list[dict] = []
    unmatched_rows: list[dict] = []
    classified_count = 0
    matched_count = 0
    total_cost = 0.0

    for msg in candidates:
        if guard is not None and guard.exceeded():
            print(f"[gmail_outcome] cost guard tripped: {guard.reason} — "
                  f"stopping classification loop", flush=True)
            break

        cls = classify_email(client, args.model, msg)
        classified_count += 1
        total_cost += cls.cost_usd
        if guard is not None:
            guard.record(cls.cost_usd)

        # Drop low-confidence below threshold (still log unmatched ones
        # for forensic review).
        if cls.confidence < args.min_confidence:
            unmatched_rows.append({
                "email_id": getattr(msg, "uid", ""),
                "date": msg.date,
                "sender": msg.sender_email,
                "subject": msg.subject,
                "extracted_company": cls.extracted_company,
                "category": cls.category,
                "confidence": cls.confidence,
                "reason": "below_min_confidence",
            })
            continue

        # Map category → status. `unrelated` / `other` short-circuits.
        if not cls.proposed_status:
            continue

        # Match to a tracker entry.
        job = match_company(cls.extracted_company, tracker_jobs)
        if job is None:
            unmatched_rows.append({
                "email_id": getattr(msg, "uid", ""),
                "date": msg.date,
                "sender": msg.sender_email,
                "subject": msg.subject,
                "extracted_company": cls.extracted_company,
                "category": cls.category,
                "confidence": cls.confidence,
                "reason": "no_tracker_match",
            })
            continue

        # Skip terminal-status jobs.
        if job.get("status") in TERMINAL_STATUSES:
            continue

        # Skip no-op transitions (proposed status equals current status).
        if job.get("status") == cls.proposed_status:
            continue

        matched_count += 1
        proposals.append({
            "job_id": job.get("id", ""),
            "company": job.get("company", ""),
            "current_status": job.get("status", ""),
            "proposed_status": cls.proposed_status,
            "reason": f"gmail_outcome {cls.category}",
            "evidence": {
                "source": "automation/gmail_outcome.py",
                "email_id": getattr(msg, "uid", ""),
                "sender": msg.sender_email,
                "subject": msg.subject,
                "date": msg.date,
                "quote": cls.evidence_quote,
                "confidence": cls.confidence,
                "extracted_company": cls.extracted_company,
                "extracted_role": cls.extracted_role,
                "category": cls.category,
                "model": cls.model,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        })

    # ---------- Persist ----------
    written = append_proposals(proposals)
    unmatched_path = _write_unmatched_jsonl(today_str, unmatched_rows)

    summary = {
        "emails_fetched": len(candidates),
        "classified": classified_count,
        "matched": matched_count,
        "proposals_written": written,
        "unmatched": len(unmatched_rows),
        "cost_usd": round(total_cost, 6),
        "min_confidence": args.min_confidence,
        "model": args.model,
    }
    json_path, md_path = _write_summary_files(today_str, summary,
                                                proposals, unmatched_rows)

    # ---------- Optional --commit ----------
    committed_count, committed_ids = 0, []
    if args.commit and proposals:
        committed_count, committed_ids = commit_high_confidence(
            proposals, min_conf_for_commit=args.commit_min_confidence,
        )
        summary["committed_count"] = committed_count
        summary["committed_ids"] = committed_ids

    # ---------- Final report ----------
    print(f"[gmail_outcome] summary :")
    print(f"  emails_fetched   : {summary['emails_fetched']}")
    print(f"  classified       : {summary['classified']}")
    print(f"  matched          : {summary['matched']}")
    print(f"  proposals_written: {summary['proposals_written']}")
    print(f"  unmatched        : {summary['unmatched']}")
    print(f"  cost_usd         : ${summary['cost_usd']:.4f}")
    if args.commit:
        print(f"  committed        : {committed_count} job(s) "
              f"({', '.join(committed_ids) if committed_ids else 'none'})")
    print(f"  json             : {json_path}")
    print(f"  md               : {md_path}")
    if unmatched_path:
        print(f"  unmatched_jsonl  : {unmatched_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
