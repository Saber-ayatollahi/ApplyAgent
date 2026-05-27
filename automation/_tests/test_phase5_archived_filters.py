"""Phase 5 routing: archived rows excluded from automation-side filters.

Covers the two automation sites where archived tracker rows were being
counted in calculations they should not affect:

  Site A — auto_promote._classify_against expire-stale loop. An archived
           Found row whose URL has dropped from the latest scan should
           NOT be flipped to Expired (redundant noise; the row is already
           archived and out of every UI lane).

  Site B — outcome_feedback.build_report cold-lane denominator. Archived
           rows must not inflate s.applied; otherwise, archiving roles in
           a sector falsely triggers the "you applied N times with 0
           interviews" cold-lane warning.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
# Mirror the import-path setup used by other auto_promote tests so the
# in-test module references match the ones loaded by auto_promote at runtime.
sys.path.insert(0, str(AUTO.parent))   # for `import automation.*`
sys.path.insert(0, str(AUTO))           # for un-namespaced imports

import auto_promote  # noqa: E402
from automation import suppressions as supp  # noqa: E402
import outcome_feedback  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers (mirrored from test_promote_selection_mode.py — kept local
# rather than imported so this file stays self-contained for reviewers).
# ---------------------------------------------------------------------------

def _scored_row(company: str, title: str, url: str, *,
                fit_score: int = 8, verdict: str = "apply_now",
                sector: str = "Canadian Big 6 Banks",
                location: str = "Toronto, ON",
                source: str = "scrape",
                jd_len: int = 1500) -> dict:
    return {
        "company": company,
        "title": title,
        "link": url,
        "url": url,
        "location": location,
        "sector": sector,
        "source": source,
        "_jd_len": jd_len,
        "fit": {
            "fit_score": fit_score,
            "fit_verdict": verdict,
            "tier": 2 if verdict == "tailor_and_apply" else 1,
            "summary": f"synthetic {company}",
            "top_3_reasons": ["r1", "r2", "r3"],
            "skill_gaps": [],
            "applicable_resume_variants": ["risk"],
        },
    }


def _empty_tracker() -> dict:
    return {
        "meta": {
            "version": "2.0",
            "schema_version": 3,
            "total_roles": 0,
            "changelog": [],
            "status_enum": [
                "Found", "Watch", "Applied", "Recruiter_Screen", "Phone_Screen",
                "Take_Home", "Onsite", "Offer", "Rejected", "Hired",
                "Withdrawn", "Expired",
            ],
        },
        "jobs": [],
    }


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Redirect TRACKER + OUT_DIR + suppressions paths to tmp_path."""
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    tracker = data_dir / "job_tracker_data.json"
    tracker.write_text(json.dumps(_empty_tracker()), encoding="utf-8")

    monkeypatch.setattr(auto_promote, "OUT_DIR", out_dir)
    monkeypatch.setattr(auto_promote, "TRACKER", tracker)

    live = data_dir / "suppressions.json"
    example = data_dir / "suppressions.example.json"
    events = data_dir / "suppressions_events.jsonl"
    history = data_dir / "suppressions_history.json"
    pending = data_dir / "suppressions_pending_archives.jsonl"
    example.write_text(
        json.dumps({"version": 1, "sectors": [], "companies": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(supp, "LIVE_PATH", live)
    monkeypatch.setattr(supp, "EXAMPLE_PATH", example)
    monkeypatch.setattr(supp, "EVENTS_PATH", events)
    monkeypatch.setattr(supp, "HISTORY_PATH", history)
    monkeypatch.setattr(supp, "PENDING_ARCHIVES_PATH", pending)
    monkeypatch.setattr(auto_promote, "_suppressions", supp)
    monkeypatch.delenv("APPLYAGENT_SUPPRESSIONS_SNAPSHOT", raising=False)

    return {
        "tmp": tmp_path,
        "out_dir": out_dir,
        "tracker": tracker,
        "data_dir": data_dir,
    }


def _write_scored(out_dir: Path, name: str, results: list[dict]) -> Path:
    path = out_dir / name
    path.write_text(
        json.dumps({"scan_date": "2026-05-26", "results": results}, indent=2),
        encoding="utf-8",
    )
    return path


def _run_main(monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["auto_promote.py", *argv])
    return auto_promote.main()


# ---------------------------------------------------------------------------
# Site A — auto_promote expire-stale skips archived rows
# ---------------------------------------------------------------------------

def test_expire_stale_skips_archived_rows(isolated, monkeypatch):
    """Two auto- tracker rows in Found state, both with URLs absent from the
    latest scan. One is archived, one is not. Only the non-archived row
    should be flipped to Expired."""
    archived_url = "https://example.com/jobs/archived-row"
    active_url = "https://example.com/jobs/active-row"

    tr = _empty_tracker()
    tr["jobs"] = [
        {
            "id": "auto-archived-row",
            "company": "ArchivedCo",
            "title": "Old Role",
            "url": archived_url,
            "status": "Found",
            "archived": True,
            "archived_at": "2026-05-20T00:00:00Z",
            "archive_reason": "wrong sector",
            "fit_score_numeric": 7,
            "source": "scraper+fit_scorer",
        },
        {
            "id": "auto-active-row",
            "company": "ActiveCo",
            "title": "Other Role",
            "url": active_url,
            "status": "Found",
            "archived": False,
            "fit_score_numeric": 7,
            "source": "scraper+fit_scorer",
        },
    ]
    isolated["tracker"].write_text(json.dumps(tr), encoding="utf-8")

    # Latest scan contains a different URL only — both tracker rows are stale.
    fresh_url = "https://example.com/jobs/fresh"
    rows = [_scored_row("FreshCo", "Risk Lead", fresh_url, fit_score=8)]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--expire-stale",
        "--min-score", "7",
    ])
    assert rc == 0

    final = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    by_id = {j["id"]: j for j in final["jobs"]}

    # Archived row: status untouched (still "Found"), archived flag preserved.
    assert by_id["auto-archived-row"]["status"] == "Found"
    assert by_id["auto-archived-row"]["archived"] is True

    # Active row: flipped to Expired.
    assert by_id["auto-active-row"]["status"] == "Expired"
    assert by_id["auto-active-row"]["archived"] is False


def test_expire_stale_still_expires_when_no_archived_rows_present(
    isolated, monkeypatch,
):
    """Sanity guard: the Phase 5 routing must NOT regress the legacy
    expire-stale path when no archived rows exist."""
    stale_url = "https://example.com/jobs/stale"
    tr = _empty_tracker()
    tr["jobs"] = [
        {
            "id": "auto-stale",
            "company": "StaleCo",
            "title": "Old",
            "url": stale_url,
            "status": "Found",
            "archived": False,
            "fit_score_numeric": 7,
            "source": "scraper+fit_scorer",
        },
    ]
    isolated["tracker"].write_text(json.dumps(tr), encoding="utf-8")

    # Latest scan contains a different URL — the stale row is no longer there.
    rows = [_scored_row("OtherCo", "Title", "https://example.com/jobs/other",
                        fit_score=8)]
    _write_scored(isolated["out_dir"], "scan_synth_scored.json", rows)

    rc = _run_main(monkeypatch, [
        "--scan", "scan_synth_scored.json",
        "--commit",
        "--expire-stale",
        "--min-score", "7",
    ])
    assert rc == 0
    final = json.loads(isolated["tracker"].read_text(encoding="utf-8"))
    by_id = {j["id"]: j for j in final["jobs"]}
    assert by_id["auto-stale"]["status"] == "Expired"


# ---------------------------------------------------------------------------
# Site B — outcome_feedback cold-lane denominator skips archived rows
# ---------------------------------------------------------------------------

def _applied_job(job_id: str, *, sector: str = "Canadian Big 6 Banks",
                 archived: bool = False, status: str = "Applied") -> dict:
    return {
        "id": job_id,
        "company": f"Co{job_id}",
        "title": "Risk Analyst",
        "url": f"https://example.com/{job_id}",
        "sector": sector,
        "tier": 1,
        "primary_variant": "risk",
        "status": status,
        "archived": archived,
    }


def test_cold_lane_denominator_excludes_archived(tmp_path):
    """10 sector-X Applied rows, of which 5 are archived. The cold-lane
    denominator (`applied`) must count 5, not 10."""
    tracker_path = tmp_path / "tracker.json"
    jobs = []
    # 5 active Applied rows + 5 archived Applied rows in the same sector.
    for i in range(5):
        jobs.append(_applied_job(f"active-{i}", archived=False))
    for i in range(5):
        jobs.append(_applied_job(f"archived-{i}", archived=True))
    tracker_path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")

    report = outcome_feedback.build_report(tracker_path)

    sector_key = "sector:Canadian Big 6 Banks"
    assert sector_key in report.sectors
    s = report.sectors[sector_key]
    assert s.applied == 5, f"expected 5 active applieds, got {s.applied}"
    assert s.total_in_pipeline == 5, (
        f"expected 5 active rows, got {s.total_in_pipeline}"
    )
    assert s.interviewed == 0
    # 5 < the cold_lane threshold of 5+ AND interviewed==0 — actually
    # >=5 is the threshold so this hits exactly. Confirm BOTH the count
    # came out right AND that the lane qualifies.
    cold_lane_keys = [ln for ln in report.cold_lanes if sector_key in ln]
    assert len(cold_lane_keys) == 1
    # Total tracker count should also exclude archived (5, not 10).
    assert report.total_in_tracker == 5


def test_cold_lane_denominator_without_archived_rows_unchanged(tmp_path):
    """Sanity guard: with no archived rows, behavior is identical to the
    pre-Phase-5 baseline."""
    tracker_path = tmp_path / "tracker.json"
    jobs = [_applied_job(f"r-{i}") for i in range(6)]
    tracker_path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")

    report = outcome_feedback.build_report(tracker_path)
    sector_key = "sector:Canadian Big 6 Banks"
    assert report.sectors[sector_key].applied == 6
    assert report.total_in_tracker == 6
    cold_lane_keys = [ln for ln in report.cold_lanes if sector_key in ln]
    assert len(cold_lane_keys) == 1


def test_cold_lane_keeps_rejected_outcomes_in_denominator(tmp_path):
    """Critical regression guard: routing must NOT exclude Rejected rows.
    Rejected is exactly the outcome the cold-lane signal is built to surface
    (you applied N times → N rejections → cold lane). Using is_active here
    instead of an archived-only gate would have broken this."""
    tracker_path = tmp_path / "tracker.json"
    jobs = []
    # 5 Rejected rows — all should count toward s.applied (Rejected is in
    # APPLIED_STATUSES) and the lane should hit the cold-lane threshold.
    for i in range(5):
        jobs.append(_applied_job(f"r-{i}", status="Rejected"))
    tracker_path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")

    report = outcome_feedback.build_report(tracker_path)
    sector_key = "sector:Canadian Big 6 Banks"
    s = report.sectors[sector_key]
    assert s.applied == 5
    assert s.rejected == 5
    assert s.interviewed == 0
    # The cold-lane signal MUST fire on this fixture.
    cold_lane_keys = [ln for ln in report.cold_lanes if sector_key in ln]
    assert len(cold_lane_keys) == 1
