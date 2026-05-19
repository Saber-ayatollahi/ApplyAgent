#!/usr/bin/env python3
"""tracker_geo_audit.py - list tracker rows whose location fails the geo gate.

Read-only. The geo gate (location_filter.keep_for_toronto_pipeline) was
tightened after some rows were promoted to the tracker; this script surfaces
the historical leaks for manual review. It does NOT modify the tracker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
from location_filter import keep_for_toronto_pipeline  # type: ignore  # noqa: E402

TRACKER = ROOT / "data" / "job_tracker_data.json"


def main() -> int:
    data = json.loads(TRACKER.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) or []
    fails = [j for j in jobs if not keep_for_toronto_pipeline(j.get("location") or "")]
    for j in fails:
        title = j.get("title", "?")
        company = j.get("company", "?")
        loc = j.get("location", "?")
        url = j.get("url") or j.get("link") or j.get("job_url") or j.get("portal_url") or ""
        print(f"{title}  ·  {company}  ·  {loc}  ·  {url}")
    print()
    print(f"{len(fails)} of {len(jobs)} tracker rows failed geo gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
