"""Test _clean_alert_fields() — failure modes A/B/C/D + idempotency + edges.

Standalone (no pytest). Run: python automation/_tests/test_clean_alert_fields.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gmail_reader import _clean_alert_fields  # type: ignore


PASS = 0
FAIL = 0
FAILS: list[str] = []


def check(label, got, expected):
    global PASS, FAIL
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL [{label}]\n  got      = {got!r}\n  expected = {expected!r}")


# -----------------------------------------------------------------------------
# Mode A — activity tail in title
# -----------------------------------------------------------------------------
# Pure trailing "Actively recruiting" on title should be stripped.
t, c, l = _clean_alert_fields("Senior Risk Analyst Actively recruiting", "BMO", "Toronto, ON")
check("A1 title=role+Actively recruiting", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Trailing "23 connections"
t, c, l = _clean_alert_fields("Senior Risk Analyst 23 connections", "BMO", "Toronto, ON")
check("A2 title=role+N connections", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Trailing "Promoted"
t, c, l = _clean_alert_fields("Senior Risk Analyst Promoted", "BMO", "Toronto, ON")
check("A3 title=role+Promoted", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Trailing on COMPANY
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO Actively recruiting", "Toronto, ON")
check("A4 company=co+activity", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Trailing on LOCATION
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "Toronto, ON Actively recruiting")
check("A5 location=loc+activity", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# BARE — location IS just activity text → blank
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "23 connections")
check("A6 location BARE = '23 connections'", (t, c, l),
      ("Senior Risk Analyst", "BMO", ""))

t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "Actively recruiting")
check("A7 location BARE = 'Actively recruiting'", (t, c, l),
      ("Senior Risk Analyst", "BMO", ""))

# -----------------------------------------------------------------------------
# Mode B — separator mojibake / dot in `company`
# -----------------------------------------------------------------------------
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO · Toronto, ON", "")
check("B1 company='BMO · Toronto, ON' empty loc", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Mojibake replacement char
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO � Toronto, ON", "")
check("B2 company='BMO U+FFFD Toronto, ON'", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# em-dash / en-dash / hyphen variants in company
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO — Toronto, ON", "")
check("B3 company='BMO em-dash Toronto'", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO - Toronto, ON", "")
check("B4 company='BMO - Toronto'", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Existing location should NOT be overwritten by split
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO · Mississauga, ON", "Toronto, ON")
check("B5 prefer existing location", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# Split also strips mode tail from new_loc
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO · Toronto, ON (Hybrid)", "")
check("B6 split + mode-tail removed", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# -----------------------------------------------------------------------------
# Mode C — title-company echo (title contains separator)
# -----------------------------------------------------------------------------
t, c, l = _clean_alert_fields("BMO · Senior Risk Analyst", "BMO", "Toronto, ON")
check("C1 title='BMO · Sr Analyst'", (t, c, l),
      ("BMO", "BMO", "Toronto, ON"))
# Note: the regex splits at first separator; left side "BMO" becomes title.
# This matches what the code DOES, but it's NOT ideal — see Bugs section.

# Title with role+separator+company echo trailing
t, c, l = _clean_alert_fields("Senior Risk Analyst · BMO · Toronto, ON",
                               "BMO", "Toronto, ON")
check("C2 title='Sr Analyst · BMO · ...'", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# -----------------------------------------------------------------------------
# Mode D — per code comments mode D is "title ends with company name redundantly"
# (i.e. "Treasury Manager KOHO" → "Treasury Manager"). Mode-tail "(Hybrid)" /
# "(On-site)" is a SEPARATE strip applied to LOCATION at the end.
# -----------------------------------------------------------------------------
t, c, l = _clean_alert_fields("Treasury Manager KOHO", "KOHO", "Canada")
check("D1 title ends with company", (t, c, l),
      ("Treasury Manager", "KOHO", "Canada"))

# Case-insensitive
t, c, l = _clean_alert_fields("Treasury Manager koho", "KOHO", "Canada")
check("D2 case-insensitive company tail", (t, c, l),
      ("Treasury Manager", "KOHO", "Canada"))

# Company too short — should NOT strip (3-char minimum guard)
t, c, l = _clean_alert_fields("Director Risk TD", "TD", "Toronto, ON")
check("D3 short company (2 chars) — no strip", (t, c, l),
      ("Director Risk TD", "TD", "Toronto, ON"))

# Mode-tail on location: "(Hybrid)" / "(On-site)" / "(Remote)" stripped
t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "Toronto, ON (Hybrid)")
check("Mode-tail Hybrid", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "Toronto, ON (On-site)")
check("Mode-tail On-site", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "Toronto, ON (Onsite)")
check("Mode-tail Onsite (no hyphen)", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

t, c, l = _clean_alert_fields("Senior Risk Analyst", "BMO", "Toronto, ON (Remote)")
check("Mode-tail Remote", (t, c, l),
      ("Senior Risk Analyst", "BMO", "Toronto, ON"))

# -----------------------------------------------------------------------------
# Idempotency
# -----------------------------------------------------------------------------
inputs = [
    ("Senior Risk Analyst Actively recruiting", "BMO · Toronto, ON", ""),
    ("Treasury Manager KOHO", "KOHO", "Canada (Remote)"),
    ("Head, North American Provisioning & Risk Analytics BMO · Toronto, ON Actively recruiting",
     "BMO · Toronto, ON", "Actively recruiting"),
    ("Senior Manager, International Banking Treasury Scotiabank · Toronto, ON 23 connections",
     "Scotiabank · Toronto, ON", "23 connections"),
    ("Senior Manager, Operations Risk Connor, Clark & Lunn Financial Group (CC&L) · Toronto, ON (On-site) Actively recruiting",
     "Senior Manager, Operations Risk", ""),
]
for i, (t0, c0, l0) in enumerate(inputs):
    once = _clean_alert_fields(t0, c0, l0)
    twice = _clean_alert_fields(*once)
    check(f"Idempotency #{i}", twice, once)

# -----------------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------------
check("Edge empty all", _clean_alert_fields("", "", ""), ("", "", ""))

check("Edge whitespace only",
      _clean_alert_fields("   ", "  ", " "), ("", "", ""))

check("Edge title==company",
      _clean_alert_fields("BMO", "BMO", "Toronto, ON"),
      ("BMO", "BMO", "Toronto, ON"))

check("Edge None handling title",
      _clean_alert_fields(None, "BMO", "Toronto, ON"),  # type: ignore
      ("", "BMO", "Toronto, ON"))

check("Edge None handling all",
      _clean_alert_fields(None, None, None),  # type: ignore
      ("", "", ""))

# Unicode in body
t, c, l = _clean_alert_fields(
    "Senior é Manager, Opérations Risk Actively recruiting",
    "BMO", "Montréal, QC")
check("Unicode in title (e-acute)", (t, c, l),
      ("Senior é Manager, Opérations Risk", "BMO", "Montréal, QC"))

# Length truncation
long_title = "A" * 250
t, c, l = _clean_alert_fields(long_title, "BMO", "Toronto, ON")
check("Length cap 180 on title", len(t), 180)

long_co = "B" * 250
t, c, l = _clean_alert_fields("Foo", long_co, "Toronto, ON")
check("Length cap 120 on company", len(c), 120)

long_loc = "C" * 250
t, c, l = _clean_alert_fields("Foo", "BMO", long_loc)
check("Length cap 120 on location", len(l), 120)

# Real-world example from the contaminated scan_gmail_20260518_203733.json
t, c, l = _clean_alert_fields(
    "Treasury Manager KOHO · Canada (Remote) 8 school alumni",
    "Treasury Manager",
    "KOHO · Canada (Remote)")
check("Real corrupt #1 (Treasury Manager / KOHO)",
      (t, c, l),
      ("Treasury Manager KOHO", "Treasury Manager", "Canada"))

# Real-world #2: title contaminated, location is activity
t, c, l = _clean_alert_fields(
    "Head, North American Provisioning & Risk Analytics BMO · Toronto, ON Actively recruiting",
    "BMO · Toronto, ON",
    "Actively recruiting",
)
check("Real corrupt #2 (BMO Provisioning Lead)",
      (t, c, l),
      ("Head, North American Provisioning & Risk Analytics", "BMO", "Toronto, ON"))

# Real-world #3: Vancouver row should still be CLEANED (geo gate is downstream)
t, c, l = _clean_alert_fields(
    "Senior Manager, Operations Risk Connor, Clark & Lunn Financial Group (CC&L) · Vancouver, BC (Hybrid) Actively recruiting",
    "Senior Manager, Operations Risk",
    "Connor, Clark & Lunn Financial Group (CC&L) · Vancouver, BC (Hybrid)")
check("Real corrupt #3 (Vancouver, BC, mode D no match)",
      (t, c, l),
      ("Senior Manager, Operations Risk Connor, Clark & Lunn Financial Group (CC&L)",
       "Senior Manager, Operations Risk", "Vancouver, BC"))


# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
print(f"\n{PASS} pass / {FAIL} fail")
for f in FAILS:
    print(f)


def test_all_checks_pass():
    """Pytest entrypoint. The checks above run at import time and accumulate
    into the module-level FAIL counter; assert none failed so this file is a
    real pytest test rather than a collection-aborting standalone script."""
    assert FAIL == 0, "\n".join(FAILS)


if __name__ == "__main__":
    sys.exit(0 if FAIL == 0 else 1)
