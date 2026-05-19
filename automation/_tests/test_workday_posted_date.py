"""Workday's JSON API returns postedOn as relative strings like "Posted 6 Days
Ago" / "Posted Today" / "Posted Yesterday" / "Posted 30+ Days Ago", not ISO
dates. Audit found ~309/1,137 worklist rows had non-ISO posted_date for this
reason; downstream [:10] slicing produced garbage. Verify _normalize_workday_posted
collapses them to ISO YYYY-MM-DD."""
from __future__ import annotations
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jd_scraper import _normalize_workday_posted  # type: ignore


def _expect(actual, expected, label):
    assert actual == expected, f"{label}: expected {expected!r}, got {actual!r}"
    print(f"  OK  {label}: {actual!r}")


def main() -> int:
    fixed = date(2026, 5, 19)
    cases = [
        ("Posted Today",           fixed.isoformat()),
        ("Posted Yesterday",       (fixed - timedelta(days=1)).isoformat()),
        ("posted 1 day ago",       (fixed - timedelta(days=1)).isoformat()),
        ("Posted 6 Days Ago",      (fixed - timedelta(days=6)).isoformat()),
        ("Posted 30+ Days Ago",    (fixed - timedelta(days=30)).isoformat()),
        ("2026-05-12",             "2026-05-12"),
        ("2026-05-12T00:00:00Z",   "2026-05-12T00:00:00Z"),
        ("",                       ""),
        (None,                     ""),
        ("garbage",                ""),
        # Weeks / months coverage
        ("Posted 1 Week Ago",      (fixed - timedelta(days=7)).isoformat()),
        ("Posted 2 Weeks Ago",     (fixed - timedelta(days=14)).isoformat()),
        ("Posted 1 Month Ago",     (fixed - timedelta(days=30)).isoformat()),
        ("Posted 2 Months Ago",    (fixed - timedelta(days=60)).isoformat()),
        ("Posted 30+ Months Ago",  (fixed - timedelta(days=900)).isoformat()),
        # Whitespace / case variants
        ("  POSTED TODAY  ",       fixed.isoformat()),
        ("posted   6   days   ago", (fixed - timedelta(days=6)).isoformat()),
    ]
    print("=" * 60)
    print("workday posted_date normalization")
    print("=" * 60)
    for raw, expected in cases:
        got = _normalize_workday_posted(raw, today=fixed)
        _expect(got, expected, repr(raw))
    print()
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
