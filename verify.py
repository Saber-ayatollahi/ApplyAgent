#!/usr/bin/env python3
"""verify.py — Post-install sanity check for Saber's Job Search System.

Runs a series of checks and prints pass/fail for each.  Exit 0 if all pass.

Checks:
  1. Python 3.9+
  2. All required packages importable
  3. Canonical project files exist
  4. JSON files parse
  5. All agent scripts compile
  6. Tracker schema sanity (total_roles matches jobs array length)
  7. Ephemeral output directories exist
  8. ANTHROPIC_API_KEY presence (warning only — not required for dry-runs)
  9. weekly_report.py end-to-end smoke test (no network/API needed)
 10. jd_tailor.py --dry-run end-to-end (no API needed)
 11. fit_scorer.py --dry-run end-to-end (no API needed)
 12. Streamlit importable
 13. UI pages render via AppTest (no exceptions in any of the 11 nav pages)

Usage:
    python verify.py
    python verify.py --verbose
    python verify.py --fast    # skip end-to-end smoke tests
"""
from __future__ import annotations
import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OK = "  [PASS]"
WARN = "  [WARN]"
FAIL = "  [FAIL]"


class Outcome:
    def __init__(self):
        self.passed = 0
        self.warned = 0
        self.failed = 0

    def pass_(self, msg):
        self.passed += 1
        print(f"{OK}  {msg}")

    def warn_(self, msg):
        self.warned += 1
        print(f"{WARN}  {msg}")

    def fail_(self, msg):
        self.failed += 1
        print(f"{FAIL}  {msg}")


def check_python(o: Outcome):
    print("\n[1] Python version")
    v = sys.version_info
    if v.major == 3 and v.minor >= 9:
        o.pass_(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        o.fail_(f"Python {v.major}.{v.minor}.{v.micro} — need 3.9+")


def check_packages(o: Outcome):
    print("\n[2] Required packages importable")
    required = [("requests", "requests"),
                ("bs4", "beautifulsoup4"),
                ("dateutil", "python-dateutil"),
                ("anthropic", "anthropic"),
                ("pandas", "pandas"),
                ("streamlit", "streamlit")]
    for mod, pkg in required:
        try:
            importlib.import_module(mod)
            o.pass_(f"{pkg} imports")
        except ImportError:
            o.fail_(f"{pkg} NOT installed. Run: pip install -r requirements.txt")


def check_files(o: Outcome):
    print("\n[3] Canonical project files present")
    required = [
        "README.md", "CHANGELOG.md", "requirements.txt", ".gitignore",
        "docs/Saber_Ayatollahi_Master_Repository.md", "docs/Target_Companies_2026.md",
        "data/job_tracker_data.json", "data/recruiter_crm.json",
        "docs/cover_letter_templates.md", "docs/interview_prep.md",
        "docs/operating_cadence.md", "docs/references_and_salary.md",
        "docs/linkedin_content_engine.md", "docs/this_week.md",
        "automation/jd_scraper.py", "automation/fit_scorer.py",
        "automation/auto_promote.py", "automation/jd_tailor.py",
        "automation/weekly_report.py", "automation/expansion_companies.py",
        "automation/README.md",
        "ui/app.py", "ui/requirements.txt", "ui/README.md",
    ]
    for rel in required:
        p = ROOT / rel
        if p.exists():
            o.pass_(rel)
        else:
            o.fail_(f"{rel} missing")


def check_json(o: Outcome):
    print("\n[4] JSON files parse")
    for rel in ("data/job_tracker_data.json", "data/recruiter_crm.json"):
        p = ROOT / rel
        try:
            json.loads(p.read_text(encoding="utf-8"))
            o.pass_(f"{rel} valid JSON")
        except Exception as e:
            o.fail_(f"{rel} INVALID: {e}")


def check_compile(o: Outcome):
    print("\n[5] Agent scripts compile")
    scripts = ["automation/jd_scraper.py", "automation/fit_scorer.py",
               "automation/auto_promote.py", "automation/jd_tailor.py",
               "automation/weekly_report.py", "ui/app.py", "verify.py"]
    for rel in scripts:
        p = ROOT / rel
        if not p.exists():
            o.fail_(f"{rel} missing")
            continue
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
            o.pass_(f"{rel} compiles")
        except SyntaxError as e:
            o.fail_(f"{rel} SYNTAX ERROR: {e}")


def check_tracker_schema(o: Outcome):
    print("\n[6] Tracker schema sanity")
    try:
        tr = json.loads((ROOT / "data" / "job_tracker_data.json").read_text(encoding="utf-8"))
        meta_total = tr.get("meta", {}).get("total_roles")
        actual = len(tr.get("jobs", []))
        if meta_total == actual:
            o.pass_(f"tracker total_roles={meta_total} matches jobs[] length={actual}")
        else:
            o.warn_(f"tracker total_roles={meta_total} ≠ jobs[] length={actual} (non-fatal)")
        required_fields = ["id", "company", "title", "status", "tier", "fit_score",
                           "contact", "outreach_log", "followup_schedule"]
        missing = []
        for j in tr.get("jobs", []):
            for f in required_fields:
                if f not in j:
                    missing.append((j.get("id", "?"), f))
        if missing:
            o.fail_(f"{len(missing)} jobs missing required fields (first: {missing[0]})")
        else:
            o.pass_(f"all {actual} jobs have required fields")
    except Exception as e:
        o.fail_(f"tracker read/parse failed: {e}")


def check_output_dirs(o: Outcome):
    print("\n[7] Output directory scaffolding")
    for rel in ("automation/outputs", "automation/outputs/jd_cache",
                "automation/outputs/fit_cache"):
        p = ROOT / rel
        if p.exists():
            o.pass_(f"{rel} exists")
        else:
            try:
                p.mkdir(parents=True, exist_ok=True)
                o.pass_(f"{rel} created")
            except Exception as e:
                o.fail_(f"{rel} could not be created: {e}")


def check_api_key(o: Outcome):
    print("\n[8] ANTHROPIC_API_KEY")
    if os.environ.get("ANTHROPIC_API_KEY"):
        o.pass_(f"set (length {len(os.environ['ANTHROPIC_API_KEY'])})")
    else:
        o.warn_("NOT set — fit_scorer.py and jd_tailor.py (non-dry-run) will refuse to run.")
        print("         Fix: $env:ANTHROPIC_API_KEY = \"sk-ant-...\" (PowerShell)")
        print("              export ANTHROPIC_API_KEY=sk-ant-...      (bash)")


def check_weekly_report(o: Outcome):
    print("\n[9] weekly_report.py end-to-end")
    try:
        r = subprocess.run([sys.executable, str(ROOT / "automation" / "weekly_report.py")],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=30)
        if r.returncode == 0 and "Wrote" in (r.stdout + r.stderr):
            o.pass_("weekly_report.py ran and produced a report")
        else:
            o.fail_(f"weekly_report.py exited {r.returncode}: {(r.stdout + r.stderr)[:200]}")
    except Exception as e:
        o.fail_(f"could not run weekly_report.py: {e}")


def check_jd_tailor_dry(o: Outcome):
    print("\n[10] jd_tailor.py --dry-run")
    try:
        tr = json.loads((ROOT / "data" / "job_tracker_data.json").read_text(encoding="utf-8"))
        job_id = tr["jobs"][0]["id"] if tr.get("jobs") else None
        if not job_id:
            o.warn_("no jobs in tracker to test against")
            return
        r = subprocess.run([sys.executable, str(ROOT / "automation" / "jd_tailor.py"),
                            "--job-id", job_id, "--dry-run"],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=60)
        combined = r.stdout + r.stderr
        if r.returncode == 0 and ("DRY RUN" in combined or "wrote prompt" in combined.lower()):
            o.pass_(f"jd_tailor dry-run OK for {job_id}")
        else:
            o.fail_(f"jd_tailor dry-run exited {r.returncode}: {combined[:300]}")
    except Exception as e:
        o.fail_(f"could not run jd_tailor.py: {e}")


def check_fit_scorer_dry(o: Outcome):
    print("\n[11] fit_scorer.py --dry-run")
    # Pick the freshest dated scan_YYYYMMDD.json. v4 was retired when the
    # weekly pipeline started writing date-stamped scans.
    out_dir = ROOT / "automation" / "outputs"
    candidates = sorted(out_dir.glob("scan_*.json"), reverse=True)
    # Prefer date-stamped scans; ignore _scored / _delta / _brief sidecars.
    scan = next(
        (p for p in candidates
         if p.stem.replace("scan_", "").isdigit() and len(p.stem) == 13),
        None,
    )
    if scan is None:
        o.warn_("no scan_YYYYMMDD.json in outputs/; skipping fit_scorer dry-run")
        return
    try:
        r = subprocess.run([sys.executable, str(ROOT / "automation" / "fit_scorer.py"),
                            "--scan", scan.name, "--dry-run"],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=120)
        combined = r.stdout + r.stderr
        if r.returncode == 0 and "DRY RUN" in combined:
            o.pass_(f"fit_scorer dry-run OK ({scan.name})")
        else:
            o.fail_(f"fit_scorer exited {r.returncode}: {combined[:300]}")
    except Exception as e:
        o.fail_(f"could not run fit_scorer.py: {e}")


def check_streamlit(o: Outcome):
    print("\n[12] Streamlit importable")
    try:
        import streamlit  # noqa: F401
        o.pass_(f"streamlit {streamlit.__version__}")
    except Exception as e:
        o.fail_(f"streamlit import failed: {e}")


def check_pages_render(o: Outcome):
    print("\n[13] UI pages render (AppTest)")
    test_path = ROOT / "tests" / "test_pages.py"
    if not test_path.exists():
        o.warn_("tests/test_pages.py missing; skipping page-render check")
        return
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([sys.executable, str(test_path)],
                           capture_output=True, text=True, cwd=str(ROOT),
                           timeout=180, env=env)
        combined = (r.stdout or "") + (r.stderr or "")
        # Look for the standalone runner's summary line.
        match = re.search(r"Results:\s+(\d+)/(\d+)\s+pages OK", combined)
        if r.returncode == 0 and match:
            o.pass_(f"all {match.group(2)} pages render without exceptions")
        elif match:
            o.fail_(f"{match.group(1)}/{match.group(2)} pages OK; see logs/e2e_apptest_result.json")
        else:
            o.fail_(f"page-render harness exited {r.returncode}: {combined[-300:]}")
    except Exception as e:
        o.fail_(f"could not run tests/test_pages.py: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true",
                    help="Skip end-to-end smoke tests (9, 10, 11)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print("  verify.py — sanity check for the job-search system")
    print("=" * 60)

    o = Outcome()
    check_python(o)
    check_packages(o)
    check_files(o)
    check_json(o)
    check_compile(o)
    check_tracker_schema(o)
    check_output_dirs(o)
    check_api_key(o)
    check_streamlit(o)
    if not args.fast:
        check_weekly_report(o)
        check_jd_tailor_dry(o)
        check_fit_scorer_dry(o)
        check_pages_render(o)

    print()
    print("=" * 60)
    print(f"  RESULTS: {o.passed} pass · {o.warned} warn · {o.failed} fail")
    print("=" * 60)
    if o.failed:
        print("  -> Fix the [FAIL] rows above before shipping.")
        return 1
    elif o.warned:
        print("  -> OK to ship; warnings are non-blocking.")
        return 0
    else:
        print("  -> All clear. System is ship-ready.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
