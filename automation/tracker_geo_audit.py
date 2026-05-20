#!/usr/bin/env python3
"""tracker_geo_audit.py - audit (and optionally scrub) tracker rows whose
location fails the geo gate.

Default mode is read-only: prints rows where
`location_filter.keep_for_toronto_pipeline` returns False.

`--scrub` performs a one-time soft-mark of historical leaks created before
auto_promote learned to gate at promote time. Soft-mark = set
`status="Expired"`, `rejection_reason="geo_gate_historical_leak"`,
`rejection_date=<today>`, append to `notes`. Preserves all other fields
(fit_*, resume_variants, outreach_log) for audit / future reference.

Safety guards on `--scrub`:
  - Only touches rows with id starting `auto-` (system-promoted, never
    human-edited)
  - Only touches rows with status in {Found, Watch} (untouched by Saber)
  - Only touches rows with `date_applied` falsy (never applied to)
  - Always backs up the tracker first to a timestamped sibling file
  - Wraps the mutation in safe_json.mutate_json so concurrent UI edits
    don't lose. Without --commit it's a dry-run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
from location_filter import keep_for_toronto_pipeline  # type: ignore  # noqa: E402

try:
    from safe_json import mutate_json as _sj_mutate  # type: ignore  # noqa: E402
except ImportError:
    _sj_mutate = None  # type: ignore

TRACKER = ROOT / "data" / "job_tracker_data.json"


def _eligible_for_scrub(j: dict) -> bool:
    """A row is eligible for scrub iff:
      - it fails the live geo gate
      - id is system-promoted (auto-*)
      - status is one of the untouched values (Found, Watch)
      - never applied to
      - not already Expired (idempotent)
    """
    if keep_for_toronto_pipeline(j.get("location") or ""):
        return False
    if not str(j.get("id", "")).startswith("auto-"):
        return False
    if j.get("status") not in ("Found", "Watch"):
        return False
    if j.get("date_applied"):
        return False
    return True


def _scrub_row(j: dict, today_iso: str) -> dict:
    """Return a soft-marked copy of j (caller replaces in place)."""
    orig_loc = j.get("location") or ""
    out = dict(j)
    out["status"] = "Expired"
    out["rejection_reason"] = "geo_gate_historical_leak"
    out["rejection_date"] = today_iso
    out["next_action"] = None
    note_addendum = (
        f" | geo_scrub {today_iso}: location='{orig_loc}' failed "
        f"keep_for_toronto_pipeline; promoted before geo gate landed at "
        f"auto_promote-time"
    )
    out["notes"] = (out.get("notes") or "") + note_addendum
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit (and optionally scrub) tracker rows that fail the geo gate."
    )
    ap.add_argument(
        "--scrub", action="store_true",
        help="Soft-mark eligible rows (status=Expired, rejection_reason="
             "geo_gate_historical_leak). Default is dry-run; pass --commit to write.",
    )
    ap.add_argument(
        "--commit", action="store_true",
        help="When combined with --scrub, actually write the tracker.",
    )
    ap.add_argument(
        "--include-expired", action="store_true",
        help="Audit all rows, including ones already soft-marked Expired. "
             "Default excludes Expired rows so post-scrub audits show 0.",
    )
    args = ap.parse_args()

    data = json.loads(TRACKER.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) or []
    fails = [j for j in jobs if not keep_for_toronto_pipeline(j.get("location") or "")]

    if not args.scrub:
        live_fails = ([j for j in fails if j.get("status") != "Expired"]
                      if not args.include_expired else fails)
        for j in live_fails:
            title = j.get("title", "?")
            company = j.get("company", "?")
            loc = j.get("location", "?")
            url = (j.get("url") or j.get("link") or j.get("job_url")
                   or j.get("portal_url") or "")
            print(f"{title}  ·  {company}  ·  {loc}  ·  {url}")
        print()
        if args.include_expired:
            print(f"{len(fails)} of {len(jobs)} tracker rows failed geo gate "
                  f"(includes Expired)")
        else:
            print(f"{len(live_fails)} of {len(jobs)} live tracker rows "
                  f"failed geo gate ({len(fails) - len(live_fails)} already "
                  f"soft-marked Expired; --include-expired to see them)")
        return 0

    # Scrub mode
    eligible = [j for j in fails if _eligible_for_scrub(j)]
    ineligible = [j for j in fails if not _eligible_for_scrub(j)]

    today_iso = datetime.now().strftime("%Y-%m-%d")
    print(f"[scrub] {len(fails)} rows fail geo gate; {len(eligible)} eligible "
          f"for soft-mark; {len(ineligible)} skipped (human-edited or applied).")
    for j in eligible:
        print(f"  scrub: {j['id']}  ·  {j.get('company','?')}  ·  "
              f"{j.get('title','?')}  ·  {j.get('location','?')}")
    for j in ineligible:
        why = []
        if not str(j.get("id","")).startswith("auto-"):
            why.append("non-auto id")
        if j.get("status") not in ("Found", "Watch"):
            why.append(f"status={j.get('status')!r}")
        if j.get("date_applied"):
            why.append("applied")
        print(f"  skip:  {j.get('id','?')}  ·  {','.join(why) or 'unknown'}")

    if not args.commit:
        print("\n[scrub] DRY-RUN — re-run with --scrub --commit to apply.")
        return 0

    if not eligible:
        print("\n[scrub] Nothing eligible to write.")
        return 0

    # Backup before any mutation. Use a distinct stamp so we don't clobber
    # auto_promote's daily backup (.bak.YYYYMMDD.json).
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TRACKER.with_suffix(f".bak.geo_scrub_{stamp}.json")
    shutil.copy2(TRACKER, backup)
    print(f"\n[scrub] Backup -> {backup.name}")

    eligible_ids = {j["id"] for j in eligible}

    def mutator(d):
        if not isinstance(d, dict) or "jobs" not in d:
            return d
        new_jobs = []
        scrubbed = 0
        for j in d.get("jobs", []) or []:
            if j.get("id") in eligible_ids:
                new_jobs.append(_scrub_row(j, today_iso))
                scrubbed += 1
            else:
                new_jobs.append(j)
        d["jobs"] = new_jobs
        d.setdefault("meta", {}).setdefault("changelog", []).append({
            "date": today_iso,
            "event": (f"geo_scrub: -{scrubbed} historical leaks soft-marked "
                      f"Expired (rejection_reason=geo_gate_historical_leak)"),
            "roles": len(new_jobs),
        })
        return d

    if _sj_mutate is None:
        print("[scrub] WARN: safe_json not available; falling back to plain "
              "read-modify-write (NOT cross-process safe).", file=sys.stderr)
        new = mutator(data)
        TRACKER.write_text(json.dumps(new, indent=2), encoding="utf-8")
    else:
        _sj_mutate(TRACKER, mutator,
                   default={"jobs": [], "meta": {}})
    print(f"[scrub] COMMIT: soft-marked {len(eligible)} row(s) Expired.")
    print(f"[scrub] Re-run without --scrub to verify the audit shows 0 "
          f"(non-Expired) rows failing the gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
