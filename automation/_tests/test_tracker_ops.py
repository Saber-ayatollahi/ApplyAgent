"""Unit tests for tracker_ops + tracker_migrate. Pure dicts; no disk I/O."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO))

import tracker_migrate  # noqa: E402
import tracker_ops  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _job(job_id: str, **overrides) -> dict:
    base = {
        "id": job_id,
        "company": "Acme",
        "title": "Risk Analyst",
        "url": f"https://x.co/{job_id}",
        "status": "Found",
        "archived": False,
        "fit_score_numeric": 8,
        "date_found": "2026-05-01",
        "date_applied": None,
        "notes": "auto-promoted",
    }
    base.update(overrides)
    return base


def _tracker(jobs: list[dict] | None = None, with_meta: bool = True) -> dict:
    t: dict = {"jobs": jobs if jobs is not None else [_job("a-1"), _job("a-2")]}
    if with_meta:
        t["meta"] = {
            "version": "2.0",
            "schema_version": 3,
            "status_enum": [
                "Found", "Watch", "Applied", "Recruiter_Screen", "Phone_Screen",
                "Take_Home", "Onsite", "Offer", "Rejected", "Hired",
                "Withdrawn", "Expired",
            ],
            "changelog": [],
        }
    return t


# ---------------------------------------------------------------------------
# is_active matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "job, expected",
    [
        ({"archived": False, "status": "Found"}, True),
        ({"archived": False, "status": "Rejected"}, False),
        ({"archived": True, "status": "Found"}, False),
        ({"archived": True, "status": "Applied"}, False),
        ({"status": "Found"}, True),                # missing archived defaults False
        ({"status": "Hired"}, False),                # terminal status, missing archived
        ({"archived": False, "status": "Withdrawn"}, False),
        ({"archived": False, "status": "Offer"}, False),
        ({"archived": False, "status": "Expired"}, False),
        ({"archived": False, "status": "Applied"}, True),
    ],
)
def test_is_active_matrix(job, expected):
    assert tracker_ops.is_active(job) is expected


# ---------------------------------------------------------------------------
# archive / restore / set_status / set_archive_reason
# ---------------------------------------------------------------------------

def test_archive_sets_fields_and_returns_same_dict():
    t = _tracker()
    out = tracker_ops.archive(t, "a-1", reason="manual")
    assert out is t
    j = tracker_ops.find_job(t, "a-1")
    assert j["archived"] is True
    assert j["archive_reason"] == "manual"
    assert isinstance(j["archived_at"], str) and j["archived_at"].endswith("Z")


def test_archive_unknown_id_raises_keyerror():
    t = _tracker()
    with pytest.raises(KeyError):
        tracker_ops.archive(t, "does-not-exist")


def test_archive_preserves_existing_fields():
    t = _tracker(jobs=[_job(
        "a-1",
        fit_score_numeric=9,
        date_applied="2026-05-10",
        notes="warm intro pending",
        status="Applied",
    )])
    tracker_ops.archive(t, "a-1", reason="lost interest")
    j = tracker_ops.find_job(t, "a-1")
    assert j["fit_score_numeric"] == 9
    assert j["date_applied"] == "2026-05-10"
    assert j["notes"] == "warm intro pending"
    assert j["status"] == "Applied"
    assert j["company"] == "Acme"
    assert j["url"] == "https://x.co/a-1"


def test_restore_clears_archive_fields():
    t = _tracker()
    tracker_ops.archive(t, "a-1", reason="manual")
    tracker_ops.restore(t, "a-1")
    j = tracker_ops.find_job(t, "a-1")
    assert j["archived"] is False
    assert "archived_at" not in j
    assert "archive_reason" not in j


def test_restore_idempotent_on_non_archived():
    t = _tracker()
    tracker_ops.restore(t, "a-1")
    j = tracker_ops.find_job(t, "a-1")
    assert j["archived"] is False
    # second call still fine
    tracker_ops.restore(t, "a-1")
    assert j["archived"] is False


def test_set_status_validates_against_status_enum():
    t = _tracker()
    with pytest.raises(ValueError):
        tracker_ops.set_status(t, "a-1", "Bogus")
    # valid status flows through
    tracker_ops.set_status(t, "a-1", "Applied")
    assert tracker_ops.find_job(t, "a-1")["status"] == "Applied"


def test_set_status_accepts_any_string_when_meta_missing():
    t = _tracker(with_meta=False)
    tracker_ops.set_status(t, "a-1", "WhateverCustomStatus")
    assert tracker_ops.find_job(t, "a-1")["status"] == "WhateverCustomStatus"


def test_set_archive_reason_requires_archived_first():
    t = _tracker()
    with pytest.raises(ValueError):
        tracker_ops.set_archive_reason(t, "a-1", "wrong sector")
    tracker_ops.archive(t, "a-1")
    tracker_ops.set_archive_reason(t, "a-1", "wrong sector")
    assert tracker_ops.find_job(t, "a-1")["archive_reason"] == "wrong sector"


# ---------------------------------------------------------------------------
# apply_followup_gate
# ---------------------------------------------------------------------------

def test_apply_followup_gate():
    # active Found → not suppressed
    assert tracker_ops.apply_followup_gate({"status": "Found", "archived": False}) is False
    # terminal statuses suppress
    for s in tracker_ops.TERMINAL_STATUSES:
        assert tracker_ops.apply_followup_gate({"status": s, "archived": False}) is True
    # archived suppresses regardless of status
    assert tracker_ops.apply_followup_gate({"status": "Applied", "archived": True}) is True
    assert tracker_ops.apply_followup_gate({"status": "Found", "archived": True}) is True


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def test_migration_idempotent():
    t = {
        "meta": {"schema_version": 0, "changelog": []},
        "jobs": [{"id": "x", "status": "Found"}],
    }
    tracker_migrate.migrate_in_place(t)
    snapshot = {
        "schema_version": t["meta"]["schema_version"],
        "changelog_len": len(t["meta"]["changelog"]),
        "archived": t["jobs"][0]["archived"],
    }
    tracker_migrate.migrate_in_place(t)
    assert t["meta"]["schema_version"] == snapshot["schema_version"]
    assert len(t["meta"]["changelog"]) == snapshot["changelog_len"]
    assert t["jobs"][0]["archived"] == snapshot["archived"]


def test_migration_stamps_archived_false_on_legacy_rows():
    t = {
        "meta": {"schema_version": 2, "changelog": []},
        "jobs": [
            {"id": "x", "status": "Found"},
            {"id": "y", "status": "Applied"},
        ],
    }
    tracker_migrate.migrate_in_place(t)
    assert all(j["archived"] is False for j in t["jobs"])
    # no archive_reason / archived_at added on legacy rows
    for j in t["jobs"]:
        assert "archived_at" not in j
        assert "archive_reason" not in j


def test_migration_preserves_existing_archived_true_rows():
    t = {
        "meta": {"schema_version": 2, "changelog": []},
        "jobs": [
            {"id": "x", "status": "Applied", "archived": True,
             "archived_at": "2026-05-01T00:00:00Z", "archive_reason": "muted sector"},
            {"id": "y", "status": "Found"},
        ],
    }
    tracker_migrate.migrate_in_place(t)
    x = next(j for j in t["jobs"] if j["id"] == "x")
    y = next(j for j in t["jobs"] if j["id"] == "y")
    assert x["archived"] is True
    assert x["archived_at"] == "2026-05-01T00:00:00Z"
    assert x["archive_reason"] == "muted sector"
    assert y["archived"] is False


def test_migration_handles_missing_meta():
    t = {"jobs": [{"id": "x", "status": "Found"}]}
    tracker_migrate.migrate_in_place(t)
    assert t["meta"]["schema_version"] == tracker_migrate.SCHEMA_VERSION
    assert t["jobs"][0]["archived"] is False
    assert isinstance(t["meta"]["changelog"], list)
    assert len(t["meta"]["changelog"]) == 1


def test_migration_appends_changelog_entry():
    t = {
        "meta": {"schema_version": 2, "changelog": [{"date": "2026-05-18", "event": "init", "roles": 0}]},
        "jobs": [{"id": "x", "status": "Found"}],
    }
    before = len(t["meta"]["changelog"])
    tracker_migrate.migrate_in_place(t)
    assert len(t["meta"]["changelog"]) == before + 1
    entry = t["meta"]["changelog"][-1]
    assert "schema_migration" in entry["event"]
    assert "v2" in entry["event"]
    assert "v3" in entry["event"]
    assert entry["roles"] == 1
    assert isinstance(entry["date"], str)


def test_needs_migration_flag():
    assert tracker_migrate.needs_migration({"meta": {"schema_version": 2}}) is True
    assert tracker_migrate.needs_migration({"meta": {"schema_version": 3}}) is False
    assert tracker_migrate.needs_migration({}) is True
    assert tracker_migrate.needs_migration({"meta": {}}) is True
