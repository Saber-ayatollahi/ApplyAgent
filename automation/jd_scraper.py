#!/usr/bin/env python3
"""
jd_scraper.py — Weekly scraper for Saber's target careers pages.

Hits the careers portals of each tracker target company, pulls job listings that
match an ALM/IRRBB/model-risk/fixed-income/derivatives/risk-analytics keyword filter,
dedupes against the tracker, and writes a candidate list for manual triage.

Because company careers pages vary wildly (Workday, Greenhouse, SmartRecruiters,
custom HTML, JS-heavy SPAs), this script:
1. Uses LinkedIn Jobs search via a public search URL with a keyword + company filter.
2. For Workday-hosted portals, hits the Workday JSON API (documented pattern).
3. Falls back to fetching the rendered careers page HTML + Claude-based extraction
   for the remaining companies.

Usage:
    python jd_scraper.py                       # run full weekly scan
    python jd_scraper.py --company Scotiabank  # single company
    python jd_scraper.py --linkedin-only       # skip portals, LinkedIn only

Writes:
    automation/outputs/scan_YYYYMMDD.json      # candidate list
    automation/outputs/scan_YYYYMMDD.md        # human-readable triage report

Notes:
- LinkedIn is the highest-signal source. The guest-search URL pattern works without auth.
- This is a starter implementation; expect to iterate per-portal as patterns are encountered.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

# Force UTF-8 stdio so unicode prints (✓, ⚠, ∪) don't crash cp1252
# consoles. Without this, jd_scraper rebuild stage prints crashed on
# Windows interactive runs (subprocess via scan_runner is fine because
# its stdout is redirected to a utf-8 logfile, but standalone CLI fails).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    print("ERROR: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "job_tracker_data.json"
OUT_DIR = ROOT / "automation" / "outputs"

sys.path.insert(0, str(ROOT / "automation"))
from location_filter import keep_for_toronto_pipeline as _keep_geo_raw  # noqa: E402

# Per-stage drop audit. Populated by `_keep_geo`/`_is_negative` wrappers below;
# emitted in the scan envelope under `filter_drops` so the audit-pack export
# can show users WHICH roles got rejected by title/geo filters and why.
_DROP_LOG_TITLE: list[dict] = []
_DROP_LOG_GEO: list[dict] = []
# Set per-company in run_scan() so drop entries can attribute to the right
# tenant; fetchers don't take company as a parameter, so this avoids an
# invasive signature change across 6 fetcher functions.
_current_company_ctx: str = ""
_current_sector_ctx: str = ""


def _keep_geo(loc: str, *, title: str = "", link: str = "",
              source: str = "") -> bool:
    """Wrap location_filter; log rejections to _DROP_LOG_GEO."""
    if _keep_geo_raw(loc):
        return True
    _DROP_LOG_GEO.append({
        "company": _current_company_ctx,
        "sector": _current_sector_ctx,
        "title": title,
        "link": link,
        "location": loc,
        "source": source,
    })
    return False

# Keyword tiers. "Any" match in a title or JD makes the role a candidate.
KEYWORDS_STRONG = [
    "alm", "asset liability", "asset-liability",
    "irrbb", "interest rate risk",
    "model validation", "model risk",
    "treasury risk", "balance sheet", "balance-sheet",
    "ldi", "liability driven", "liability-driven",
    "fixed income", "rates derivative",
    "cash flow projection", "liquidity stress", "liquidity risk",
    "risk analytics", "quantitative analyst", "quant analyst",
    "aladdin", "bloomberg risk",
    "ifrs 17", "ifrs17", "ifrs 9", "ifrs9",
    "credit risk", "market risk", "capital markets risk",
    "derivatives", "valuation", "portfolio risk",
    "enterprise risk", "financial risk",
    "fixed-income", "structured finance",
    "financial modeling", "financial modelling",
    "risk modeling", "risk modelling",
    "corporate treasury", "treasurer",
    "economic scenario", "monte carlo",
    "stress testing", "scenario analysis",
    "actuarial", "reserve", "capital model",
    "osfi", "b-12", "e-23", "lcr", "nsfr", "ftp",
    "pension analytics", "investment analytics",
    "analytics", "quant", "quantitative",
    # Lane 7.3 — Investment & Market Risk Analytics (VaR/CVaR, attribution, optimization)
    "cvar", "conditional var", "value at risk", "expected shortfall",
    "risk attribution", "risk decomposition", "portfolio optimization",
    "total portfolio risk", "factor risk", "investment risk", "tail risk",
    # Lane 7.4 — Vendor-Platform / Solutions Engineering & Client Solutions
    "solutions engineering", "solutions engineer", "sales engineer",
    "pre-sales", "presales", "client solutions", "client engagement",
    "client experience", "implementation consultant", "solutions consultant",
    "product specialist", "technical consultant", "client advisory",
]

KEYWORDS = KEYWORDS_STRONG  # backwards-compat for existing keyword_match() callers

# Strong-negative filter for obviously-wrong roles.
#
# We re-use the richer NEG_TITLE_TERMS list from fit_scorer.py as the source of
# truth. Scraper used to carry a shorter list, which meant we'd scrape (e.g.)
# "Senior Software Engineer, Risk Analytics" — pass it through dedup — only for
# the scorer to drop it at stage-1. That's ~5-10% of the weekly LLM budget
# burnt on roles we'd already decided were out of scope. Single source fixes
# that and keeps the two filters in sync going forward.
#
# Fall back to a minimal inline list if fit_scorer isn't importable (e.g.,
# standalone scraper runs on a CI box with no fit_scorer checked out).
try:
    from fit_scorer import NEG_TITLE_TERMS as _NEG_FROM_SCORER  # type: ignore
    NEGATIVE_TERMS = list(_NEG_FROM_SCORER)
except Exception:
    NEGATIVE_TERMS = [
        "intern", "co-op", "coop", "student", "graduate program",
        "retail branch", "teller", "branch manager", "customer service",
        "sales representative", "account executive", "business development representative",
        "marketing", "communications", "social media", "content writer",
        "cleaning", "security guard", "janitor", "facilities",
        "receptionist", "administrative assistant",
        "scientist, chemistry", "mechanical engineer", "electrical engineer",
    ]

# Companies to scan. Grouped by sector.
# `workday` tuple = (tenant, subdomain, board).  `greenhouse` = board token.
# Workday tenants validated empirically 2026-05-03 via ATS-discovery agent (live HTTP 200s).
TARGETS = [
    # ───── Canadian Big 6 Banks (6/6) ─────
    {"name": "Scotiabank", "sector": "Canadian Big 6 Banks", "linkedin_slug": "scotiabank", "workday": None, "successfactors": "https://jobs.scotiabank.com"},
    {"name": "RBC", "sector": "Canadian Big 6 Banks", "linkedin_slug": "rbc", "workday": None},
    {"name": "TD Bank", "sector": "Canadian Big 6 Banks", "linkedin_slug": "td", "workday": ("td", "wd3", "TD_Bank_Careers")},
    {"name": "BMO", "sector": "Canadian Big 6 Banks", "linkedin_slug": "bmo-financial-group", "workday": ("bmo", "wd3", "External")},
    {"name": "CIBC", "sector": "Canadian Big 6 Banks", "linkedin_slug": "cibc", "workday": ("cibc", "wd3", "search")},
    {"name": "National Bank of Canada", "sector": "Canadian Big 6 Banks", "linkedin_slug": "national-bank-of-canada", "workday": None},

    # ───── Canadian Pension Funds (9/9) ─────
    {"name": "HOOPP", "sector": "Canadian Pension Funds", "linkedin_slug": "hoopp", "workday": ("hoopp", "wd10", "HOOPP")},
    {"name": "OMERS", "sector": "Canadian Pension Funds", "linkedin_slug": "omers", "workday": ("omers", "wd3", "OMERS_External")},
    {"name": "Ontario Teachers' Pension Plan", "sector": "Canadian Pension Funds", "linkedin_slug": "ontario-teachers-pension-plan", "workday": ("otppb", "wd3", "OntarioTeachers_Careers")},
    {"name": "CPP Investments", "sector": "Canadian Pension Funds", "linkedin_slug": "cpp-investments", "workday": ("cppib", "wd10", "cppinvestments")},
    {"name": "PSP Investments", "sector": "Canadian Pension Funds", "linkedin_slug": "psp-investments", "workday": None},
    {"name": "OPTrust", "sector": "Canadian Pension Funds", "linkedin_slug": "optrust", "workday": ("optrust", "wd3", "OPTrust")},
    {"name": "CAAT Pension Plan", "sector": "Canadian Pension Funds", "linkedin_slug": "caat-pension-plan", "workday": ("caatpension", "wd10", "Careers")},
    {"name": "IMCO", "sector": "Canadian Pension Funds", "linkedin_slug": "imco", "workday": None},
    {"name": "CDPQ", "sector": "Canadian Pension Funds", "linkedin_slug": "cdpq", "workday": ("cdpq", "wd10", "CDPQ")},

    # ───── Canadian Asset Managers (12/12) ─────
    {"name": "Brookfield Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "brookfield", "workday": ("brookfield", "wd5", "brookfield")},
    {"name": "RBC Global Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "rbc-global-asset-management", "workday": None},
    {"name": "TD Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "td-asset-management", "workday": ("td", "wd3", "TD_Bank_Careers")},
    {"name": "BMO Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "bmo-global-asset-management", "workday": ("bmo", "wd3", "External")},
    {"name": "CI Financial", "sector": "Canadian Asset Managers", "linkedin_slug": "ci-financial", "workday": None},
    {"name": "Mackenzie Investments", "sector": "Canadian Asset Managers", "linkedin_slug": "mackenzie-investments", "workday": None},
    {"name": "AGF Management", "sector": "Canadian Asset Managers", "linkedin_slug": "agf-management-limited", "workday": ("agf", "wd3", "AGF_Careers")},
    {"name": "Fidelity Canada", "sector": "Canadian Asset Managers", "linkedin_slug": "fidelity-canada", "workday": None},
    {"name": "Connor Clark & Lunn", "sector": "Canadian Asset Managers", "linkedin_slug": "connor-clark-&-lunn-financial-group", "workday": None},
    {"name": "Guardian Capital Group", "sector": "Canadian Asset Managers", "linkedin_slug": "guardian-capital-group", "workday": None},
    {"name": "Picton Mahoney Asset Management", "sector": "Canadian Asset Managers", "linkedin_slug": "picton-mahoney-asset-management", "workday": None},
    {"name": "Canada Infrastructure Bank", "sector": "Canadian Asset Managers", "linkedin_slug": "canada-infrastructure-bank", "workday": None, "greenhouse": "canadainfrastructurebank"},

    # ───── US & Global Asset Managers (6/6) ─────
    {"name": "BlackRock", "sector": "US & Global Asset Managers", "linkedin_slug": "blackrock", "workday": ("blackrock", "wd1", "BlackRock_Professional")},
    {"name": "PIMCO", "sector": "US & Global Asset Managers", "linkedin_slug": "pimco", "workday": None},
    {"name": "Vanguard", "sector": "US & Global Asset Managers", "linkedin_slug": "vanguard", "workday": ("vanguard", "wd5", "Vanguard_External")},
    {"name": "Invesco", "sector": "US & Global Asset Managers", "linkedin_slug": "invesco", "workday": ("invesco", "wd1", "IVZ")},
    {"name": "Wellington Management", "sector": "US & Global Asset Managers", "linkedin_slug": "wellington-management", "workday": ("wellington", "wd5", "External")},
    {"name": "Schroders", "sector": "US & Global Asset Managers", "linkedin_slug": "schroders", "workday": None},

    # ───── US Banks with Toronto Presence (9/9) ─────
    {"name": "JPMorgan Chase", "sector": "US Banks (Toronto)", "linkedin_slug": "jpmorganchase", "workday": None},
    {"name": "Goldman Sachs", "sector": "US Banks (Toronto)", "linkedin_slug": "goldman-sachs", "workday": None},
    {"name": "Morgan Stanley", "sector": "US Banks (Toronto)", "linkedin_slug": "morgan-stanley", "workday": ("ms", "wd5", "External")},
    {"name": "Citi", "sector": "US Banks (Toronto)", "linkedin_slug": "citi", "workday": None, "phenom": "https://jobs.citi.com"},
    {"name": "HSBC", "sector": "US Banks (Toronto)", "linkedin_slug": "hsbc", "workday": None},
    {"name": "Deutsche Bank", "sector": "US Banks (Toronto)", "linkedin_slug": "deutsche-bank", "workday": ("db", "wd3", "DBWebsite")},
    {"name": "BNY Mellon", "sector": "US Banks (Toronto)", "linkedin_slug": "bny-mellon", "workday": None},
    {"name": "State Street", "sector": "US Banks (Toronto)", "linkedin_slug": "state-street", "workday": ("statestreet", "wd1", "Global")},
    {"name": "Northern Trust", "sector": "US Banks (Toronto)", "linkedin_slug": "northern-trust", "workday": ("ntrs", "wd1", "northerntrust")},

    # ───── Analytics & Risk Vendors (8/8) ─────
    {"name": "Bloomberg", "sector": "Analytics & Risk Vendors", "linkedin_slug": "bloomberg-lp", "workday": None},
    {"name": "MSCI", "sector": "Analytics & Risk Vendors", "linkedin_slug": "msci-inc", "workday": None},
    {"name": "S&P Global", "sector": "Analytics & Risk Vendors", "linkedin_slug": "s-p-global", "workday": ("spgi", "wd5", "SPGI_Careers")},
    {"name": "FactSet", "sector": "Analytics & Risk Vendors", "linkedin_slug": "factset", "workday": None},
    {"name": "Morningstar DBRS", "sector": "Analytics & Risk Vendors", "linkedin_slug": "morningstar", "workday": None},
    {"name": "SS&C Technologies", "sector": "Analytics & Risk Vendors", "linkedin_slug": "ss-c-technologies", "workday": ("ssctech", "wd1", "SSCTechnologies")},
    {"name": "Numerix", "sector": "Analytics & Risk Vendors", "linkedin_slug": "numerix-llc", "workday": None},
    {"name": "Prometeia", "sector": "Analytics & Risk Vendors", "linkedin_slug": "prometeia", "workday": None},

    # ───── Canadian Insurers (6/6) ─────
    {"name": "Manulife", "sector": "Canadian Insurers", "linkedin_slug": "manulife", "workday": ("manulife", "wd3", "MFCJH_Jobs")},
    {"name": "Sun Life", "sector": "Canadian Insurers", "linkedin_slug": "sun-life-financial", "workday": ("sunlife", "wd3", "Experienced")},
    {"name": "Canada Life", "sector": "Canadian Insurers", "linkedin_slug": "canada-life", "workday": None, "successfactors": "https://jobs.canadalife.com"},
    {"name": "Intact Financial", "sector": "Canadian Insurers", "linkedin_slug": "intact-financial-corporation", "workday": None},
    {"name": "Definity Financial", "sector": "Canadian Insurers", "linkedin_slug": "definity", "workday": None},
    {"name": "iA Financial Group", "sector": "Canadian Insurers", "linkedin_slug": "industrial-alliance", "workday": ("ia", "wd3", "Professional")},
    {"name": "RGA", "sector": "Canadian Insurers", "linkedin_slug": "rga-reinsurance-group-of-america", "workday": ("rgare", "wd1", "Careers")},

    # ───── Mid-size Canadian Banks (1/1) ─────
    {"name": "EQB", "sector": "Mid Canadian Banks", "linkedin_slug": "eqbank", "workday": None},

    # ───── Big 4 FS Risk Advisory (4/4) ─────
    {"name": "Deloitte Canada", "sector": "Big 4 Risk Advisory", "linkedin_slug": "deloitte", "workday": None, "successfactors": "https://careers.deloitte.ca"},
    {"name": "EY Canada", "sector": "Big 4 Risk Advisory", "linkedin_slug": "ernstandyoung", "workday": None, "successfactors": "https://careers.ey.com"},
    {"name": "KPMG Canada", "sector": "Big 4 Risk Advisory", "linkedin_slug": "kpmg-canada", "workday": None},
    {"name": "PwC Canada", "sector": "Big 4 Risk Advisory", "linkedin_slug": "pwc-canada", "workday": None},

    # ───── Pension / ALM Consulting (3/3) ─────
    {"name": "Mercer", "sector": "Pension/ALM Consulting", "linkedin_slug": "mercer", "workday": None},
    {"name": "WTW", "sector": "Pension/ALM Consulting", "linkedin_slug": "willis-towers-watson", "workday": None},
    {"name": "Aon", "sector": "Pension/ALM Consulting", "linkedin_slug": "aon", "workday": None},

    # ───── FS Strategy & Risk Consulting (1/1) ─────
    {"name": "Oliver Wyman", "sector": "FS Strategy Consulting", "linkedin_slug": "oliver-wyman", "workday": None},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# LinkedIn public job search (guest endpoint — no auth needed)
LINKEDIN_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
    "keywords={keywords}&location=Toronto%2C+Ontario%2C+Canada&f_C={company_id}&start=0"
)


def keyword_match(text: str) -> list[str]:
    tl = text.lower()
    hits = [k for k in KEYWORDS if k in tl]
    return hits


# Keyword phrases used as separate LinkedIn queries. LinkedIn guest search parses
# "A OR B" as a literal phrase, not as a boolean — so we must run multiple queries
# and merge results.
LINKEDIN_QUERY_PHRASES = [
    # Core lane
    "ALM", "IRRBB", "model validation", "model risk",
    "interest rate risk", "fixed income", "treasury risk", "balance sheet",
    # Derivatives + rates
    "derivatives", "rates", "swaps", "structured credit",
    # Quant / analytics
    "quantitative", "quant developer", "risk analytics",
    # Risk domains
    "portfolio risk", "credit risk", "liquidity risk", "market risk",
    "counterparty risk", "operational risk",
    # Regulatory / reporting
    "IFRS 17", "IFRS 9", "capital markets risk", "regulatory capital",
    "stress testing", "OSFI",
    # Specialty
    "valuation", "model governance", "actuarial",
    # Emerging (OSFI B-15 climate, digital assets)
    "climate risk", "digital assets",
    # Lane 7.3 — Investment & Market Risk Analytics
    "investment risk", "portfolio optimization", "VaR", "risk attribution",
    # Lane 7.4 — Vendor-Platform / Solutions Engineering & Client Solutions
    "solutions engineering", "client solutions", "client engagement", "Aladdin",
]

# Fuzzy brand aliases — words that plausibly appear in the "company" subtitle on LinkedIn
# job cards, even if the card doesn't show the full legal name. Every target entry gets
# a `brand_aliases` list built from its name unless explicitly provided.
_GENERIC_TOKENS = {"canada", "canadian", "group", "inc", "financial", "bank",
                   "management", "investments", "capital", "corp", "limited",
                   "company", "global", "pension", "plan"}


def _brand_aliases(name: str) -> list[str]:
    """Return a list of lowercase tokens that, if any one is in the card-company text,
    the card counts as this brand."""
    raw = name.lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", raw) if t and t not in _GENERIC_TOKENS]
    # Always include the full lower-case name (minus punctuation), and the first two tokens
    aliases = [raw.replace("  ", " ").strip()]
    if tokens:
        aliases.append(tokens[0])
        if len(tokens) > 1:
            aliases.append(f"{tokens[0]} {tokens[1]}")
    return list(set(a for a in aliases if len(a) >= 3))


def _is_finance_title(title: str) -> bool:
    """Lightweight title filter for the company-only LinkedIn fallback.
    Must have at least one finance/risk/actuarial keyword AND not be a negative term.
    Deliberately a bit broader than fit_scorer stage-1 so we don't prefilter too much here;
    stage-1 will triage further downstream."""
    tl = (title or "").lower()
    if any(n in tl for n in NEGATIVE_TERMS):
        return False
    loose_keywords = (
        "risk", "alm", "irrbb", "model", "treasury", "liquidity", "capital",
        "balance sheet", "fixed income", "derivat", "valuation", "quant",
        "actuar", "portfolio", "ifrs", "osfi", "basel", "credit", "market risk",
        "analytics", "analytique", "stress", "scenario", "hedge",
        "finance", "financial", "forecast", "economic", "economist",
        "investment", "wealth", "pension", "reserving", "pricing",
        "regulator", "compliance", "audit", "governance",
        "director", "vp", "vice president", "managing director",
        "principal", "head of", "chief", "avp",
        "solutions", "presales", "optimization", "attribution",
    )
    return any(k in tl for k in loose_keywords)


# LinkedIn location filters. Toronto is the default; Mississauga serves GTA-west
# (Citi, Aviva, Sagen, Canadian Tire Bank). LinkedIn's commute-radius heuristic
# reaches most GTA roles from Toronto coords, but Mississauga-posted roles often
# paginate off the first 3 pages because distance dings their rank. The
# second-location pass is gated on "LinkedIn-only" companies (no Workday/GH/Lever/
# SF) so we don't 2× traffic for well-covered targets.
_LINKEDIN_LOC_TORONTO = "Toronto%2C+Ontario%2C+Canada"
_LINKEDIN_LOC_MISSISSAUGA = "Mississauga%2C+Ontario%2C+Canada"

# Scan-wide kill-switch. Flipped to True inside fetch_linkedin_jobs when any
# single company trips the 3-consecutive-429 threshold — a strong signal that
# LinkedIn is throttling OUR IP for the rest of this run. Remaining companies
# then short-circuit LinkedIn calls (backoff loops waste ~70s/keyword×12kw =
# ~14min per throttled company if we don't). Reset at the start of scan().
_linkedin_globally_throttled = False


def _linkedin_throttle_reset():
    global _linkedin_globally_throttled
    _linkedin_globally_throttled = False


def _linkedin_throttle_set():
    global _linkedin_globally_throttled
    _linkedin_globally_throttled = True


def _company_has_non_linkedin_ats(company: dict) -> bool:
    """True if this target has any configured non-LinkedIn source (Workday,
    Greenhouse, Lever, SuccessFactors, or Phenom). When False, LinkedIn is doing
    all the work for this company and the GTA-west second pass is worth the
    extra quota."""
    return bool(
        company.get("workday")
        or company.get("greenhouse")
        or company.get("lever")
        or company.get("successfactors")
        or company.get("phenom")
    )


def fetch_linkedin_jobs(company: dict, max_queries: int = 12, pages_per_query: int = 3) -> list[dict]:
    """
    Query LinkedIn's public guest-search API.

    Three-phase strategy:
      1. Keyword + company, Toronto location (12 keywords × 3 pages) — high-signal
      2. Company-only, Toronto location (4 pages) — catches titles without a keyword
         (e.g., "Associate Director" at RBC; global-AMs with sparse Toronto listings)
      3. Company-only, Mississauga location (2 pages) — ONLY for LinkedIn-only
         companies (no ATS configured). LinkedIn ranks by distance from the
         query coords; GTA-west-posted roles (Citi Mississauga NTMR, Aviva etc.)
         rank poorly at Toronto coords but surface at Mississauga coords.

    The company-only phases apply a loose finance-title filter before accepting
    the result, so we don't flood stage-1 with every Java Dev at Goldman.
    """
    # Scan-wide throttle short-circuit: if a prior company already hit the
    # LinkedIn 3-×-429 wall, don't bother making more requests this run.
    if _linkedin_globally_throttled:
        print(f"  [linkedin] skipping {company['name']} — scan-wide throttle tripped",
              file=sys.stderr)
        return []

    aliases = company.get("brand_aliases") or _brand_aliases(company["name"])
    seen_links: set[str] = set()
    all_jobs: list[dict] = []
    rate_limited = False

    def _emit_card(card, kw_label: str, source_phase: str) -> bool:
        """Parse one LinkedIn card. Returns True if we added a row."""
        title_el = card.select_one("h3")
        link_el = card.select_one("a.base-card__full-link") or card.select_one("a")
        co_el = card.select_one("h4, .base-search-card__subtitle")
        loc_el = card.select_one(".job-search-card__location")
        time_el = card.select_one("time")
        if not (title_el and link_el):
            return False
        title = title_el.get_text(strip=True)
        link = (link_el.get("href") or "").split("?")[0]
        if not link or link in seen_links:
            return False
        co = (co_el.get_text(strip=True) if co_el else company["name"]).lower()
        if not any(a in co for a in aliases):
            return False
        # In the company-only phases, require a finance/risk signal in the title
        # to keep the volume manageable
        if source_phase in ("company_only", "company_only_gtaw") and not _is_finance_title(title):
            return False
        loc = loc_el.get_text(strip=True) if loc_el else "Toronto"
        # Posted date — LinkedIn wraps it in <time datetime="2026-05-01">
        posted = time_el.get("datetime") if time_el else None
        seen_links.add(link)
        source = {
            "keyword": "linkedin",
            "company_only": "linkedin_co",
            "company_only_gtaw": "linkedin_co_gtaw",  # GTA-west pass — tag so we can audit
        }.get(source_phase, "linkedin")
        all_jobs.append({
            "title": title,
            "link": link,
            "company_reported": co_el.get_text(strip=True) if co_el else company["name"],
            "location": loc,
            "keyword_hit": kw_label,
            "source": source,
            "posted_date": posted,
        })
        return True

    def _run_query(keywords_str: str, pages: int, kw_label: str, phase: str,
                    location: str = _LINKEDIN_LOC_TORONTO) -> bool:
        """Returns True if hard-rate-limited (multiple 429s), to break outer loop."""
        nonlocal rate_limited
        consecutive_429 = 0
        for page in range(pages):
            start = page * 25
            url = (
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                f"keywords={requests.utils.quote(keywords_str)}"
                f"&location={location}"
                f"&start={start}"
            )
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code == 429:
                    consecutive_429 += 1
                    backoff = 10 * (2 ** (consecutive_429 - 1))  # 10s, 20s, 40s
                    print(f"  [linkedin] 429 on '{keywords_str[:30]}' page {page} "
                          f"— backing off {backoff}s (attempt {consecutive_429})",
                          file=sys.stderr)
                    time.sleep(backoff)
                    if consecutive_429 >= 3:
                        rate_limited = True
                        _linkedin_throttle_set()
                        print(f"  [linkedin] scan-wide throttle TRIPPED on "
                              f"'{keywords_str[:30]}' — remaining companies' "
                              f"LinkedIn calls will be skipped this run",
                              file=sys.stderr)
                        return True
                    continue  # retry the same page
                consecutive_429 = 0
                if r.status_code != 200:
                    return False
                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select("li")
                if not cards:
                    return False
                added = sum(1 for card in cards if _emit_card(card, kw_label, phase))
                if added == 0:
                    return False
                time.sleep(0.5)
            except Exception as e:
                print(f"  [linkedin] error on '{keywords_str}' page {page} for {company['name']}: {e}",
                      file=sys.stderr)
                return False
        return False

    # Phase 1: keyword + company name, Toronto coords
    for kw in LINKEDIN_QUERY_PHRASES[:max_queries]:
        if rate_limited:
            break
        if _run_query(f"{kw} {company['name']}", pages_per_query, kw, "keyword"):
            break
        time.sleep(0.5)

    # Phase 2: company-only, Toronto coords (4 pages; catches keyword-less titles)
    if not rate_limited:
        _run_query(company["name"], pages=4, kw_label="company_only", phase="company_only")
        time.sleep(0.5)

    # Phase 3: company-only, Mississauga coords — ONLY for LinkedIn-only companies.
    # Small budget (2 pages) since this is a supplementary pass; the finance-title
    # filter inside _emit_card will keep the signal-to-noise high.
    if not rate_limited and not _company_has_non_linkedin_ats(company):
        before_gtaw = len(all_jobs)
        _run_query(company["name"], pages=2, kw_label="company_only_gtaw",
                    phase="company_only_gtaw", location=_LINKEDIN_LOC_MISSISSAUGA)
        gtaw_added = len(all_jobs) - before_gtaw
        if gtaw_added:
            print(f"  [linkedin] GTA-west pass: +{gtaw_added} new for {company['name']}",
                  file=sys.stderr)
        time.sleep(0.5)

    return all_jobs


# ---------------------------------------------------------------------------
# Greenhouse — a number of vendors and some Canadian firms host on Greenhouse.
# API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
# ---------------------------------------------------------------------------
def fetch_greenhouse_jobs(token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs = []
        for j in data.get("jobs", []):
            title = j.get("title", "")
            loc = (j.get("location", {}) or {}).get("name", "")
            if not _keep_geo(loc, title=title,
                             link=j.get("absolute_url", ""),
                             source=f"greenhouse:{token}"):
                continue
            if not keyword_match(title):
                continue
            # Greenhouse exposes updated_at (iso) and first_published (iso)
            posted = j.get("first_published") or j.get("updated_at")
            jobs.append({
                "title": title,
                "link": j.get("absolute_url", ""),
                "location": loc,
                "source": f"greenhouse:{token}",
                "posted_date": posted,
            })
        return jobs
    except Exception as e:
        print(f"  [greenhouse:{token}] error: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Lever — https://api.lever.co/v0/postings/{slug}?mode=json
# ---------------------------------------------------------------------------
def fetch_lever_jobs(slug: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs = []
        for j in data:
            title = j.get("text", "")
            categories = j.get("categories", {}) or {}
            loc = categories.get("location", "") or ""
            if not _keep_geo(loc, title=title,
                             link=j.get("hostedUrl", ""),
                             source=f"lever:{slug}"):
                continue
            if not keyword_match(title):
                continue
            # Lever exposes createdAt as epoch-millis
            posted = None
            created_at = j.get("createdAt")
            if isinstance(created_at, (int, float)) and created_at > 0:
                try:
                    posted = datetime.fromtimestamp(created_at / 1000, timezone.utc).date().isoformat()
                except Exception:
                    posted = None
            jobs.append({
                "title": title,
                "link": j.get("hostedUrl", ""),
                "location": loc,
                "source": f"lever:{slug}",
                "posted_date": posted,
            })
        return jobs
    except Exception as e:
        print(f"  [lever:{slug}] error: {e}", file=sys.stderr)
        return []


_WORKDAY_REL = re.compile(
    r"posted\s+(\d+)\+?\s+(day|week|month)s?\s+ago",
    re.IGNORECASE,
)


def _normalize_workday_posted(raw: str, today: Optional[date] = None) -> str:
    """Workday's postedOn arrives as relative strings ("Posted 6 Days Ago",
    "Posted Today", "Posted Yesterday", "Posted 30+ Days Ago", "Posted 2
    Months Ago", "Posted 1 Week Ago"). Convert to ISO YYYY-MM-DD so
    downstream [:10] slicing and date diffs work. Pass through anything
    already ISO-shaped or empty."""
    if not raw:
        return ""
    s = str(raw).strip()
    # Already ISO-ish — leave alone.
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s
    today = today or date.today()
    low = s.lower()
    if "today" in low:
        return today.isoformat()
    if "yesterday" in low:
        return (today - timedelta(days=1)).isoformat()
    m = _WORKDAY_REL.search(s)
    if m:
        try:
            n = int(m.group(1))
        except ValueError:
            return ""
        unit = m.group(2).lower()
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        return (today - timedelta(days=days)).isoformat()
    return ""


_WD_URL_RE = re.compile(
    r"^https?://([^/]+\.myworkdayjobs\.com)/(.+?)(/job/.+)$", re.IGNORECASE
)


def _workday_cxs_url(link: str):
    """Derive the CXS job-detail endpoint from a public myworkdayjobs URL.
    Returns (detail_url, host, board_path) or None. Pure / no network.

    Public:  https://cppib.wd10.myworkdayjobs.com/cppinvestments/job/Toronto/X_JR1
    Detail:  https://cppib.wd10.myworkdayjobs.com/wday/cxs/cppib/cppinvestments/job/Toronto/X_JR1
    A locale prefix (.../en-US/cppinvestments/job/...) is tolerated — the board
    is the path segment immediately before /job/."""
    if not link:
        return None
    m = _WD_URL_RE.match(link.strip())
    if not m:
        return None
    host, pre, path = m.group(1), m.group(2), m.group(3)
    board = pre.rstrip("/").split("/")[-1]   # site segment immediately before /job/
    tenant = host.split(".")[0]
    return f"https://{host}/wday/cxs/{tenant}/{board}{path}", host, f"{board}{path}"


def workday_precise_date(link: str, *, timeout: int = 12) -> Optional[str]:
    """Best-effort PRECISE posting date for a Workday job, from the CXS
    job-detail endpoint's ``jobPostingInfo.startDate``.

    Workday's *list* API only exposes a relative ``postedOn`` string, and
    "Posted 30+ Days Ago" floors to exactly 30 days — so a role that is
    really 45 days old looks like 30. The per-job detail endpoint carries
    the true ISO ``startDate``.

    Returns 'YYYY-MM-DD' or None. Unlisted / direct-link postings return 403
    here even when their public page is live — callers must fall back to the
    relative date in that case."""
    parsed = _workday_cxs_url(link)
    if not parsed:
        return None
    durl, host, board_path = parsed
    try:
        r = requests.get(
            durl,
            headers={**HEADERS, "Accept": "application/json",
                     "Referer": f"https://{host}/{board_path}"},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        jpi = (r.json() or {}).get("jobPostingInfo", {}) or {}
        sd = str(jpi.get("startDate") or "")
        if re.match(r"^\d{4}-\d{2}-\d{2}", sd):
            return sd[:10]
    except Exception:
        return None
    return None


WORKDAY_SUBDOMAINS = ["wd3", "wd5", "wd1", "wd10", "wd102"]


def fetch_workday_jobs(workday_spec) -> list[dict]:
    """Query Workday's JSON API.
    `workday_spec` can be either:
      - (tenant, subdomain, board)  — preferred, validated form
      - (tenant, board)             — legacy; will probe subdomains
      - (tenant_with_dot, board)    — e.g. ("hoopp.wd10", "HOOPP")"""
    if len(workday_spec) == 3:
        tenant, subdomain, board = workday_spec
        hosts = [f"{tenant}.{subdomain}.myworkdayjobs.com"]
        tenant_key = tenant
    else:
        tenant, board = workday_spec
        if "." in tenant:
            hosts = [f"{tenant}.myworkdayjobs.com"]
            tenant_key = tenant.split(".")[0]
        else:
            hosts = [f"{tenant}.{sub}.myworkdayjobs.com" for sub in WORKDAY_SUBDOMAINS]
            tenant_key = tenant

    # Run per-keyword searches. Workday supports keyword search + pagination.
    # This is more robust than a one-shot "Toronto" fetch because Workday scores
    # by relevance and returns many more model/ALM/risk matches under those terms.
    WORKDAY_KEYWORDS = [
        "model validation", "model risk", "ALM", "IRRBB", "treasury",
        "fixed income", "market risk", "liquidity risk", "quantitative",
        "balance sheet", "derivatives", "IFRS 17", "risk analytics",
    ]
    seen_paths: set[str] = set()
    jobs: list[dict] = []
    for host in hosts:
        worked = False
        for kw in WORKDAY_KEYWORDS:
            url = f"https://{host}/wday/cxs/{tenant_key}/{board}/jobs"
            for offset in (0, 20):
                body = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": kw}
                try:
                    r = requests.post(url, json=body, headers=HEADERS, timeout=20)
                    if r.status_code != 200:
                        break
                    worked = True
                    data = r.json()
                    postings = data.get("jobPostings", [])
                    if not postings:
                        break
                    # Keep only Toronto/Ontario/Canada-located; filter on title+location
                    for p in postings:
                        title = p.get("title", "")
                        loc = (p.get("locationsText", "") or "").lower()
                        path = p.get("externalPath", "") or ""
                        if path in seen_paths:
                            continue
                        # externalPath is "/job/<loc>/<title>_<reqid>" relative
                        # to the SITE. The clickable external URL needs the site
                        # (board) segment in front: https://<host>/<board>/job/…
                        # Without it, Workday 404s and the browser bounces to
                        # community.workday.com/invalid-url (verified: bare
                        # /job/ → 404, /<board>/job/ → 200).
                        _wd_link = f"https://{host}/{board}{path}"
                        if not _keep_geo(loc, title=title,
                                         link=_wd_link,
                                         source=f"workday:{tenant_key}"):
                            continue
                        # Date: the list API's relative postedOn is exact for
                        # <30d ("Posted 6 Days Ago") but floors "30+ Days Ago"
                        # to 30. For that imprecise case (or a missing string),
                        # fetch the precise startDate from the detail endpoint;
                        # otherwise trust the cheap relative value (no extra GET).
                        _raw_posted = p.get("postedOn", "") or ""
                        _rel = _normalize_workday_posted(_raw_posted)
                        if (not _rel) or ("30+" in _raw_posted):
                            _posted = workday_precise_date(_wd_link) or _rel
                        else:
                            _posted = _rel
                        jobs.append({
                            "title": title,
                            "link": _wd_link,
                            "location": p.get("locationsText", ""),
                            "posted_date": _posted,
                            "keyword_hit": kw,
                            "source": f"workday:{tenant_key}",
                        })
                        seen_paths.add(path)
                    if len(postings) < 20:
                        break
                except Exception as e:
                    print(f"  [workday:{host}] error on '{kw}': {e}", file=sys.stderr)
                    break
        if worked:
            return jobs
    return jobs


# ---------------------------------------------------------------------------
# SuccessFactors RSS adapter
# ---------------------------------------------------------------------------
# Many Canadian government / regulator / vendor career portals run on SAP
# SuccessFactors. These expose a standard RSS endpoint at /services/rss/job/
# that returns up to ~20 items per keyword query (no auth required).
#
# Usage in TARGETS: {"successfactors": "https://careers.bankofcanada.ca"}
# ---------------------------------------------------------------------------
_SF_KEYWORDS = ["risk", "model", "capital", "treasury", "liquidity", "analytics",
                "quantitative", "valuation", "actuarial", "derivatives",
                "balance sheet", "market risk"]




def fetch_successfactors_jobs(sf_base: str) -> list[dict]:
    """Query a SuccessFactors career portal's RSS feed for multiple keywords
    and return GTA / Canada-remote roles. `sf_base` must be a host like
    'https://careers.bankofcanada.ca' (no trailing slash)."""
    base = sf_base.rstrip("/")
    seen_links: set[str] = set()
    out: list[dict] = []
    for kw in _SF_KEYWORDS:
        url = f"{base}/services/rss/job/?locale=en_US&keywords=({requests.utils.quote(kw)})"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
            for it in items:
                title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", it, re.S)
                link_m = re.search(r"<link>([^<]+)</link>", it)
                pub_m = re.search(r"<pubDate>([^<]+)</pubDate>", it)
                if not title_m or not link_m:
                    continue
                full_title = title_m.group(1).strip()
                link = link_m.group(1).strip().split("?")[0]
                if link in seen_links:
                    continue
                # Split "Job Title (Location)" — the location is the last parenthetical
                paren = re.search(r"\(([^()]+)\)\s*$", full_title)
                location = paren.group(1) if paren else ""
                title = re.sub(r"\s*\(([^()]+)\)\s*$", "", full_title).strip()
                loc_lower = location.lower()
                if not _keep_geo(loc_lower, title=title, link=link,
                                 source=f"successfactors:{base.replace('https://', '')}"):
                    continue
                posted = None
                if pub_m:
                    # RFC822: "Sat, 03 May 2026 12:00:00 GMT" -> ISO
                    try:
                        from email.utils import parsedate_to_datetime
                        posted = parsedate_to_datetime(pub_m.group(1)).date().isoformat()
                    except Exception:
                        posted = pub_m.group(1)
                seen_links.add(link)
                out.append({
                    "title": title,
                    "link": link,
                    "location": location,
                    "keyword_hit": kw,
                    "source": f"successfactors:{base.replace('https://', '')}",
                    "posted_date": posted,
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"  [sf:{base}] error on '{kw}': {e}", file=sys.stderr)
            continue
    return out


# ---------------------------------------------------------------------------
# Phenom ATS adapter (Citi jobs.citi.com, RBC jobs.rbc.com, Walmart, AT&T, etc.)
# ---------------------------------------------------------------------------
# Phenom's keyword-driven search is the ONLY reliable way to surface roles —
# direct /search-jobs/<city>/<country> geography walks hide some postings that
# are otherwise live at direct URLs (confirmed empirically with the Citi
# Mississauga VP Non-Trading Market Risk role, which is unreachable via
# /search-jobs/Canada/287 pagination but IS returned by ?k=market+risk).
#
# URL form that works (verified on jobs.citi.com, 2026-05-05):
#   /search-jobs?k=<keyword>&p=<page>        — pagination uses lowercase `p`
# The returned HTML page contains 15 job cards under <section id="search-results-list">.
# Each card wraps an anchor like /job/<city>/<slug>/<tenant_id>/<job_id>.
#
# Usage in TARGETS: {"phenom": "https://jobs.citi.com"}
# ---------------------------------------------------------------------------
_PHENOM_KEYWORDS = [
    "market risk", "non-trading", "IRRBB", "interest rate risk",
    "model validation", "model risk", "ALM",
    "treasury risk", "balance sheet", "liquidity risk",
    "capital management", "derivatives",
]

# Canadian city slugs that appear in Phenom /job/<city>/... paths. This is the
# cheapest way to filter to Canada-only without parsing each card's metadata.
# Kept deliberately loose — missing a slug here means we drop a real role.
#
# Intentionally EXCLUDED: 'london' (ambiguous with London, UK — Citi's HQ
# slugs many UK roles as /job/london/...). A Citi role in London, ON would be
# missed; we accept that rather than the much larger false-positive cost of
# pulling UK London roles into a Toronto-focused scan.
_PHENOM_CANADA_CITY_SLUGS = {
    "toronto", "mississauga", "markham", "vaughan", "brampton", "oakville",
    "burlington", "milton", "richmond-hill", "pickering", "ajax", "whitby",
    "oshawa", "north-york", "scarborough", "etobicoke", "thornhill", "concord",
    "woodbridge", "montreal", "vancouver", "calgary", "edmonton", "ottawa",
    "quebec", "halifax", "winnipeg", "regina", "saskatoon", "victoria",
    "waterloo", "kitchener",
    # Add the word 'canada' for tenants that include the country in the slug
    "canada",
}


def fetch_phenom_jobs(base_url: str, tenant_name: str = "") -> list[dict]:
    """Query a Phenom-hosted careers portal (e.g., jobs.citi.com) for multiple
    keywords and return Canada-located roles. `base_url` must be a host root
    like 'https://jobs.citi.com' (no trailing slash).

    Filter: /job/<city>/... path slug must be a known Canadian city. This skips
    Phenom's own card-metadata parsing (which is inconsistent across tenants).
    """
    base = base_url.rstrip("/")
    tenant = tenant_name or base.split("://", 1)[-1].split(".")[1]  # e.g. "citi"
    seen_paths: set[str] = set()
    out: list[dict] = []

    # A job's path shape: /job/<city>/<slug>/<tenant_id>/<job_id>
    path_re = re.compile(r"/job/([a-z\-]+)/([a-z0-9\-]+)/(\d+)/(\d{10,12})")

    # Per-keyword cap. Each keyword visits up to 5 pages (75 roles) — Phenom
    # tenants with no roles for a keyword return duplicated page-1 contents,
    # so the dedup loop will short-circuit early.
    for kw in _PHENOM_KEYWORDS:
        seen_before = len(seen_paths)
        for page in range(1, 6):
            url = (f"{base}/search-jobs?"
                   f"k={requests.utils.quote(kw)}&p={page}")
            try:
                r = requests.get(url, headers=HEADERS, timeout=25)
                if r.status_code != 200:
                    break
                matches = path_re.findall(r.text)
                if not matches:
                    break
                new_on_page = 0
                for city_slug, role_slug, tenant_id, job_id in matches:
                    full_path = f"/job/{city_slug}/{role_slug}/{tenant_id}/{job_id}"
                    if full_path in seen_paths:
                        continue
                    title = role_slug.replace("-", " ").title()
                    if city_slug not in _PHENOM_CANADA_CITY_SLUGS:
                        seen_paths.add(full_path)  # still mark so we don't re-evaluate
                        _keep_geo(city_slug.replace("-", " ").title(),
                                  title=title,
                                  link=f"{base}{full_path}",
                                  source=f"phenom:{tenant}")
                        continue
                    # Extract title from the slug (role_slug uses dashes for spaces)
                    # Fine-tune a few title-cased corner cases
                    title = (title.replace(" Vp", " VP").replace(" Svp", " SVP")
                                  .replace(" Avp", " AVP").replace("Irrbb", "IRRBB")
                                  .replace("Alm", "ALM").replace("Ifrs", "IFRS")
                                  .replace("Osfi", "OSFI"))
                    seen_paths.add(full_path)
                    out.append({
                        "title": title,
                        "link": f"{base}{full_path}",
                        "location": city_slug.replace("-", " ").title(),
                        "keyword_hit": kw,
                        "source": f"phenom:{tenant}",
                        "posted_date": None,  # Phenom doesn't expose postedOn in list HTML
                    })
                    new_on_page += 1
                if new_on_page == 0:
                    break  # whole page was duplicates — stop paginating this keyword
                time.sleep(0.5)
            except Exception as e:
                print(f"  [phenom:{tenant}] error on '{kw}' p{page}: {e}",
                      file=sys.stderr)
                break
        added = len(seen_paths) - seen_before
        # Mild pacing between keywords
        time.sleep(0.3)
    return out


def load_tracker_urls() -> set[str]:
    """Load existing tracker URLs so we dedupe."""
    data = json.loads(TRACKER.read_text(encoding="utf-8"))
    return {j.get("url", "") for j in data.get("jobs", []) if j.get("url")}


# ---------------------------------------------------------------------------
# url_history.json — persistent registry of "when did we first see this URL".
# Lets us stamp `found_at` on every row without relying on the scraper order.
# File shape: { "<url>": {"found_at": "YYYY-MM-DD", "first_source": "workday:bmo"}}
# ---------------------------------------------------------------------------
URL_HISTORY = OUT_DIR / "url_history.json"


def load_url_history() -> dict:
    if not URL_HISTORY.exists():
        return {}
    try:
        return json.loads(URL_HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_url_history(hist: dict):
    """Write url_history atomically: write to a tempfile in the same directory,
    then os.replace() onto the final path. Ensures a mid-write crash (or
    concurrent scraper instance) never leaves a partial file that would strip
    out prior found_at timestamps.

    os.replace is atomic on all supported platforms (POSIX rename, Win32
    MoveFileEx with REPLACE_EXISTING). Must be same-filesystem — guaranteed
    because tempfile is in the same dir.
    """
    import os
    import tempfile
    URL_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    # delete=False: we want to close it before renaming (Windows holds locks
    # on open files). dir=URL_HISTORY.parent: guarantees same filesystem.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(URL_HISTORY.parent),
        prefix=".url_history.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(hist, f, indent=2)
        os.replace(tmp_path, URL_HISTORY)
    except Exception:
        # Clean up tempfile on failure — otherwise stale .tmp files accumulate
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def stamp_found_at(results: list[dict], today_iso: str | None = None) -> dict:
    """Mutate each row to add `found_at` from history (or today if new).
    Returns the updated history dict (caller should persist)."""
    today_iso = today_iso or date.today().isoformat()
    hist = load_url_history()
    for r in results:
        url = r.get("link", "")
        if not url:
            continue
        entry = hist.get(url)
        if entry is None:
            hist[url] = {
                "found_at": today_iso,
                "first_source": r.get("source", ""),
            }
            r["found_at"] = today_iso
            r["newly_seen"] = True
        else:
            r["found_at"] = entry.get("found_at", today_iso)
            r["newly_seen"] = False
    return hist


def _is_negative(title: str) -> bool:
    tl = title.lower()
    return any(n in tl for n in NEGATIVE_TERMS)


def _is_negative_log(j: dict) -> bool:
    """Same as _is_negative() but records dropped rows to _DROP_LOG_TITLE.
    Use at the per-source iteration in run_scan(); skip for internal callers
    that just need a boolean (e.g. dedup helpers)."""
    title = j.get("title", "") or ""
    tl = title.lower()
    matched = [n for n in NEGATIVE_TERMS if n in tl]
    if not matched:
        return False
    _DROP_LOG_TITLE.append({
        "company": _current_company_ctx,
        "sector": _current_sector_ctx,
        "title": title,
        "link": j.get("link", ""),
        "location": j.get("location", ""),
        "source": j.get("source", ""),
        "matched_terms": ",".join(matched[:5]),
    })
    return True


# ---------------------------------------------------------------------------
# Dedup — collapse cross-source duplicates (Workday + LinkedIn posting the same role)
# ---------------------------------------------------------------------------
# Source preference when collapsing dupes. Workday JDs are richer + more stable.
# Phenom sits with the other "direct ATS" adapters (greenhouse/lever/SF) because
# its JD pages are a real server-rendered document, unlike LinkedIn card stubs.
# Without this entry, Phenom rows (e.g., the Citi Mississauga NTMR role) get
# rank=0 and lose every near-dup collision with a LinkedIn entry.
_SOURCE_PRIORITY = {"workday": 4, "greenhouse": 3, "lever": 3, "successfactors": 3,
                    "phenom": 3,
                    "linkedin_co": 2, "linkedin_co_gtaw": 2, "linkedin": 1,
                    "gmail_linkedin_alert": 1}


def _source_rank(src: str) -> int:
    if not src:
        return 0
    return _SOURCE_PRIORITY.get(src.split(":", 1)[0], 0)


def _normalize_title(title: str) -> str:
    """Canonical form for near-dup detection. Strips hints that don't change the job:
    hybrid/remote tags, trailing job IDs, Toronto location qualifiers, punctuation.
    Must match worklist.py:_normalize_title in lockstep."""
    t = (title or "").lower()
    # Remove trailing job IDs like "(4451)" or "(7557)"
    t = re.sub(r"\s*\(\s*\d{3,6}\s*\)\s*$", "", t)
    # Remove work-mode tags
    t = re.sub(r"\s*\((hybrid|remote|on[- ]?site|contract|temporary|permanent|full[- ]?time|part[- ]?time|\d+\s*month\s*contract)\)\s*",
               " ", t)
    # Strip location suffixes
    t = re.sub(r"[-–—,]\s*(toronto|ontario|gta|canada)[^a-z]*$", "", t)
    # Seniority/abbreviation expansions
    t = re.sub(r"\bsr\.?(?=\s|$)", "senior", t)
    t = re.sub(r"\bsnr(?=\s|$)", "senior", t)
    t = re.sub(r"\bvice[\s\-]+president\b", "vp", t)
    t = t.replace("&", "and")
    # Collapse punctuation/whitespace
    t = re.sub(r"[,/\-–—_]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def dedupe(jobs: list[dict]) -> tuple[list[dict], dict]:
    """Collapse dupes in two passes:
      (a) exact URL match — keep first occurrence
      (b) (company_lower, normalized_title) match — keep highest-source-rank entry
    Returns (deduped_list, stats_dict).
    """
    stats = {"input": len(jobs), "dropped_url": 0, "dropped_near": 0}
    by_url: dict[str, dict] = {}
    for j in jobs:
        link = j.get("link") or ""
        if not link:
            # Keep URL-less rows; they can't dedupe
            continue
        if link in by_url:
            stats["dropped_url"] += 1
            # Prefer the higher-rank source if we already have one
            if _source_rank(j.get("source", "")) > _source_rank(by_url[link].get("source", "")):
                by_url[link] = j
        else:
            by_url[link] = j
    deduped_url = list(by_url.values()) + [j for j in jobs if not j.get("link")]

    # Near-dup: same (company_lower, normalized_title) across different URLs.
    by_ct: dict[tuple, dict] = {}
    for j in deduped_url:
        key = (
            (j.get("company") or "").lower().strip(),
            _normalize_title(j.get("title", "")),
        )
        if not key[0] or not key[1]:
            by_ct[(id(j), "")] = j  # can't dedupe; keep unique
            continue
        if key in by_ct:
            stats["dropped_near"] += 1
            # Prefer higher-rank source
            if _source_rank(j.get("source", "")) > _source_rank(by_ct[key].get("source", "")):
                by_ct[key] = j
        else:
            by_ct[key] = j

    out = list(by_ct.values())
    stats["output"] = len(out)
    return out, stats


CHECKPOINT_PATH = OUT_DIR / "scan_checkpoint.json"
PAUSE_FLAG_PATH = OUT_DIR / "scan_pause.flag"


def _targets_signature(companies: list[dict]) -> str:
    """Stable hash of the target list so we detect "the user edited TARGETS
    after pausing" and refuse to resume from a stale checkpoint."""
    import hashlib
    names = sorted([c.get("name", "") for c in companies])
    return hashlib.sha1("|".join(names).encode("utf-8")).hexdigest()[:12]


def _load_checkpoint() -> dict | None:
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_checkpoint(state: dict):
    """Atomic write so a kill mid-checkpoint doesn't corrupt the file."""
    import os, tempfile
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(OUT_DIR), prefix=".scan_checkpoint.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, CHECKPOINT_PATH)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def _clear_checkpoint():
    try: CHECKPOINT_PATH.unlink()
    except FileNotFoundError: pass


def _pause_requested() -> bool:
    return PAUSE_FLAG_PATH.exists()


# ---------------------------------------------------------------------------
# Connectivity pre-flight & circuit breaker
# ---------------------------------------------------------------------------
_PREFLIGHT_URLS = [
    ("https://boards-api.greenhouse.io/v1/boards/test/jobs", "Greenhouse"),
    ("https://www.linkedin.com/robots.txt", "LinkedIn"),
]

_CIRCUIT_BREAKER_THRESHOLD = 5  # consecutive all-error companies before aborting


def _preflight_connectivity_check(skip_linkedin: bool = False) -> dict | None:
    """Quick HTTPS probe before scanning 159 companies.

    Returns None if connectivity is fine, or a dict describing the failure
    (suitable for inclusion in diagnostics/checkpoint)."""
    import ssl
    targets = _PREFLIGHT_URLS if not skip_linkedin else _PREFLIGHT_URLS[:1]
    ssl_failures = []
    for url, label in targets:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            # Any HTTP response (even 404) means SSL/network is fine
            return None
        except requests.exceptions.SSLError as e:
            ssl_failures.append((label, str(e)[:200]))
        except requests.exceptions.ConnectionError as e:
            if "SSL" in str(e) or "CERTIFICATE_VERIFY_FAILED" in str(e):
                ssl_failures.append((label, str(e)[:200]))
            else:
                # Non-SSL connection error (DNS, firewall) — still try next
                continue
        except Exception:
            continue
    if ssl_failures:
        return {
            "error": "ssl_blocked",
            "message": (
                "HTTPS connections are being intercepted (SSL certificate "
                "verification failed). This usually means a corporate VPN or "
                "proxy (Zscaler, Netskope, etc.) is doing SSL inspection. "
                "Disconnect from VPN and retry."
            ),
            "details": ssl_failures,
        }
    return None


def scan(companies, linkedin_only: bool = False, workday_only: bool = False,
         skip_linkedin: bool = False, resume: bool = False) -> tuple[list[dict], dict]:
    """Run the scan. Returns (candidates, diagnostics) where diagnostics lists
    companies that returned 0 candidates (for UI surfacing).

    Checkpoint + pause semantics:
      - After each company is processed we write a checkpoint with the list
        of completed company names and all accumulated results/diagnostics.
      - If automation/outputs/scan_pause.flag exists, we stop cleanly after
        the current company, leaving the checkpoint in place. The diagnostics
        dict carries state='paused' so callers know to defer downstream stages.
      - resume=True means: load the checkpoint, prime `found`/`per_company`
        from it, and skip any company already in the completed set. Target
        list must match (same companies, same order) — we detect divergence
        via a SHA1 of company names and refuse to resume mismatched runs.
    """
    # Reset the scan-wide LinkedIn throttle — even if the previous run
    # tripped it, we want to retry this run from clean state.
    _linkedin_throttle_reset()
    # Audit-pack drop logs are populated by `_keep_geo`/`_is_negative_log`
    # using these context strings; we update them per-company below.
    global _current_company_ctx, _current_sector_ctx
    _DROP_LOG_TITLE.clear()
    _DROP_LOG_GEO.clear()
    companies = list(companies)

    # -------- Connectivity pre-flight --------
    conn_err = _preflight_connectivity_check(skip_linkedin=skip_linkedin)
    if conn_err:
        print(f"[scan] ABORT: {conn_err['message']}", file=sys.stderr)
        return [], {"error": "connectivity_preflight_failed", **conn_err}

    # -------- Resume setup --------
    sig = _targets_signature(companies)
    completed: set[str] = set()
    found: list[dict] = []
    per_company: list[dict] = []

    if resume:
        ck = _load_checkpoint()
        if ck is None:
            print("[scan] --resume requested but no checkpoint found. "
                  "Starting a fresh scan.", file=sys.stderr)
        elif ck.get("targets_signature") != sig:
            print(f"[scan] Checkpoint signature mismatch (expected {sig}, got "
                  f"{ck.get('targets_signature')}). Target list changed since pause. "
                  "Delete scan_checkpoint.json to start fresh, or revert target "
                  "edits and retry.", file=sys.stderr)
            return [], {"error": "checkpoint_signature_mismatch",
                         "checkpoint_sig": ck.get("targets_signature"),
                         "current_sig": sig}
        else:
            completed = set(ck.get("completed", []))
            found = ck.get("found", [])
            per_company = ck.get("per_company", [])
            print(f"[scan] Resuming from checkpoint: "
                  f"{len(completed)}/{len(companies)} companies already done, "
                  f"{len(found)} candidates captured so far.",
                  file=sys.stderr)
            # Clear any leftover pause flag; the user's --resume is a positive
            # intent to continue, not to immediately pause again.
            try: PAUSE_FLAG_PATH.unlink()
            except FileNotFoundError: pass

    seen = load_tracker_urls()
    paused = False
    circuit_breaker_count = 0  # consecutive companies with zero results from ALL sources
    abort_reason: dict | None = None
    # TARGETS has shared Workday tenants (TD Bank + TD Asset Management both
    # use ("td","wd3","TD_Bank_Careers"); same for BMO). Without memoization
    # we issue every keyword query twice. Key on the validated 3-tuple form
    # so legacy 2-tuple specs don't accidentally collide.
    _wd_cache: dict[tuple, list[dict]] = {}
    for i, c in enumerate(companies, 1):
        # Skip already-completed companies on resume
        if c["name"] in completed:
            continue
        # Check for pause BEFORE starting the company so we don't waste work
        if _pause_requested():
            print(f"[scan] Pause flag detected at company {i}/{len(companies)} "
                  f"({c['name']}). Saving checkpoint and exiting.", file=sys.stderr)
            paused = True
            break
        print(f"[scan {i}/{len(companies)}] {c['name']} (sector: {c.get('sector', '—')})", file=sys.stderr)
        # Audit-pack attribution: filter wrappers read these to label drop rows.
        _current_company_ctx = c["name"]
        _current_sector_ctx = c.get("sector", "")
        before = len(found)
        sources_used = []

        # 1. Workday tenant (highest-signal when available)
        wd_count = 0
        if c.get("workday") and not linkedin_only:
            wd_before = len(found)
            wd_key = tuple(c["workday"]) if isinstance(c["workday"], (list, tuple)) else c["workday"]
            wd_jobs = _wd_cache.get(wd_key)
            if wd_jobs is None:
                wd_jobs = fetch_workday_jobs(c["workday"])
                _wd_cache[wd_key] = wd_jobs
            for src_j in wd_jobs:
                if src_j["link"] in seen:
                    continue
                if _is_negative_log(src_j):
                    continue
                # Shallow-copy so mutating company/sector for THIS company
                # doesn't overwrite the same fields when a sibling brand
                # (TD Bank vs TD Asset Management) reuses the same tenant.
                j = dict(src_j)
                j["company"] = c["name"]; j["sector"] = c.get("sector", "")
                found.append(j)
            wd_count = len(found) - wd_before
            if wd_count: sources_used.append(f"workday:{wd_count}")

        # 2. Greenhouse
        gh_count = 0
        if c.get("greenhouse") and not linkedin_only:
            gh_before = len(found)
            for j in fetch_greenhouse_jobs(c["greenhouse"]):
                if j["link"] in seen:
                    continue
                if _is_negative_log(j):
                    continue
                j["company"] = c["name"]; j["sector"] = c.get("sector", "")
                found.append(j)
            gh_count = len(found) - gh_before
            if gh_count: sources_used.append(f"greenhouse:{gh_count}")

        # 3. Lever
        lv_count = 0
        if c.get("lever") and not linkedin_only:
            lv_before = len(found)
            for j in fetch_lever_jobs(c["lever"]):
                if j["link"] in seen:
                    continue
                if _is_negative_log(j):
                    continue
                j["company"] = c["name"]; j["sector"] = c.get("sector", "")
                found.append(j)
            lv_count = len(found) - lv_before
            if lv_count: sources_used.append(f"lever:{lv_count}")

        # 3b. SuccessFactors RSS (BoC, CMHC, Moody's Corp, etc.)
        sf_count = 0
        if c.get("successfactors") and not linkedin_only:
            sf_before = len(found)
            for j in fetch_successfactors_jobs(c["successfactors"]):
                if j["link"] in seen:
                    continue
                if _is_negative_log(j):
                    continue
                j["company"] = c["name"]; j["sector"] = c.get("sector", "")
                found.append(j)
            sf_count = len(found) - sf_before
            if sf_count: sources_used.append(f"sf:{sf_count}")

        # 3c. Phenom (jobs.citi.com, jobs.rbc.com, etc.) — keyword-driven search
        ph_count = 0
        if c.get("phenom") and not linkedin_only:
            ph_before = len(found)
            tenant_name = c.get("name", "").lower().split()[0]
            for j in fetch_phenom_jobs(c["phenom"], tenant_name=tenant_name):
                if j["link"] in seen:
                    continue
                if _is_negative_log(j):
                    continue
                j["company"] = c["name"]; j["sector"] = c.get("sector", "")
                found.append(j)
            ph_count = len(found) - ph_before
            if ph_count: sources_used.append(f"phenom:{ph_count}")

        # 4. LinkedIn (breadth; paginated, multi-keyword + company-only fallback).
        li_count = 0
        if not workday_only and not skip_linkedin:
            li_before = len(found)
            for j in fetch_linkedin_jobs(c):
                if j["link"] in seen:
                    continue
                if _is_negative_log(j):
                    continue
                j["company"] = c["name"]; j["sector"] = c.get("sector", "")
                found.append(j)
            li_count = len(found) - li_before
            if li_count: sources_used.append(f"linkedin:{li_count}")

        added = len(found) - before
        per_company.append({
            "name": c["name"],
            "sector": c.get("sector", ""),
            "total": added,
            "workday": wd_count,
            "greenhouse": gh_count,
            "lever": lv_count,
            "successfactors": sf_count,
            "phenom": ph_count,
            "linkedin": li_count,
            "has_workday_config": bool(c.get("workday")),
            "has_greenhouse_config": bool(c.get("greenhouse")),
            "has_lever_config": bool(c.get("lever")),
            "has_successfactors_config": bool(c.get("successfactors")),
            "has_phenom_config": bool(c.get("phenom")),
        })
        print(f"  -> {added} new candidate(s) [{', '.join(sources_used) or 'none'}]",
              file=sys.stderr)

        # Circuit breaker: if many consecutive companies return 0 from all
        # configured sources, network is probably broken (VPN/proxy/SSL).
        has_any_source = (c.get("workday") or c.get("greenhouse") or
                          c.get("lever") or c.get("successfactors") or
                          c.get("phenom") or (not workday_only and not skip_linkedin))
        if added == 0 and has_any_source:
            circuit_breaker_count += 1
        else:
            circuit_breaker_count = 0

        if circuit_breaker_count >= _CIRCUIT_BREAKER_THRESHOLD:
            abort_reason = {
                "error": "circuit_breaker_tripped",
                "message": (
                    f"Aborted: {_CIRCUIT_BREAKER_THRESHOLD} consecutive companies "
                    f"returned 0 results from all sources. This typically means "
                    f"network connectivity is blocked (VPN/proxy/SSL inspection). "
                    f"Check your connection and retry."
                ),
                "failed_at_company": c["name"],
                "failed_at_index": i,
            }
            print(f"[scan] ABORT: {abort_reason['message']}", file=sys.stderr)
            break

        # Checkpoint AFTER finishing this company so a kill at any point
        # from this moment until the next company starts is safely resumable.
        completed.add(c["name"])
        try:
            _save_checkpoint({
                "targets_signature": sig,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "total_companies": len(companies),
                "completed": sorted(completed),
                "completed_count": len(completed),
                "found": found,
                "per_company": per_company,
                "options": {
                    "linkedin_only": linkedin_only,
                    "workday_only": workday_only,
                    "skip_linkedin": skip_linkedin,
                },
            })
        except Exception as ck_err:
            print(f"[scan] WARN: checkpoint save failed ({ck_err}); "
                  "scan continues but resume won't work if killed now.",
                  file=sys.stderr)

        time.sleep(0.75)

    diagnostics = {
        "per_company": per_company,
        "zero_result_companies": [c["name"] for c in per_company if c["total"] == 0],
        "linkedin_throttled": _linkedin_globally_throttled,
        "paused": paused,
        "aborted": abort_reason,
        "completed_count": len(completed),
        "total_companies": len(companies),
    }
    return found, diagnostics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", help="Scan only this company.")
    ap.add_argument("--sector", help="Scan only companies in this sector.")
    ap.add_argument("--linkedin-only", action="store_true")
    ap.add_argument("--workday-only", action="store_true",
                    help="Skip LinkedIn entirely; only query Workday APIs (fast, no throttling)")
    ap.add_argument("--expansion", action="store_true",
                    help="Also scan the expansion_companies list (Fairstone, ivari, MCAP, insurers, fintechs, regulators, etc.)")
    ap.add_argument("--expansion-only", action="store_true",
                    help="Scan ONLY the expansion_companies list")
    ap.add_argument("--gmail", action="store_true",
                    help="Harvest LinkedIn/Indeed job-alert emails from Gmail inbox "
                         "(last 14 days) and merge them into the scan. Read-only; "
                         "requires Gmail app password saved in ~/.applyagent/config.json.")
    ap.add_argument("--gmail-days", type=int, default=14,
                    help="How many days of Gmail alerts to harvest (default 14). "
                         "Only used with --gmail.")
    ap.add_argument("--resume", action="store_true",
                    help="Resume from the most recent scan_checkpoint.json "
                         "instead of starting a fresh scan. Skips companies "
                         "already completed; target list must match.")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load expansion list if requested
    try:
        from expansion_companies import EXPANSION_TARGETS
    except ImportError:
        EXPANSION_TARGETS = []
    if args.expansion_only:
        targets = list(EXPANSION_TARGETS)
    elif args.expansion:
        targets = list(TARGETS) + list(EXPANSION_TARGETS)
    else:
        targets = list(TARGETS)
    if args.company:
        targets = [t for t in targets if t["name"].lower() == args.company.lower()]
        if not targets:
            print(f"ERROR: company {args.company!r} not in target list", file=sys.stderr)
            return 1
    if args.sector:
        targets = [t for t in targets if args.sector.lower() in (t.get("sector") or "").lower()]
        if not targets:
            print(f"ERROR: no companies matched sector {args.sector!r}", file=sys.stderr)
            return 1

    # Permanent exclude-list (source-level block; distinct from triage
    # suppressions). Drop excluded companies by CANONICAL key BEFORE scan() so
    # their Workday tenant is never queried — even by an asset-management
    # sibling that shares it — and so _targets_signature reflects the filtered
    # set on both write and --resume. Identity no-op when nothing is excluded.
    try:
        import excludes  # type: ignore
    except ImportError:
        from . import excludes  # type: ignore
    _before_excl = len(targets)
    targets = excludes.filter_targets(targets)
    if len(targets) != _before_excl:
        print(f"[scan] exclude-list dropped {_before_excl - len(targets)} "
              f"target(s) before scan.", file=sys.stderr)
    if not targets:
        print("ERROR: every target is on the exclude-list — nothing to scrape.",
              file=sys.stderr)
        return 1

    raw, diagnostics = scan(targets, linkedin_only=args.linkedin_only,
                             workday_only=args.workday_only,
                             skip_linkedin=getattr(args, "skip_linkedin", False),
                             resume=args.resume)

    # Connectivity or circuit-breaker failure — abort with clear message.
    if diagnostics.get("error"):
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"SCAN FAILED: {diagnostics.get('message', diagnostics['error'])}",
              file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        return 1
    if diagnostics.get("aborted"):
        info = diagnostics["aborted"]
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"SCAN ABORTED: {info['message']}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        return 1

    # If the user paused mid-scan we stop here. The checkpoint file holds
    # everything we've captured so far; the scored/promote pipeline should
    # NOT run on a partial snapshot, so we exit with code 2 (distinct from
    # "success" 0 and "hard failure" 1) to signal "paused, resumable".
    if diagnostics.get("paused"):
        print(
            f"[scan] PAUSED at "
            f"{diagnostics.get('completed_count', 0)}/{diagnostics.get('total_companies', '?')}"
            f" companies. Checkpoint written to {CHECKPOINT_PATH.name}. "
            "Re-run with --resume to continue; or clear scan_pause.flag first "
            "if you launched the next run without --resume.",
            file=sys.stderr,
        )
        return 2

    # Optional: fold in Gmail-harvested LinkedIn alerts. Dedup below collapses
    # URL collisions with the web scan, so "seen in both" produces one row.
    gmail_diag = None
    if args.gmail:
        try:
            from gmail_reader import scrape_from_inbox  # type: ignore
            gmail_rows = scrape_from_inbox(days=args.gmail_days)
            # Drop alerts already in tracker + obvious negatives
            seen_tracker = load_tracker_urls()
            # Re-stamp audit context so gmail drops aren't attributed to
            # whichever company finished last in the per-company loop.
            global _current_company_ctx, _current_sector_ctx
            _current_company_ctx = "(gmail)"
            _current_sector_ctx = ""
            # Permanent exclude-list: drop alert rows whose company canonicalizes
            # to an excluded key (e.g. "RBC Capital Markets" → rbc). Snapshot
            # loaded once before the loop (the per-row is_excluded call is a
            # hot path). Same module the scrape-side filter uses.
            try:
                import excludes  # type: ignore
            except ImportError:
                from . import excludes  # type: ignore
            _excl = excludes.load()
            dropped_excluded = 0
            kept: list[dict] = []
            for g in gmail_rows:
                if not g.get("link"):
                    continue
                if g["link"] in seen_tracker:
                    continue
                if _is_negative_log(g):
                    continue
                if excludes.is_excluded(g.get("company"), _excl):
                    dropped_excluded += 1
                    continue
                # Attach minimal sector/company plumbing so downstream diagnostics work.
                # Company comes from the email; we can't sector it confidently here,
                # so leave sector blank — scoring uses title + JD, not sector.
                kept.append(g)
            raw.extend(kept)
            gmail_diag = {
                "fetched": len(gmail_rows),
                "kept": len(kept),
                "dropped_tracker_dup": sum(
                    1 for g in gmail_rows
                    if g.get("link") in seen_tracker
                ),
                "dropped_excluded": dropped_excluded,
            }
            print(f"[scan] Gmail: harvested {len(gmail_rows)} alert row(s), "
                  f"kept {len(kept)} (after tracker + negative-title + "
                  f"exclude-list filter; {dropped_excluded} excluded).",
                  file=sys.stderr)
        except Exception as e:
            print(f"[scan] Gmail harvest failed: {e}", file=sys.stderr)
            gmail_diag = {"error": str(e)[:200]}

    # Cross-source dedup: collapse same URL + same (company, normalized title).
    # Done post-scan so we can dedupe across companies too (rare but possible on LinkedIn).
    results, dedupe_stats = dedupe(raw)
    print(
        f"[scan] Dedup: {dedupe_stats['input']} raw -> {dedupe_stats['output']} unique "
        f"(-{dedupe_stats['dropped_url']} dup URL, -{dedupe_stats['dropped_near']} near-dup)",
        file=sys.stderr,
    )

    # Stamp found_at on every row (from history, or today if URL is new).
    hist = stamp_found_at(results)
    save_url_history(hist)
    newly_seen = sum(1 for r in results if r.get("newly_seen"))
    print(f"[scan] Freshness: {newly_seen} newly-seen URL(s), "
          f"{len(results) - newly_seen} previously seen.", file=sys.stderr)

    stamp = datetime.now().strftime("%Y%m%d")
    json_path = OUT_DIR / f"scan_{stamp}.json"
    md_path = OUT_DIR / f"scan_{stamp}.md"

    # Count companies actually reached + sector coverage for the report header.
    sector_counts: dict[str, int] = {}
    for r in results:
        s = r.get("sector", "Uncategorized")
        sector_counts[s] = sector_counts.get(s, 0) + 1

    if gmail_diag is not None:
        diagnostics["gmail"] = gmail_diag
    # Per-stage drop audit. Consumed by audit_pack.py for the xlsx export so
    # users can see WHICH titles/locations the scraper rejected and why
    # (matched_terms for title; raw location string for geo).
    filter_drops = {
        "title": list(_DROP_LOG_TITLE),
        "geo": list(_DROP_LOG_GEO),
    }
    json_path.write_text(
        json.dumps(
            {
                "scan_date": stamp,
                "companies_scanned": len(targets),
                "total_new_candidates": len(results),
                "dedup_stats": dedupe_stats,
                "by_sector": sector_counts,
                "diagnostics": diagnostics,
                "filter_drops": filter_drops,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if diagnostics.get("zero_result_companies"):
        print(
            f"[scan] WARN: {len(diagnostics['zero_result_companies'])} companies returned 0 results "
            f"(may need Workday config or LinkedIn fixes):",
            file=sys.stderr,
        )
        for n in diagnostics["zero_result_companies"][:20]:
            print(f"    - {n}", file=sys.stderr)

    md_lines = [
        f"# Scan {stamp}",
        "",
        f"- **Companies scanned:** {len(targets)}",
        f"- **Total new candidates:** {len(results)}",
        "",
        "## By sector",
        "",
        "| Sector | Candidates |",
        "|---|---|",
    ]
    for s, n in sorted(sector_counts.items(), key=lambda x: -x[1]):
        md_lines.append(f"| {s} | {n} |")
    md_lines += [
        "",
        "## Candidates",
        "",
        "| Sector | Company | Title | Location | Source | Link |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda r: (r.get("sector", ""), r.get("company", ""))):
        link = r.get("link", "")
        md_lines.append(
            f"| {r.get('sector', '')} | {r.get('company', '')} | {r.get('title', '')} | "
            f"{r.get('location', '')} | {r.get('source', '')} | [open]({link}) |"
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\n[scan] Wrote {json_path}")
    print(f"[scan] Wrote {md_path}")
    print(f"[scan] {len(results)} new candidates across {len(sector_counts)} sectors.")

    # Clean run finished — clear the checkpoint so a stray --resume on the
    # next invocation doesn't accidentally skip companies in a new scan.
    _clear_checkpoint()

    # Auto-rebuild worklist so the next score run sees these rows.
    # Every scrape OR Gmail fetch triggers a rebuild — the user never
    # has to remember to merge anything. See automation/worklist.py.
    #
    # We DO NOT propagate rebuild failures into the scrape's exit code:
    # the scrape produced a valid scan_*.json, that's its contract. But
    # we make the warning LOUD with traceback so a silent stale-worklist
    # state can't slip through unnoticed. Pipelines call rebuild() again
    # themselves so they're covered regardless.
    try:
        try:
            import worklist  # type: ignore
        except ImportError:
            from . import worklist  # type: ignore
        wstats = worklist.rebuild()
        print(f"[scan] worklist rebuilt: {wstats['total']} rows "
              f"({wstats['scrape']} scrape, {wstats['gmail']} gmail, "
              f"{wstats['both']} both)")
    except Exception as e:
        import traceback
        print(f"[scan] ⚠⚠ WORKLIST REBUILD FAILED — scrape itself "
              f"succeeded but worklist.json is stale. Run "
              f"`python automation/worklist.py` to retry manually.\n"
              f"      {type(e).__name__}: {e}",
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
