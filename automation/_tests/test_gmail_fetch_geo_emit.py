"""Test gmail_fetch.py geo-filter emit shape (no real IMAP).

Approach: simulate the `raw_rows` step + the geo gate + diagnostics
construction, mirroring gmail_fetch.main()'s logic without IMAP.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from location_filter import keep_for_toronto_pipeline  # type: ignore

PASS = 0
FAIL = 0
FAILS: list[str] = []


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL [{label}] {detail}")


def simulate_geo(raw_rows: list[dict]) -> tuple[list[dict], list[str], int]:
    """Mirror gmail_fetch.main() geo-gate block."""
    rows = []
    dropped_loc_examples: list[str] = []
    for row in raw_rows:
        if keep_for_toronto_pipeline(row.get("location") or ""):
            rows.append(row)
        elif len(dropped_loc_examples) < 5:
            dropped_loc_examples.append(
                f"{row.get('company', '?')} - {row.get('location', '?')}"
            )
    rows_dropped_location = len(raw_rows) - len(rows)
    return rows, dropped_loc_examples, rows_dropped_location


# 1. Mixed: GTA + non-GTA + empty
raw = [
    {"company": "BMO", "location": "Toronto, ON"},
    {"company": "RBC", "location": "Mississauga, ON"},
    {"company": "Deloitte", "location": "Raleigh, NC"},
    {"company": "Cathay Bank", "location": "El Monte, CA"},
    {"company": "Foo", "location": ""},  # empty stays
    {"company": "Bar", "location": None},  # None stays
    {"company": "Vancouver Co", "location": "Vancouver, BC"},
]
rows, ex, dropped = simulate_geo(raw)
check("kept GTA+empty rows", len(rows) == 4,
      detail=f"got {len(rows)} kept (expected 4: BMO, RBC, Foo, Bar)")
check("dropped count = 3", dropped == 3, detail=f"got {dropped}")
check("dropped examples truncated to 5", len(ex) <= 5, detail=f"got {len(ex)}")
check("dropped contains Raleigh", any("Raleigh" in s for s in ex), detail=str(ex))
check("dropped contains Vancouver", any("Vancouver" in s for s in ex), detail=str(ex))
check("dropped count == raw - kept", dropped == len(raw) - len(rows))

# 2. All non-GTA
raw = [
    {"company": "A", "location": "New York, NY"},
    {"company": "B", "location": "Chicago, IL"},
    {"company": "C", "location": "Vancouver, BC"},
    {"company": "D", "location": "Ottawa, ON"},
]
rows, ex, dropped = simulate_geo(raw)
check("all non-GTA dropped", dropped == 4)
check("ex caps at 5 (not 4)", len(ex) == 4, detail=f"got {len(ex)}")
check("kept = 0", rows == [])

# 3. >5 drops, examples capped at 5
raw = [{"company": str(i), "location": "Raleigh, NC"} for i in range(10)]
rows, ex, dropped = simulate_geo(raw)
check("10 drops, all non-GTA", dropped == 10)
check("examples capped at 5", len(ex) == 5, detail=f"got {len(ex)}")

# 4. All empty location → all kept
raw = [{"company": str(i), "location": ""} for i in range(5)]
rows, ex, dropped = simulate_geo(raw)
check("all empty kept", len(rows) == 5)
check("no examples", ex == [])
check("zero dropped", dropped == 0)

# 5. No location field at all (KeyError tolerance)
raw = [{"company": "A"}]  # no 'location' key
rows, ex, dropped = simulate_geo(raw)
check("missing location key → kept (empty falsy)", len(rows) == 1)

# 6. Real-world contaminated rows from scan_gmail_20260518_203733.json:
#   pre-cleanup, location is "Connor, Clark & Lunn ... Vancouver, BC (Hybrid)"
raw = [
    {"company": "Senior Manager, Operations Risk",
     "location": "Connor, Clark & Lunn Financial Group (CC&L) · Vancouver, BC (Hybrid)"},
    {"company": "Senior Manager, Operations Risk",
     "location": "Connor, Clark & Lunn Financial Group (CC&L) · Toronto, ON (On-site)"},
]
rows, ex, dropped = simulate_geo(raw)
# These rows will pre-cleanup KEEP both (Vancouver string contains Toronto?
# NO. But 'vancouver' substring is in first → drop. 'toronto' in second → keep)
check("contaminated Vancouver-laden loc dropped (substring match)",
      dropped == 1, detail=f"got dropped={dropped}, ex={ex}")
# This shows the geo gate works on MOJIBAKE'd / CONTAMINATED location strings
# only because of substring matching. Risk: a string containing both city
# names — e.g. 'Toronto and Vancouver hybrid' — would FALSE-KEEP because
# 'toronto' is the GTA city check.

# 7. Risk case: location has both GTA + non-GTA city names
raw = [
    {"company": "X", "location": "Toronto, ON / Vancouver, BC"},
    {"company": "Y", "location": "Vancouver / Toronto - hybrid"},
]
rows, ex, dropped = simulate_geo(raw)
check("ambiguous: dual-city kept (Toronto substring wins)",
      len(rows) == 2, detail=f"got {len(rows)}; ex={ex}")
# This is a FALSE KEEP risk for ambiguous postings.

# Summary
print(f"\n{PASS} pass / {FAIL} fail")
for f in FAILS:
    print(f)
sys.exit(0 if FAIL == 0 else 1)
