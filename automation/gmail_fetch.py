#!/usr/bin/env python3
"""
gmail_fetch.py — Standalone LinkedIn/Indeed alert fetcher.

Until now, Gmail-harvested alerts only got pulled as a side-effect of a full
jd_scraper run (--gmail flag). There was no way to refresh alerts
independently. This script is the missing link — it can be launched from
the UI Pipeline tab as a 10-second operation, produces a scan_gmail_<stamp>.json
that feeds the same scorer/promote pipeline as any other scan.

Usage:
    python automation/gmail_fetch.py                      # last 14 days
    python automation/gmail_fetch.py --days 30
    python automation/gmail_fetch.py --dry-run            # print counts only

Outputs:
    automation/outputs/scan_gmail_<YYYYMMDD_HHMMSS>.json  (scan_v4 schema)

The output file name starts with scan_gmail_ so it's easy to distinguish
from full web scrapes and the existing scoring pipeline can still run:

    python automation/fit_scorer.py --scan scan_gmail_<stamp>.json
    python automation/run_pipeline.py --skip-scrape --scan scan_gmail_<stamp>.json

Tracker dedupe happens at auto_promote time — a URL already in tracker
is skipped. So running this daily is safe even if alerts overlap.

Exit codes:
    0   success (any row count)
    1   credentials missing / invalid
    2   Gmail fetch failed
    3   no rows found (not an error per se, but signals 'nothing to do')
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"


def _load_tracker_urls() -> set[str]:
    """Dedupe against roles already in the tracker. Cheap read."""
    tp = ROOT / "data" / "job_tracker_data.json"
    if not tp.exists():
        return set()
    try:
        data = json.loads(tp.read_text(encoding="utf-8"))
        return {j.get("url") for j in data.get("jobs", []) if j.get("url")}
    except Exception:
        return set()


def _emit_scan_shape(rows: list[dict], source_label: str) -> dict:
    """Wrap Gmail rows in the same envelope fit_scorer / auto_promote expect.

    Also stamps a `gmail_alerts` block listing the UIDs of every email that
    contributed at least one row. The UI uses this list to ask the user
    'move these N alerts to Gmail Trash?' — only emails that produced data
    are eligible, so we never drop a lead we couldn't parse."""
    contributing_uids = sorted({
        str(r.get("gmail_uid")) for r in rows
        if r.get("gmail_uid")
    })
    return {
        "scan_date": datetime.now().strftime("%Y-%m-%d"),
        "scan_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source_label,
        "dedup_stats": {
            "input": len(rows),
            "output": len(rows),
            "dropped_url": 0,
            "dropped_near": 0,
        },
        "diagnostics": {
            "zero_result_companies": [],
            "per_company": [],
            "note": "Produced by gmail_fetch.py — pure Gmail alert harvest, "
                    "no web scraping.",
        },
        "gmail_alerts": {
            "contributing_uids": contributing_uids,
            "deleted": False,
            "deleted_at": None,
            "delete_result": None,
        },
        "results": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14,
                    help="How many days of alerts to pull (default 14)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch and print counts; don't write a scan file.")
    ap.add_argument("--skip-tracker-dedup", action="store_true",
                    help="Include alerts already in the tracker. Useful when "
                         "rescoring an old URL with different resume variants.")
    ap.add_argument("--output", default=None,
                    help="Override the output filename. Default: "
                         "scan_gmail_<YYYYMMDD_HHMMSS>.json")
    args = ap.parse_args()

    try:
        from gmail_reader import (  # type: ignore
            load_credentials, scrape_from_inbox, validate,
        )
    except ImportError:
        try:
            from .gmail_reader import (  # type: ignore
                load_credentials, scrape_from_inbox, validate,
            )
        except Exception as e:
            print(f"[gmail_fetch] cannot import gmail_reader: {e}", file=sys.stderr)
            return 1

    email_addr, pw = load_credentials()
    if not email_addr or not pw:
        print("[gmail_fetch] ❌ Gmail credentials not set. Open the Streamlit "
              "sidebar → Gmail section, save an app password.", file=sys.stderr)
        return 1

    # Quick validation so we fail with a clear message rather than a cryptic
    # IMAP error mid-fetch.
    check = validate(email_addr, pw)
    if not check.ok:
        print(f"[gmail_fetch] ❌ Gmail auth failed: {check.message}", file=sys.stderr)
        return 1
    print(f"[gmail_fetch] ✓ authenticated as {email_addr} — fetching "
          f"alerts from last {args.days} days...", file=sys.stderr)

    # Capture diagnostics so "0 rows" is debuggable: how many alert emails
    # IMAP matched, how many we tried to parse, how many produced rows.
    # Without this, the user can't tell "no LinkedIn alerts in inbox" from
    # "alerts arrived but parser returned nothing" (a parser regression).
    try:
        from gmail_reader import fetch_inbox_signals, parse_linkedin_alert  # type: ignore
    except ImportError:
        from .gmail_reader import fetch_inbox_signals, parse_linkedin_alert  # type: ignore

    try:
        messages = fetch_inbox_signals(days=args.days, limit=200, include_body=True)
    except Exception as e:
        print(f"[gmail_fetch] ❌ inbox fetch failed: {e}", file=sys.stderr)
        return 2

    alert_msgs = [m for m in messages
                   if m.kind == "alert" and "linkedin.com" in m.sender_email.lower()]
    rows: list[dict] = []
    msgs_with_rows = 0
    msgs_without_rows = 0
    for m in alert_msgs:
        parsed = parse_linkedin_alert(m.snippet)
        if parsed:
            msgs_with_rows += 1
        else:
            msgs_without_rows += 1
        for row in parsed:
            row["posted_date"] = m.date or None
            row["gmail_uid"] = m.uid
            rows.append(row)
    print(f"[gmail_fetch] inbox match: {len(messages)} sender-classified, "
          f"{len(alert_msgs)} LinkedIn alert(s); "
          f"parsed {len(rows)} row(s) from {msgs_with_rows} digest(s) "
          f"({msgs_without_rows} digest(s) yielded zero rows)",
          file=sys.stderr)

    # Dedupe against tracker
    dropped_tracker = 0
    if not args.skip_tracker_dedup:
        tracker_urls = _load_tracker_urls()
        kept = []
        for r in rows:
            if r.get("link") in tracker_urls:
                dropped_tracker += 1
                continue
            kept.append(r)
        rows = kept
        print(f"[gmail_fetch] after tracker dedup: {len(rows)} kept "
              f"(-{dropped_tracker} already in tracker)", file=sys.stderr)

    if args.dry_run:
        print(f"\n[gmail_fetch] DRY RUN: would write {len(rows)} row(s).")
        for r in rows[:10]:
            print(f"  · {r.get('company','?')} — {(r.get('title') or '?')[:70]}")
        if len(rows) > 10:
            print(f"  ... +{len(rows)-10} more")
        return 0 if rows else 3

    # ALWAYS write the envelope so the UI can see the run completed and
    # surface diagnostics. Previously a 0-row run wrote nothing — making
    # success-with-no-rows indistinguishable from "fetch never ran" or
    # "Streamlit lost track of the subprocess". The envelope now carries
    # `harvest_diagnostics` so the UI can render
    # 'Inbox had N alerts but parser returned 0 rows — likely parse bug'.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = args.output or f"scan_gmail_{stamp}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / fname
    envelope = _emit_scan_shape(rows, source_label="gmail_linkedin_alert")
    envelope["harvest_diagnostics"] = {
        "days_window": args.days,
        "imap_messages_matched": len(messages),
        "linkedin_alerts_seen": len(alert_msgs),
        "digests_with_rows": msgs_with_rows,
        "digests_without_rows": msgs_without_rows,
        "rows_after_parse": len(rows) + dropped_tracker,
        "rows_dropped_tracker_dedup": dropped_tracker,
        "rows_final": len(rows),
    }
    out_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    if not rows:
        print(f"[gmail_fetch] ⚠ wrote {out_path.name} with 0 rows. "
              f"({len(alert_msgs)} alert(s) seen — likely parse miss "
              "or all rows already in tracker.)", file=sys.stderr)
        return 0  # not an error — UI will surface the diagnostic

    print(f"[gmail_fetch] ✓ wrote {out_path.name} with {len(rows)} "
          f"row(s).", file=sys.stderr)
    n_uids = len(envelope.get("gmail_alerts", {}).get("contributing_uids", []))
    if n_uids:
        print(f"[gmail_fetch]   {n_uids} alert email(s) produced rows — "
              f"the UI will offer to move them to Trash.", file=sys.stderr)
    print(f"[gmail_fetch]   Next: python automation/fit_scorer.py "
          f"--scan {fname}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
