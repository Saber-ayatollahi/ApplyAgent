#!/usr/bin/env python3
"""run_pipeline.py — Agentic end-to-end orchestrator.

Chains the full job-search pipeline in one process so the UI can launch a
single "Run pipeline" button instead of juggling three CLIs:

    [1] scrape   (jd_scraper.py)   ->  scan_<stamp>.json
    [2] score    (fit_scorer.py)   ->  scan_<stamp>_scored.json
    [3] promote  (auto_promote.py) ->  job_tracker_data.json updated

Each stage's stdout is streamed live, prefixed, and a machine-readable
status JSON is written alongside so the UI can show per-stage progress.

Usage:
    python run_pipeline.py                           # full scan + score + promote preview
    python run_pipeline.py --scrape-mode ats         # direct-ATS-only scrape
    python run_pipeline.py --skip-scrape --scan scan_v4.json
    python run_pipeline.py --commit-promote          # actually write tracker
    python run_pipeline.py --min-score 7 --include-watch

Scrape modes:
    full        scrape all targets incl. expansion (default, 20-40 min)
    core        core 77 targets only (15-30 min)
    ats         Workday+Greenhouse+Lever only (3-6 min, no LinkedIn)
    linkedin    LinkedIn guest search only (15-25 min)
    expansion   expansion list only (5-10 min)
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdio so emoji + unicode symbols (∪, ✓, ❌) don't crash on
# cp1252 Windows consoles. Without this, `print("scrape ∪ ...")` raises
# UnicodeEncodeError mid-pipeline and the run stalls in a half-finished
# state. reconfigure() is Python 3.7+; safe to call unconditionally.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
PIPELINE_DIR = OUT_DIR / "pipelines"

SCRAPE_MODE_ARGS = {
    "full":      ["--expansion"],
    "core":      [],
    "ats":       ["--workday-only"],
    "linkedin":  ["--linkedin-only"],
    "expansion": ["--expansion-only"],
}


def _stream(cmd: list[str], prefix: str, status: dict, stage: str) -> int:
    """Run cmd, stream output with prefix, update `status["stages"][stage]`.

    Previously this wrote to the FLAT `status[stage]` key, but every other
    call-site in this file (and the UI's `pipe["stages"][stage]` reader)
    expects the stage slot nested under `"stages"`. The mismatch silently
    truncated every real pipeline run: the scrape subprocess would finish
    cleanly, then the follow-up `status["stages"]["scrape"]["scan_file"] = ...`
    crashed with KeyError, leaving the pipeline dead and every downstream
    stage un-run. Ticketed as "phantom running state"."""
    status.setdefault("stages", {})
    status["stages"][stage] = {
        "cmd": cmd,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "state": "running",
    }
    _write_status(status)
    t0 = time.time()
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    last_line = ""
    assert proc.stdout is not None
    for line in proc.stdout:
        last_line = line.rstrip()
        print(f"[{prefix}] {last_line}", flush=True)
    rc = proc.wait()
    status["stages"][stage].update({
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(time.time() - t0, 1),
        "returncode": rc,
        "last_line": last_line,
        "state": "finished" if rc == 0 else "failed",
    })
    _write_status(status)
    return rc


def _write_status(status: dict):
    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    status_path = PIPELINE_DIR / f"pipeline_{status['pipeline_id']}.json"
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")


def _find_latest_scan() -> Path | None:
    files = sorted(OUT_DIR.glob("scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    files = [f for f in files if "_scored" not in f.name]
    return files[0] if files else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scrape-mode", choices=list(SCRAPE_MODE_ARGS), default="full",
                    help="Which scrape strategy to run (default: full).")
    ap.add_argument("--sector", help="Pass-through: limit scrape to this sector (substring).")
    ap.add_argument("--company", help="Pass-through: limit scrape to this single company.")

    ap.add_argument("--skip-scrape", action="store_true",
                    help="Don't scrape; score an existing scan file.")
    ap.add_argument("--skip-score", action="store_true",
                    help="Only scrape; don't score.")
    ap.add_argument("--skip-promote", action="store_true",
                    help="Scrape + score; don't run auto-promote.")
    ap.add_argument("--scan", help="When --skip-scrape: filename of existing scan in outputs/.")

    # Scorer options
    ap.add_argument("--score-limit", type=int, default=0, help="Cap scored count (0=all).")
    ap.add_argument("--score-concurrency", type=int, default=6)
    ap.add_argument("--score-dry-run", action="store_true",
                    help="Rule-stage only, no LLM calls.")

    # Promote options
    ap.add_argument("--min-score", type=int, default=7)
    ap.add_argument("--include-watch", action="store_true")
    ap.add_argument("--commit-promote", action="store_true",
                    help="Write tracker. Without this flag, promote is dry-run preview.")

    args = ap.parse_args()

    # Preflight the Anthropic API if this run will actually call the LLM.
    # Catches revoked/stale/empty-credit keys BEFORE we burn 15 min scraping
    # and then fail every scorer worker. Skip when the scorer itself is
    # skipped or running in dry-run mode (neither calls the LLM).
    will_call_llm = (not args.skip_score and not args.score_dry_run) \
        or (not args.skip_promote and not args.skip_score)
    if will_call_llm:
        try:
            from api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
        except ImportError:
            try:
                from .api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
            except Exception:
                _cli_preflight = None  # type: ignore
        if _cli_preflight is not None:
            _cli_preflight(module="run_pipeline")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pipeline_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    status = {
        "pipeline_id": pipeline_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "args": vars(args),
        "state": "running",
        "stages": {},
    }
    _write_status(status)

    print(f"=== ApplyAgent pipeline {pipeline_id} ===", flush=True)
    print(f"Mode: scrape={args.scrape_mode} skip_scrape={args.skip_scrape} "
          f"skip_score={args.skip_score} skip_promote={args.skip_promote}", flush=True)

    # Guard: if anything crashes or the user Ctrl-Cs, mark the pipeline
    # "crashed" instead of leaving state=running forever. The UI and
    # scan_runner both use state=running as an "actively working" signal;
    # a stuck status file produces phantom banners and disables buttons
    # for days. try/finally catches KeyError, KeyboardInterrupt, SystemExit
    # (via except BaseException) so even kill-tree can't leave zombies.
    try:
        return _run(args, status, pipeline_id)
    except BaseException as e:
        if status.get("state") == "running":
            status["state"] = "crashed"
            status["crashed_at"] = datetime.now().isoformat(timespec="seconds")
            status["crash_reason"] = f"{type(e).__name__}: {str(e)[:300]}"
            _write_status(status)
            print(f"\n[pipeline] ❌ CRASHED: {status['crash_reason']}", flush=True)
        raise


def _run(args, status: dict, pipeline_id: str) -> int:
    # Worklist contract: every stage operates on worklist.json (the deduped
    # union of latest web scrape + recent Gmail harvests). The pipeline
    # rebuilds the worklist between scrape and score so the scorer always
    # sees a fresh, provenance-tagged pool. See automation/worklist.py.
    try:
        import worklist  # type: ignore
    except ImportError:
        from . import worklist  # type: ignore

    # -------- [1] SCRAPE --------
    if args.skip_scrape:
        # No new scrape — the worklist will fold whatever scrape already
        # exists. If --scan was passed, we honor it as a one-off override
        # at score time (see stage 2).
        print("[stage 1] SKIPPED (using existing scrape inputs)", flush=True)
        status["stages"]["scrape"] = {"state": "skipped"}
        _write_status(status)
    else:
        cmd = [sys.executable, str(ROOT / "automation" / "jd_scraper.py")]
        cmd += SCRAPE_MODE_ARGS[args.scrape_mode]
        if args.sector:
            cmd += ["--sector", args.sector]
        if args.company:
            cmd += ["--company", args.company]
        rc = _stream(cmd, "scrape", status, "scrape")
        if rc != 0:
            status["state"] = "failed"
            _write_status(status)
            return rc
        latest = _find_latest_scan()
        if latest:
            status["stages"]["scrape"]["scan_file"] = latest.name
            try:
                d = json.loads(latest.read_text(encoding="utf-8"))
                status["stages"]["scrape"]["candidate_count"] = len(d.get("results", []))
            except Exception:
                pass
            _write_status(status)

    # -------- [1.5] REBUILD WORKLIST --------
    # The single merge surface. Folds latest scrape + 30d Gmail pool into
    # worklist.json. Idempotent — safe to call even if the scrape stage
    # was skipped or if no new files arrived.
    print("[stage 1.5] Rebuilding worklist (scrape ∪ recent Gmail pool)...", flush=True)
    try:
        wstats = worklist.rebuild()
        status["stages"]["worklist"] = {
            "state": "finished",
            "rows": wstats.get("total", 0),
            "scrape_only": wstats.get("scrape", 0),
            "gmail_only": wstats.get("gmail", 0),
            "both": wstats.get("both", 0),
            "new_since_last_score": wstats.get("new_since_last_score", 0),
        }
        print(f"[worklist] {wstats['total']} rows "
              f"({wstats['scrape']} scrape, {wstats['gmail']} gmail, "
              f"{wstats['both']} both) · "
              f"{wstats['new_since_last_score']} new since last score",
              flush=True)
    except Exception as e:
        status["stages"]["worklist"] = {"state": "failed", "error": str(e)[:300]}
        print(f"[worklist] REBUILD FAILED: {e}", flush=True)
        status["state"] = "failed"
        _write_status(status)
        return 4
    _write_status(status)

    # -------- [2] SCORE --------
    # Always score worklist.json (or args.scan if explicitly provided).
    score_target = args.scan or "worklist.json"
    score_target_path = OUT_DIR / score_target
    if args.skip_score:
        print("[stage 2] SKIPPED", flush=True)
        status["stages"]["score"] = {"state": "skipped"}
        _write_status(status)
    else:
        if not score_target_path.exists():
            print(f"ERROR: score target {score_target} not found.", flush=True)
            status["state"] = "failed"
            _write_status(status)
            return 2
        cmd = [sys.executable, str(ROOT / "automation" / "fit_scorer.py"),
               "--scan", score_target,
               "--concurrency", str(args.score_concurrency)]
        if args.score_limit:
            cmd += ["--limit", str(args.score_limit)]
        if args.score_dry_run:
            cmd.append("--dry-run")
        rc = _stream(cmd, "score", status, "score")
        if rc != 0:
            status["state"] = "failed"
            _write_status(status)
            return rc
        scored_path = OUT_DIR / (score_target_path.stem + "_scored.json")
        if scored_path.exists():
            status["stages"]["score"]["scored_file"] = scored_path.name
            try:
                d = json.loads(scored_path.read_text(encoding="utf-8"))
                status["stages"]["score"]["scored_count"] = d.get("stage2_scored", 0)
                verdicts: dict = {}
                for r in d.get("results", []):
                    v = (r.get("fit") or {}).get("fit_verdict", "?")
                    verdicts[v] = verdicts.get(v, 0) + 1
                status["stages"]["score"]["verdicts"] = verdicts
            except Exception:
                pass
            _write_status(status)

    # -------- [3] PROMOTE --------
    if args.skip_promote:
        print("[stage 3] SKIPPED", flush=True)
        status["stages"]["promote"] = {"state": "skipped"}
    else:
        # Default to worklist_scored.json (or the matching companion of
        # whatever score_target was used). auto_promote.py also defaults
        # to worklist_scored.json on its own if --scan is omitted.
        scored_companion = OUT_DIR / (score_target_path.stem + "_scored.json")
        if scored_companion.exists():
            target_scored = scored_companion
        else:
            ws = worklist.effective_scored()
            if ws is None:
                print("[stage 3] FAILED — no scored scan available to promote.",
                      flush=True)
                status["state"] = "failed"
                _write_status(status)
                return 1
            target_scored = ws
        cmd = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
               "--scan", target_scored.name,
               "--min-score", str(args.min_score)]
        if args.include_watch:
            cmd.append("--include-watch")
        if args.commit_promote:
            cmd.append("--commit")
        rc = _stream(cmd, "promote", status, "promote")
        if rc != 0:
            status["state"] = "failed"
            _write_status(status)
            return rc
        status["stages"]["promote"]["committed"] = bool(args.commit_promote)

    status["state"] = "finished"
    status["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_status(status)
    print(f"\n=== Pipeline {pipeline_id} complete ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
