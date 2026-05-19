"""Verify worklist.rebuild() applies keep_for_toronto_pipeline to legacy
gmail rows. Audit found old scan_gmail_*.json files (pre-dating the geo gate
in gmail_fetch.py) leak Raleigh / Chicago / NYC rows into the pool. We isolate
rebuild() against a tmp OUT_DIR and confirm:
  - Toronto row kept
  - Canada-remote row kept (uses "Remote - Canada", a form the current
    location_filter accepts; the "Canada (Remote)" false-drop is audit #2,
    out of scope here)
  - Raleigh row dropped
  - stats.gmail_geo_dropped reports the drop count."""
from __future__ import annotations
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import worklist  # type: ignore


def _write_envelope(path: Path, rows: list[dict]) -> None:
    env = {
        "version": 1,
        "scan_date": datetime.now().date().isoformat(),
        "results": rows,
    }
    path.write_text(json.dumps(env, indent=2), encoding="utf-8")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wl_geo_"))
    try:
        # Redirect worklist's OUT_DIR + WORKLIST + WORKLIST_SCORED to tmp.
        worklist.OUT_DIR = tmp
        worklist.WORKLIST = tmp / "worklist.json"
        worklist.WORKLIST_SCORED = tmp / "worklist_scored.json"
        worklist.LEGACY_DIR = tmp / "_legacy"

        gmail_path = tmp / "scan_gmail_20260518_120000.json"
        rows = [
            {"title": "ALM Analyst",      "company": "RBC",   "location": "Toronto, ON",
             "link": "https://www.linkedin.com/jobs/view/100000001"},
            {"title": "Treasury Manager", "company": "KOHO",  "location": "Remote - Canada",
             "link": "https://www.linkedin.com/jobs/view/100000002"},
            {"title": "Risk Analyst",     "company": "ACME",  "location": "Raleigh, NC",
             "link": "https://www.linkedin.com/jobs/view/100000003"},
            {"title": "Risk Analyst",     "company": "BIGCO", "location": "Chicago, IL",
             "link": "https://www.linkedin.com/jobs/view/100000004"},
        ]
        _write_envelope(gmail_path, rows)

        stats = worklist.rebuild(quarantine=False)
        env = json.loads(worklist.WORKLIST.read_text(encoding="utf-8"))
        kept_urls = {r.get("link") for r in env.get("results", [])}

        print("kept urls   :", sorted(kept_urls))
        print("stats       :", stats)

        assert "https://www.linkedin.com/jobs/view/100000001" in kept_urls, "Toronto row missing"
        assert "https://www.linkedin.com/jobs/view/100000002" in kept_urls, "Canada-remote row missing"
        assert "https://www.linkedin.com/jobs/view/100000003" not in kept_urls, "Raleigh leaked"
        assert "https://www.linkedin.com/jobs/view/100000004" not in kept_urls, "Chicago leaked"
        assert stats.get("gmail_geo_dropped") == 2, f"expected 2 geo drops, got {stats.get('gmail_geo_dropped')}"
        print("PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
