"""Synthetic populated-tracker AppTest.

The default tracker is empty (0 jobs), which means the standard test_pages
harness never exercises:
  - Today's queue hero on Dashboard (Apply now / Follow up / Reach out)
  - Auto-promote banner on Pipeline
  - Inline tailor + apply drawer on Dashboard / Jobs Kanban

This test substitutes a temporary populated tracker with diverse rows
covering each rendering branch, then drives Dashboard + Jobs Kanban
through AppTest. Original tracker is backed up + restored even on
test failure.

Usage:
    python tests/test_populated_tracker.py
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
TRACKER = ROOT / "data" / "job_tracker_data.json"
WORKLIST_SCORED = ROOT / "automation" / "outputs" / "worklist_scored.json"

sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

from streamlit.testing.v1 import AppTest  # noqa: E402


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode("ascii")


def _today() -> date:
    return date.today()


def _build_synthetic_tracker() -> dict:
    """Diverse tracker covering every Today's-queue branch."""
    today = _today()
    return {
        "meta": {
            "version": "2.0",
            "created_at": "2026-05-18T18:16:10",
            "total_roles": 5,
            "campaign_start": (today - timedelta(days=14)).isoformat(),
            "campaign_end": (today + timedelta(days=46)).isoformat(),
            "changelog": [],
            "status_enum": ["Found", "Watch", "Applied", "Tailoring",
                             "Recruiter_Screen", "Rejected", "Withdrawn",
                             "Expired", "Onsite", "Offer"],
            "weekly_kpi_targets": {
                "tailored_applications": 8,
                "outreach_messages": 10,
                "coffees": 3,
            },
        },
        "jobs": [
            # 1) Apply-now: high fit, urgent, has CRM warm-intro path
            #    (RBC matches a recruiter in the test CRM)
            {
                "id": "auto-rbc-director-alm",
                "company": "RBC",
                "sector": "Canadian Big 6 Banks",
                "tier": 1,
                "title": "Director, ALM Modelling",
                "level": "Director",
                "location": "Toronto, ON",
                "url": "https://example.com/rbc/alm",
                "portal_url": "https://example.com/rbc/",
                "date_found": today.isoformat(),
                "date_jd_verified": today.isoformat(),
                "date_applied": None,
                "date_last_followup": None,
                "source": "scraper+fit_scorer",
                "status": "Found",
                "fit_score": "High",
                "fit_score_numeric": 9,
                "resume_variants": ["alm_primary"],
                "primary_variant": "alm_primary",
                "urgency": "High",
                "expected_comp_band_cad": "",
                "fit_notes": "Strong ALM fit. Top reasons: Moody's ALM exp; LDI; OSFI",
                "keywords": [],
                "resume_file": None,
                "cover_letter_file": None,
                "contact": {},
                "outreach_log": [],
                "followup_schedule": {"next_due": None, "cadence_days": [3, 10, 21]},
                "rejection_reason": None,
                "rejection_date": None,
                "next_action": "Apply",
                "notes": "auto-promoted; verdict=apply_now",
            },
            # 2) Apply-now: medium fit, gmail-sourced
            {
                "id": "auto-bmo-vp-risk",
                "company": "BMO",
                "sector": "Canadian Big 6 Banks",
                "tier": 1,
                "title": "VP, Risk Analytics",
                "location": "Toronto, ON",
                "url": "https://example.com/bmo/vp-risk",
                "date_found": today.isoformat(),
                "date_applied": None,
                "source": "gmail_linkedin_alert+fit_scorer",
                "status": "Found",
                "fit_score": "High",
                "fit_score_numeric": 8,
                "primary_variant": "alm_primary",
                "urgency": "Medium",
                "fit_notes": "Risk analytics fit",
                "outreach_log": [],
                "followup_schedule": {"next_due": None, "cadence_days": [3, 10, 21]},
            },
            # 3) Follow-up: applied 5 days ago, no outreach
            {
                "id": "auto-scotia-senior-alm",
                "company": "Scotiabank",
                "sector": "Canadian Big 6 Banks",
                "tier": 1,
                "title": "Senior Manager, ALM",
                "location": "Toronto, ON",
                "url": "https://example.com/scotia/alm",
                "date_found": (today - timedelta(days=10)).isoformat(),
                "date_applied": (today - timedelta(days=5)).isoformat(),
                "source": "scrape+gmail+fit_scorer",
                "status": "Applied",
                "fit_score": "High",
                "fit_score_numeric": 8,
                "primary_variant": "alm_primary",
                "urgency": "Medium",
                "outreach_log": [],
                "followup_schedule": {
                    "next_due": (today - timedelta(days=2)).isoformat(),
                    "cadence_days": [3, 10, 21],
                },
            },
            # 4) Already-rejected: should NOT show in Today's queue
            {
                "id": "auto-cibc-rejected",
                "company": "CIBC",
                "sector": "Canadian Big 6 Banks",
                "tier": 2,
                "title": "Risk Analyst",
                "location": "Toronto, ON",
                "url": "https://example.com/cibc/x",
                "date_found": (today - timedelta(days=20)).isoformat(),
                "date_applied": (today - timedelta(days=15)).isoformat(),
                "source": "scraper+fit_scorer",
                "status": "Rejected",
                "fit_score": "Medium",
                "fit_score_numeric": 6,
                "rejection_date": (today - timedelta(days=2)).isoformat(),
                "rejection_reason": "Out of scope",
                "outreach_log": [],
            },
            # 5) Watch with low fit: should NOT show in Today's queue (fit<6)
            {
                "id": "auto-lowfit-watch",
                "company": "TestCo",
                "sector": "Fintech",
                "tier": 4,
                "title": "Junior Analyst",
                "location": "Toronto, ON",
                "url": "https://example.com/testco/jr",
                "date_found": today.isoformat(),
                "date_applied": None,
                "source": "scraper+fit_scorer",
                "status": "Watch",
                "fit_score": "Low",
                "fit_score_numeric": 4,
                "outreach_log": [],
            },
        ],
    }


def _build_synthetic_scored() -> dict:
    """Synthetic worklist_scored with apply_now verdicts so the auto-promote
    banner activates."""
    return {
        "scan_date": _today().isoformat(),
        "source": "worklist_scored",
        "stage1_passed": 3,
        "stage2_scored": 3,
        "results": [
            {
                "company": "RBC", "title": "Director ALM",
                "link": "https://example.com/rbc/x",
                "source": "scrape",
                "fit": {
                    "fit_verdict": "apply_now", "fit_score": 9, "tier": 1,
                    "summary": "strong fit",
                    "top_3_reasons": ["alm exp", "ldi", "osfi"],
                },
            },
            {
                "company": "BMO", "title": "VP Risk",
                "link": "https://example.com/bmo/y",
                "source": "gmail",
                "fit": {
                    "fit_verdict": "tailor_and_apply", "fit_score": 8, "tier": 1,
                    "summary": "good fit",
                    "top_3_reasons": ["risk", "bank"],
                },
            },
            {
                "company": "TestCo", "title": "Skip",
                "link": "https://example.com/testco/skip",
                "source": "scrape",
                "fit": {
                    "fit_verdict": "skip", "fit_score": 3, "tier": 4,
                    "summary": "no fit",
                    "top_3_reasons": [],
                },
            },
        ],
    }


def _run_one(page: str) -> dict:
    out = {"page": page, "ok": False, "elapsed_s": 0.0,
            "exceptions": [], "n_widgets": 0}
    t0 = time.time()
    try:
        at = AppTest.from_file(str(APP), default_timeout=90)
        at.session_state["_applyagent_nav"] = page
        at.run()
        out["exceptions"] = [str(getattr(e, "value", e)) for e in at.exception]
        out["n_widgets"] = (
            len(at.tabs) + len(at.dataframe) + len(at.button)
            + len(at.radio) + len(at.metric) + len(at.markdown)
        )
        out["ok"] = not out["exceptions"] and out["n_widgets"] > 0
    except Exception as e:
        out["exceptions"] = [
            f"AppTest harness crashed: {e}\n{traceback.format_exc()}"
        ]
    finally:
        out["elapsed_s"] = round(time.time() - t0, 2)
    return out


def main() -> int:
    # Backup originals
    tracker_bak = TRACKER.with_suffix(".json.test_backup")
    scored_bak = WORKLIST_SCORED.with_suffix(".json.test_backup")

    if TRACKER.exists():
        shutil.copy2(TRACKER, tracker_bak)
    if WORKLIST_SCORED.exists():
        shutil.copy2(WORKLIST_SCORED, scored_bak)

    failures = 0
    try:
        # Substitute synthetic state
        TRACKER.write_text(
            json.dumps(_build_synthetic_tracker(), indent=2),
            encoding="utf-8",
        )
        WORKLIST_SCORED.write_text(
            json.dumps(_build_synthetic_scored(), indent=2),
            encoding="utf-8",
        )

        # Run the pages that exercise the new code
        target_pages = ["🏠 Dashboard", "🎯 Pipeline", "📋 Jobs Kanban"]
        results = []
        print(f"E2E populated-tracker AppTest - {len(target_pages)} pages")
        for p in target_pages:
            r = _run_one(p)
            results.append(r)
            marker = "OK  " if r["ok"] else "FAIL"
            print(f"  [{marker}] {_ascii(p):<24s} "
                  f"{r['elapsed_s']:>5.1f}s "
                  f"widgets={r['n_widgets']:>3}  "
                  f"exceptions={len(r['exceptions'])}")
            for ex in r["exceptions"][:3]:
                print(f"        ! {_ascii(str(ex))[:300]}")
            if not r["ok"]:
                failures += 1
        print(f"\n{len(results) - failures}/{len(results)} pages OK")
    finally:
        # Always restore originals
        if tracker_bak.exists():
            shutil.move(str(tracker_bak), str(TRACKER))
        elif TRACKER.exists():
            TRACKER.unlink()
        if scored_bak.exists():
            shutil.move(str(scored_bak), str(WORKLIST_SCORED))
        elif WORKLIST_SCORED.exists():
            WORKLIST_SCORED.unlink()

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
