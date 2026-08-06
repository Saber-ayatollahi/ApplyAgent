"""lane_tagger.py — Tag each scraped job with the strategy *lane* it serves.

Maps a row's (sector, title) to one of the job-search lanes from the master
plan (docs/Job_Search_Master_Plan.md) so the triage report and dashboard can
group roles by *where they belong* in the strategy, not just by sector.

Logic (deterministic, stdlib-only):
  1. Title-based override first — a Solutions-Engineering title routes to
     Lane A even at a bank or pension (an SE role is an SE role anywhere).
  2. Otherwise fall back to the company's sector.

Lanes:
  A · Solutions Engineering      — vendor-platform / SE / client-solutions (Spearhead A)
  B · Pension / Buy-Side         — pensions, asset managers, hedge funds (Spearhead B)
  Floor · Bank Risk/ALM/Val      — banks + insurers (reliable floor)
  Side · Fintech                 — fintech / non-bank lenders (USD/remote side-track)
  Opportunistic                  — consulting, regulators, custody, anything else

Usage:
    from lane_tagger import lane_for, tag_rows
    row["lane"] = lane_for(row.get("sector"), row.get("title"))
    tag_rows(results)        # adds "lane" to every dict in place
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

# ── Lane labels ────────────────────────────────────────────────────────────
LANE_A = "A · Solutions Engineering"
LANE_B = "B · Pension / Buy-Side"
LANE_FLOOR = "Floor · Bank Risk/ALM/Validation"
LANE_SIDE = "Side · Fintech"
LANE_OPP = "Opportunistic"

# ── Sector → lane (defaults; title overrides can move a row to Lane A) ──────
SECTOR_TO_LANE = {
    # Spearhead A — vendor-platform / solutions engineering
    "Analytics & Risk Vendors": LANE_A,
    "Market Infrastructure": LANE_A,
    # Spearhead B — pension / buy-side investment & total-fund risk
    "Canadian Pension Funds": LANE_B,
    "Canadian Asset Managers": LANE_B,
    "US & Global Asset Managers": LANE_B,
    "Hedge Funds / Alt AM": LANE_B,
    "Private Credit": LANE_B,
    # Floor — banks + insurers
    "Canadian Big 6 Banks": LANE_FLOOR,
    "Mid Canadian Banks": LANE_FLOOR,
    "US Banks (Toronto)": LANE_FLOOR,
    "Canadian Insurers": LANE_FLOOR,
    # Side-track — fintech / lenders (USD / remote)
    "Fintech": LANE_SIDE,
    "Non-Bank Lenders": LANE_SIDE,
    "Mortgage Lenders": LANE_SIDE,
    # Opportunistic — consulting, regulators, custody
    "Big 4 Risk Advisory": LANE_OPP,
    "Pension/ALM Consulting": LANE_OPP,
    "FS Strategy Consulting": LANE_OPP,
    "Regulators & Crown": LANE_OPP,
    "Fund Admin/Custody": LANE_OPP,
}

# ── Title override → Lane A (Solutions Engineering roles, found anywhere) ───
_SE_TITLE_RE = re.compile(
    r"\b("
    r"solutions?\s+engineer|solutions?\s+architect|solutions?\s+consultant|"
    r"pre[-\s]?sales|sales\s+engineer|"
    r"client\s+engagement|client\s+experience|client\s+solutions|"
    r"implementation(\s+consultant|\s+specialist|\s+manager)?|"
    r"professional\s+services|technical\s+account|"
    r"product\s+specialist|platform\s+specialist|aladdin"
    r")\b",
    re.IGNORECASE,
)


def lane_for(sector: str | None, title: str | None = "") -> str:
    """Return the strategy lane for a row, given its sector and (optional) title."""
    t = (title or "").strip()
    if t and _SE_TITLE_RE.search(t):
        return LANE_A
    s = (sector or "").strip()
    return SECTOR_TO_LANE.get(s, LANE_OPP)


def tag_rows(rows: Iterable[dict]) -> Counter:
    """Add a 'lane' key to every row dict in place. Returns a lane→count Counter."""
    counts: Counter = Counter()
    for r in rows:
        lane = lane_for(r.get("sector"), r.get("title"))
        r["lane"] = lane
        counts[lane] += 1
    return counts


# Stable display order for reports/dashboards.
LANE_ORDER = [LANE_A, LANE_B, LANE_FLOOR, LANE_SIDE, LANE_OPP]


if __name__ == "__main__":
    samples = [
        ("Analytics & Risk Vendors", "Senior Solutions Engineer"),
        ("Canadian Big 6 Banks", "VP, Solutions Engineering (Aladdin)"),  # title wins -> A
        ("Canadian Pension Funds", "Director, Total Fund Risk"),
        ("Canadian Big 6 Banks", "Manager, Model Validation"),
        ("Fintech", "Model Risk Manager"),
        ("Big 4 Risk Advisory", "Senior Manager, Quantitative Market Risk"),
        ("US & Global Asset Managers", "Director, Investment Risk"),
        ("US & Global Asset Managers", "Aladdin Client Engagement Lead"),  # title wins -> A
    ]
    for sec, title in samples:
        print(f"{lane_for(sec, title):34s} <- [{sec}] {title}")
