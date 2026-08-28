"""location_filter.py — Shared GTA / Canada-remote predicate.

Extracted so gmail_fetch.py can apply the same geo gate as the web scraper
without paying jd_scraper's ~9s import cost. Keep this module dependency-free
(stdlib only) so it stays cheap to import everywhere.
"""
from __future__ import annotations

import re


_GTA_CITIES = (
    "toronto", "mississauga", "markham", "vaughan", "brampton",
    "oakville", "burlington", "milton", "richmond hill",
    "pickering", "ajax", "whitby", "oshawa", "north york",
    "scarborough", "etobicoke", "thornhill", "concord", "woodbridge",
    "aurora", "newmarket", "stouffville",
)

# US 2-letter postal codes that, when paired with a GTA-city substring, indicate
# a US namesake (e.g. "Toronto, OH" — Ohio town named Toronto). "CA" is omitted
# here because it doubles as Canada's country code; we handle it separately.
_US_STATES = (
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND",
    "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
)

# GTA-city tokens must be followed by location-part punctuation (comma, slash,
# paren, end-of-string, whitespace-then-newline) — NOT a hyphen-letter, which
# would indicate a compound brand name like "Toronto-Dominion".
_GTA_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _GTA_CITIES) + r")\b(?!-\w)",
    re.IGNORECASE,
)
_GTA_WITH_US_STATE_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _GTA_CITIES) + r")\s*,\s*(" +
    "|".join(_US_STATES) + r")\b",
    re.IGNORECASE,
)
# Strict Canada-remote anchors. Loose `"canada" in s and "remote" in s` over-
# matched company names ("Canada Goose"), UK streets ("Canada Square, London"),
# and explicit negations ("CA, not Canada"). Parenthesised forms require canada
# be the sole meaningful token in the parens — "(Canada too)" doesn't qualify.
#
# `in canada` and `across canada` are anchored to a clause boundary
# (start-of-string OR after `,;|/(-—`) so JD-body prose like "Headquartered
# in Canada, role is in NYC" or "Operating across Canada and the US" doesn't
# false-keep when scraper noise leaks into the location field.
# Province-level Ontario with NO city named. LinkedIn routinely labels GTA
# postings just "Ontario, Canada", and the bare-"Canada" rule below already
# keeps the strictly LESS specific "Canada" — so dropping these was
# inconsistent as well as lossy (23 such rows in the 2026-08-23 pool alone).
# Deliberately requires the string to contain ONLY province/country tokens:
# once a city is named the existing city rules decide, so "Ottawa, Ontario"
# and "London, ON" stay dropped (non-GTA) and "Toronto, ON" stays kept.
_ONTARIO_ONLY_TOKENS = {"ontario", "on", "canada", "ca"}


def _is_province_level_ontario(sl: str) -> bool:
    """True when `sl` names Ontario (or ON) and no city at all."""
    tokens = [t for t in re.split(r"[^a-z]+", sl) if t]
    if not tokens:
        return False
    if not any(t in ("ontario", "on") for t in tokens):
        return False
    return all(t in _ONTARIO_ONLY_TOKENS for t in tokens)


_CLAUSE_PREFIX = r"(?:^|[,;|/(\-—]\s*)"
_CANADA_ANCHOR_RE = re.compile(
    r"(remote\s*[-—,/]\s*canada\b|canada\s*[-—,/]\s*remote\b|"
    + _CLAUSE_PREFIX + r"in\s+canada\b|"
    + _CLAUSE_PREFIX + r"across\s+canada\b|"
    + r"\bremote\s+canada\b|"
    r"canada\s*\(\s*remote\s*\)|remote\s*\(\s*canada\s*\))",
    re.IGNORECASE,
)


def is_gta_or_canada_remote(loc: str) -> bool:
    """True if `loc` refers to the GTA proper or Canada-remote.

    Match order matters: positive Canadian anchors fire BEFORE the GTA-city /
    US-state-suffix guard so multi-city strings like "Toronto, OH / Remote,
    Canada" or "New York, NY or Toronto, ON" aren't false-dropped by a stray
    US-state token elsewhere in the string.

    Accepts:
      - Strict Canada-remote phrasings ("Remote, Canada", "Canada (Remote)",
        "across Canada", "remote Canada", ...)
      - Bare "Canada" / "CA"
      - Any GTA city via word-boundary match (rejects "Hamilton" → "milton"
        and US namesakes paired with a US-state suffix on that same city)
      - Commute-reachable SW Ontario (Waterloo / Kitchener)
    Rejects Ottawa-only, Montreal, Vancouver, US namesakes, UK "Canada Square",
    and loose "Canada Goose / remote-elsewhere" patterns.
    """
    sl = str(loc or "").lower()
    # Positive Canadian anchors first — these override the US-namesake guard
    # so a multi-city "Toronto, OH / Remote, Canada" still keeps.
    if _CANADA_ANCHOR_RE.search(sl):
        return True
    if sl.strip() in ("canada", "ca"):
        return True
    # Province-level "Ontario, Canada" / "ON, Canada" / "Ontario" — kept for the
    # same reason bare "Canada" is: the GTA is the densest slice of it, and the
    # scorer can judge the role. A named non-GTA city short-circuits this.
    if _is_province_level_ontario(sl):
        return True
    if "waterloo" in sl or "kitchener" in sl:
        return True
    # GTA city via word boundary, but reject when paired with a US-state suffix
    # on that same city (e.g. "Toronto, OH"). The anchored regex prevents a
    # stray ", NY" elsewhere in the string from poisoning a legit "Toronto, ON".
    if _GTA_CITY_RE.search(sl):
        if _GTA_WITH_US_STATE_RE.search(sl):
            return False
        return True
    return False


def keep_for_toronto_pipeline(loc: str) -> bool:
    """Producer-side geo gate for harvested rows.

    Returns True (keep) when:
      - location is empty/missing — let the scorer/LLM decide rather than
        silently lose a Toronto role whose location field LinkedIn omitted
      - location is bare "Remote" with no country anchor — same rationale;
        LinkedIn often emits just "Remote" for Canadian-remote postings
      - location passes is_gta_or_canada_remote

    Returns False (drop) only when location is present AND clearly non-GTA
    (e.g. "Raleigh, NC", "United States", "London, UK").
    """
    s = str(loc or "").strip()
    if not s:
        return True
    if s.lower() in ("remote", "remote (anywhere)", "anywhere"):
        return True
    return is_gta_or_canada_remote(s)


# ─────────────────────────────────────────────────────────────────────────────
# Broadened geo gate (additive, 2026-06): keep Canada + US + remote.
# Used by jd_scraper when the search scope is widened beyond Toronto. The
# original keep_for_toronto_pipeline above is left untouched for callers that
# still want the GTA-only gate.
# ─────────────────────────────────────────────────────────────────────────────
_US_CITIES = (
    "new york", "nyc", "brooklyn", "manhattan", "jersey city", "newark",
    "boston", "chicago", "san francisco", "palo alto", "los angeles",
    "seattle", "austin", "dallas", "houston", "atlanta", "charlotte",
    "miami", "denver", "philadelphia", "washington, dc", "washington dc",
    "minneapolis", "phoenix", "san diego", "san jose", "raleigh", "columbus",
    "pittsburgh", "salt lake city", "stamford", "greenwich, ct",
)
_US_STATE_SUFFIX_RE = re.compile(r",\s*(" + "|".join(_US_STATES) + r")", re.IGNORECASE)

_CA_TOKENS = (
    "canada", "ontario", "quebec", "québec", "montreal", "montréal",
    "ottawa", "vancouver", "calgary", "edmonton", "winnipeg", "halifax",
    "victoria", "alberta", "british columbia", "manitoba", "saskatchewan",
    "nova scotia", "new brunswick", "newfoundland",
)


def has_us(loc: str) -> bool:
    """Heuristic: does `loc` refer to the United States?"""
    sl = str(loc or "").lower()
    if not sl:
        return False
    if "united states" in sl or "usa" in sl:
        return True
    if _US_STATE_SUFFIX_RE.search(sl):
        return True
    if any(c in sl for c in _US_CITIES):
        return True
    return False


def has_canada(loc: str) -> bool:
    """Heuristic: any Canadian token (broader than the GTA/anchor predicate)."""
    sl = str(loc or "").lower()
    return any(t in sl for t in _CA_TOKENS)


def keep_canada_us_remote(loc: str) -> bool:
    """Broadened geo gate: keep Canada (GTA or elsewhere), the US (remote OR
    on-site for a TN move), and location-agnostic remote. Drops only clearly
    overseas on-site roles ("London, UK", "Singapore"). Empty / bare-remote are
    kept (scorer decides), mirroring keep_for_toronto_pipeline.
    """
    s = str(loc or "").strip()
    if not s:
        return True
    sl = s.lower()
    if "remote" in sl:
        return True
    if is_gta_or_canada_remote(s) or has_canada(s):
        return True
    if has_us(s):
        return True
    return False
