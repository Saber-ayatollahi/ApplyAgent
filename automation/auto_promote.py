#!/usr/bin/env python3
"""
auto_promote.py — Promote scored scan results to tracker; expire stale URLs.

Reads:
    automation/outputs/scan_<date>_scored.json  (fit_scorer output)
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
    python auto_promote.py --scan scan_20260512_scored.json  # alternative source
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

# Force UTF-8 stdio so emoji + ∪ symbols don't crash cp1252 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Cross-process-safe tracker reads/writes. Degrades to plain json if unavailable.
try:
    from safe_json import (  # type: ignore
        read_json as _sj_read,
        write_json as _sj_write,
        mutate_json as _sj_mutate,
    )
except ImportError:
    _sj_read = None  # type: ignore
    _sj_write = None  # type: ignore
    _sj_mutate = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
TRACKER = ROOT / "data" / "job_tracker_data.json"

# Promote-time geo gate. Producers (gmail_fetch, jd_scraper, worklist.rebuild)
# already filter, but rows with mojibake/garbled location strings — where
# `keep_for_toronto_pipeline` returns True via the empty-string fall-through
# but `is_gta_or_canada_remote` returns False — slip past. The audit on
# 2026-05-19 found 8 such rows already in the tracker. Add a second-line
# defense at promote so a future leak is contained, and so the audit
# becomes a one-time scrub, not a recurring chore.
try:
    from location_filter import (  # type: ignore
        keep_for_toronto_pipeline as _keep_geo,
    )
except ImportError:
    from .location_filter import (  # type: ignore
        keep_for_toronto_pipeline as _keep_geo,
    )

# Sector tier registry (replaces the old in-file SECTOR_ROUGH_TIER dict).
# Aliased so make_entry's reference site stays unchanged.
try:
    from sectors import TIER_OF as SECTOR_ROUGH_TIER  # type: ignore
except ImportError:
    from .sectors import TIER_OF as SECTOR_ROUGH_TIER  # type: ignore

# Suppression registry — re-checked at promote time so any sector/company
# muted between scoring and promote is caught before the row lands in the
# tracker. Optional import; if the module is missing (older deploys) the
# promote run silently treats every row as not-suppressed. Note: the
# suppressions module uses relative imports internally, so the script-mode
# (`python auto_promote.py`) path needs to add the project root to sys.path
# and then go through the `automation` package.
try:
    from . import suppressions as _suppressions  # type: ignore
except ImportError:
    try:
        from automation import suppressions as _suppressions  # type: ignore
    except ImportError:
        try:
            # Last-ditch: project root on sys.path → import via package.
            import sys as _sys
            _proj = str(Path(__file__).resolve().parent.parent)
            if _proj not in _sys.path:
                _sys.path.insert(0, _proj)
            from automation import suppressions as _suppressions  # type: ignore
        except Exception:
            _suppressions = None  # type: ignore

# Tracker schema migration. Runs inside the commit mutator so it executes
# under the same exclusive lock as the promote write.
try:
    import tracker_migrate as _tracker_migrate  # type: ignore
except ImportError:
    try:
        from . import tracker_migrate as _tracker_migrate  # type: ignore
    except ImportError:
        _tracker_migrate = None  # type: ignore

# Phase 5: route status filters through tracker_ops.is_active so archived rows
# are excluded from the expire-stale loop (otherwise an archived Found row whose
# URL drops out of the latest scan would get its status flipped to Expired —
# pointless noise; the row is already archived and out of every UI lane).
try:
    import tracker_ops as _tracker_ops  # type: ignore
except ImportError:
    try:
        from . import tracker_ops as _tracker_ops  # type: ignore
    except ImportError:
        _tracker_ops = None  # type: ignore

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

    # Preserve provenance from the scan row. Without this, every promoted
    # entry got tagged "scraper+fit_scorer" and we lost the ability to tell
    # Gmail-alert rows from web-scraped rows in the tracker.
    #
    # Worklist rows carry source ∈ {"scrape", "gmail", "both"}; legacy
    # raw scans carry the original source string ("gmail_linkedin_alert",
    # "workday_direct_ats", etc.). Translate both into a tracker-friendly
    # tag so the UI can render 📬 / 🛰 / 🔁 badges consistently.
    raw_src = (r.get("source") or "").strip()
    if raw_src == "both":
        entry_source = "scrape+gmail+fit_scorer"
    elif raw_src == "gmail" or raw_src.startswith("gmail_"):
        entry_source = "gmail_linkedin_alert+fit_scorer"
    elif raw_src == "scrape":
        entry_source = "scraper+fit_scorer"
    else:
        # Unknown / legacy source string — preserve verbatim, tag the scorer
        entry_source = f"{raw_src or 'unknown'}+fit_scorer"

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
        # Forward-compat per schema_version 3 — every promoted row carries
        # archived explicitly so tracker_ops.is_active() doesn't have to fall
        # back to the missing-key default.
        "archived": False,
        "date_found": date.today().isoformat(),
        "date_jd_verified": date.today().isoformat() if r.get("_jd_len", 0) > 200 else None,
        "date_applied": None,
        "date_last_followup": None,
        "source": entry_source,
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
                         "If omitted, promotes worklist_scored.json (the deduped "
                         "scrape ∪ Gmail pool — see automation/worklist.py).")
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
    ap.add_argument("--only-url", action="append", default=None, metavar="URL",
                    help="Promote ONLY the scored row(s) whose canonical URL matches "
                         "the supplied URL. Repeatable for multiple URLs. Skips the "
                         "expire-stale pass (nonsensical for a single-row promote). "
                         "Example: --only-url "
                         "https://www.linkedin.com/jobs/view/3987654321 "
                         "--commit")
    ap.add_argument("--only-urls", default=None, metavar="FILE",
                    help="Promote ONLY rows whose canonical URL appears in FILE "
                         "(newline-delimited; blank lines and lines starting with "
                         "'#' are ignored). Manual mode: bypasses --min-score, "
                         "promotes verdict=watch as Watch, promotes verdict=skip as "
                         "Watch/tier 4 with manual_override_skip_verdict=true. Geo "
                         "gate and dedupe still apply. Mutually exclusive with "
                         "--only-url.")
    args = ap.parse_args()

    # Mutually exclusive — a single promote run is either single-URL rescue
    # (legacy `--only-url`) or batch manual selection (`--only-urls FILE`).
    if args.only_url and args.only_urls:
        print("ERROR: --only-url and --only-urls are mutually exclusive.",
              file=sys.stderr)
        return 2

    # Read the manual URL set up-front so a malformed file fails before we
    # touch the tracker.
    only_urls_targets: set[str] | None = None
    if args.only_urls:
        try:
            import worklist as _wl_only  # type: ignore
        except ImportError:
            from . import worklist as _wl_only  # type: ignore
        urls_file = Path(args.only_urls)
        if not urls_file.exists():
            print(f"ERROR: --only-urls file not found: {urls_file}",
                  file=sys.stderr)
            return 1
        raw_lines = urls_file.read_text(encoding="utf-8").splitlines()
        only_urls_targets = set()
        for line in raw_lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            canon = _wl_only.norm_url({"link": s})
            if canon:
                only_urls_targets.add(canon)
        if not only_urls_targets:
            print(f"[only-urls] {urls_file} contained no usable URLs; "
                  f"nothing to promote.", file=sys.stderr)
            return 0

    if not args.scan:
        # Default: read worklist_scored.json (worklist contract). If that
        # doesn't exist, fall back to the freshest scan_*_scored.json so
        # the legacy single-file flow keeps working during migration.
        try:
            import worklist  # type: ignore
        except ImportError:
            from . import worklist  # type: ignore
        ws = worklist.effective_scored()
        if ws is not None:
            args.scan = ws.name
            print(f"[auto_promote] No --scan supplied; using {args.scan} "
                  f"(worklist contract).", file=sys.stderr)
        else:
            candidates = sorted(
                OUT_DIR.glob("scan_*_scored.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            candidates = [p for p in candidates if p.stem != "scan_v4_scored"]
            if not candidates:
                print("ERROR: no worklist_scored.json or scan_*_scored.json in "
                      "outputs/. Run fit_scorer.py first.", file=sys.stderr)
                return 1
            args.scan = candidates[0].name
            print(f"[auto_promote] No --scan and no worklist_scored.json; "
                  f"falling back to {args.scan}.", file=sys.stderr)
        print(f"[auto_promote] No --scan supplied; using latest: {args.scan}",
              file=sys.stderr)
    scored_path = OUT_DIR / args.scan
    if not scored_path.exists():
        print(f"ERROR: {scored_path} not found. Run fit_scorer.py first.", file=sys.stderr)
        return 1

    scored = json.loads(scored_path.read_text(encoding="utf-8"))

    # --only-url: filter the scored input down to the supplied URL(s) before
    # we even look at the tracker. Uses worklist.norm_url so a LinkedIn
    # tracking-redirect URL still matches its canonical /jobs/view/<id> form.
    only_url_targets: set[str] | None = None
    if args.only_url:
        try:
            import worklist  # type: ignore
        except ImportError:
            from . import worklist  # type: ignore
        only_url_targets = {
            worklist.norm_url({"link": u}) for u in args.only_url if u
        }
        only_url_targets.discard("")
        all_results = scored.get("results", [])
        scored["results"] = [
            r for r in all_results if worklist.norm_url(r) in only_url_targets
        ]
        matched = len(scored["results"])
        if matched == 0:
            print(f"[only-url] matched 0 row(s); promoted 0; skipped 0 "
                  f"(URL(s) not present in {scored_path.name}).")
            return 0

    # --only-urls: EXCLUSIVE manual mode. Pre-filters the scored input down
    # to the URLs in the file, mirroring --only-url's contract. The user's
    # mental model is "I picked these N; promote exactly these N" — additive
    # behavior would silently include threshold-eligible rows the user did
    # NOT pick. Threshold-only behavior is the default when --only-urls is
    # absent. As a consequence, run-level selection_mode "mixed" is
    # unreachable via --only-urls alone (deliberate — see review-validated
    # decisions in docs/pipeline_redesign.md).
    if args.only_urls and only_urls_targets is not None:
        try:
            import worklist  # type: ignore
        except ImportError:
            from . import worklist  # type: ignore
        all_results = scored.get("results", []) or []
        scored["results"] = [
            r for r in all_results if worklist.norm_url(r) in only_urls_targets
        ]
        matched = len(scored["results"])
        if matched == 0:
            print(f"[only-urls] matched 0 row(s) from "
                  f"{Path(args.only_urls).name} in {scored_path.name}; "
                  f"nothing to promote.")
            return 0

    # Two-phase design (B4 — race-safety):
    #   Phase 1 (preview):     read tracker once, classify each scored row vs
    #                          the current tracker. Counts feed the report.
    #   Phase 2 (commit):      under safe_json's exclusive lock, RE-classify
    #                          against the freshest tracker on disk and apply
    #                          all mutations in a single atomic write. Without
    #                          this, a UI 'Mark Applied' between read and
    #                          write got silently clobbered.
    # The phase-1 counts feed the human report; phase-2 truth wins on commit.
    try:
        import worklist as _wl  # type: ignore
    except ImportError:
        from . import worklist as _wl  # type: ignore

    # Load suppression snapshot once. Env var APPLYAGENT_SUPPRESSIONS_SNAPSHOT
    # mirrors fit_scorer's path so a single pipeline run reads the same
    # frozen state at both stages. Empty dict means "nothing suppressed."
    import os
    def _load_suppression_snapshot() -> dict:
        if _suppressions is None:
            return {"sectors": [], "companies": []}
        snap_path = os.environ.get("APPLYAGENT_SUPPRESSIONS_SNAPSHOT")
        if snap_path:
            try:
                return json.loads(Path(snap_path).read_text(encoding="utf-8"))
            except Exception:
                # Malformed snapshot path -> fall back to live state rather
                # than silently treat the run as suppression-free.
                pass
        try:
            return _suppressions.load_active()
        except Exception:
            return {"sectors": [], "companies": []}

    _suppression_snapshot = _load_suppression_snapshot()

    # Run-level selection mode is derived after _classify_against runs and
    # reports per-row tags. Manual rows are those whose canonical URL is in
    # only_urls_targets (the manual file).
    manual_targets: set[str] = only_urls_targets or set()

    def _classify_against(tr: dict) -> dict:
        """Pure function: classify scored.results vs `tr`.
        Returns dict with new_entries / upgrades / counts / expirations."""
        existing_by_url = {
            _wl.norm_url(j): j for j in tr.get("jobs", []) or [] if j.get("url")
        }
        existing_ids = {j["id"] for j in tr.get("jobs", []) or []}
        new_entries: list[dict] = []
        upgrades: list[tuple[str, dict, int]] = []  # (canonical_url, e, score)
        # Audit-pack trail: every row we skip, with reason. Consumed by
        # audit_pack.py so users can see WHICH roles got rejected at promote.
        skipped_rows: list[dict] = []
        # New v3.1.1 bucket: rows that scored fine earlier but match a
        # suppression added between scoring and promote.
        suppressed_after_score: list[dict] = []
        added = updated = skipped_dupe = skipped_verdict = skipped_score = 0
        skipped_geo = 0

        def _audit(r: dict, reason: str, score: int, verdict: str,
                   extra: str = "") -> None:
            skipped_rows.append({
                "reason": reason,
                "company": r.get("company", ""),
                "title": r.get("title", ""),
                "url": r.get("url") or r.get("link", ""),
                "location": r.get("location", ""),
                "score": score,
                "verdict": verdict,
                "note": extra,
            })

        for r in scored.get("results", []) or []:
            f = r.get("fit") or {}
            verdict = f.get("fit_verdict") or "skip"
            score = int(f.get("fit_score") or 0)
            row_canon = _wl.norm_url(r)
            is_manual = row_canon in manual_targets

            # Re-check suppression at promote time. THRESHOLD rows that hit
            # a sector/company mute are dropped into suppressed_after_score
            # (race-window catch). MANUAL rows that hit a mute are promoted
            # with a manual_override_suppression tag and the would-be drop
            # reason recorded — manual selection is explicit user intent and
            # mirrors fit_scorer's --only-url behavior (Cluster B item 6 in
            # the redesign doc). The user can still lift the mute later, but
            # the row is not silently buried.
            override_suppression_reason: str | None = None
            if _suppressions is not None:
                supp_hit, supp_reason = _suppressions.is_suppressed(
                    r, _suppression_snapshot
                )
                if supp_hit:
                    if is_manual:
                        override_suppression_reason = supp_reason or "suppressed"
                        # Record the override in suppressed_after_score for
                        # audit, but DO NOT continue — the row will promote
                        # below with selection_mode=manual_override_suppression.
                        suppressed_after_score.append({
                            "url": r.get("link") or r.get("url") or "",
                            "company": r.get("company", ""),
                            "sector": r.get("sector", ""),
                            "drop_reason": supp_reason or "suppressed",
                            "selection_mode": "manual_override_suppression",
                            "promoted_anyway": True,
                        })
                    else:
                        suppressed_after_score.append({
                            "url": r.get("link") or r.get("url") or "",
                            "company": r.get("company", ""),
                            "sector": r.get("sector", ""),
                            "drop_reason": supp_reason or "suppressed",
                            "selection_mode": "threshold",
                            "promoted_anyway": False,
                        })
                        continue

            # Threshold mode — the original verdict + min-score filters apply.
            # Manual mode — bypass min-score, escalate skip-verdict to a
            # Watch/tier-4 fallback so user picks never silently disappear.
            selection_mode = "threshold"
            override_skip = False
            if not is_manual:
                if verdict not in VERDICT_DEFAULTS or VERDICT_DEFAULTS[verdict] is None:
                    skipped_verdict += 1
                    _audit(r, "verdict", score, verdict)
                    continue
                if verdict == "watch" and not args.include_watch:
                    skipped_verdict += 1
                    _audit(r, "verdict_watch_excluded", score, verdict)
                    continue
                if score < args.min_score:
                    skipped_score += 1
                    _audit(r, "below_min_score", score, verdict,
                           f"min={args.min_score}")
                    continue
            else:
                # Manual selection — every selected row must land somewhere.
                # Suppression-override takes precedence over skip/below-threshold
                # tags so the audit trail surfaces the strongest signal.
                if override_suppression_reason is not None:
                    selection_mode = "manual_override_suppression"
                    if verdict == "skip":
                        override_skip = True  # still escalate to Watch/tier-4
                elif verdict == "skip":
                    override_skip = True
                    selection_mode = "manual_override_skip"
                elif score < args.min_score:
                    selection_mode = "manual_below_threshold"
                else:
                    selection_mode = "manual"
            # Promote-time geo gate. The pool gate at gmail_fetch /
            # jd_scraper / worklist.rebuild keeps rows with empty/garbled
            # location for the scorer LLM to judge — fine for paid scoring,
            # but mojibake rows ("Madison-Davis, LLC ▒ Los Angeles") slip
            # into the tracker. We tighten here: at promote time, the row
            # must affirmatively pass the GTA/Canada predicate. Empty string
            # still passes (LinkedIn omits loc for some Toronto jobs). Geo
            # wins over manual selection — correctness boundary.
            if not _keep_geo(r.get("location") or ""):
                skipped_geo += 1
                _audit(r, "geo", score, verdict, r.get("location") or "")
                continue
            if override_skip:
                # Manual override of a skip verdict. Force Watch/tier-4 with
                # a marker in notes so the row is visible in the tracker but
                # clearly tagged as a user-driven exception.
                e = make_entry(r)
                e["status"] = "Watch"
                e["urgency"] = "Low"
                e["tier"] = 4
                e["notes"] = (
                    (e.get("notes") or "")
                    + " | manual_override_skip_verdict=true"
                ).strip(" |")
            else:
                e = make_entry(r)
            if override_suppression_reason is not None:
                e["notes"] = (
                    (e.get("notes") or "")
                    + f" | manual_override_suppression={override_suppression_reason}"
                ).strip(" |")
            e["selection_mode"] = selection_mode
            # Dedupe via canonical URL — raw j["url"] vs scan link can drift
            # on Workday session tokens / LinkedIn tracking redirects, and a
            # canonicalised form (worklist.norm_url) is the only stable key.
            canon = _wl.norm_url(e)
            if canon in existing_by_url:
                existing = existing_by_url[canon]
                if int(existing.get("fit_score_numeric", 0)) < score:
                    upgrades.append((canon, e, score))
                    updated += 1
                else:
                    skipped_dupe += 1
                    _audit(r, "dupe", score, verdict,
                           f"existing={existing.get('fit_score_numeric', 0)}")
                continue
            if e["id"] in existing_ids:
                e["id"] = e["id"] + "-" + str(score)
            new_entries.append(e)
            existing_ids.add(e["id"])
            added += 1
        # Expire stale auto- entries not in latest scan. Skip in --only-url
        # / --only-urls mode (single-row or batch-manual promote shouldn't
        # mark the rest of the tracker expired).
        scan_canon = {_wl.norm_url(r) for r in (scored.get("results") or [])}
        expirations: list[str] = []
        if args.expire_stale and not args.only_url and not args.only_urls:
            held_statuses = ("Applied", "Recruiter_Screen", "Phone_Screen",
                             "Take_Home", "Onsite", "Offer")
            for j in tr.get("jobs", []) or []:
                if not str(j.get("id", "")).startswith("auto-"):
                    continue
                # Phase 5: route through tracker_ops.is_active so archived rows
                # are skipped — an archived row's status flip to Expired is noise.
                # is_active also covers all TERMINAL_STATUSES (incl. Expired/Offer),
                # so the prior held_statuses + Expired guards become redundant
                # for the Offer/Expired entries; we keep held_statuses for the
                # interview-pipeline statuses (Applied, Recruiter_Screen, ...)
                # that are NOT terminal but should still be protected.
                if _tracker_ops is not None and not _tracker_ops.is_active(j):
                    continue
                if _wl.norm_url(j) in scan_canon:
                    continue
                if j.get("status") in held_statuses:
                    continue
                if j.get("status") == "Expired":
                    continue
                expirations.append(j["id"])
        return {
            "new_entries": new_entries,
            "upgrades": upgrades,
            "expirations": expirations,
            "added": added,
            "updated": updated,
            "skipped_dupe": skipped_dupe,
            "skipped_verdict": skipped_verdict,
            "skipped_score": skipped_score,
            "skipped_geo": skipped_geo,
            "skipped_rows": skipped_rows,
            "suppressed_after_score": suppressed_after_score,
        }

    # Phase 1 — preview against current tracker
    if _sj_read is not None:
        tr = _sj_read(TRACKER, default={"jobs": [], "meta": {}})
    else:
        tr = json.loads(TRACKER.read_text(encoding="utf-8"))
    preview = _classify_against(tr)
    new_entries = preview["new_entries"]
    added = preview["added"]
    updated = preview["updated"]
    skipped_dupe = preview["skipped_dupe"]
    skipped_verdict = preview["skipped_verdict"]
    skipped_score = preview["skipped_score"]
    skipped_geo = preview["skipped_geo"]
    expired = len(preview["expirations"])
    suppressed_after_score = preview.get("suppressed_after_score", []) or []

    # Run-level selection_mode: derive from the per-row tags so a manual
    # file with zero matched rows still reports "manual" (the user's intent),
    # while a default run reports "threshold".
    per_row_modes = {e.get("selection_mode", "threshold") for e in new_entries}
    has_manual = any(m.startswith("manual") for m in per_row_modes) or bool(args.only_urls)
    has_threshold = "threshold" in per_row_modes
    if has_manual and has_threshold:
        run_selection_mode = "mixed"
    elif has_manual:
        run_selection_mode = "manual"
    else:
        run_selection_mode = "threshold"

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
        f"- Selection mode: **{run_selection_mode}**",
        f"- New entries to add: **{added}**",
        f"- Existing entries upgraded (higher score): {updated}",
        f"- Expired (URL not in scan): {expired}" if args.expire_stale else "",
        f"- Skipped — wrong verdict: {skipped_verdict}",
        f"- Skipped — below min-score: {skipped_score}",
        f"- Skipped — already in tracker at equal/higher score: {skipped_dupe}",
        f"- Skipped — geo gate (out of GTA/Canada-remote): {skipped_geo}",
        f"- Suppressed at promote (race-window): {len(suppressed_after_score)}",
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

    # JSON sibling for audit-pack export. Carries structured `skipped_rows[]`
    # so the xlsx download can show users WHICH rows the promote stage
    # rejected and why (verdict / below_min / geo / duplicate_lower_score).
    report_json_path = OUT_DIR / f"promote_report_{stamp}.json"
    report_json_path.write_text(
        json.dumps(
            {
                "scan_date": stamp,
                "source": str(args.scan),
                "min_score": args.min_score,
                "include_watch": args.include_watch,
                "mode": "commit" if args.commit else "dry_run",
                "selection_mode": run_selection_mode,
                "summary": {
                    "added": added,
                    "updated": updated,
                    "expired": expired,
                    "skipped_verdict": skipped_verdict,
                    "skipped_score": skipped_score,
                    "skipped_dupe": skipped_dupe,
                    "skipped_geo": skipped_geo,
                    "suppressed_after_score": len(suppressed_after_score),
                },
                "skipped_rows": preview["skipped_rows"],
                "suppressed_after_score": suppressed_after_score,
                "promoted": [
                    {
                        "id": e["id"],
                        "company": e["company"],
                        "title": e["title"],
                        "score": e["fit_score_numeric"],
                        "tier": e.get("tier"),
                        "sector": e.get("sector"),
                        "url": e["url"],
                        "selection_mode": e.get("selection_mode", "threshold"),
                    }
                    for e in new_entries
                ],
                # Back-compat alias — older audit_pack readers expect this key.
                "new_entries": [
                    {
                        "id": e["id"],
                        "company": e["company"],
                        "title": e["title"],
                        "score": e["fit_score_numeric"],
                        "tier": e.get("tier"),
                        "sector": e.get("sector"),
                        "url": e["url"],
                        "selection_mode": e.get("selection_mode", "threshold"),
                    }
                    for e in new_entries
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Captured by the mutator closure for the commit log message.
    final_counts = {"added": 0, "updated": 0, "expired": 0, "geo": 0}

    def _commit_mutator(current: dict) -> dict:
        """Re-classify against the freshest tracker on disk and apply.
        Called by safe_json.mutate_json under the exclusive lock so concurrent
        UI writes can't be clobbered between the read and write."""
        if not isinstance(current, dict):
            current = {"jobs": [], "meta": {}}
        current.setdefault("jobs", [])
        current.setdefault("meta", {})

        # Run schema migration inside the lock so any pre-v3 tracker on disk
        # gains archived: False on every row before the promote write lands.
        # Idempotent — a no-op once meta.schema_version >= 3.
        if _tracker_migrate is not None:
            _tracker_migrate.migrate_in_place(current)

        fresh = _classify_against(current)
        # Apply upgrades to existing rows (in-place; current["jobs"] is the
        # truth-on-disk list).
        upgrade_by_canon = {canon: (e, score)
                            for (canon, e, score) in fresh["upgrades"]}
        if upgrade_by_canon:
            for j in current["jobs"]:
                canon = _wl.norm_url(j)
                if canon in upgrade_by_canon:
                    e, score = upgrade_by_canon[canon]
                    j["fit_score_numeric"] = score
                    j["fit_score"] = e["fit_score"]
                    j["fit_notes"] = e["fit_notes"]
                    if e.get("resume_variants"):
                        j["resume_variants"] = e["resume_variants"]
                        j["primary_variant"] = e["primary_variant"]
        # Apply expirations
        if fresh["expirations"]:
            exp_set = set(fresh["expirations"])
            today = date.today().isoformat()
            for j in current["jobs"]:
                if j.get("id") in exp_set:
                    j["status"] = "Expired"
                    j["notes"] = ((j.get("notes", "") +
                                   f" | Auto-expired {today}: URL not in "
                                   f"latest scan").strip())
        # Append new entries. selection_mode is a report-only annotation;
        # strip before persisting so the tracker schema stays clean.
        for ne in fresh["new_entries"]:
            ne.pop("selection_mode", None)
        current["jobs"].extend(fresh["new_entries"])
        current["meta"]["total_roles"] = len(current["jobs"])
        current["meta"]["last_scan"] = date.today().isoformat()
        current["meta"].setdefault("changelog", []).append({
            "date": date.today().isoformat(),
            "event": (f"auto_promote: +{fresh['added']} new, "
                      f"{fresh['updated']} upgraded, "
                      f"{len(fresh['expirations'])} expired, "
                      f"{fresh['skipped_geo']} geo-skipped "
                      f"(min_score={args.min_score})"),
            "roles": len(current["jobs"]),
        })
        final_counts["added"] = fresh["added"]
        final_counts["updated"] = fresh["updated"]
        final_counts["expired"] = len(fresh["expirations"])
        final_counts["geo"] = fresh["skipped_geo"]
        # The post-mutation new_entries list (used by --auto-tailor)
        final_counts["new_entries"] = fresh["new_entries"]  # type: ignore
        return current

    if args.commit:
        # Backup BEFORE the mutation so the on-disk file we copy is the
        # caller's pre-mutation truth. shutil.copy2 reads under no lock; in
        # the worst case it races a concurrent UI write and we get a slightly-
        # newer-than-pre-mutation snapshot — still a valid rollback target.
        bak = TRACKER.with_suffix(f".bak.{stamp}.json")
        shutil.copy2(TRACKER, bak)

        if _sj_mutate is not None:
            _sj_mutate(TRACKER, _commit_mutator,
                       default={"jobs": [], "meta": {}})
        elif _sj_write is not None:
            # Best-effort fallback: re-read, mutate, write. Not race-safe
            # but better than nothing if portalocker is missing.
            cur = _sj_read(TRACKER, default={"jobs": [], "meta": {}})
            _sj_write(TRACKER, _commit_mutator(cur))
        else:
            # Last-resort fallback: inline atomic write w/ no cross-process
            # lock. The first thing a fresh install of this repo should do
            # is `pip install portalocker`.
            cur = json.loads(TRACKER.read_text(encoding="utf-8"))
            new = _commit_mutator(cur)
            import os as _os, tempfile as _tf
            fd, tmp = _tf.mkstemp(prefix=TRACKER.name + ".", suffix=".tmp",
                                   dir=str(TRACKER.parent))
            try:
                with _os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(new, f, indent=2)
                    f.flush()
                    _os.fsync(f.fileno())
                _os.replace(tmp, TRACKER)
            except Exception:
                try: _os.unlink(tmp)
                except OSError: pass
                raise

        # Use the freshly-classified counts (which may differ slightly from
        # the preview if the tracker changed between phases — rare).
        added = final_counts["added"]
        updated = final_counts["updated"]
        expired = final_counts["expired"]
        skipped_geo = final_counts["geo"]
        new_entries = final_counts.get("new_entries") or new_entries  # type: ignore
        print(f"[auto_promote] COMMIT: added {added}, upgraded {updated}, "
              f"expired {expired}, geo-skipped {skipped_geo}")
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
        print(f"[auto_promote] DRY-RUN: would add {added}, upgrade {updated}, "
              f"expire {expired}, geo-skip {skipped_geo}")
        print(f"[auto_promote] Re-run with --commit to apply.")
    print(f"[auto_promote] Report: {report_path}")

    # UI-parseable summary for single-URL promote mode. "promoted" counts
    # added + upgraded (anything that landed or would land in the tracker);
    # "skipped" combines dedupe / wrong-verdict / below-min-score / geo so
    # the caller doesn't have to reason about the breakdown.
    if args.only_url:
        promoted = added + updated
        skipped_total = (skipped_dupe + skipped_verdict + skipped_score
                         + skipped_geo)
        print(f"[only-url] matched {matched} row(s); promoted {promoted}; "
              f"skipped {skipped_total} (tracker dupe / non-actionable verdict "
              f"/ geo gate)")
    if args.only_urls:
        promoted = added + updated
        skipped_total = (skipped_dupe + skipped_geo
                         + len(suppressed_after_score))
        print(f"[only-urls] matched {matched} row(s); promoted {promoted}; "
              f"skipped {skipped_total} (tracker dupe / geo gate / "
              f"suppressed_after_score); selection_mode={run_selection_mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
