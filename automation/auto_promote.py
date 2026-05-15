#!/usr/bin/env python3
"""
auto_promote.py — Promote scored scan results to tracker; expire stale URLs.

Reads:
    automation/outputs/scan_v4_scored.json  (fit_scorer output)
    job_tracker_data.json
Writes:
    job_tracker_data.json (backed up to .bak.YYYY-MM-DD first)
    automation/outputs/promote_report_YYYYMMDD.md

Rules:
  - Promote verdict=apply_now    -> status=Found, tier=1, urgency=High
  - Promote verdict=tailor_and_apply -> status=Watch, tier=2, urgency=Medium
  - Skip verdict=watch/skip unless --include-watch
  - Dedupe by URL; don't overwrite existing tracker entries; merge fit fields only
  - Expiry detection: every existing tracker entry with source=scraper_v2+v3_tier1 or
    source starting with 'scraper_' whose URL is not in the latest scan OR latest
    scored set -> status=Expired (unless it's already Applied/Screen/Onsite/Offer)

Usage:
    python auto_promote.py                      # dry run: print what would happen
    python auto_promote.py --commit             # write the tracker
    python auto_promote.py --commit --min-score 8
    python auto_promote.py --commit --include-watch --min-score 6
    python auto_promote.py --scan scan_v4.json  # alternative source
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

# Cross-process-safe tracker reads/writes. Degrades to plain json if unavailable.
try:
    from safe_json import read_json as _sj_read, write_json as _sj_write  # type: ignore
except ImportError:
    _sj_read = None  # type: ignore
    _sj_write = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
TRACKER = ROOT / "data" / "job_tracker_data.json"


SECTOR_ROUGH_TIER = {
    "Canadian Big 6 Banks": 1,
    "Canadian Pension Funds": 1,
    "US & Global Asset Managers": 2,
    "Analytics & Risk Vendors": 2,
    "Canadian Insurers": 2,
    "Big 4 Risk Advisory": 3,
    "Pension/ALM Consulting": 3,
    "US Banks (Toronto)": 3,
    "Canadian Asset Managers": 3,
    "Mid Canadian Banks": 2,
    "FS Strategy Consulting": 3,
    "Fintech": 4,
    "Regulators & Crown": 3,
    "Market Infrastructure": 4,
    "Fund Admin/Custody": 4,
    "Mortgage Lenders": 4,
    "Hedge Funds / Alt AM": 4,
    "Private Credit": 4,
}

VERDICT_DEFAULTS = {
    "apply_now":        {"status": "Found", "urgency": "High",   "default_tier": 1},
    "tailor_and_apply": {"status": "Watch", "urgency": "Medium", "default_tier": 2},
    "watch":            {"status": "Watch", "urgency": "Low",    "default_tier": 3},
    "skip":             None,
}


def slugify(s: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n] or "role"


def make_entry(r: dict) -> dict:
    f = r.get("fit") or {}
    verdict = f.get("fit_verdict") or "skip"
    defaults = VERDICT_DEFAULTS.get(verdict) or {}
    fit_tier = f.get("tier") or defaults.get("default_tier") or 3
    sector_tier = SECTOR_ROUGH_TIER.get(r.get("sector", ""), 4)
    final_tier = min(fit_tier, sector_tier)

    co = r["company"]
    co_slug = slugify(co, 20)
    title_slug = slugify(r["title"], 30)
    _id = f"auto-{co_slug}-{title_slug}"

    variants = f.get("applicable_resume_variants") or []
    primary_variant = variants[0] if variants else ""

    return {
        "id": _id,
        "company": co,
        "sector": r.get("sector", ""),
        "tier": final_tier,
        "title": r["title"],
        "level": "",
        "location": r.get("location", ""),
        "url": r["link"],
        "portal_url": r["link"].split("?")[0].rsplit("/", 1)[0] + "/",
        "date_found": date.today().isoformat(),
        "date_jd_verified": date.today().isoformat() if r.get("_jd_len", 0) > 200 else None,
        "date_applied": None,
        "date_last_followup": None,
        "source": "scraper+fit_scorer",
        "status": defaults.get("status", "Watch"),
        "fit_score": "High" if f.get("fit_score", 0) >= 8 else "Medium" if f.get("fit_score", 0) >= 6 else "Low",
        "fit_score_numeric": int(f.get("fit_score", 0)),
        "resume_variants": variants,
        "primary_variant": primary_variant,
        "urgency": defaults.get("urgency", "Low"),
        "expected_comp_band_cad": "",
        "fit_notes": f.get("summary", "") + " | Top reasons: " + "; ".join(f.get("top_3_reasons", [])[:3]),
        "keywords": [],
        "resume_file": None,
        "cover_letter_file": None,
        "contact": {"recruiter_name": None, "recruiter_email": None,
                    "hiring_manager_name": None, "hiring_manager_linkedin": None,
                    "warm_intro_candidate": None, "moodys_alumni_at_target": None},
        "outreach_log": [],
        "followup_schedule": {"next_due": None, "cadence_days": [3, 10, 21]},
        "rejection_reason": None,
        "rejection_date": None,
        "next_action": "Verify JD live; tailor; find warm intro before submit." if verdict == "apply_now"
                       else "Monitor. Revisit in weekly scan.",
        "notes": f"auto-promoted {date.today().isoformat()} | verdict={verdict} | "
                 f"skill_gaps={f.get('skill_gaps', [])}",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=None,
                    help="Filename in automation/outputs/ of the scored scan to promote. "
                         "If omitted, picks the freshest scan_YYYYMMDD_scored.json.")
    ap.add_argument("--commit", action="store_true", help="Actually write the tracker")
    ap.add_argument("--min-score", type=int, default=7,
                    help="Only promote roles with fit_score >= this (default 7)")
    ap.add_argument("--include-watch", action="store_true",
                    help="Include verdict=watch roles")
    ap.add_argument("--expire-stale", action="store_true",
                    help="Mark tracker entries with auto-* IDs as Expired if not in scan")
    ap.add_argument("--auto-tailor", action="store_true",
                    help="After commit, spawn jd_tailor.py for each new Tier-1 role "
                         "(outputs land in outputs/ as <company>_<role>_<date>_prompt.md). "
                         "Ignored in dry-run.")
    args = ap.parse_args()

    if not args.scan:
        # Old default was scan_v4_scored.json — retired. Pick the freshest
        # scan_YYYYMMDD_scored.json so running standalone Just Works.
        candidates = sorted(
            (p for p in OUT_DIR.glob("scan_*_scored.json")
             if p.stem.replace("scan_", "").replace("_scored", "").isdigit()),
            reverse=True,
        )
        if not candidates:
            print("ERROR: no scan_YYYYMMDD_scored.json in outputs/. Run fit_scorer.py first.",
                  file=sys.stderr)
            return 1
        args.scan = candidates[0].name
        print(f"[auto_promote] No --scan supplied; using latest: {args.scan}",
              file=sys.stderr)
    scored_path = OUT_DIR / args.scan
    if not scored_path.exists():
        print(f"ERROR: {scored_path} not found. Run fit_scorer.py first.", file=sys.stderr)
        return 1

    scored = json.loads(scored_path.read_text(encoding="utf-8"))
    if _sj_read is not None:
        tr = _sj_read(TRACKER, default={"jobs": [], "meta": {}})
    else:
        tr = json.loads(TRACKER.read_text(encoding="utf-8"))

    existing_by_url = {j["url"]: j for j in tr["jobs"] if j.get("url")}
    existing_ids = {j["id"] for j in tr["jobs"]}
    added, updated, skipped_dupe, skipped_verdict, skipped_score = 0, 0, 0, 0, 0

    new_entries = []
    for r in scored.get("results", []):
        f = r.get("fit") or {}
        verdict = f.get("fit_verdict") or "skip"
        score = int(f.get("fit_score") or 0)
        if verdict not in VERDICT_DEFAULTS or VERDICT_DEFAULTS[verdict] is None:
            skipped_verdict += 1
            continue
        if verdict == "watch" and not args.include_watch:
            skipped_verdict += 1
            continue
        if score < args.min_score:
            skipped_score += 1
            continue
        e = make_entry(r)
        # Dedupe
        if e["url"] in existing_by_url:
            existing = existing_by_url[e["url"]]
            # Merge: only update if existing doesn't have fit_score_numeric, or it's lower
            if int(existing.get("fit_score_numeric", 0)) < score:
                existing["fit_score_numeric"] = score
                existing["fit_score"] = e["fit_score"]
                existing["fit_notes"] = e["fit_notes"]
                # Populate variant info even on re-score (older entries won't have it)
                if e.get("resume_variants"):
                    existing["resume_variants"] = e["resume_variants"]
                    existing["primary_variant"] = e["primary_variant"]
                updated += 1
            else:
                skipped_dupe += 1
            continue
        # Same-id check (multiple scan pulls can generate same slug)
        if e["id"] in existing_ids:
            e["id"] = e["id"] + "-" + str(score)
        new_entries.append(e)
        existing_ids.add(e["id"])
        added += 1

    # Expire stale auto- entries not in latest scan
    scan_urls = {r["link"] for r in scored.get("results", [])}
    expired = 0
    if args.expire_stale:
        for j in tr["jobs"]:
            if j["id"].startswith("auto-") and j.get("url") not in scan_urls:
                if j.get("status") in ("Applied", "Recruiter_Screen", "Phone_Screen",
                                        "Take_Home", "Onsite", "Offer"):
                    continue
                if j.get("status") != "Expired":
                    j["status"] = "Expired"
                    j["notes"] = (j.get("notes", "") + f" | Auto-expired {date.today().isoformat()}: URL not in latest scan").strip()
                    expired += 1

    stamp = date.today().strftime("%Y%m%d")
    report_lines = [
        f"# Auto-promote report -- {date.today().isoformat()}",
        "",
        f"- Source: `{args.scan}`",
        f"- Min score: {args.min_score}",
        f"- Include watch: {args.include_watch}",
        f"- **Mode: {'COMMIT' if args.commit else 'DRY-RUN'}**",
        "",
        "## Outcome",
        f"- New entries to add: **{added}**",
        f"- Existing entries upgraded (higher score): {updated}",
        f"- Expired (URL not in scan): {expired}" if args.expire_stale else "",
        f"- Skipped — wrong verdict: {skipped_verdict}",
        f"- Skipped — below min-score: {skipped_score}",
        f"- Skipped — already in tracker at equal/higher score: {skipped_dupe}",
        "",
        "## Top 20 would-be-added (by score)",
        "",
        "| Score | Verdict | Tier | Sector | Company | Title | Resume | Link |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in sorted(new_entries, key=lambda x: -x["fit_score_numeric"])[:20]:
        variants_str = "/".join(e.get("resume_variants") or []) or "—"
        report_lines.append(
            f"| {e['fit_score_numeric']} | {e['status']} | {e['tier']} | {e['sector']} | "
            f"{e['company']} | {e['title'].replace('|', '/')} | {variants_str} | "
            f"[open]({e['url']}) |"
        )
    report_path = OUT_DIR / f"promote_report_{stamp}.md"
    report_path.write_text("\n".join([l for l in report_lines if l is not None]), encoding="utf-8")

    if args.commit:
        # Backup
        bak = TRACKER.with_suffix(f".bak.{stamp}.json")
        shutil.copy2(TRACKER, bak)
        tr["jobs"].extend(new_entries)
        tr["meta"]["total_roles"] = len(tr["jobs"])
        tr["meta"]["last_scan"] = date.today().isoformat()
        tr["meta"]["changelog"].append({
            "date": date.today().isoformat(),
            "event": f"auto_promote: +{added} new, {updated} upgraded, {expired} expired (min_score={args.min_score})",
            "roles": len(tr["jobs"]),
        })
        if _sj_write is not None:
            _sj_write(TRACKER, tr)
        else:
            # Inline atomic fallback — same shape as safe_json._atomic_write
            # but without the cross-process lock. Better than a raw write_text
            # which truncates on crash.
            import os as _os, tempfile as _tf
            fd, tmp = _tf.mkstemp(prefix=TRACKER.name + ".", suffix=".tmp",
                                   dir=str(TRACKER.parent))
            try:
                with _os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(tr, f, indent=2)
                    f.flush()
                    _os.fsync(f.fileno())
                _os.replace(tmp, TRACKER)
            except Exception:
                try: _os.unlink(tmp)
                except OSError: pass
                raise
        print(f"[auto_promote] COMMIT: added {added}, upgraded {updated}, expired {expired}")
        print(f"[auto_promote] Tracker backed up to {bak.name}")

        # Auto-tailor hook — spawn one jd_tailor process per new Tier-1 role.
        # We fire-and-forget: the caller sees outputs appear in automation/outputs/
        # and gets a "draft ready" badge in the UI when the file exists.
        if args.auto_tailor:
            import subprocess
            tier1 = [e for e in new_entries if e.get("tier") == 1]
            if not tier1:
                print(f"[auto_promote] No new Tier-1 roles to auto-tailor.")
            else:
                print(f"[auto_promote] Auto-tailoring {len(tier1)} Tier-1 role(s)...")
                tailor_py = Path(__file__).parent / "jd_tailor.py"
                for e in tier1:
                    cmd = [sys.executable, str(tailor_py), "--job-id", e["id"]]
                    try:
                        # Detach so we don't block — tailor can take ~60s per role
                        _lf = open(OUT_DIR / f"tailor_{e['id']}_stdout.log", "wb")
                        try:
                            subprocess.Popen(
                                cmd,
                                stdout=_lf,
                                stderr=subprocess.STDOUT,
                                cwd=str(Path(__file__).parent.parent),
                            )
                        finally:
                            try: _lf.close()
                            except Exception: pass
                        print(f"  [tailor] spawned for {e['id']} ({e['company']})")
                    except Exception as ex:
                        print(f"  [tailor] failed to spawn for {e['id']}: {ex}",
                              file=sys.stderr)
    else:
        print(f"[auto_promote] DRY-RUN: would add {added}, upgrade {updated}, expire {expired}")
        print(f"[auto_promote] Re-run with --commit to apply.")
    print(f"[auto_promote] Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
