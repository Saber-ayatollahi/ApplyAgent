"""Smoke + unit coverage for the triage-drop audit tool's pure helpers.

The LLM judge itself needs the API and is exercised manually; these pin the
non-network plumbing (JSON extraction, dedup, and that _current_drops reflects
the LIVE rule triage) so the tool can't silently import-break or regress.
"""
from __future__ import annotations

import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import audit_triage_drops as A  # noqa: E402


def test_extract_json_plain_and_fenced():
    assert A._extract_json('[{"n": 1, "why": "x"}]') == [{"n": 1, "why": "x"}]
    assert A._extract_json('here you go:\n```json\n[{"n":2}]\n```') == [{"n": 2}]
    assert A._extract_json("no array here") == []
    assert A._extract_json("[broken") == []


def test_dedup_by_title_company():
    rows = [
        {"title": "Analyst, Risk", "company": "CPP"},
        {"title": "analyst, risk", "company": "cpp"},   # case-dup
        {"title": "Analyst, Risk", "company": "BMO"},    # diff company
    ]
    out = A._dedup(rows)
    assert len(out) == 2


def test_current_drops_reflects_live_triage():
    rows = [
        {"title": "Senior Manager, Model Validation", "source": "scrape"},  # passes
        {"title": "Software Developer", "source": "scrape"},                # drops
        {"title": "Customer Experience Associate", "source": "scrape"},     # drops
    ]
    dropped_titles = {r["title"] for r in A._current_drops(rows)}
    assert "Software Developer" in dropped_titles
    assert "Customer Experience Associate" in dropped_titles
    assert "Senior Manager, Model Validation" not in dropped_titles


def test_all_rows_merges_results_and_drops():
    scan = {"results": [{"title": "a"}], "triage_drops": [{"title": "b"}, {"title": "c"}]}
    assert len(A._all_rows(scan)) == 3


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
