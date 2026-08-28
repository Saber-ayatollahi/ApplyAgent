#!/usr/bin/env python3
"""backfill_unscored.py — Score tracker rows that never got a fit score.

Why this exists
---------------
Rows added ad-hoc via the UI tailor form (and any row whose LLM scoring
errored) land in the tracker with ``fit_score_numeric: 0``. That 0 is a
placeholder, not a verdict — but everything downstream (sorting, weekly
report, promote ranking, "needs attention") reads it as a real score of
zero, so genuinely strong roles sink to the bottom of every list.

This walks the tracker, finds those rows, scores each one through the same
``fit_scorer`` path the pipeline uses, and writes the result back **in
place** — preserving status, date_applied, outreach_log and follow-ups.

Cost: ~$0.001-0.01 per role. Results are cached, so re-runs are free.

Usage
-----
    python automation/backfill_unscored.py --dry-run     # list what would be scored
    python automation/backfill_unscored.py               # score them all
    python automation/backfill_unscored.py --limit 5     # score the first 5
    python automation/backfill_unscored.py --rescore     # bypass the fit cache
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "job_tracker_data.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_scorer  # noqa: E402
import score_url as _su  # noqa: E402

# Fields we are allowed to overwrite. Everything else on the row (status,
# date_applied, outreach_log, followup_schedule, ...) is the user's data
# and must survive untouched.
_FIT_FIELDS = (
    "fit_score", "fit_score_numeric", "fit_verdict", "fit_notes",
    "resume_variants", "primary_variant", "urgency", "next_action",
    "tier", "sector", "needs_scoring",
)


def _needs_scoring(job: dict) -> bool:
    """A row needs scoring if it has no real numeric score."""
    if job.get("archived"):
        return False
    if not (job.get("url") or job.get("portal_url")):
        return False
    if job.get("needs_scoring"):
        return True
    if str(job.get("fit_score", "")).lower() in ("unscored", "manual"):
        return True
    return int(job.get("fit_score_numeric") or 0) == 0


def _load_api_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    cfg = Path.home() / ".applyagent" / "config.json"
    if cfg.exists():
        try:
            k = json.loads(cfg.read_text(encoding="utf-8")).get("anthropic_api_key")
            if k:
                os.environ["ANTHROPIC_API_KEY"] = k
                return True
        except Exception:
            pass
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="List the rows that would be scored, then exit")
    ap.add_argument("--limit", type=int, default=0,
                    help="Only score the first N rows (0 = no limit)")
    ap.add_argument("--rescore", action="store_true",
                    help="Bypass the fit cache and force fresh LLM calls")
    args = ap.parse_args()

    tracker = json.loads(TRACKER.read_text(encoding="utf-8"))
    jobs = tracker.get("jobs", tracker if isinstance(tracker, list) else [])

    targets = [j for j in jobs if isinstance(j, dict) and _needs_scoring(j)]
    if args.limit:
        targets = targets[:args.limit]

    if not targets:
        print("Nothing to do — every tracker row has a fit score.")
        return 0

    print(f"{len(targets)} unscored row(s):\n")
    for j in targets:
        print(f"  [{j.get('status', '?'):<10}] {(j.get('company') or '')[:24]:<24} "
              f"{(j.get('title') or '')[:46]}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    if not _load_api_key():
        print("\nERROR: ANTHROPIC_API_KEY not set (env or ~/.applyagent/config.json)",
              file=sys.stderr)
        return 2
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 2

    # Back up before any mutation — same convention as the rest of the repo.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = TRACKER.with_suffix(f".bak.backfill_{stamp}.json")
    shutil.copy2(TRACKER, bak)
    print(f"\nBacked up tracker -> {bak.name}\n")

    client = Anthropic()
    scored = failed = 0

    for j in targets:
        url = (j.get("url") or j.get("portal_url") or "").strip()
        label = f"{j.get('company')} — {(j.get('title') or '')[:48]}"
        try:
            if args.rescore:
                cache = fit_scorer._cache_path_fit(url)
                if cache.exists():
                    cache.unlink()

            jd = fit_scorer.fetch_jd(url)
            if not jd or len(jd) < 200:
                print(f"  SKIP (thin/no JD: {len(jd or '')} chars)  {label}")
                failed += 1
                continue

            role = {
                "company": j.get("company") or _su._infer_company(url),
                "title": j.get("title") or "",
                "sector": j.get("sector") or _su._parse_sector_hint(j.get("company") or ""),
                "location": j.get("location", ""),
                "link": url,
                "source": "backfill_unscored",
            }
            fit = fit_scorer.score_with_llm(client, role, jd)

            num = int(fit.get("fit_score", fit.get("score", 0)) or 0)
            verdict = fit.get("verdict", "")
            variants = fit.get("resume_variants") or []

            j["fit_score_numeric"] = num
            j["fit_score"] = fit.get("fit_category") or fit.get("fit_score_label") or (
                "High" if num >= 7 else "Medium" if num >= 4 else "Low")
            j["fit_verdict"] = verdict
            j["fit_notes"] = ((fit.get("summary") or "")
                              + " | Reasons: "
                              + "; ".join(fit.get("top_3_reasons") or []))[:600]
            if variants:
                j["resume_variants"] = variants
                j.setdefault("primary_variant", variants[0])
            if fit.get("tier"):
                j["tier"] = fit["tier"]
            if role["sector"] and not j.get("sector"):
                j["sector"] = role["sector"]
            j["next_action"] = (fit.get("top_3_reasons") or [""])[0][:160]
            j.pop("needs_scoring", None)
            j["date_scored"] = date.today().isoformat()

            print(f"  {num:>2}/10  {label}")
            scored += 1
        except Exception as e:
            print(f"  FAIL ({type(e).__name__}: {e})  {label}", file=sys.stderr)
            failed += 1

    # Atomic write — temp + replace, so a torn file is impossible.
    tmp = TRACKER.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, TRACKER)

    print(f"\nDone — {scored} scored, {failed} skipped/failed. Backup: {bak.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
