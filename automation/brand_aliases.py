"""brand_aliases.py — Canonical company-token lookup for cross-source dedup.

When the same role is posted via Workday ("BMO") and harvested via a LinkedIn
alert ("BMO Financial Group" or "Bank of Montreal"), both should collapse onto
the same near-dup key. This module returns a stable canonical token for any
known brand variant.

Stdlib-only so it stays cheap to import everywhere (worklist, gmail_reader,
jd_scraper). For brands not in the explicit map, falls back to the first
non-generic token of the company name — same as jd_scraper._brand_aliases'
heuristic, kept identical here on purpose so downstream behavior matches.
"""
from __future__ import annotations

import re

# Tokens that don't help disambiguate a brand. Mirrors jd_scraper._GENERIC_TOKENS.
_GENERIC_TOKENS = {
    "canada", "canadian", "group", "inc", "financial", "bank",
    "management", "investments", "capital", "corp", "limited",
    "company", "global", "pension", "plan", "the", "of", "and",
    "ltd", "llc", "co", "international", "services",
}

# Explicit aliases: every variant we've seen in the wild → canonical token.
# Built from worklist samples — both web-scrape labels and LinkedIn alert labels.
# Lowercased keys; match is exact-after-normalization.
_EXPLICIT_ALIASES: dict[str, str] = {
    # Big-6 banks
    "bmo": "bmo",
    "bmo financial group": "bmo",
    "bmo capital markets": "bmo",
    "bmo asset management": "bmo",
    "bank of montreal": "bmo",
    "rbc": "rbc",
    "rbc capital markets": "rbc",
    "rbc global asset management": "rbc",
    "royal bank": "rbc",
    "royal bank of canada": "rbc",
    "td": "td",
    "td bank": "td",
    "td bank group": "td",
    "td securities": "td",
    "td asset management": "td",
    "td insurance": "td",
    "td ameritrade": "td",
    "td wealth": "td",
    "td direct investing": "td",
    "toronto-dominion": "td",
    "toronto dominion": "td",
    "the toronto-dominion bank": "td",
    "cibc": "cibc",
    "cibc capital markets": "cibc",
    "canadian imperial bank of commerce": "cibc",
    "scotia": "scotia",
    "scotiabank": "scotia",
    "bank of nova scotia": "scotia",
    "bns": "scotia",
    "eqb": "eqb",
    "eq bank": "eqb",
    "equitable bank": "eqb",
    "equitable group": "eqb",
    "national bank": "nbc",
    "national bank of canada": "nbc",
    "national bank financial": "nbc",
    "nbc": "nbc",
    # National Bank surfaces in French in Quebec-sourced alerts; without these
    # "Banque Nationale" canonicalizes to "banque" and leaks past an NBC exclude.
    "banque nationale": "nbc",
    "banque nationale du canada": "nbc",
    "banque nationale financiere": "nbc",
    "bnc": "nbc",
    # Major insurers
    "manulife": "manulife",
    "manulife financial": "manulife",
    "manulife investment management": "manulife",
    "manulife real estate": "manulife",
    "manulife wealth": "manulife",
    "sun life": "sunlife",
    "sun life financial": "sunlife",
    "sunlife": "sunlife",
    "sun life investment management": "sunlife",
    "canada life": "canadalife",
    "the canada life assurance company": "canadalife",
    "great-west lifeco": "canadalife",
    "intact": "intact",
    "intact financial": "intact",
    "intact financial corporation": "intact",
    "definity": "definity",
    "definity insurance": "definity",
    "iA": "ia",
    "ia financial group": "ia",
    "industrial alliance": "ia",
    "fairfax": "fairfax",
    "fairfax financial": "fairfax",
    # Pension funds + asset managers
    "cpp investments": "cppib",
    "cppib": "cppib",
    "canada pension plan investment board": "cppib",
    "omers": "omers",
    "ontario municipal employees retirement system": "omers",
    "otpp": "otpp",
    "ontario teachers": "otpp",
    "ontario teachers' pension plan": "otpp",
    "healthcare of ontario pension plan": "hoopp",
    "hoopp": "hoopp",
    # LinkedIn alerts label HOOPP with the full name in parens, which the
    # generic fallback would leave uncollapsed ("hoopp healthcare of ontario
    # pension plan") — pin the combined variant so it canonicalizes + inherits
    # the pension sector.
    "hoopp healthcare of ontario pension plan": "hoopp",
    "imco": "imco",
    "investment management corporation of ontario": "imco",
    "psp investments": "psp",
    "psp": "psp",
    "caisse de depot": "cdpq",
    "cdpq": "cdpq",
    "caat pension": "caat",
    "caat": "caat",
    # Globals with Toronto presence
    "citi": "citi",
    "citigroup": "citi",
    "citibank": "citi",
    "jpmorgan": "jpmorgan",
    "jp morgan": "jpmorgan",
    "j.p. morgan": "jpmorgan",
    "jpmorgan chase": "jpmorgan",
    "morgan stanley": "morganstanley",
    "goldman sachs": "goldman",
    "goldman": "goldman",
    "deutsche bank": "deutsche",
    "deutsche": "deutsche",
    "hsbc": "hsbc",
    "hsbc bank canada": "hsbc",
    "barclays": "barclays",
    "ubs": "ubs",
    "credit suisse": "creditsuisse",
    # Big consultancies that hire risk roles
    "deloitte": "deloitte",
    "deloitte canada": "deloitte",
    "ey": "ey",
    "ernst & young": "ey",
    "ernst and young": "ey",
    "kpmg": "kpmg",
    "pwc": "pwc",
    "pricewaterhousecoopers": "pwc",
    "mckinsey": "mckinsey",
    "mckinsey & company": "mckinsey",
    "bcg": "bcg",
    "boston consulting group": "bcg",
    "bain": "bain",
    "bain & company": "bain",
    "accenture": "accenture",
    # Regulators
    "osfi": "osfi",
    "office of the superintendent of financial institutions": "osfi",
    "bank of canada": "boc",
    "boc": "boc",
    "fsra": "fsra",
    "financial services regulatory authority of ontario": "fsra",
    "osc": "osc",
    "ontario securities commission": "osc",
}


_NON_ALPHA = re.compile(r"[^a-z0-9 ]+")
_WHITESPACE = re.compile(r"\s+")


def _normalize_company_string(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = (name or "").lower().strip()
    # Treat various dash forms as space so "td-bank" matches "td bank"
    s = re.sub(r"[-–—_/]+", " ", s)
    # Drop everything else non-alphanumeric
    s = _NON_ALPHA.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


# Normalize keys at module load so "j.p. morgan" → "j p morgan" matches
# inputs that pass through _normalize_company_string. Done once; lookup stays O(1).
_NORMALIZED_ALIASES: dict[str, str] = {
    _normalize_company_string(k): v for k, v in _EXPLICIT_ALIASES.items()
}


def canonical_brand(name: str) -> str:
    """Return a canonical lowercase token for a company name. Stable across
    variants — "BMO", "Bank of Montreal", "BMO Financial Group" all → "bmo".

    Lookup order:
      1. Normalize input (lowercase, strip punctuation).
      2. Exact match against the (normalized) explicit alias map.
      3. Prefix match: longest-key-first walk so "td bank group" beats "td"
         when input has the longer prefix.
      4. Fallback: first non-generic token of the input. Mirrors
         jd_scraper._brand_aliases for backward-compat. If there's no usable
         token, return the normalized whole string.
    """
    if not name:
        return ""
    norm = _normalize_company_string(name)
    if not norm:
        return ""

    if norm in _NORMALIZED_ALIASES:
        return _NORMALIZED_ALIASES[norm]

    for key in sorted(_NORMALIZED_ALIASES.keys(), key=len, reverse=True):
        if norm.startswith(key + " ") or norm == key:
            if len(key) >= len(norm) * 0.6:
                return _NORMALIZED_ALIASES[key]

    tokens = [t for t in norm.split(" ") if t and t not in _GENERIC_TOKENS]
    if tokens:
        candidate = tokens[0]
        _canonical_values = set(_NORMALIZED_ALIASES.values())
        if candidate in _canonical_values and len(tokens) > 1:
            remaining = set(norm.split(" ")) - {candidate} - _GENERIC_TOKENS
            if remaining:
                return norm
        return candidate
    return norm
