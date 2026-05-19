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
_US_STATE_SUFFIX_RE = re.compile(
    r",\s*(" + "|".join(_US_STATES) + r")\b", re.IGNORECASE
)


def _has_us_state_anchor(loc_lower: str) -> bool:
    """True if `loc_lower` looks like '<city>, <US-state>'. Used to reject
    GTA-namesake US towns ('Toronto, OH', 'London, KY', etc.) that would
    otherwise pass the substring match against _GTA_CITIES."""
    return bool(_US_STATE_SUFFIX_RE.search(loc_lower))


def is_gta_or_canada_remote(loc: str) -> bool:
    """True if `loc` refers to the GTA or Canada-remote.

    Accepts:
      - Any GTA city (Toronto proper, Mississauga, Markham, Oakville, ...)
      - Canada-remote variants
      - Commute-reachable SW Ontario (Waterloo / Kitchener)
    Rejects Ottawa-only, Montreal, Vancouver, US namesakes (Toronto OH), etc.
    """
    loc_lower = str(loc or "").lower()
    if any(c in loc_lower for c in _GTA_CITIES):
        # Reject US namesake towns like "Toronto, OH" or "London, KY" that
        # share a name with a GTA city. The substring match alone cannot
        # distinguish them — pair it with a US-state-suffix guard.
        if _has_us_state_anchor(loc_lower):
            return False
        return True
    if "remote - canada" in loc_lower or "canada - remote" in loc_lower:
        return True
    if "remote canada" in loc_lower or "remote, canada" in loc_lower:
        return True
    # "Canada (Remote)" / "Remote (Canada)" / "Remote in Canada" — LinkedIn
    # uses these phrasings for nationwide Canadian-remote postings. Any string
    # containing both "canada" and "remote" tokens qualifies, regardless of
    # punctuation. Combined with the US-state-suffix guard above, this won't
    # match e.g. "Canada, KY (Remote-friendly)".
    if "canada" in loc_lower and "remote" in loc_lower:
        return True
    if loc_lower.strip() in ("canada", "ca"):
        return True
    if "waterloo" in loc_lower or "kitchener" in loc_lower:
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
