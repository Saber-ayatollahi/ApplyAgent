"""worklist.rebuild() must drop excluded companies from BOTH the latest web
scan and the replayed 30-day Gmail envelopes — the can't-leak chokepoint.

Without this, ticking the exclude box would still let on-disk Big-6 rows
re-materialize into worklist.json for ~30 days. Imports are BARE (matching
worklist.rebuild()'s `import excludes`) so monkeypatching hits the same
module object the code under test uses.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

AUTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO))  # bare `import worklist` / `import excludes`

import worklist  # type: ignore  # noqa: E402
import excludes  # type: ignore  # noqa: E402


def _write_envelope(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps({
        "version": 1,
        "scan_date": datetime.now().date().isoformat(),
        "results": rows,
    }, indent=2), encoding="utf-8")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Redirect both worklist OUT_DIR and the exclude-list file into tmp."""
    monkeypatch.setattr(worklist, "OUT_DIR", tmp_path)
    monkeypatch.setattr(worklist, "WORKLIST", tmp_path / "worklist.json")
    monkeypatch.setattr(worklist, "WORKLIST_SCORED", tmp_path / "worklist_scored.json")
    monkeypatch.setattr(worklist, "LEGACY_DIR", tmp_path / "_legacy")

    example = tmp_path / "excludes.example.json"
    example.write_text(json.dumps({"version": 1, "companies": []}), encoding="utf-8")
    monkeypatch.setattr(excludes, "LIVE_PATH", tmp_path / "excludes.json")
    monkeypatch.setattr(excludes, "EXAMPLE_PATH", example)
    return tmp_path


def _rebuild_urls(tmp_path) -> set[str]:
    env = json.loads((tmp_path / "worklist.json").read_text(encoding="utf-8"))
    return {r.get("link") for r in env.get("results", [])}


def test_rebuild_drops_excluded_from_ondisk_gmail_envelope(isolated):
    tmp = isolated
    _write_envelope(tmp / "scan_gmail_20260520_120000.json", [
        {"title": "Director, IRRBB", "company": "RBC", "location": "Toronto, ON",
         "link": "https://www.linkedin.com/jobs/view/200000001"},
        {"title": "ALM Analyst", "company": "KOHO", "location": "Toronto, ON",
         "link": "https://www.linkedin.com/jobs/view/200000002"},
    ])
    excludes.add("RBC")
    stats = worklist.rebuild(quarantine=False)
    urls = _rebuild_urls(tmp)
    assert "https://www.linkedin.com/jobs/view/200000001" not in urls  # RBC gone
    assert "https://www.linkedin.com/jobs/view/200000002" in urls       # KOHO kept
    assert stats.get("excluded_dropped", 0) >= 1


def test_rebuild_drops_excluded_from_web_scan(isolated):
    """Web scan row tagged 'TD Asset Management' must drop when TD is excluded
    (canonical match flows through rebuild too)."""
    tmp = isolated
    _write_envelope(tmp / "scan_20260520_120000.json", [
        {"title": "Quant", "company": "TD Asset Management", "location": "Toronto, ON",
         "link": "https://example.com/td-am-1"},
        {"title": "Analyst", "company": "HOOPP", "location": "Toronto, ON",
         "link": "https://example.com/hoopp-1"},
    ])
    excludes.add("TD Bank")
    worklist.rebuild(quarantine=False)
    urls = _rebuild_urls(tmp)
    assert "https://example.com/td-am-1" not in urls
    assert "https://example.com/hoopp-1" in urls


def test_rebuild_no_exclude_keeps_all(isolated):
    tmp = isolated
    _write_envelope(tmp / "scan_gmail_20260520_120000.json", [
        {"title": "Director, IRRBB", "company": "RBC", "location": "Toronto, ON",
         "link": "https://www.linkedin.com/jobs/view/200000001"},
        {"title": "ALM Analyst", "company": "KOHO", "location": "Toronto, ON",
         "link": "https://www.linkedin.com/jobs/view/200000002"},
    ])
    stats = worklist.rebuild(quarantine=False)
    urls = _rebuild_urls(tmp)
    assert "https://www.linkedin.com/jobs/view/200000001" in urls
    assert "https://www.linkedin.com/jobs/view/200000002" in urls
    assert stats.get("excluded_dropped", 0) == 0
