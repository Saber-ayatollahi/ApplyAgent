"""Regression tests for reset_ops.plan_clear_scans worklist handling.

The "clear scans" path must ALSO remove the derived worklist pool
(worklist.json + triage + prev-score), otherwise the Refresh funnel keeps
showing a stale row count after a clear. These tests pin that contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "automation"))

import reset_ops  # noqa: E402


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    """Point reset_ops at a throwaway outputs/ dir."""
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(reset_ops, "OUT_DIR", out)
    return out


def _touch(p: Path, text: str = "{}") -> None:
    p.write_text(text, encoding="utf-8")


def test_clear_scans_includes_worklist_pool(out_dir):
    # Raw inputs
    _touch(out_dir / "scan_20260601.json")
    _touch(out_dir / "scan_gmail_20260601_120000.json")
    _touch(out_dir / "scan_20260601_scored.json")
    # Derived pool
    _touch(out_dir / "worklist.json")
    _touch(out_dir / "worklist_triage.json")
    _touch(out_dir / "worklist_scored.json")
    _touch(out_dir / "worklist_scored.prev.json")

    plan = reset_ops.plan_clear_scans()
    names = {p.name for p in plan.files_to_delete}

    # Raw scans (web + gmail) and scored snapshots
    assert "scan_20260601.json" in names
    assert "scan_gmail_20260601_120000.json" in names
    assert "scan_20260601_scored.json" in names
    # Derived worklist pool — the regression target
    assert "worklist.json" in names
    assert "worklist_triage.json" in names
    assert "worklist_scored.json" in names       # caught by *_scored glob
    assert "worklist_scored.prev.json" in names  # caught by explicit extra


def test_clear_scans_no_duplicate_entries(out_dir):
    # worklist_scored.json matches BOTH the *_scored glob and would be a
    # candidate for the extra list — must appear exactly once.
    _touch(out_dir / "worklist_scored.json")
    _touch(out_dir / "worklist.json")
    plan = reset_ops.plan_clear_scans()
    paths = plan.files_to_delete
    assert len(paths) == len(set(paths)), "duplicate file entries in plan"


def test_clear_scans_preserves_checkpoint_and_tracker(out_dir):
    _touch(out_dir / "scan_checkpoint.json")
    _touch(out_dir / "worklist.json")
    plan = reset_ops.plan_clear_scans()
    names = {p.name for p in plan.files_to_delete}
    # The in-progress checkpoint must survive so a paused scrape can resume.
    assert "scan_checkpoint.json" not in names


def test_clear_scans_empty_dir_is_noop(out_dir):
    plan = reset_ops.plan_clear_scans()
    assert plan.files_to_delete == []


def test_execute_actually_removes_worklist(out_dir):
    _touch(out_dir / "scan_20260601.json")
    _touch(out_dir / "worklist.json")
    _touch(out_dir / "worklist_triage.json")
    plan = reset_ops.plan_clear_scans()
    result = reset_ops.execute(plan)
    assert result.errors == []
    assert not (out_dir / "worklist.json").exists()
    assert not (out_dir / "worklist_triage.json").exists()
    assert not (out_dir / "scan_20260601.json").exists()
