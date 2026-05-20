"""Test scan_delta._is_web_scrape correctly excludes non-scrape artifacts.

Run: python automation/_tests/test_scan_delta_filter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "automation"))

from scan_delta import _is_web_scrape  # type: ignore

PASS = FAIL = 0
FAILS: list[str] = []


def check(filename: str, expected: bool, label: str = ""):
    global PASS, FAIL
    p = Path(filename)
    got = _is_web_scrape(p)
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL _is_web_scrape({filename!r}): got {got}, expected {expected} [{label}]")


# Web scrapes — KEEP
check("scan_20260519.json", True, "normal daily scan")
check("scan_20260518.json", True, "prior day scan")
check("scan_20260510.json", True, "older scan")

# Gmail harvests — EXCLUDE
check("scan_gmail_20260519.json", False, "gmail harvest")
check("scan_gmail_20260517.json", False, "gmail harvest older")

# Base / checkpoint / merged — EXCLUDE
check("scan_base_20260501.json", False, "base scan")
check("scan_checkpoint_20260515.json", False, "checkpoint")
check("scan_20260519_merged.json", False, "merged scan")
check("working_set_20260519.json", False, "working set")
check("gmail_pool_20260519.json", False, "gmail pool")

# Scored — EXCLUDE (different pipeline artifact)
check("scan_20260519_scored.json", False, "scored output")
check("scan_gmail_20260519_scored.json", False, "gmail scored")

print(f"\n{PASS} pass / {FAIL} fail")
for f in FAILS:
    print(f)
sys.exit(0 if FAIL == 0 else 1)
