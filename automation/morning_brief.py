#!/usr/bin/env python3
"""morning_brief.py — Rank today's fresh jobs and emit a top-N brief.

Part of the nightly flow:
  jd_scraper -> scan_delta -> morning_brief -> Dashboard widget

This script:
  1. Loads the most recent delta_<YYYYMMDD>.json (jobs new vs yesterday)
  2. Scores the NEW jobs only via fit_scorer (respects the fit_cache so
     roles already scored are free)
  3. Writes brief_<YYYYMMDD>.json + brief_<YYYYMMDD>.md with the top-N
     apply_now / tailor_and_apply candidates ranked by (fit_score, tier)

Cost-controlled: only scores delta (~20-50 roles/day instead of 1,500).
Estimated $0.01-0.05 per run at haiku prices.

Usage:
    python morning_brief.py                      # auto-pick latest delta, top 5
    python morning_brief.py --top 3
    python morning_brief.py --delta delta_20260504.json --top 5
    python morning_brief.py --no-score           # skip LLM, use cached fits only
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"


def _latest_delta() -> Path | None:
    files = sorted(OUT_DIR.glob("delta_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _score_delta_inline(delta_jobs: list[dict], concurrency: int = 4,
                          dry_run: bool = False) -> list[dict]:
    """Run fit_scorer's scoring loop on just the delta jobs. Reuses the cache
    and triage logic. Returns the scored roles."""
    sys.path.insert(0, str(ROOT / "automation"))
    import fit_scorer as fs

    # Stage 1 — rule triage
    triaged = []
    for r in delta_jobs:
        tri = fs.rule_triage(r.get("title", ""))
        r["_triage"] = tri
        if tri["stage1_pass"]:
            triaged.append(r)

    print(f"[morning_brief] delta={len(delta_jobs)} -> triaged={len(triaged)}",
          file=sys.stderr)

    if dry_run or not triaged:
        return triaged

    try:
        import anthropic  # type: ignore
    except ImportError:
        print("[morning_brief] anthropic SDK missing — skipping LLM stage",
              file=sys.stderr)
        return triaged

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[morning_brief] ANTHROPIC_API_KEY not set — skipping LLM stage",
              file=sys.stderr)
        return triaged

    # API preflight: same fail-fast contract as fit_scorer/jd_tailor. Without
    # this, a revoked key lets the brief loop through every triaged role,
    # producing a full sweep of error verdicts before reporting.
    try:
        from api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
        _cli_preflight(module="morning_brief")
    except Exception:
        pass

    # Wire cost_guard into the scorer's module-global so score_with_llm
    # honors the daily/per-run caps. Without this, a runaway brief loop
    # could dodge the daily cap that fit_scorer enforces.
    try:
        from cost_guard import CostGuard as _CostGuard  # type: ignore
        if fs._cost_guard is None:
            fs._cost_guard = _CostGuard.from_env()
            fs._cost_guard.preflight_or_exit()
            print(f"[morning_brief] {fs._cost_guard.summary()}", file=sys.stderr)
    except Exception:
        pass

    client = anthropic.Anthropic()

    # Score each triaged role. Reuse fit_cache, so previously-scored roles are free.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    fs.progress_begin("morning_brief", len(triaged))
    import time
    t0 = time.time()
    scored: list[dict] = []

    def score_one(r):
        from_cache = fs._cache_path_fit(r["link"]).exists()
        try:
            jd = fs.fetch_jd(r["link"])
            r["_jd_len"] = len(jd)
            r["fit"] = fs.score_with_llm(client, r, jd)
        except Exception as e:
            r["fit"] = {"fit_score": 0, "fit_verdict": "error",
                        "summary": f"scoring error: {e}"[:200]}
            return r, from_cache, True
        return r, from_cache, False

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(score_one, r) for r in triaged]
        for i, fut in enumerate(as_completed(futures), 1):
            r, from_cache, err = fut.result()
            scored.append(r)
            fs.progress_tick(r, from_cache, err, t0)
    fs.progress_end("finished")
    return scored


def _rank_and_filter(scored: list[dict]) -> list[dict]:
    """Rank by (fit_verdict priority, fit_score desc, tier asc)."""
    verdict_priority = {"apply_now": 0, "tailor_and_apply": 1,
                         "watch": 2, "skip": 3, "error": 4}

    def _key(r):
        f = r.get("fit") or {}
        return (
            verdict_priority.get(f.get("fit_verdict", "skip"), 5),
            -f.get("fit_score", 0),
            f.get("tier", 4),
        )
    return sorted(scored, key=_key)


def _render_md(top: list[dict], total: int, delta_file: str,
                 brief_date: str) -> str:
    lines = [
        f"# 🌅 Morning brief — {brief_date}",
        "",
        f"_Source delta: `{delta_file}` · {total} fresh candidates triaged_",
        "",
    ]
    if not top:
        lines += ["_No fresh matches above threshold today. Check again tomorrow._", ""]
        return "\n".join(lines)

    lines += [f"## Top {len(top)} fresh matches", ""]
    for i, r in enumerate(top, 1):
        f = r.get("fit") or {}
        variants = f.get("applicable_resume_variants") or []
        variants_str = " · ".join(variants) if variants else "—"
        lines += [
            f"### {i}. [{f.get('fit_score', '?')}/10 · {f.get('fit_verdict', '?')} · "
            f"Tier {f.get('tier', '?')}] {r.get('company', '')} — {r.get('title', '')}",
            "",
            f"**Lead-with resume:** {variants_str}  ",
            f"**Sector:** {r.get('sector', '')}  ·  **Location:** {r.get('location', '')}  ·  "
            f"**Source:** {r.get('source', '')}",
            "",
            f"**Summary:** {f.get('summary', '')}",
            "",
        ]
        reasons = f.get("top_3_reasons") or []
        if reasons:
            lines += ["**Why it fits:**"]
            for reason in reasons:
                lines += [f"- {reason}"]
            lines += [""]
        gaps = f.get("skill_gaps") or []
        if gaps:
            lines += ["**Gaps to acknowledge:** " + "; ".join(gaps), ""]
        lines += [f"🔗 [Open posting]({r.get('link', '')})", "", "---", ""]
    return "\n".join(lines)


def _auto_add_to_tracker(top_actionable: list[dict], max_add: int) -> list[str]:
    """Add top-K actionable roles to the tracker as Found/Watch entries.
    Returns the list of new tracker IDs added (or []).
    Idempotent: skips URLs already in the tracker.

    Uses safe_json.mutate_json so the read-build-write happens inside an
    exclusive file lock — a concurrent UI edit or auto_promote run won't
    clobber our additions (and vice versa)."""
    tracker_path = ROOT / "data" / "job_tracker_data.json"
    if not tracker_path.exists():
        return []

    today_iso = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%Y%m%d")
    added_ids: list[str] = []

    def _mutator(tr: dict) -> dict:
        if not isinstance(tr, dict) or "jobs" not in tr:
            return tr  # bail; safe_json will re-persist as-is
        existing_urls = {j.get("url") for j in tr.get("jobs", []) if j.get("url")}
        existing_ids = {j["id"] for j in tr["jobs"]}
        for r in top_actionable[:max_add]:
            f = r.get("fit") or {}
            url = r.get("link")
            if not url or url in existing_urls:
                continue
            verdict = f.get("fit_verdict")
            if verdict not in ("apply_now", "tailor_and_apply"):
                continue
            new_id = f"brief-{stamp}-{len(added_ids) + 1:02d}"
            while new_id in existing_ids:
                new_id = new_id + "a"
            variants = f.get("applicable_resume_variants") or []
            num_score = int(f.get("fit_score") or 0)
            fit_category = ("High" if num_score >= 8
                             else ("Medium" if num_score >= 6 else "Low"))
            tr["jobs"].append({
                "id": new_id,
                "company": r.get("company", ""),
                "title": r.get("title", ""),
                "sector": r.get("sector", ""),
                "location": r.get("location", ""),
                "url": url,
                "source": r.get("source", ""),
                "tier": f.get("tier", 3),
                "fit_score": fit_category,
                "fit_score_numeric": num_score,
                "fit_verdict": verdict,
                "fit_notes": f.get("summary", ""),
                "resume_variants": variants,
                "primary_variant": variants[0] if variants else "",
                "status": "Found" if verdict == "apply_now" else "Watch",
                "urgency": "High" if verdict == "apply_now" else "Medium",
                "date_found": today_iso,
                "posted_date": r.get("posted_date"),
                "next_action": (f.get("top_3_reasons") or [""])[0][:160],
                "followup_schedule": {"next_due": None, "cadence_days": [3, 10, 21]},
                "outreach_log": [],
            })
            added_ids.append(new_id)
            existing_ids.add(new_id)
            existing_urls.add(url)
        return tr

    # Try the locked path first; fall back to legacy if safe_json unavailable.
    try:
        from safe_json import mutate_json  # type: ignore
        # Backup before mutating (matches previous semantics).
        if any(True for _ in top_actionable[:max_add]):
            import shutil
            bak = tracker_path.with_suffix(f".bak.auto_brief_{stamp}.json")
            shutil.copy2(tracker_path, bak)
        mutate_json(tracker_path, _mutator)
    except ImportError:
        tr = json.loads(tracker_path.read_text(encoding="utf-8"))
        _mutator(tr)
        if added_ids:
            import shutil
            bak = tracker_path.with_suffix(f".bak.auto_brief_{stamp}.json")
            shutil.copy2(tracker_path, bak)
            # Inline atomic fallback — same shape as safe_json._atomic_write
            # but without the cross-process lock. Better than a raw write_text
            # which truncates on crash.
            import os as _os, tempfile as _tf
            fd, tmp = _tf.mkstemp(prefix=tracker_path.name + ".", suffix=".tmp",
                                   dir=str(tracker_path.parent))
            try:
                with _os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(tr, f, indent=2)
                    f.flush()
                    _os.fsync(f.fileno())
                _os.replace(tmp, tracker_path)
            except Exception:
                try: _os.unlink(tmp)
                except OSError: pass
                raise
    return added_ids


def _spawn_tailors(job_ids: list[str]) -> None:
    """Fire-and-forget tailor subprocess per job_id. Logs land in outputs/."""
    if not job_ids:
        return
    import subprocess
    tailor_py = ROOT / "automation" / "jd_tailor.py"
    for jid in job_ids:
        log_path = OUT_DIR / f"tailor_{jid}_stdout.log"
        cmd = [sys.executable, str(tailor_py), "--job-id", jid]
        try:
            _lf = open(log_path, "wb")
            try:
                subprocess.Popen(
                    cmd,
                    stdout=_lf,
                    stderr=subprocess.STDOUT,
                    cwd=str(ROOT),
                )
            finally:
                try: _lf.close()
                except Exception: pass
            print(f"  [brief->tailor] spawned for {jid}", file=sys.stderr)
        except Exception as e:
            print(f"  [brief->tailor] failed for {jid}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delta", help="Filename of delta_<date>.json in outputs/")
    ap.add_argument("--top", type=int, default=5, help="How many to include in the brief")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-score", action="store_true",
                    help="Don't call the LLM; just rank stage-1 triage by score")
    ap.add_argument("--auto-add", type=int, default=0, metavar="K",
                    help="After ranking, auto-add the top K actionable roles to the "
                         "tracker. 0 = disabled (default).")
    ap.add_argument("--auto-tailor", action="store_true",
                    help="After auto-add, spawn jd_tailor for each added role. "
                         "Only effective with --auto-add > 0.")
    args = ap.parse_args()

    delta_path = (OUT_DIR / args.delta) if args.delta else _latest_delta()
    if not delta_path or not delta_path.exists():
        print("ERROR: no delta_*.json found. Run scan_delta.py first.", file=sys.stderr)
        return 1

    delta_payload = json.loads(delta_path.read_text(encoding="utf-8"))
    new_jobs = delta_payload.get("new_jobs") or []
    print(f"[morning_brief] Loaded {len(new_jobs)} new jobs from {delta_path.name}",
          file=sys.stderr)

    scored = _score_delta_inline(new_jobs, concurrency=args.concurrency,
                                   dry_run=args.no_score)

    ranked = _rank_and_filter(scored)
    # Only "actionable" roles make the brief (apply_now or tailor_and_apply)
    actionable = [r for r in ranked
                  if (r.get("fit") or {}).get("fit_verdict") in
                  ("apply_now", "tailor_and_apply")]
    top = actionable[: args.top]

    brief_date = datetime.now().strftime("%Y%m%d")
    out_json = OUT_DIR / f"brief_{brief_date}.json"
    out_md = OUT_DIR / f"brief_{brief_date}.md"

    # Count scoring errors so UI can tell "API failed" from "quiet day"
    error_count = sum(1 for r in scored
                      if (r.get("fit") or {}).get("fit_verdict") == "error")
    sample_errors = [
        (r.get("fit") or {}).get("summary", "")
        for r in scored
        if (r.get("fit") or {}).get("fit_verdict") == "error"
    ][:3]

    payload = {
        "brief_date": brief_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "delta_file": delta_path.name,
        "total_new": len(new_jobs),
        "triaged": sum(1 for r in scored if (r.get("_triage") or {}).get("stage1_pass")),
        "scored": len([r for r in scored if r.get("fit")]),
        "actionable": len(actionable),
        "error_count": error_count,
        "sample_errors": sample_errors,
        "top": top,
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(
        _render_md(top, total=len(new_jobs), delta_file=delta_path.name,
                    brief_date=brief_date),
        encoding="utf-8",
    )

    print(f"[morning_brief] actionable={len(actionable)}, top-{len(top)} selected. "
          f"Wrote {out_json.name} + {out_md.name}", file=sys.stderr)

    # Optional: auto-add top-K to tracker
    if args.auto_add > 0 and actionable:
        added = _auto_add_to_tracker(actionable, args.auto_add)
        if added:
            print(f"[morning_brief] Auto-added {len(added)} role(s) to tracker: "
                  f"{', '.join(added)}", file=sys.stderr)
            payload["auto_added_ids"] = added
            out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            if args.auto_tailor:
                _spawn_tailors(added)
                print(f"[morning_brief] Spawned {len(added)} tailor subprocess(es).",
                      file=sys.stderr)
        else:
            print(f"[morning_brief] Auto-add: nothing to add (duplicates or none "
                  f"actionable).", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
