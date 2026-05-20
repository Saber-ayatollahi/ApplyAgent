"""Test keep_for_toronto_pipeline + is_gta_or_canada_remote.

Standalone (no pytest). Run: python automation/_tests/test_location_filter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from location_filter import is_gta_or_canada_remote, keep_for_toronto_pipeline  # type: ignore

PASS = 0
FAIL = 0
FAILS: list[str] = []


def check_keep(loc, expected, label=""):
    global PASS, FAIL
    got = keep_for_toronto_pipeline(loc)
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL keep_for_toronto_pipeline({loc!r}) — got {got}, expected {expected} [{label}]")


def check_gta(loc, expected, label=""):
    global PASS, FAIL
    got = is_gta_or_canada_remote(loc)
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL is_gta_or_canada_remote({loc!r}) — got {got}, expected {expected} [{label}]")


# ----- KEEP cases (all GTA + Canada-remote variants) -----
check_keep("Toronto, ON", True, "Toronto plain")
check_keep("Toronto", True, "Toronto plain (no province)")
check_keep("Greater Toronto Area", True, "GTA spelled out")
check_keep("Mississauga, ON", True, "Mississauga (905)")
check_keep("Markham, ON", True, "Markham")
check_keep("Vaughan, ON", True, "Vaughan")
check_keep("Brampton, ON", True, "Brampton")
check_keep("Oakville, ON", True, "Oakville")
check_keep("Burlington, ON", True, "Burlington")
check_keep("Milton, ON", True, "Milton")
check_keep("Richmond Hill, ON", True, "Richmond Hill")
check_keep("Pickering, ON", True, "Pickering")
check_keep("Ajax, ON", True, "Ajax")
check_keep("Whitby, ON", True, "Whitby")
check_keep("Oshawa, ON", True, "Oshawa")
check_keep("North York, ON", True, "North York")
check_keep("Scarborough, ON", True, "Scarborough")
check_keep("Etobicoke, ON", True, "Etobicoke")
check_keep("Thornhill, ON", True, "Thornhill")
check_keep("Concord, ON", True, "Concord")
check_keep("Woodbridge, ON", True, "Woodbridge")
check_keep("Aurora, ON", True, "Aurora")
check_keep("Newmarket, ON", True, "Newmarket")
check_keep("Stouffville, ON", True, "Stouffville")
check_keep("Waterloo, ON", True, "Waterloo (SW Ontario)")
check_keep("Kitchener, ON", True, "Kitchener (SW Ontario)")
check_keep("Remote, Canada", True, "Remote, Canada")
check_keep("Remote - Canada", True, "Remote - Canada")
check_keep("Canada - Remote", True, "Canada - Remote")
check_keep("Canada (Remote)", True, "Canada (Remote)")  # spec edge
check_keep("Canada", True, "Canada bare")
check_keep("CA", True, "CA two-letter")  # currently treats "CA" as Canada
check_keep("", True, "Empty (let scorer decide)")
check_keep("   ", True, "Whitespace (let scorer decide)")
check_keep(None, True, "None (let scorer decide)")  # type: ignore
check_keep("Remote", True, "Remote no country (kept)")

# ----- DROP cases -----
check_keep("New York, NY", False, "NY drop")
check_keep("Raleigh, NC", False, "Raleigh drop")
check_keep("San Francisco, CA", False, "SF (state CA, not country) drop?")
# WARNING: "CA" check — loc.lower() = "san francisco, ca". The current code
# ALSO matches loc_lower.strip() == "ca" (only the EXACT bare "ca") so SF
# should drop. But the substring "canada" is not in there, so OK. Let's see.
check_keep("Vancouver, BC", False, "Vancouver drop (BC, not GTA)")
check_keep("Montreal, QC", False, "Montreal drop")
check_keep("Ottawa, ON", False, "Ottawa drop (Ontario but not GTA)")
check_keep("Calgary, AB", False, "Calgary drop")
check_keep("Halifax, NS", False, "Halifax drop")
check_keep("United States", False, "United States drop")
check_keep("Chicago, IL", False, "Chicago drop")
check_keep("London, UK", False, "London UK drop")
check_keep("El Monte, CA", False, "El Monte CA (US state) drop")
# WARNING: "El Monte, CA" — the bare-"ca" check is on STRIP whole string,
# so substring "ca" should NOT match. Good. But let me check.

# ----- is_gta_or_canada_remote direct -----
check_gta("Toronto, ON", True, "Toronto direct")
check_gta("Mississauga, ON", True, "Mississauga direct")
check_gta("Vancouver, BC", False, "Vancouver direct false")
check_gta("Ottawa, ON", False, "Ottawa direct false")
check_gta("", False, "Empty is_gta = False")  # but keep wraps to True
check_gta(None, False, "None is_gta = False")  # type: ignore
check_gta("Canada", True, "Canada direct true")
check_gta("CA", True, "CA bare direct true")
check_gta("ca", True, "ca lowercase bare direct")
check_gta("San Francisco, CA", False, "SF not bare ca")
check_gta("REMOTE, CANADA", True, "REMOTE, CANADA case")
check_gta("Greater Toronto Area", True, "GTA phrase")

# ----- Edge: weird input types -----
def safe_call(fn, val, label):
    global PASS, FAIL
    try:
        fn(val)
        PASS += 1
    except Exception as e:
        FAIL += 1
        FAILS.append(f"FAIL {label} ({fn.__name__}({val!r})) raised: {type(e).__name__}: {e}")

safe_call(keep_for_toronto_pipeline, None, "keep(None)")
safe_call(keep_for_toronto_pipeline, [], "keep([])")
safe_call(keep_for_toronto_pipeline, {}, "keep({})")
safe_call(keep_for_toronto_pipeline, 42, "keep(42)")

safe_call(is_gta_or_canada_remote, None, "is_gta(None)")
safe_call(is_gta_or_canada_remote, [], "is_gta([])")
safe_call(is_gta_or_canada_remote, {}, "is_gta({})")
safe_call(is_gta_or_canada_remote, 42, "is_gta(42)")

# ----- Subtle false-keep: a US city named after Canada? -----
# "Canada, KY" (real place) — loc_lower = "canada, ky" → contains "canada" but
# NOT "remote - canada" / "remote, canada" / equals "canada" / "ca". Let's see.
check_gta("Canada, KY", False, "Canada KY US city (potential false keep)")
# Actually the code checks: loc_lower.strip() == "canada" — "canada, ky" != "canada", so False. Good.

# What about "Toronto, OH" (real US city)?
check_gta("Toronto, OH", False, "Toronto OH US namesake correctly rejected")
# US-state-suffix guard rejects GTA-namesake US towns.

# What about "London, ON" (real Ontario city, not GTA but commute distance)?
check_gta("London, ON", False, "London ON not in GTA list")
# Currently false; no London in _GTA_CITIES. But — "london, on" doesn't contain "kitchener" etc.
# Worth flagging that London ON is excluded but Waterloo is included.

# Mojibake-laden input
check_gta("Toronto � ON", True, "Mojibake'd Toronto still parses")
check_gta("Mississauga � ON (Hybrid)", True, "Mojibake'd + mode tail")

# Multi-line (LinkedIn sometimes)
check_gta("Toronto, ON\n(Hybrid)", True, "newline embedded")

# ----- False-positive guards (HIGH-1: loose canada+remote substring leak) -----
check_keep("Canada Goose Inc - Remote office in Texas, USA", False, "company name 'Canada' + remote elsewhere")
check_keep("Remote — must reside in CA, not Canada", False, "explicit Canada negation")
check_keep("United States Remote (Canada too)", False, "US-primary, Canada-also")
check_keep("Toronto-Dominion Canada Square, London", False, "Canada Square is a UK street")

# ----- Order-of-clauses (HIGH-2: US-state suffix shouldn't poison legit GTA match) -----
check_gta("Toronto, OH / Remote, Canada", True, "OH namesake but offers Canada remote")
check_gta("New York, NY or Toronto, ON", True, "multi-city: NY suffix shouldn't nuke Toronto, ON")
check_gta("Hybrid - Toronto, ON or Remote Canada", True, "hybrid phrasing")

# ----- Word-boundary (LOW-3: 'milton' substring leak via 'hamilton') -----
check_gta("Hamilton, OH", False, "Hamilton OH should drop (no longer rescued by 'milton' substring)")
# NOTE: Hamilton, ON now correctly drops — it's not in _GTA_CITIES; commute distance from Toronto.
# Only flag if you want to add Hamilton explicitly to _GTA_CITIES.
check_gta("Hamilton, ON", False, "Hamilton ON now correctly drops (not in _GTA_CITIES)")

# ----- Real LinkedIn formats -----
check_gta("Greater Toronto Area (Remote)", True, "GTA phrase + remote modifier")
check_gta("Toronto, ON / Remote", True, "GTA + remote slash")
check_gta("Montreal, QC (Remote possible)", False, "Montreal — out of region even if remote")
check_keep("Anywhere", True, "Anywhere — let scorer decide")
check_keep("Remote (Anywhere)", True, "Remote anywhere — let scorer decide")

# ----- Clause-prefix anchoring (B2 regression: "in canada" / "across canada" must be
#       at clause start, not mid-sentence prose) -----
check_gta("Headquartered in Canada, role is in NYC", False, "prose 'in Canada' not clause-anchored")
check_gta("Operating across Canada and the US — role is NYC-based", False, "prose 'across Canada' not clause-anchored")
check_keep("Headquartered in Canada, role is in NYC", False, "keep() prose leak")
check_keep("Operating across Canada and the US — role is NYC-based", False, "keep() prose leak")
check_gta("in Canada", True, "clause-start 'in canada' (bare)")
check_gta("Remote, in Canada", True, "comma-then-in-canada OK")
check_gta("Hybrid — across Canada", True, "dash-then-across-canada OK")
check_keep("across Canada", True, "keep() bare across canada")

# ----- _compute_diff bucket: newly-scored row detection -----
# (tested separately in test_compute_diff.py)

# ----- scan_delta: gmail filter -----
# (integration test — run via test_scan_delta_filter.py)

# ----- Summary -----
print(f"\n{PASS} pass / {FAIL} fail")
for f in FAILS:
    print(f)
sys.exit(0 if FAIL == 0 else 1)
