#!/usr/bin/env python3
"""scan_delta.py — Find jobs that appeared in TODAY's scan but not in a prior one.

Part of the nightly-brief flow. After jd_scraper runs, this diffs against the
prior scan and emits:
  automation/outputs/delta_<today>.json         # new roles (full rows)
  automation/outputs/delta_<today>.md           # human-readable summary

Dedup is on `link` (the most stable identifier; titles drift on LinkedIn).

Usage:
    python scan_delta.py                              # today vs. prior scan
    python scan_delta.py --current scan_20260504.json --baseline scan_20260503.json
    python scan_delta.py --lookback-days 3            # delta vs. 3-day-ago scan
    python scan_delta.py --lookback-days 7            # weekly delta

Exit codes:
  0  success, delta file written (even if empty)
  1  no current scan found
  2  only one scan exists (can't compute delta)
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"


def _list_scans() -> list[Path]:
    files = sorted(OUT_DIR.glob("scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [f for f in files if "_scored" not in f.name]


def _latest_current() -> Path | None:
    scans = _list_scans()
    return scans[0] if scans else None


def _pick_baseline(current: Path, lookback_days: int) -> Path | None:
    """Pick the scan that is closest to (current_mtime - lookback_days) without
    being the current file itself."""
    scans = _list_scans()
    # Remove current file from candidates
    scans = [s for s in scans if s != current]
    if not scans:
        return None
    target_mtime = current.stat().st_mtime - lookback_days * 86400
    # Pick the scan with mtime closest to target, but strictly older than current
    older = [s for s in scans if s.stat().st_mtime < current.stat().st_mtime]
    if not older:
        return None
    older.sort(key=lambda s: abs(s.stat().st_mtime - target_mtime))
    return older[0]


def compute_delta(current: dict, baseline: dict) -> dict:
    """Pure function: return {new_jobs, removed_jobs, persisting} for testing."""
    cur_links = {r.get("link"): r for r in current.get("results", []) if r.get("link")}
    base_links = {r.get("link"): r for r in baseline.get("results", []) if r.get("link")}
    new_links = set(cur_links) - set(base_links)
    removed_links = set(base_links) - set(cur_links)
    return {
        "new_jobs": [cur_links[l] for l in new_links],
        "removed_jobs": [base_links[l] for l in removed_links],
        "persisting_count": len(set(cur_links) & set(base_links)),
    }


def _render_md(delta: dict, current: Path, baseline: Path) -> str:
    new_jobs = delta["new_jobs"]
    removed = delta["removed_jobs"]
    lines = [
        f"# Scan delta — {current.name} vs {baseline.name}",
        "",
        f"- **{len(new_jobs)}** new postings since baseline",
        f"- **{len(removed)}** postings removed/expired since baseline",
        f"- **{delta['persisting_count']}** carried over",
        "",
    ]
    if new_jobs:
        lines += [
            "## New postings (ranked by stage-1 triage score)",
            "",
            "| Score | Sector | Company | Title | Source | Location | Link |",
            "|---|---|---|---|---|---|---|",
        ]
        # Lazy-import so this script works even if fit_scorer has a syntax issue
        try:
            sys.path.insert(0, str(ROOT / "automation"))
            from fit_scorer import rule_triage
            for j in sorted(new_jobs,
                            key=lambda r: -rule_triage(r.get("title", "")).get("score", 0)):
                tri = rule_triage(j.get("title", ""))
                link = j.get("link", "")
                lines.append(
                    f"| {tri.get('score', 0)} | {j.get('sector', '')} | "
                    f"{j.get('company', '')} | {j.get('title', '')[:60].replace('|', '/')} | "
                    f"{j.get('source', '')} | {j.get('location', '')[:30]} | "
                    f"[open]({link}) |"
                )
        except Exception:
            for j in new_jobs:
                lines.append(
                    f"|  | {j.get('sector', '')} | {j.get('company', '')} | "
                    f"{j.get('title', '')[:60].replace('|', '/')} | "
                    f"{j.get('source', '')} | {j.get('location', '')[:30]} | "
                    f"[open]({j.get('link', '')}) |"
                )
    if removed:
        lines += ["", "## Removed/expired", ""]
        for j in removed[:20]:
            lines.append(f"- {j.get('company', '')}: {j.get('title', '')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--current", help="Filename in outputs/ of today's scan.")
    ap.add_argument("--baseline", help="Filename in outputs/ of the prior scan.")
    ap.add_argument("--lookback-days", type=int, default=1,
                    help="How far back to pick baseline (default: 1 = yesterday).")
    args = ap.parse_args()

    # Resolve current
    if args.current:
        current_path = OUT_DIR / args.current
    else:
        current_path = _latest_current()
    if not current_path or not current_path.exists():
        print("ERROR: no current scan found (expected scan_*.json in outputs/).",
              file=sys.stderr)
        return 1

    # Resolve baseline
    if args.baseline:
        baseline_path = OUT_DIR / args.baseline
    else:
        baseline_path = _pick_baseline(current_path, args.lookback_days)
    if not baseline_path or not baseline_path.exists() or baseline_path == current_path:
        print(f"WARN: no baseline scan available (need a prior scan_*.json older "
              f"than {current_path.name}). First-run = all roles are 'new'.",
              file=sys.stderr)
        # Treat as empty baseline — everything is new
        baseline = {"results": []}
        baseline_name = "(none)"
    else:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_name = baseline_path.name

    current = json.loads(current_path.read_text(encoding="utf-8"))
    delta = compute_delta(current, baseline)

    stamp = datetime.now().strftime("%Y%m%d")
    out_json = OUT_DIR / f"delta_{stamp}.json"
    out_md = OUT_DIR / f"delta_{stamp}.md"

    payload = {
        "delta_date": stamp,
        "current_scan": current_path.name,
        "baseline_scan": baseline_name,
        "new_count": len(delta["new_jobs"]),
        "removed_count": len(delta["removed_jobs"]),
        "persisting_count": delta["persisting_count"],
        "new_jobs": delta["new_jobs"],
        "removed_jobs": delta["removed_jobs"],
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(
        _render_md(delta, current_path,
                    baseline_path if baseline_path else current_path),
        encoding="utf-8",
    )

    print(f"[scan_delta] {len(delta['new_jobs'])} new, "
          f"{len(delta['removed_jobs'])} removed, "
          f"{delta['persisting_count']} persisting.", file=sys.stderr)
    print(f"[scan_delta] Wrote {out_json.name} + {out_md.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
