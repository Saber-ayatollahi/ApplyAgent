"""Unit tests for ui.pipeline_state — pure-function banner state machine.

Two layers:
1. `compute_next_action(Snapshot)` — exhaustive priority-ladder cases.
2. `derive_snapshot(...)` — file-system wiring tests using tmp_path.

The state machine is the load-bearing piece — if it picks the wrong banner,
the user is told to do the wrong thing. Every priority-ladder rule needs
at least one positive case AND a precedence case proving the rule above
beats it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from ui import pipeline_state as ps  # noqa: E402


# ---------------------------------------------------------------------------
# Builder helpers — keeps test cases readable
# ---------------------------------------------------------------------------

def _snap(**overrides) -> ps.Snapshot:
    """Snapshot with sensible 'nothing-going-on' defaults; override per test."""
    base = dict(
        scrape_age_h=1.0,
        gmail_age_h=1.0,
        worklist_total=100,
        triage_passed=50,
        triage_dropped=50,
        billable_count=0,
        cached_count=0,
        reusable_count=0,
        promotable_count=0,
        suppressed_promotable_count=0,
        quarantine_count=0,
        recent_promote_count=0,
        last_promote_age_h=None,
        scored_age_h=2.0,
        active_runs=(),
        last_failure=None,
        api_key_valid=True,
        gmail_connected=True,
        suppression_invalid_names=(),
        suppression_recently_expired=(),
    )
    base.update(overrides)
    return ps.Snapshot(**base)


# ---------------------------------------------------------------------------
# Rule 1 — SAFETY (quarantine_ratio > 0.5)
# ---------------------------------------------------------------------------

def test_safety_wins_over_everything():
    """Even with active runs + promotables, quarantine ratio > 0.5 wins."""
    s = _snap(
        worklist_total=10,
        quarantine_count=20,           # 20 / (20 + 10) = 0.66
        active_runs=({"label": "scoring", "pct": 50.0},),
        promotable_count=5,
    )
    b = ps.compute_next_action(s)
    assert b.state == "SAFETY"
    assert b.severity == "error"
    assert b.cta_action == "quarantine"


def test_safety_off_at_50_pct_threshold():
    """At exactly 50% it's not >0.5, so SAFETY does NOT fire."""
    s = _snap(worklist_total=10, quarantine_count=10, promotable_count=3)
    b = ps.compute_next_action(s)
    assert b.state != "SAFETY"


# ---------------------------------------------------------------------------
# Rule 2 — ACTIVE
# ---------------------------------------------------------------------------

def test_active_wins_over_promote():
    s = _snap(
        active_runs=({"label": "scoring", "pct": 30.0},),
        promotable_count=5,
    )
    b = ps.compute_next_action(s)
    assert b.state == "ACTIVE"
    assert b.cta_action == "stop_run"
    assert "30%" in b.headline


def test_active_handles_multiple_runs():
    s = _snap(active_runs=(
        {"label": "scrape", "pct": 80},
        {"label": "score", "pct": 10},
    ))
    b = ps.compute_next_action(s)
    assert "+1 other" in b.headline


# ---------------------------------------------------------------------------
# Rule 3 — RECENT (only when no usable downstream work)
# ---------------------------------------------------------------------------

def test_recent_failure_blocks_only_when_nothing_to_do():
    """Failed scrape with no usable downstream → RECENT wins."""
    s = _snap(
        worklist_total=0,
        promotable_count=0,
        billable_count=0,
        reusable_count=0,
        last_failure={"stage": "scrape", "age_h": 0.1, "pipeline_id": "abc"},
    )
    b = ps.compute_next_action(s)
    assert b.state == "RECENT"
    assert "Retry scrape" in b.cta_label


def test_recent_failure_yields_to_promote():
    """Failed scrape but worklist still has promotables → PROMOTE wins.

    The design-doc note: 'failed scrape with usable worklist → green CTA wins'."""
    s = _snap(
        promotable_count=3,
        last_failure={"stage": "scrape", "age_h": 0.1, "pipeline_id": "abc"},
    )
    b = ps.compute_next_action(s)
    assert b.state == "PROMOTE"


def test_recent_failure_old_does_not_fire():
    """Failure older than 30min doesn't trigger RECENT."""
    s = _snap(
        worklist_total=0, promotable_count=0,
        billable_count=0, reusable_count=0,
        last_failure={"stage": "scrape", "age_h": 5.0, "pipeline_id": "abc"},
    )
    b = ps.compute_next_action(s)
    assert b.state != "RECENT"


# ---------------------------------------------------------------------------
# Rule 4 — PROMOTE
# ---------------------------------------------------------------------------

def test_promote_wins_over_score():
    s = _snap(
        promotable_count=5,
        billable_count=200,
        reusable_count=10,
    )
    b = ps.compute_next_action(s)
    assert b.state == "PROMOTE"
    assert b.cta_action == "promote"
    assert "5" in b.headline


def test_promote_headline_mentions_after_suppressions():
    """The 'after suppressions' phrasing is the user-visible signal that
    the count is post-filter — covered by Cluster B § visibility."""
    s = _snap(promotable_count=12)
    b = ps.compute_next_action(s)
    assert "after suppressions" in b.headline


# ---------------------------------------------------------------------------
# Rule 5 — REVIEW (just scored, 0 promotable, ≥1 verdict)
# ---------------------------------------------------------------------------

def test_review_when_just_scored_nothing_promotable():
    s = _snap(
        promotable_count=0,
        scored_age_h=0.5,
        triage_passed=20,
    )
    b = ps.compute_next_action(s)
    assert b.state == "REVIEW"


def test_review_does_not_fire_for_old_scored():
    """If scored_age > 24h, the user already saw this; don't nag."""
    s = _snap(
        promotable_count=0,
        scored_age_h=48.0,
        triage_passed=20,
    )
    b = ps.compute_next_action(s)
    assert b.state != "REVIEW"


def test_suppress_aware_empty_wins_over_review():
    """When promotables=0 BECAUSE everything was suppressed, surface that
    specifically — generic REVIEW would point at the wrong remedy."""
    s = _snap(
        promotable_count=0,
        suppressed_promotable_count=8,
        scored_age_h=0.5,
        triage_passed=20,
    )
    b = ps.compute_next_action(s)
    assert b.state == "SUPPRESS-AWARE-EMPTY"
    assert "8" in b.headline
    assert b.cta_action == "review_suppressions"


# ---------------------------------------------------------------------------
# Rule 6 — SCORE / SCORE-BLOCKED
# ---------------------------------------------------------------------------

def test_score_when_billable_present():
    """SCORE fires when there's no fresher REVIEW prompt — i.e., the user
    already saw the previous batch (>24h ago)."""
    s = _snap(
        billable_count=200, reusable_count=20,
        scored_age_h=72.0,           # not "just scored"
    )
    b = ps.compute_next_action(s)
    assert b.state == "SCORE"
    assert "220" in b.headline
    assert "200 billable" in b.detail
    assert "20 free" in b.detail


def test_score_blocked_when_api_key_invalid():
    s = _snap(
        billable_count=200, api_key_valid=False,
        scored_age_h=72.0,
    )
    b = ps.compute_next_action(s)
    assert b.state == "SCORE-BLOCKED"
    assert b.cta_action == "set_api_key"
    # Chip is still attached so the user sees the consistent decoration.
    assert any(c.icon == "🔑" for c in b.chips)


def test_score_yields_to_promote():
    s = _snap(billable_count=500, promotable_count=2)
    b = ps.compute_next_action(s)
    assert b.state == "PROMOTE"


# ---------------------------------------------------------------------------
# Rule 7 — REFRESH
# ---------------------------------------------------------------------------

def test_refresh_when_inputs_stale():
    s = _snap(
        worklist_total=100,
        scrape_age_h=72.0,
        gmail_age_h=72.0,
        promotable_count=0,
        billable_count=0,
        scored_age_h=72.0,
    )
    b = ps.compute_next_action(s)
    assert b.state == "REFRESH"


def test_refresh_uses_max_age():
    """If scrape is old but Gmail is fresh, refresh shouldn't fire."""
    s = _snap(
        scrape_age_h=72.0, gmail_age_h=1.0,
        promotable_count=0, billable_count=0,
        scored_age_h=72.0,
    )
    b = ps.compute_next_action(s)
    assert b.state != "REFRESH"


# ---------------------------------------------------------------------------
# Rule 8 — EMPTY
# ---------------------------------------------------------------------------

def test_empty_when_no_worklist():
    s = _snap(
        worklist_total=0,
        triage_passed=0,
        scored_age_h=None,
    )
    b = ps.compute_next_action(s)
    assert b.state == "EMPTY"
    assert b.cta_action == "setup"


# ---------------------------------------------------------------------------
# Rule 8.5 — SUPPRESS-EXPIRED (7-day window)
# ---------------------------------------------------------------------------

def test_suppress_expired_fires_above_default():
    s = _snap(
        worklist_total=100,
        triage_passed=50,
        scored_age_h=72.0,         # too old to be REVIEW
        suppression_recently_expired=(
            {"name": "Big 6 Banks", "until": "2026-05-25"},
        ),
    )
    b = ps.compute_next_action(s)
    assert b.state == "SUPPRESS-EXPIRED"
    assert "Big 6 Banks" in b.headline


def test_suppress_expired_yields_to_promote():
    """Even if a mute lapsed, an actual promotable should be the priority."""
    s = _snap(
        promotable_count=4,
        suppression_recently_expired=(
            {"name": "Big 6 Banks", "until": "2026-05-25"},
        ),
    )
    b = ps.compute_next_action(s)
    assert b.state == "PROMOTE"


# ---------------------------------------------------------------------------
# Rule 8.6 — SUPPRESS-INVALID (sector renamed)
# ---------------------------------------------------------------------------

def test_suppress_invalid_fires():
    s = _snap(
        worklist_total=100,
        triage_passed=50,
        scored_age_h=72.0,
        suppression_invalid_names=("OldSectorName",),
    )
    b = ps.compute_next_action(s)
    assert b.state == "SUPPRESS-INVALID"
    assert "OldSectorName" in b.headline
    assert b.severity == "warn"


def test_suppress_invalid_truncates_long_list():
    s = _snap(
        worklist_total=100, triage_passed=50, scored_age_h=72.0,
        suppression_invalid_names=("A", "B", "C", "D", "E"),
    )
    b = ps.compute_next_action(s)
    assert "+2 more" in b.headline


def test_suppress_invalid_yields_to_expired():
    """If both invalid AND recently-expired, expired is the more urgent
    user-facing decision (renew/lift)."""
    s = _snap(
        worklist_total=100, triage_passed=50, scored_age_h=72.0,
        suppression_recently_expired=(
            {"name": "Big 6 Banks", "until": "2026-05-25"},
        ),
        suppression_invalid_names=("OldSectorName",),
    )
    b = ps.compute_next_action(s)
    assert b.state == "SUPPRESS-EXPIRED"


# ---------------------------------------------------------------------------
# Rule 9 — DEFAULT
# ---------------------------------------------------------------------------

def test_default_when_nothing_to_do():
    s = _snap(
        worklist_total=100,
        promotable_count=0,
        billable_count=0,
        reusable_count=0,
        triage_passed=50,
        scored_age_h=72.0,           # not "just scored"
        scrape_age_h=2.0,
        gmail_age_h=2.0,
    )
    b = ps.compute_next_action(s)
    assert b.state == "DEFAULT"
    assert b.severity == "success"
    assert b.cta_action is None


# ---------------------------------------------------------------------------
# Chips — decoration only, never the banner alone
# ---------------------------------------------------------------------------

def test_api_key_chip_attaches_to_promote():
    """Chip is informational; PROMOTE is still the primary action even with
    an invalid key (promote doesn't need the key)."""
    s = _snap(promotable_count=3, api_key_valid=False)
    b = ps.compute_next_action(s)
    assert b.state == "PROMOTE"
    assert any(c.icon == "🔑" for c in b.chips)


def test_recent_promote_chip_within_decay_window():
    s = _snap(
        recent_promote_count=4,
        last_promote_age_h=0.05,    # ~3 min, within 12-min window
        promotable_count=0,
        billable_count=0,
        scored_age_h=72.0,
    )
    b = ps.compute_next_action(s)
    success_chips = [c for c in b.chips if c.icon == "✅"]
    assert success_chips
    assert "Promoted 4" in success_chips[0].label


def test_recent_promote_chip_decays_after_window():
    s = _snap(
        recent_promote_count=4,
        last_promote_age_h=1.0,     # outside 12-min window
        promotable_count=0, billable_count=0, scored_age_h=72.0,
    )
    b = ps.compute_next_action(s)
    assert not any(c.icon == "✅" for c in b.chips)


# ---------------------------------------------------------------------------
# derive_snapshot — file-system wiring
# ---------------------------------------------------------------------------

@pytest.fixture
def fs(tmp_path):
    """Build a minimal fake outputs/ tree the way the real pipeline does."""
    out = tmp_path / "outputs"
    out.mkdir()
    cache = tmp_path / "fit_cache"
    cache.mkdir()
    pipelines = out / "pipelines"
    pipelines.mkdir()
    tracker = tmp_path / "job_tracker_data.json"
    tracker.write_text(json.dumps({"jobs": []}), encoding="utf-8")
    return {
        "out": out, "cache": cache, "pipelines": pipelines,
        "tracker": tracker, "tmp": tmp_path,
    }


def test_derive_snapshot_empty_filesystem(fs):
    """No artifacts → all-zero snapshot, EMPTY banner."""
    s = ps.derive_snapshot(
        out_dir=fs["out"],
        fit_cache_dir=fs["cache"],
        tracker_path=fs["tracker"],
    )
    assert s.worklist_total == 0
    assert s.triage_passed == 0
    assert s.billable_count == 0

    b = ps.compute_next_action(s)
    assert b.state == "EMPTY"


def test_derive_snapshot_reads_worklist_and_scored(fs):
    """worklist + scored populated → counts roll up correctly."""
    out = fs["out"]
    (out / "worklist.json").write_text(json.dumps({
        "rebuilt_at": datetime.now().isoformat(timespec="seconds"),
        "results": [{"url": f"https://x/{i}", "company": "C", "sector": ""}
                    for i in range(10)],
        "quarantine": [{"url": "https://x/q1"}],
    }), encoding="utf-8")
    (out / "worklist_scored.json").write_text(json.dumps({
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "stage1_passed": 5,
        "stage1_dropped": 5,
        "results": [
            {"url": f"https://x/{i}", "fit": {"score": 8, "verdict": "apply_now"}}
            for i in range(3)
        ] + [
            {"url": f"https://x/{i+3}",
             "fit": {"score": 5, "verdict": "watch"}} for i in range(2)
        ],
    }), encoding="utf-8")
    s = ps.derive_snapshot(
        out_dir=out, fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
        min_score=7,
    )
    assert s.worklist_total == 10
    assert s.triage_passed == 5
    assert s.triage_dropped == 5
    assert s.quarantine_count == 1
    assert s.promotable_count == 3   # three rows ≥7, none in tracker
    assert s.suppressed_promotable_count == 0
    assert s.scored_age_h is not None and s.scored_age_h < 1


def test_derive_snapshot_reusable_count_uses_link_key(fs):
    """Regression: production worklist + scored rows are keyed `link`, not
    `url` (fit_scorer passes the worklist row straight through). The old
    `reusable_count` summed `r.get("url") in worklist_urls`, which was
    ALWAYS 0 against real data — the 'free re-score' count silently lied.
    Build the snapshot from link-keyed rows and assert it's non-zero."""
    out = fs["out"]
    (out / "worklist.json").write_text(json.dumps({
        "rebuilt_at": datetime.now().isoformat(timespec="seconds"),
        "results": [{"link": f"https://x/{i}", "company": "C", "sector": ""}
                    for i in range(4)],
    }), encoding="utf-8")
    (out / "worklist_scored.json").write_text(json.dumps({
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "stage1_passed": 4, "stage1_dropped": 0,
        "results": [
            {"link": f"https://x/{i}",
             "fit": {"fit_score": 8, "fit_verdict": "apply_now",
                     "skill_gaps": [], "summary": ""}}
            for i in range(4)
        ],
    }), encoding="utf-8")
    s = ps.derive_snapshot(
        out_dir=out, fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
        min_score=7,
    )
    # All 4 scored rows are link-matched against the worklist → reusable.
    assert s.reusable_count == 4


def test_derive_snapshot_promotable_excludes_tracker_urls(fs):
    out = fs["out"]
    (out / "worklist_scored.json").write_text(json.dumps({
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "stage1_passed": 2, "stage1_dropped": 0,
        "results": [
            {"url": "https://x/1", "fit": {"score": 8, "verdict": "apply_now"}},
            {"url": "https://x/2", "fit": {"score": 9, "verdict": "apply_now"}},
        ],
    }), encoding="utf-8")
    fs["tracker"].write_text(json.dumps({
        "jobs": [{"url": "https://x/1"}],
    }), encoding="utf-8")
    s = ps.derive_snapshot(
        out_dir=out, fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
        min_score=7,
    )
    assert s.promotable_count == 1   # https://x/2 only


def test_derive_snapshot_canonicalizes_linkedin_drift(fs):
    """Regression: LinkedIn URL drift used to evade tracker dedup in the UI.
    Tracker stores `www.linkedin.com/jobs/view/<id>` (bare canonical); the
    scored row carries `ca.linkedin.com/jobs/view/<slug>-<id>` (regional +
    slugged). Both collapse to the same id via worklist.norm_url, so the
    row must NOT count as promotable — otherwise the user clicks promote,
    auto_promote correctly drops it as a dupe, and the row stays in the
    promote table forever."""
    out = fs["out"]
    (out / "worklist_scored.json").write_text(json.dumps({
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "stage1_passed": 1, "stage1_dropped": 0,
        "results": [
            {"url": ("https://ca.linkedin.com/jobs/view/"
                     "associate-director-alm-strategy-at-scotiabank-4424008899"),
             "fit": {"score": 9, "verdict": "apply_now"}},
        ],
    }), encoding="utf-8")
    fs["tracker"].write_text(json.dumps({
        "jobs": [{"url": "https://www.linkedin.com/jobs/view/4424008899"}],
    }), encoding="utf-8")
    s = ps.derive_snapshot(
        out_dir=out, fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
        min_score=7,
    )
    assert s.promotable_count == 0


def test_derive_snapshot_suppressed_promotable_split(fs):
    """A would-be promotable that hits a sector mute counts toward
    `suppressed_promotable_count`, not `promotable_count`."""
    out = fs["out"]
    (out / "worklist_scored.json").write_text(json.dumps({
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "stage1_passed": 2, "stage1_dropped": 0,
        "results": [
            {"url": "https://x/1", "company": "RBC",
             "sector": "Canadian Big 6 Banks",
             "fit": {"score": 9, "verdict": "apply_now"}},
            {"url": "https://x/2", "company": "Other",
             "sector": "Fintech",
             "fit": {"score": 8, "verdict": "apply_now"}},
        ],
    }), encoding="utf-8")
    state = {
        "version": 1,
        "sectors": [{"name": "Canadian Big 6 Banks",
                     "canonical_key": "canadian big 6 banks",
                     "until": None, "reason": "test"}],
        "companies": [],
    }
    s = ps.derive_snapshot(
        out_dir=out, fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
        suppressions_state=state, min_score=7,
    )
    assert s.promotable_count == 1
    assert s.suppressed_promotable_count == 1


def test_derive_snapshot_invalid_suppression_name_surfaces(fs):
    """Sector renamed → registry no longer matches → SUPPRESS-INVALID."""
    state = {
        "version": 1,
        "sectors": [{"name": "RetiredSectorName",
                     "canonical_key": "retiredsectorname",
                     "until": None, "reason": "old"}],
        "companies": [],
    }
    s = ps.derive_snapshot(
        out_dir=fs["out"], fit_cache_dir=fs["cache"],
        tracker_path=fs["tracker"], suppressions_state=state,
    )
    assert "RetiredSectorName" in s.suppression_invalid_names


def test_derive_snapshot_picks_up_recent_failure(fs):
    """A failed pipeline status file within 24h → last_failure populated."""
    pipelines = fs["pipelines"]
    fail_file = pipelines / "pipeline_20260527_120000.json"
    fail_file.write_text(json.dumps({
        "pipeline_id": "20260527_120000",
        "stages": {"score": {"state": "failed"}, "scrape": {"state": "finished"}},
    }), encoding="utf-8")
    s = ps.derive_snapshot(
        out_dir=fs["out"], fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
    )
    assert s.last_failure is not None
    assert s.last_failure["stage"] == "score"


def test_derive_snapshot_skips_old_pipeline_failures(fs):
    """Pipeline file older than 24h shouldn't poison the snapshot."""
    pipelines = fs["pipelines"]
    fail_file = pipelines / "pipeline_old.json"
    fail_file.write_text(json.dumps({
        "pipeline_id": "old", "stages": {"score": {"state": "failed"}},
    }), encoding="utf-8")
    # Push mtime back 48h.
    old_ts = (datetime.now() - timedelta(hours=48)).timestamp()
    import os
    os.utime(fail_file, (old_ts, old_ts))
    s = ps.derive_snapshot(
        out_dir=fs["out"], fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
    )
    assert s.last_failure is None


# ---------------------------------------------------------------------------
# coverage_for_entry — used by the Triage card's Active suppressions table
# ---------------------------------------------------------------------------

def test_coverage_for_entry_sector_includes_unsectored():
    rows = [
        {"sector": "Canadian Big 6 Banks", "company": "RBC"},
        {"sector": "Canadian Big 6 Banks", "company": "TD"},
        {"sector": "Fintech", "company": "Wave"},
        {"sector": "", "company": "Mystery Co"},   # unsectored
    ]
    cov = ps.coverage_for_entry(
        {"scope": "sector", "name": "Canadian Big 6 Banks"}, rows,
    )
    assert cov["matched"] == 2
    assert cov["unsectored"] == 1


def test_coverage_for_entry_company_includes_unsectored_count():
    """Company-scope still reports unsectored count for the visibility line
    in the mute-confirm: 'N rows in this sector lack tags' style."""
    rows = [
        {"sector": "Fintech", "company": "Acme Corp"},
        {"sector": "", "company": "Mystery"},
        {"sector": "", "company": "Acme Corp"},
    ]
    cov = ps.coverage_for_entry(
        {"scope": "company", "name": "Acme Corp"}, rows,
    )
    assert cov["matched"] == 2
    assert cov["unsectored"] == 2


# ---------------------------------------------------------------------------
# Phase 3B — apply_selection_edit (URL-keyed selection state)
#
# These tests document the contract that fixes the index-based bug in
# the existing data_editor selection: filter changes must NOT corrupt
# selection state, and a row off-screen must NOT be silently un-selected.
# ---------------------------------------------------------------------------

def test_selection_edit_initial_tick():
    """Empty selection + user ticks one visible row → that row is selected."""
    new = ps.apply_selection_edit(
        selection=set(),
        visible_urls={"https://x/1", "https://x/2", "https://x/3"},
        ticked_urls={"https://x/2"},
    )
    assert new == {"https://x/2"}


def test_selection_edit_filter_change_preserves_offscreen_state():
    """User selects /1 from a wide view; user filters down to NOT show /1;
    nothing was ticked in the new view → /1 must remain selected."""
    new = ps.apply_selection_edit(
        selection={"https://x/1"},
        visible_urls={"https://x/2", "https://x/3"},   # /1 hidden
        ticked_urls=set(),                               # nothing ticked
    )
    assert new == {"https://x/1"}


def test_selection_edit_untick_visible_row():
    """User had /2 selected; the row is visible and they untick it."""
    new = ps.apply_selection_edit(
        selection={"https://x/2"},
        visible_urls={"https://x/1", "https://x/2"},
        ticked_urls=set(),                               # /2 unticked
    )
    assert new == set()


def test_selection_edit_combination_filter_and_tick():
    """Mid-flow: had {1,2,3} selected from wide view; filtered to show
    {2,3,4}; user ticks 4 and unticks 3. /1 stays selected (off-screen)."""
    new = ps.apply_selection_edit(
        selection={"https://x/1", "https://x/2", "https://x/3"},
        visible_urls={"https://x/2", "https://x/3", "https://x/4"},
        ticked_urls={"https://x/2", "https://x/4"},
    )
    assert new == {"https://x/1", "https://x/2", "https://x/4"}


def test_selection_edit_defends_against_inconsistent_ticked():
    """If ticked claims a URL not in visible, drop it (caller error)."""
    new = ps.apply_selection_edit(
        selection=set(),
        visible_urls={"https://x/1"},
        ticked_urls={"https://x/1", "https://x/9999"},   # /9999 not visible
    )
    assert new == {"https://x/1"}


# ---------------------------------------------------------------------------
# Phase 3B — compute_preflight_breakdown (caption beneath [Send N selected])
# ---------------------------------------------------------------------------

def test_preflight_empty_selection():
    bd = ps.compute_preflight_breakdown(
        selection=set(), scored_rows=[],
    )
    assert bd["total"] == 0


def test_preflight_clean_above_threshold_unsupressed():
    rows = [
        {"url": "https://x/1", "fit": {"score": 8, "verdict": "apply_now"}},
        {"url": "https://x/2", "fit": {"score": 9, "verdict": "apply_now"}},
    ]
    bd = ps.compute_preflight_breakdown(
        selection={"https://x/1", "https://x/2"},
        scored_rows=rows, min_score=7,
    )
    assert bd["total"] == 2
    assert bd["below_threshold"] == 0
    assert bd["override_mute"] == 0
    assert bd["already_tracked"] == 0


def test_preflight_below_threshold_counted():
    rows = [
        {"url": "https://x/1", "fit": {"score": 6, "verdict": "watch"}},
        {"url": "https://x/2", "fit": {"score": 8, "verdict": "apply_now"}},
    ]
    bd = ps.compute_preflight_breakdown(
        selection={"https://x/1", "https://x/2"},
        scored_rows=rows, min_score=7,
    )
    assert bd["below_threshold"] == 1


def test_preflight_override_mute_counted():
    """Selected row that's in a muted sector → counts toward override_mute.

    Per Phase-2 E2E Round 2, manual selection PROMOTES with the
    manual_override_suppression tag — this is explicit user-intent, not
    a drop. The caption tells the user 'this overrides a mute' so they're
    not surprised."""
    rows = [
        {"url": "https://x/1", "company": "RBC",
         "sector": "Canadian Big 6 Banks",
         "fit": {"score": 9, "verdict": "apply_now"}},
        {"url": "https://x/2", "company": "Wave", "sector": "Fintech",
         "fit": {"score": 8, "verdict": "apply_now"}},
    ]
    state = {
        "version": 1,
        "sectors": [{"name": "Canadian Big 6 Banks",
                     "canonical_key": "canadian big 6 banks",
                     "until": None, "reason": "test"}],
        "companies": [],
    }
    bd = ps.compute_preflight_breakdown(
        selection={"https://x/1", "https://x/2"},
        scored_rows=rows, suppressions_state=state, min_score=7,
    )
    assert bd["override_mute"] == 1
    assert bd["below_threshold"] == 0


def test_preflight_already_in_tracker_counted():
    rows = [
        {"url": "https://x/1", "fit": {"score": 8, "verdict": "apply_now"}},
        {"url": "https://x/2", "fit": {"score": 9, "verdict": "apply_now"}},
    ]
    bd = ps.compute_preflight_breakdown(
        selection={"https://x/1", "https://x/2"},
        scored_rows=rows,
        tracker_urls={"https://x/1"},
    )
    assert bd["already_tracked"] == 1


def test_preflight_canonicalizes_linkedin_drift():
    """Regression: a selected LinkedIn URL must be canonicalized through
    worklist.norm_url before checking tracker membership. The tracker key
    set is canonical, but the selection (driven by the data_editor) carries
    raw scored-row URLs that may differ by host (`ca.` vs `www.`) and slug.
    Without canonicalization the caption says "0 already tracked" and the
    user is misled into expecting a fresh promote."""
    scored_url = ("https://ca.linkedin.com/jobs/view/"
                  "associate-director-alm-strategy-at-scotiabank-4424008899")
    canon = "https://www.linkedin.com/jobs/view/4424008899"
    rows = [{"url": scored_url, "fit": {"score": 9, "verdict": "apply_now"}}]
    bd = ps.compute_preflight_breakdown(
        selection={scored_url},
        scored_rows=rows,
        tracker_urls={canon},   # canonical key, as _tracker_url_set now produces
    )
    assert bd["already_tracked"] == 1


def test_preflight_missing_url_counted():
    """User somehow selected a URL no longer in the scored file (rescore
    dropped it, e.g.). Caption flags it so they don't see a silent shrink."""
    bd = ps.compute_preflight_breakdown(
        selection={"https://x/ghost"},
        scored_rows=[],
    )
    assert bd["missing_in_scored"] == 1
    assert bd["total"] == 1


def test_preflight_caption_format_clean():
    bd = {"total": 5, "below_threshold": 0, "override_mute": 0,
          "already_tracked": 0, "missing_in_scored": 0}
    assert ps.format_preflight_caption(bd) == "Will send 5."


def test_preflight_caption_format_with_buckets():
    bd = {"total": 27, "below_threshold": 4, "override_mute": 1,
          "already_tracked": 2, "missing_in_scored": 0}
    s = ps.format_preflight_caption(bd)
    assert "Will send 27" in s
    assert "4 below fit≥7" in s
    assert "1 overrides active mute" in s
    assert "2 already in tracker" in s


def test_preflight_caption_empty_selection():
    bd = {"total": 0, "below_threshold": 0, "override_mute": 0,
          "already_tracked": 0, "missing_in_scored": 0}
    assert ps.format_preflight_caption(bd) == "Nothing selected."


def test_preflight_handles_production_fit_score_schema():
    """Production rows from fit_scorer use `fit_score`/`fit_verdict`, not
    the compact `score`/`verdict`. Both must be accepted by the helpers."""
    rows = [
        {"link": "https://x/1",  # field is `link` in production, not `url`
         "fit": {"fit_score": 6, "fit_verdict": "watch",
                 "skill_gaps": [], "summary": ""}},
        {"link": "https://x/2",
         "fit": {"fit_score": 9, "fit_verdict": "apply_now",
                 "skill_gaps": [], "summary": ""}},
    ]
    bd = ps.compute_preflight_breakdown(
        selection={"https://x/1", "https://x/2"},
        scored_rows=rows, min_score=7,
    )
    assert bd["total"] == 2
    assert bd["below_threshold"] == 1   # /1 has fit_score=6
    assert bd["missing_in_scored"] == 0


def test_derive_snapshot_promotable_with_production_schema(fs):
    """Reading worklist_scored.json written by fit_scorer (uses fit_score)."""
    out = fs["out"]
    (out / "worklist_scored.json").write_text(json.dumps({
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "stage1_passed": 2, "stage1_dropped": 0,
        "results": [
            {"url": "https://x/1",
             "fit": {"fit_score": 8, "fit_verdict": "apply_now"}},
            {"url": "https://x/2",
             "fit": {"fit_score": 5, "fit_verdict": "watch"}},
        ],
    }), encoding="utf-8")
    s = ps.derive_snapshot(
        out_dir=out, fit_cache_dir=fs["cache"], tracker_path=fs["tracker"],
        min_score=7,
    )
    assert s.promotable_count == 1   # only /1 ≥7


# ---------------------------------------------------------------------------
# Phase 3C — format_until_label
# ---------------------------------------------------------------------------

def test_format_until_label_permanent():
    assert ps.format_until_label(None) == "permanent"
    assert ps.format_until_label("") == "permanent"
    assert ps.format_until_label("null") == "permanent"


def test_format_until_label_active():
    from datetime import date, timedelta
    today = date(2026, 5, 27)
    target = today + timedelta(days=10)
    s = ps.format_until_label(target.isoformat(), today=today)
    assert "10d left" in s
    assert "2026-06-06" in s


def test_format_until_label_expired():
    from datetime import date
    s = ps.format_until_label("2020-01-01", today=date(2026, 5, 27))
    assert s == "expired"


def test_format_until_label_today():
    from datetime import date
    today = date(2026, 5, 27)
    s = ps.format_until_label(today.isoformat(), today=today)
    assert "expires today" in s


def test_format_until_label_pathological_input():
    from datetime import date
    s = ps.format_until_label("not-a-date", today=date(2026, 5, 27))
    assert s.startswith("until ")  # surfaces raw value


# ---------------------------------------------------------------------------
# Phase 5 — parse_archive_reason (context-aware Restore decoder)
# ---------------------------------------------------------------------------

def test_parse_archive_reason_sector():
    """The Mute & archive form writes 'muted_sector_<canonical_name>' —
    decode it back to ('sector', name) so Restore can re-check the mute."""
    out = ps.parse_archive_reason("muted_sector_Canadian Big 6 Banks")
    assert out == ("sector", "Canadian Big 6 Banks")


def test_parse_archive_reason_company():
    out = ps.parse_archive_reason("muted_company_Acme Corp")
    assert out == ("company", "Acme Corp")


def test_parse_archive_reason_manual_returns_none():
    """Per-row Archive button writes 'manual_review_queue' / 'manual_kanban'
    — these aren't tied to an active mute and must NOT be parsed."""
    assert ps.parse_archive_reason("manual_review_queue") is None
    assert ps.parse_archive_reason("manual_kanban") is None


def test_parse_archive_reason_empty_or_invalid():
    """Empty / None / non-string / unparseable → None (caller falls back to
    plain Restore)."""
    assert ps.parse_archive_reason("") is None
    assert ps.parse_archive_reason("muted_sector_") is None  # empty name
    assert ps.parse_archive_reason("muted_region_X") is None
    assert ps.parse_archive_reason(None) is None  # type: ignore[arg-type]
    assert ps.parse_archive_reason(123) is None   # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Phase 3C — validate_suppression_form
# ---------------------------------------------------------------------------

def test_validate_form_sector_with_ttl():
    ok, err, until, canon = ps.validate_suppression_form(
        scope="sector", name="canadian big 6 banks",
        ttl_days=30, reason="Q2 cooldown",
    )
    assert ok and err is None
    assert canon == "Canadian Big 6 Banks"  # canonicalized
    assert until is not None


def test_validate_form_sector_unknown():
    ok, err, until, canon = ps.validate_suppression_form(
        scope="sector", name="Made Up Sector", ttl_days=30,
    )
    assert not ok
    assert "unknown sector" in err.lower()
    assert until is None


def test_validate_form_company_freeform():
    ok, err, until, canon = ps.validate_suppression_form(
        scope="company", name="Acme Corp", ttl_days=60,
    )
    assert ok and err is None
    assert canon == "Acme Corp"


def test_validate_form_empty_name():
    ok, err, _, _ = ps.validate_suppression_form(
        scope="sector", name="", ttl_days=30,
    )
    assert not ok
    assert "required" in err.lower()


def test_validate_form_invalid_scope():
    ok, err, _, _ = ps.validate_suppression_form(
        scope="region", name="x", ttl_days=30,
    )
    assert not ok
    assert "scope" in err.lower()


def test_validate_form_negative_ttl():
    ok, err, _, _ = ps.validate_suppression_form(
        scope="sector", name="Fintech", ttl_days=-5,
    )
    assert not ok
    assert "positive" in err.lower()


def test_validate_form_ttl_and_until_mutually_exclusive():
    ok, err, _, _ = ps.validate_suppression_form(
        scope="sector", name="Fintech", ttl_days=30, until_str="2027-01-01",
    )
    assert not ok
    assert "mutually exclusive" in err.lower()


def test_validate_form_until_in_past_rejected():
    ok, err, _, _ = ps.validate_suppression_form(
        scope="sector", name="Fintech", until_str="2020-01-01",
    )
    assert not ok
    assert "future" in err.lower()


def test_validate_form_until_bad_format():
    ok, err, _, _ = ps.validate_suppression_form(
        scope="sector", name="Fintech", until_str="not-a-date",
    )
    assert not ok
    assert "yyyy-mm-dd" in err.lower()


def test_validate_form_permanent_allowed():
    """No ttl_days, no until_str → permanent mute (UI surfaces yellow chip)."""
    ok, err, until, canon = ps.validate_suppression_form(
        scope="sector", name="Fintech",
    )
    assert ok and err is None
    assert until is None  # permanent


# ---------------------------------------------------------------------------
# Phase 3C — normalize_drop_reason / categorize_drop_reasons
# ---------------------------------------------------------------------------

def test_normalize_neg_term():
    cat, det = ps.normalize_drop_reason("neg:intern")
    assert cat == "neg_title_match"
    assert det == "intern"


def test_normalize_suppressed_sector_drops_ttl():
    """Different TTLs collapse to the same category — histogram doesn't
    fragment when a mute is renewed with a new TTL."""
    cat_60, det_60 = ps.normalize_drop_reason("suppressed_sector_60d")
    cat_30, det_30 = ps.normalize_drop_reason("suppressed_sector_30d")
    assert cat_60 == cat_30 == "suppressed_sector"
    assert det_60 == "60d"
    assert det_30 == "30d"


def test_normalize_suppressed_company():
    cat, det = ps.normalize_drop_reason("suppressed_company_15d")
    assert cat == "suppressed_company"
    assert det == "15d"


def test_normalize_keyword_strips_hit_list():
    cat, _ = ps.normalize_drop_reason("kw_match=alm,irrbb,pension")
    assert cat == "kw_match"


def test_normalize_unknown_passthrough():
    cat, det = ps.normalize_drop_reason("level_mismatch")
    assert cat == "level_mismatch"
    assert det is None


def test_categorize_buckets_correctly():
    drops = [
        {"rule_reasons": ["suppressed_sector_60d"]},
        {"rule_reasons": ["suppressed_sector_30d"]},
        {"rule_reasons": ["suppressed_company_15d"]},
        {"rule_reasons": ["neg:intern"]},
        {"rule_reasons": ["neg:sales"]},
        {"rule_reasons": ["level_mismatch"]},
    ]
    bd = ps.categorize_drop_reasons(drops)
    assert bd["by_category"]["suppressed_sector"] == 2
    assert bd["by_category"]["suppressed_company"] == 1
    assert bd["by_category"]["neg_title_match"] == 2
    assert bd["by_category"]["level_mismatch"] == 1
    assert bd["suppressed_total"] == 3
    assert bd["neg_terms"]["intern"] == 1


def test_filter_drops_by_category_picks_only_matching():
    drops = [
        {"company": "RBC", "rule_reasons": ["suppressed_sector_60d"]},
        {"company": "Wave", "rule_reasons": ["level_mismatch"]},
        {"company": "Acme", "rule_reasons": ["suppressed_company_15d"]},
    ]
    out = ps.filter_drops_by_category(drops, "suppressed_sector")
    assert len(out) == 1
    assert out[0]["company"] == "RBC"


def test_filter_drops_by_category_none_passes_all():
    drops = [{"rule_reasons": ["x"]}, {"rule_reasons": ["y"]}]
    assert len(ps.filter_drops_by_category(drops, None)) == 2


def test_filter_drops_handles_row_with_multiple_reasons():
    """A row can have several rule_reasons; matches if ANY map to category."""
    drops = [
        {"rule_reasons": ["level_mismatch", "suppressed_sector_60d"]},
    ]
    out = ps.filter_drops_by_category(drops, "suppressed_sector")
    assert len(out) == 1


# ---------------------------------------------------------------------------
# Phase 3D — tracker_migrate via mutate_json (the production path)
#
# load_tracker() in ui/app.py runs migrate_in_place under safe_json.mutate_json
# on first read. The Streamlit code itself can't be unit-tested directly, but
# the mutation path can — these tests guarantee that an un-migrated tracker
# becomes migrated when read through the production lock-protected path.
# ---------------------------------------------------------------------------

def test_migration_through_mutate_json(tmp_path):
    """An un-migrated tracker (no schema_version, rows missing `archived`)
    → after one mutate_json round-trip with migrate_in_place, every row
    has archived=False and meta.schema_version=3."""
    sys.path.insert(0, str(ROOT / "automation"))
    from safe_json import mutate_json
    from tracker_migrate import migrate_in_place, needs_migration, SCHEMA_VERSION

    tracker_path = tmp_path / "job_tracker_data.json"
    raw = {
        "meta": {"schema_version": 1},
        "jobs": [
            {"id": "a", "company": "X", "status": "Found"},
            {"id": "b", "company": "Y", "status": "Applied",
             "archived": True},  # already has the field — should be left
        ],
    }
    tracker_path.write_text(json.dumps(raw), encoding="utf-8")
    assert needs_migration(raw)

    migrated = mutate_json(tracker_path, migrate_in_place,
                             default={"jobs": [], "meta": {}})
    on_disk = json.loads(tracker_path.read_text(encoding="utf-8"))
    for state in (migrated, on_disk):
        assert state["meta"]["schema_version"] == SCHEMA_VERSION
        assert all("archived" in j for j in state["jobs"])
        # Existing archived=True must be preserved.
        b = next(j for j in state["jobs"] if j["id"] == "b")
        assert b["archived"] is True


def test_migration_idempotent(tmp_path):
    """Running migrate_in_place twice = same result (no double-bump,
    no duplicate changelog entries growing on every read)."""
    sys.path.insert(0, str(ROOT / "automation"))
    from safe_json import mutate_json
    from tracker_migrate import migrate_in_place

    tracker_path = tmp_path / "job_tracker_data.json"
    raw = {"meta": {"schema_version": 1}, "jobs": [{"id": "a", "status": "Found"}]}
    tracker_path.write_text(json.dumps(raw), encoding="utf-8")

    first = mutate_json(tracker_path, migrate_in_place,
                          default={"jobs": [], "meta": {}})
    changelog_after_first = list(first.get("meta", {}).get("changelog", []))
    second = mutate_json(tracker_path, migrate_in_place,
                           default={"jobs": [], "meta": {}})
    changelog_after_second = list(second.get("meta", {}).get("changelog", []))
    assert changelog_after_first == changelog_after_second


def test_migration_preserves_existing_jobs(tmp_path):
    """Migration must not lose fields, mutate IDs, or reorder jobs."""
    sys.path.insert(0, str(ROOT / "automation"))
    from safe_json import mutate_json
    from tracker_migrate import migrate_in_place

    tracker_path = tmp_path / "job_tracker_data.json"
    raw = {
        "meta": {"schema_version": 1, "weekly_target": {"applies": 5}},
        "jobs": [
            {"id": "a", "company": "X", "status": "Found",
             "fit_score_numeric": 8, "outreach_log": [{"date": "2026-05-01"}]},
            {"id": "b", "company": "Y", "status": "Applied",
             "date_applied": "2026-05-15"},
        ],
    }
    tracker_path.write_text(json.dumps(raw), encoding="utf-8")
    out = mutate_json(tracker_path, migrate_in_place,
                       default={"jobs": [], "meta": {}})
    assert [j["id"] for j in out["jobs"]] == ["a", "b"]
    assert out["jobs"][0]["fit_score_numeric"] == 8
    assert out["jobs"][0]["outreach_log"] == [{"date": "2026-05-01"}]
    assert out["meta"]["weekly_target"] == {"applies": 5}


# ---------------------------------------------------------------------------
# Phase 6 — parse_archive_reason whitespace + collision edge cases
# (Agent 3 coverage gap)
# ---------------------------------------------------------------------------

def test_parse_archive_reason_whitespace_only_name():
    """`muted_sector_   ` (whitespace after the prefix) → None.

    A name that's purely whitespace is not a usable canonical key. The
    caller (Phase 5 context-aware Restore) treats this as "no parseable
    suppression to lift", which is the right behaviour."""
    out = ps.parse_archive_reason("muted_sector_   ")
    assert out is None


def test_parse_archive_reason_empty_after_prefix():
    """`muted_sector_` with nothing after → None. Same reasoning."""
    assert ps.parse_archive_reason("muted_sector_") is None
    assert ps.parse_archive_reason("muted_company_") is None


def test_parse_archive_reason_prefix_collision_resilient():
    """A company name that starts with 'muted_sector_' (pathological but
    possible) must still parse as a COMPANY mute, not silently mis-parse
    as a sector. The implementation should match the longer/more-specific
    prefix first OR honour the actual prefix order."""
    # `muted_company_muted_sector_X` is unambiguous if the parser anchors
    # on the OUTER prefix (muted_company_) before stripping.
    out = ps.parse_archive_reason("muted_company_muted_sector_X")
    assert out is not None
    scope, name = out
    assert scope == "company"
    assert name == "muted_sector_X"


def test_parse_archive_reason_multi_underscore_sector_name():
    """Sector names with underscores (e.g. 'US_Banks') round-trip cleanly."""
    out = ps.parse_archive_reason("muted_sector_US_Banks")
    assert out == ("sector", "US_Banks")


def test_parse_archive_reason_unicode_name():
    """Sector / company names with non-ASCII (accents, etc.) preserved."""
    out = ps.parse_archive_reason("muted_company_Société Générale")
    assert out == ("company", "Société Générale")
