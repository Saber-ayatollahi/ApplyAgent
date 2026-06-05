#!/usr/bin/env python3
"""Backfill `posted_date` on existing job-tracker rows.

Why this exists
---------------
`auto_promote._make_entry` historically built the tracker row WITHOUT copying
the worklist's `posted_date`, so every promoted role landed with a blank
posting date (the freshness badge then had nothing to render). The promotion
path is fixed going forward; this one-off recovers the dates already lost.

How it recovers an accurate date
--------------------------------
For each tracker URL we collect every historical posting-date reading from
`scan_*.json` + `worklist*.json`, convert each to an absolute *origin* date
(when the role went live), and take the EARLIEST origin. That is deliberate:
Workday's list API reports "Posted 30+ Days Ago", which floors to exactly 30
days and therefore always biases the date *later* than the truth. An earlier
scan that caught the same role at "Posted 17 Days Ago" pins the real origin.
The minimum across readings is the closest to the true posting date.

For Workday rows we additionally consult the live CXS `startDate` (exact) and
fold it into the same min().

Usage:
    python automation/backfill_posted_dates.py            # dry-run (report only)
    python automation/backfill_posted_dates.py --commit   # write (with .bak)
    python automation/backfill_posted_dates.py --force     # also re-date rows
                                                           # that already have one
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTO = os.path.join(ROOT, "automation")
if _AUTO not in sys.path:
    sys.path.insert(0, _AUTO)

import worklist  # noqa: E402  norm_url
from jd_scraper import _normalize_workday_posted, workday_precise_date  # noqa: E402

TRACKER = os.path.join(ROOT, "data", "job_tracker_data.json")
OUT_DIR = os.path.join(ROOT, "automation", "outputs")


def _canon(url: str) -> str:
    try:
        return worklist.norm_url({"link": url or ""})
    except Exception:
        return (url or "").split("?")[0].rstrip("/")


def _iso(s) -> str | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else None


def _to_origin(raw, ref: date) -> str | None:
    """Absolute posting (origin) date for one historical reading.
    Already-ISO → itself; relative ("Posted 17 Days Ago") → ref - delta."""
    iso = _iso(raw)
    if iso:
        return iso
    return _iso(_normalize_workday_posted(str(raw or ""), today=ref))


def _ref_date(fp: str, row: dict) -> date:
    """Reference 'as-of' date for relative strings: the row's found_at, else
    the YYYYMMDD stamp in the scan filename, else today."""
    fa = _iso(row.get("found_at"))
    if fa:
        return datetime.strptime(fa, "%Y-%m-%d").date()
    m = re.search(r"(\d{8})", os.path.basename(fp))
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except Exception:
            pass
    return date.today()


def _rows_of(d) -> list:
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    if isinstance(d, dict):
        for k in ("jobs", "rows", "results", "postings", "items"):
            if isinstance(d.get(k), list):
                return [x for x in d[k] if isinstance(x, dict)]
        out = []
        for v in d.values():
            if isinstance(v, list):
                out += [x for x in v if isinstance(x, dict)]
        return out
    return []


def build_history_map() -> dict[str, set[str]]:
    """canonical-url -> {origin ISO date, ...} from all scan/worklist history."""
    files = sorted(glob.glob(os.path.join(OUT_DIR, "scan_*.json")))
    files += [os.path.join(OUT_DIR, "worklist.json"),
              os.path.join(OUT_DIR, "worklist_scored.json")]
    out: dict[str, set[str]] = {}
    for fp in files:
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for r in _rows_of(d):
            link = r.get("link") or r.get("url") or ""
            pd = r.get("posted_date")
            if not link or not pd:
                continue
            origin = _to_origin(pd, _ref_date(fp, r))
            if origin:
                out.setdefault(_canon(link), set()).add(origin)
    return out


def best_date(url: str, hist: dict[str, set[str]],
              *, use_live: bool = True) -> tuple[str | None, str]:
    """Return (origin ISO or None, provenance).

    Precedence: the live Workday CXS ``startDate`` is authoritative (the exact
    date the current posting went live), so it wins outright when reachable.
    Otherwise we fall back to scan-history and take the EARLIEST origin, since
    the "30+ Days Ago" floor only ever biases readings later than truth."""
    if use_live and "myworkdayjobs.com" in (url or ""):
        live = workday_precise_date(url)
        if live:
            return live, "live-cxs"
    cands: set[str] = set(hist.get(_canon(url), set()))
    if not cands:
        return None, "none"
    return min(cands), "scan-history"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="write changes (otherwise dry-run report only)")
    ap.add_argument("--force", action="store_true",
                    help="also re-date rows that already have a posted_date")
    ap.add_argument("--no-live", action="store_true",
                    help="skip live Workday CXS lookups (offline)")
    args = ap.parse_args()

    tracker = json.load(open(TRACKER, encoding="utf-8"))
    jobs = tracker["jobs"] if isinstance(tracker, dict) else tracker
    hist = build_history_map()

    changes = []
    unresolved = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        cur = j.get("posted_date")
        if cur and not args.force:
            continue
        url = j.get("url") or j.get("link") or ""
        origin, src = best_date(url, hist, use_live=not args.no_live)
        if origin and origin != _iso(cur):
            age = (date.today() - datetime.strptime(origin, "%Y-%m-%d").date()).days
            changes.append((j, cur, origin, src, age))
        elif not origin and not cur:
            unresolved.append(j)

    label = "WOULD SET" if not args.commit else "SET"
    print(f"Tracker rows: {len(jobs)} | history URLs: {len(hist)}")
    print(f"{label} posted_date on {len(changes)} row(s); "
          f"{len(unresolved)} unresolved.\n")
    for j, cur, origin, src, age in changes:
        co = (j.get("company") or "")[:18]
        ti = (j.get("title") or "")[:38]
        print(f"  [{label}] {co:<18} {ti:<38} {str(cur):>10} -> {origin} "
              f"({age}d, {src})")
    if unresolved:
        print("\n  Unresolved (no historical or live date found):")
        for j in unresolved:
            print(f"    - {(j.get('company') or '')[:18]:<18} "
                  f"{(j.get('title') or '')[:42]}")

    if args.commit and changes:
        import shutil  # noqa: WPS433
        bak = TRACKER + ".bak_posted_dates"
        shutil.copy2(TRACKER, bak)
        from safe_json import mutate_json  # noqa: WPS433

        new_by_id = {j.get("id"): origin for j, _c, origin, _s, _a in changes}

        def _apply(t):
            for row in (t.get("jobs") or []):
                if isinstance(row, dict) and row.get("id") in new_by_id:
                    row["posted_date"] = new_by_id[row["id"]]
            return t

        mutate_json(TRACKER, _apply, default={"jobs": [], "meta": {}})
        print(f"\n✅ Committed {len(changes)} change(s) "
              f"(backup: {os.path.basename(bak)})")
    elif not args.commit:
        print("\n(dry-run — re-run with --commit to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
