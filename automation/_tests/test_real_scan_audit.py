"""Audit real scan_gmail_*.json files for contamination patterns NOT covered
by _clean_alert_fields modes A-D.

Pure read-only — no source modifications, no IMAP."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from gmail_reader import _clean_alert_fields  # type: ignore
from location_filter import keep_for_toronto_pipeline  # type: ignore

OUT_DIR = ROOT / "outputs"
files = sorted(OUT_DIR.glob("scan_gmail_*.json"))
if not files:
    print("no scan_gmail_*.json files")
    sys.exit(0)

print(f"Found {len(files)} scan_gmail_*.json files")
for f in files:
    print(f"  - {f.name}")

# Patterns indicating contamination
ACTIVITY_RE = re.compile(
    r"(actively recruiting|\d+\s+(connection|connections|alumni)|promoted)",
    re.IGNORECASE,
)
SEP_RE = re.compile(r"[·�]")
MODE_RE = re.compile(r"\((Hybrid|On-?site|Remote)\)", re.IGNORECASE)
SALARY_RE = re.compile(r"\$\d+K?[-–]\$?\d+K?")

per_file: dict[str, dict] = {}

for path in files:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[skip] {path.name}: {e}")
        continue
    rows = data.get("results", [])
    if not rows:
        per_file[path.name] = {"rows": 0}
        continue

    findings = {
        "total_rows": len(rows),
        "title_has_activity": 0,
        "title_has_sep": 0,
        "title_has_mode": 0,
        "company_has_activity": 0,
        "company_has_sep": 0,
        "company_has_mode": 0,
        "location_has_activity": 0,
        "location_has_sep": 0,
        "location_has_mode": 0,
        "location_has_salary": 0,
        "title_eq_company": 0,
        "company_eq_title_role": 0,
        "non_gta_kept": 0,
        "examples_title_activity": [],
        "examples_company_sep": [],
        "examples_location_sep": [],
        "examples_location_salary": [],
        "examples_non_gta_kept": [],
        "examples_company_eq_role": [],
        "idempotency_violations": [],
    }

    for r in rows:
        t = r.get("title", "") or ""
        c = r.get("company", "") or ""
        l = r.get("location", "") or ""

        if ACTIVITY_RE.search(t):
            findings["title_has_activity"] += 1
            if len(findings["examples_title_activity"]) < 3:
                findings["examples_title_activity"].append(t[:120])
        if SEP_RE.search(t):
            findings["title_has_sep"] += 1
        if MODE_RE.search(t):
            findings["title_has_mode"] += 1

        if ACTIVITY_RE.search(c):
            findings["company_has_activity"] += 1
        if SEP_RE.search(c):
            findings["company_has_sep"] += 1
            if len(findings["examples_company_sep"]) < 3:
                findings["examples_company_sep"].append(c[:120])
        if MODE_RE.search(c):
            findings["company_has_mode"] += 1

        if ACTIVITY_RE.search(l):
            findings["location_has_activity"] += 1
        if SEP_RE.search(l):
            findings["location_has_sep"] += 1
            if len(findings["examples_location_sep"]) < 3:
                findings["examples_location_sep"].append(l[:120])
        if MODE_RE.search(l):
            findings["location_has_mode"] += 1
        if SALARY_RE.search(l):
            findings["location_has_salary"] += 1
            if len(findings["examples_location_salary"]) < 3:
                findings["examples_location_salary"].append(l[:120])

        if t and c and t.strip().lower() == c.strip().lower():
            findings["title_eq_company"] += 1
        # company == role-like? (company looks like a job title — heuristic)
        if c and any(rk in c.lower() for rk in (
                "manager", "director", "analyst", "engineer", "vice president",
                "vp ", "head", "lead", "specialist", "advisor"
        )):
            findings["company_eq_title_role"] += 1
            if len(findings["examples_company_eq_role"]) < 3:
                findings["examples_company_eq_role"].append(f"co={c!r} title={t[:60]!r}")

        # geo: row was kept — was it GTA?
        if not keep_for_toronto_pipeline(l) and l:
            # if location is non-GTA AND row was emitted, that's a leak
            findings["non_gta_kept"] += 1
            if len(findings["examples_non_gta_kept"]) < 3:
                findings["examples_non_gta_kept"].append(
                    f"{c[:30]!r} loc={l[:60]!r}"
                )

        # idempotency on the live data
        once = _clean_alert_fields(t, c, l)
        twice = _clean_alert_fields(*once)
        if twice != once:
            if len(findings["idempotency_violations"]) < 3:
                findings["idempotency_violations"].append({
                    "input": (t, c, l),
                    "once": once,
                    "twice": twice,
                })

    per_file[path.name] = findings

# Print summary
import pprint
print("\n=== AUDIT RESULTS ===")
for fname, f in per_file.items():
    print(f"\n{fname}")
    pprint.pprint(f, width=120, sort_dicts=False)
