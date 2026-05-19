#!/usr/bin/env python3
"""
gmail_fetch.py — Standalone LinkedIn/Indeed alert fetcher.

Harvests LinkedIn job-alert emails into a scan_gmail_<stamp>.json file with
the same schema as web scrape outputs. After writing, automatically
rebuilds worklist.json so the scorer's next run picks the new rows up.

Usage:
    python automation/gmail_fetch.py                      # last 14 days
    python automation/gmail_fetch.py --days 30
    python automation/gmail_fetch.py --dry-run            # print counts only

Outputs:
    automation/outputs/scan_gmail_<YYYYMMDD_HHMMSS>.json  (raw harvest)
    automation/outputs/worklist.json                       (rebuilt)

Dedup philosophy: this script ONLY writes the raw harvest. All dedup —
URL match against tracker, near-dup match against the web scrape, rolling
30-day pool maintenance — is the worklist module's job. Keeping the
producer side dumb means there's exactly ONE place dedup logic lives.

Exit codes:
    0   success (any row count, including zero — diagnostics on disk)
    1   credentials missing / invalid
    2   IMAP fetch failed
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdio so emoji + unicode (·, ✓, ❌) don't crash cp1252
# consoles. With this off, gmail_fetch crashed mid-print on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"


def _emit_scan_shape(rows: list[dict], source_label: str) -> dict:
    """Wrap Gmail rows in the envelope worklist + the legacy fit_scorer
    paths expect. Stamps a `gmail_alerts` block listing the UIDs of every
    email that contributed at least one row — the UI uses this to offer
    'move these N alerts to Gmail Trash'."""
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
            "note": "Produced by gmail_fetch.py — pure Gmail alert harvest. "
                    "Dedup happens in worklist.rebuild() not here.",
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
    ap.add_argument("--output", default=None,
                    help="Override the output filename. Default: "
                         "scan_gmail_<YYYYMMDD_HHMMSS>.json")
    ap.add_argument("--no-rebuild", action="store_true",
                    help="Skip the automatic worklist.rebuild() at the end. "
                         "Use only when chaining multiple harvests where you "
                         "want a single rebuild after the last one.")
    args = ap.parse_args()

    try:
        from gmail_reader import (  # type: ignore
            load_credentials, validate, fetch_inbox_signals, parse_linkedin_alert,
        )
        from location_filter import keep_for_toronto_pipeline  # type: ignore
    except ImportError:
        try:
            from .gmail_reader import (  # type: ignore
                load_credentials, validate, fetch_inbox_signals, parse_linkedin_alert,
            )
            from .location_filter import keep_for_toronto_pipeline  # type: ignore
        except Exception as e:
            print(f"[gmail_fetch] cannot import gmail_reader: {e}", file=sys.stderr)
            return 1

    email_addr, pw = load_credentials()
    if not email_addr or not pw:
        print("[gmail_fetch] ❌ Gmail credentials not set. Open the Streamlit "
              "sidebar → Gmail section, save an app password.", file=sys.stderr)
        return 1

    check = validate(email_addr, pw)
    if not check.ok:
        print(f"[gmail_fetch] ❌ Gmail auth failed: {check.message}", file=sys.stderr)
        return 1
    print(f"[gmail_fetch] ✓ authenticated as {email_addr} — fetching "
          f"alerts from last {args.days} days...", file=sys.stderr)

    try:
        messages = fetch_inbox_signals(days=args.days, limit=200, include_body=True)
    except Exception as e:
        print(f"[gmail_fetch] ❌ inbox fetch failed: {e}", file=sys.stderr)
        return 2

    alert_msgs = [m for m in messages
                   if m.kind == "alert" and "linkedin.com" in m.sender_email.lower()]
    raw_rows: list[dict] = []
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
            raw_rows.append(row)

    # Geo gate: LinkedIn pads digest emails with "similar roles" pulled from
    # outside the Toronto-anchored saved alert (Raleigh, NYC, etc). Drop rows
    # whose location is clearly non-GTA. Empty-location rows are kept — let
    # the scorer decide rather than silently lose a Toronto role whose
    # location field LinkedIn happened to omit. Mirrors the web scraper's
    # _is_gta_or_canada_remote gate at jd_scraper.py.
    rows: list[dict] = []
    dropped_loc_examples: list[str] = []
    for row in raw_rows:
        if keep_for_toronto_pipeline(row.get("location") or ""):
            rows.append(row)
        elif len(dropped_loc_examples) < 5:
            dropped_loc_examples.append(
                f"{row.get('company','?')} — {row.get('location','?')}"
            )
    rows_dropped_location = len(raw_rows) - len(rows)

    print(f"[gmail_fetch] inbox match: {len(messages)} sender-classified, "
          f"{len(alert_msgs)} LinkedIn alert(s); "
          f"parsed {len(raw_rows)} row(s) from {msgs_with_rows} digest(s) "
          f"({msgs_without_rows} digest(s) yielded zero rows)",
          file=sys.stderr)
    if rows_dropped_location:
        print(f"[gmail_fetch] geo filter: dropped {rows_dropped_location} "
              f"non-GTA row(s) — kept {len(rows)}", file=sys.stderr)
        for ex in dropped_loc_examples:
            print(f"  · drop: {ex}", file=sys.stderr)

    if args.dry_run:
        print(f"\n[gmail_fetch] DRY RUN: would write {len(rows)} row(s) "
              f"({rows_dropped_location} dropped by geo filter).")
        for r in rows[:10]:
            print(f"  · {r.get('company','?')} — {(r.get('title') or '?')[:70]}")
        if len(rows) > 10:
            print(f"  ... +{len(rows)-10} more")
        return 0

    # ALWAYS write the envelope — even on 0 rows — so the UI can show
    # diagnostics. Previously 0-row runs wrote nothing, making success
    # indistinguishable from a crashed subprocess.
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
        "rows_parsed": len(raw_rows),
        "rows_dropped_location": rows_dropped_location,
        "rows_kept": len(rows),
        "dropped_location_examples": dropped_loc_examples,
    }
    out_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    if not rows:
        print(f"[gmail_fetch] ⚠ wrote {out_path.name} with 0 rows. "
              f"({len(alert_msgs)} alert(s) seen — likely parse miss.)",
              file=sys.stderr)
    else:
        print(f"[gmail_fetch] ✓ wrote {out_path.name} with {len(rows)} row(s).",
              file=sys.stderr)
        n_uids = len(envelope.get("gmail_alerts", {}).get("contributing_uids", []))
        if n_uids:
            print(f"[gmail_fetch]   {n_uids} alert email(s) produced rows — "
                  "the UI will offer to move them to Trash.", file=sys.stderr)

    # Auto-rebuild worklist so the next score run sees these rows.
    # The user never has to think about merge timing — every input
    # change triggers a rebuild. Worklist owns dedup against the web
    # scrape and the rolling 30d Gmail pool.
    if not args.no_rebuild:
        try:
            try:
                import worklist  # type: ignore
            except ImportError:
                from . import worklist  # type: ignore
            stats = worklist.rebuild()
            print(f"[gmail_fetch] worklist rebuilt: {stats['total']} rows "
                  f"({stats['scrape']} scrape, {stats['gmail']} gmail, "
                  f"{stats['both']} both) · "
                  f"{stats['new_since_last_score']} new since last score",
                  file=sys.stderr)
        except Exception as e:
            print(f"[gmail_fetch] ⚠ worklist rebuild failed: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
