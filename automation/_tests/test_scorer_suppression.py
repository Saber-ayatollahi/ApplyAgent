"""Tests for fit_scorer triage integration with the suppression registry.

Covers Phase 2 / Track 2A of the v3.1.1 plan: suppression check is applied
between negative-term and keyword/level scoring; --only-url overrides a
would-be suppression with `override_reason: manual_only_url` written to
`rule_reasons`; APPLYAGENT_SUPPRESSIONS_SNAPSHOT env var is consumed when set.

Tests target the triage layer in isolation — no live Anthropic/Bedrock calls.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))  # so `import automation.<m>` works
sys.path.insert(0, str(AUTO))          # so `import fit_scorer` works (script form)

from automation import suppressions as supp  # noqa: E402
from automation import fit_scorer  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — redirect suppressions paths into tmp_path so tests don't pollute
# the real data/ dir, and clear the module-level snapshot cache between cases.
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated(tmp_path, monkeypatch):
    live = tmp_path / "suppressions.json"
    example = tmp_path / "suppressions.example.json"
    events = tmp_path / "suppressions_events.jsonl"
    history = tmp_path / "suppressions_history.json"
    pending = tmp_path / "suppressions_pending_archives.jsonl"

    example.write_text(
        json.dumps({"version": 1, "sectors": [], "companies": []}, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(supp, "LIVE_PATH", live)
    monkeypatch.setattr(supp, "EXAMPLE_PATH", example)
    monkeypatch.setattr(supp, "EVENTS_PATH", events)
    monkeypatch.setattr(supp, "HISTORY_PATH", history)
    monkeypatch.setattr(supp, "PENDING_ARCHIVES_PATH", pending)

    # Reset the snapshot cache and ensure no env var leaks across tests.
    monkeypatch.setattr(fit_scorer, "_suppression_snapshot_cache", fit_scorer._UNSET)
    monkeypatch.delenv("APPLYAGENT_SUPPRESSIONS_SNAPSHOT", raising=False)

    return {"live": live, "example": example, "events": events,
            "history": history, "pending": pending, "tmp": tmp_path}


# ---------------------------------------------------------------------------
# 1. Suppressed sector drops AFTER neg-term, with the suppressed_sector_<N>d reason.
# ---------------------------------------------------------------------------
def test_triage_drops_suppressed_sector_after_negative_term(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "1 interview / 14 apps")
    snapshot = supp.load_active()

    row = {"title": "Director, ALM",
           "company": "RBC",
           "sector": "Canadian Big 6 Banks",
           "link": "https://example.com/r/1"}
    tri = fit_scorer.rule_triage(row["title"], row=row,
                                 suppression_snapshot=snapshot)

    assert tri["stage1_pass"] is False
    reasons = tri.get("rule_reasons", [])
    assert any(r.startswith("suppressed_sector_") and r.endswith("d")
               for r in reasons), f"expected suppressed_sector_<N>d, got {reasons!r}"


# ---------------------------------------------------------------------------
# 2. Negative-term wins over suppression — ordering invariant.
# ---------------------------------------------------------------------------
def test_triage_drops_negative_term_before_suppression(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "test")
    snapshot = supp.load_active()

    row = {"title": "ALM Intern Program",  # "intern" is in NEG_TITLE_TERMS
           "company": "RBC",
           "sector": "Canadian Big 6 Banks",
           "link": "https://example.com/r/2"}
    tri = fit_scorer.rule_triage(row["title"], row=row,
                                 suppression_snapshot=snapshot)

    assert tri["stage1_pass"] is False
    reasons = tri.get("rule_reasons", [])
    assert reasons, "expected at least one rule_reason"
    assert reasons[0].startswith("neg:"), \
        f"expected neg:* first, got {reasons!r}"
    assert not any(r.startswith("suppressed_") for r in reasons), \
        f"suppression reason must not be emitted when neg-term hits, got {reasons!r}"


# ---------------------------------------------------------------------------
# 3. --only-url override: row passes triage, override marker in rule_reasons.
# ---------------------------------------------------------------------------
def test_triage_passes_suppressed_row_under_only_url_override(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "test")
    snapshot = supp.load_active()

    row = {"title": "Director, ALM",
           "company": "RBC",
           "sector": "Canadian Big 6 Banks",
           "link": "https://example.com/r/3"}
    tri = fit_scorer.rule_triage(row["title"], row=row,
                                 suppression_snapshot=snapshot,
                                 only_url_override=True)

    assert tri["stage1_pass"] is True, \
        f"override should let the row pass, got {tri!r}"
    reasons = tri.get("rule_reasons", [])
    assert "override_reason:manual_only_url" in reasons, \
        f"override marker missing, got {reasons!r}"
    # The original drop reason is preserved as audit trail.
    assert any(r.startswith("would_have_dropped:suppressed_") for r in reasons), \
        f"original suppression reason should be recorded, got {reasons!r}"


# ---------------------------------------------------------------------------
# 4. Unsectored row passes through a sector mute.
# ---------------------------------------------------------------------------
def test_triage_unsectored_row_passes_sector_mute(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "test")
    snapshot = supp.load_active()

    row = {"title": "Director, ALM",
           "company": "Some Random Co",
           "sector": "",  # unsectored
           "link": "https://example.com/r/4"}
    tri = fit_scorer.rule_triage(row["title"], row=row,
                                 suppression_snapshot=snapshot)

    assert tri["stage1_pass"] is True
    reasons = tri.get("rule_reasons", [])
    assert not any(r.startswith("suppressed_") for r in reasons), \
        f"unsectored row must not be suppressed, got {reasons!r}"


# ---------------------------------------------------------------------------
# 5. Empty suppression list is a no-op (dormancy invariant).
# ---------------------------------------------------------------------------
def test_triage_with_empty_suppression_list_is_noop(isolated):
    snapshot = supp.load_active()  # empty by default
    assert snapshot.get("sectors") == []
    assert snapshot.get("companies") == []

    rows = [
        {"title": "Director, ALM", "company": "RBC",
         "sector": "Canadian Big 6 Banks", "link": "https://example.com/a"},
        {"title": "VP, Treasury Risk", "company": "TD",
         "sector": "Canadian Big 6 Banks", "link": "https://example.com/b"},
        {"title": "Senior Manager, Liquidity Risk", "company": "Acme",
         "sector": "", "link": "https://example.com/c"},
    ]
    for r in rows:
        tri = fit_scorer.rule_triage(r["title"], row=r,
                                     suppression_snapshot=snapshot)
        reasons = tri.get("rule_reasons", [])
        assert not any(rr.startswith("suppressed_") for rr in reasons), \
            f"empty snapshot must not emit suppression reasons; got {reasons!r}"
        # And the legacy stage1 keyword path must still pass these strong-hit rows.
        assert tri["stage1_pass"] is True, f"strong-hit row should pass, got {tri!r}"


# ---------------------------------------------------------------------------
# 6. APPLYAGENT_SUPPRESSIONS_SNAPSHOT env var is consumed when set.
# ---------------------------------------------------------------------------
def test_snapshot_env_var_consumed_when_set(isolated, monkeypatch):
    # Build a snapshot containing one sector mute and write to disk.
    until = date.today() + timedelta(days=45)
    snapshot = {
        "version": 1,
        "sectors": [{
            "scope": "sector",
            "name": "Canadian Big 6 Banks",
            "canonical_key": "canadian big 6 banks",
            "until": until.isoformat(),
            "reason": "snapshot test",
            "added_at": "2026-01-01T00:00:00",
            "version": 1,
        }],
        "companies": [],
    }
    snap_path = isolated["tmp"] / "snapshot.json"
    snap_path.write_text(json.dumps(snapshot), encoding="utf-8")

    monkeypatch.setenv("APPLYAGENT_SUPPRESSIONS_SNAPSHOT", str(snap_path))
    # Force a re-read by clearing the cache.
    monkeypatch.setattr(fit_scorer, "_suppression_snapshot_cache", fit_scorer._UNSET)

    loaded = fit_scorer._load_suppression_snapshot()
    assert loaded is not None
    assert loaded.get("sectors")

    row = {"title": "Director, ALM",
           "company": "RBC",
           "sector": "Canadian Big 6 Banks",
           "link": "https://example.com/r/6"}
    # Pass snapshot=None so the helper resolves from the env-var-loaded cache.
    tri = fit_scorer.rule_triage(row["title"], row=row,
                                 suppression_snapshot=None)

    assert tri["stage1_pass"] is False
    reasons = tri.get("rule_reasons", [])
    assert any(r.startswith("suppressed_sector_") for r in reasons), \
        f"snapshot env var should have driven suppression, got {reasons!r}"


# ---------------------------------------------------------------------------
# 7. Missing snapshot file degrades gracefully — no crash, no extra drops.
# ---------------------------------------------------------------------------
def test_snapshot_env_var_missing_file_does_not_crash(isolated, monkeypatch):
    bogus = isolated["tmp"] / "does_not_exist.json"
    assert not bogus.exists()
    monkeypatch.setenv("APPLYAGENT_SUPPRESSIONS_SNAPSHOT", str(bogus))
    monkeypatch.setattr(fit_scorer, "_suppression_snapshot_cache", fit_scorer._UNSET)

    # Helper returns None gracefully.
    loaded = fit_scorer._load_suppression_snapshot()
    assert loaded is None

    # Triage of a strong-hit row succeeds; no suppression reasons leak in.
    row = {"title": "Director, ALM",
           "company": "RBC",
           "sector": "Canadian Big 6 Banks",
           "link": "https://example.com/r/7"}
    tri = fit_scorer.rule_triage(row["title"], row=row,
                                 suppression_snapshot=None)

    assert tri["stage1_pass"] is True
    reasons = tri.get("rule_reasons", [])
    assert not any(r.startswith("suppressed_") for r in reasons), \
        f"missing snapshot must not emit suppression reasons, got {reasons!r}"
