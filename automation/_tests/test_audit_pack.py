"""Test audit_pack.build_audit_pack() against synthetic envelopes.

Verifies:
  - Multi-sheet xlsx round-trips through openpyxl with all expected sheets.
  - Each sheet's row count matches the input envelope.
  - Empty drop-logs (legacy scans pre-instrumentation) still produce sheets.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO))


def _make_synth_outputs(out_dir: Path, stamp: str) -> None:
    """Write minimal scan/worklist/scored/promote envelopes the audit_pack
    builder reads from. Each envelope has 2-3 rows so we can verify sheet
    row counts deterministically."""
    out_dir.mkdir(parents=True, exist_ok=True)

    scan = {
        "scan_date": stamp,
        "companies_scanned": 2,
        "total_new_candidates": 2,
        "dedup_stats": {"input": 3, "output": 2, "dropped_url": 1, "dropped_near": 0},
        "by_sector": {"Banks": 2},
        "diagnostics": {},
        "filter_drops": {
            "title": [
                {"company": "Acme", "sector": "Banks",
                 "title": "Marketing Intern", "link": "https://x.co/1",
                 "location": "Toronto", "source": "workday:acme",
                 "matched_terms": "intern,marketing"},
            ],
            "geo": [
                {"company": "Acme", "sector": "Banks",
                 "title": "Risk Analyst", "link": "https://x.co/2",
                 "location": "Boston, MA", "source": "greenhouse:acme"},
                {"company": "Acme", "sector": "Banks",
                 "title": "Quant Analyst", "link": "https://x.co/3",
                 "location": "NYC", "source": "linkedin"},
            ],
        },
        "results": [
            {"title": "Risk Manager", "link": "https://x.co/10",
             "location": "Toronto, ON", "source": "workday:acme",
             "company": "Acme", "sector": "Banks"},
            {"title": "ALM Analyst", "link": "https://x.co/11",
             "location": "Toronto, ON", "source": "linkedin",
             "company": "Beta", "sector": "Banks"},
        ],
    }
    (out_dir / f"scan_{stamp}.json").write_text(
        json.dumps(scan), encoding="utf-8")

    worklist = {
        "version": 1,
        "scan_date": stamp,
        "stats": {"total": 2},
        "merged_pairs": [
            {"kept_url": "https://x.co/10", "kept_source": "scrape",
             "dropped_url": "https://x.co/10b", "dropped_source": "gmail",
             "company": "Acme", "title": "Risk Manager",
             "reason": "near_dup_company_title"},
        ],
        "results": [
            {"title": "Risk Manager", "link": "https://x.co/10",
             "company": "Acme", "sector": "Banks", "source": "scrape",
             "first_seen": stamp, "in_pool_since": stamp,
             "is_new_since_last_score": True},
            {"title": "ALM Analyst", "link": "https://x.co/11",
             "company": "Beta", "sector": "Banks", "source": "scrape",
             "first_seen": stamp, "in_pool_since": stamp,
             "is_new_since_last_score": True},
        ],
    }
    (out_dir / "worklist.json").write_text(
        json.dumps(worklist), encoding="utf-8")

    scored = {
        "scan_date": stamp,
        "stage1_passed": 2,
        "stage1_dropped": 1,
        "results": [
            {"title": "Risk Manager", "company": "Acme", "location": "Toronto",
             "source": "scrape", "link": "https://x.co/10",
             "fit": {"fit_verdict": "tailor_and_apply", "fit_score": 78,
                     "fit_notes": "good ALM match"}},
            {"title": "ALM Analyst", "company": "Beta", "location": "Toronto",
             "source": "scrape", "link": "https://x.co/11",
             "fit": {"fit_verdict": "watch", "fit_score": 55, "fit_notes": ""}},
        ],
        "triage_drops": [
            {"company": "Gamma", "title": "Sales Rep",
             "link": "https://x.co/20", "source": "linkedin",
             "rule_reasons": ["no_strong_keywords"], "score": 1,
             "hits_breakdown": {"strong": [], "medium": [], "weak": [],
                                "level": []}},
        ],
        "only_filtered": [],
    }
    (out_dir / "worklist_scored.json").write_text(
        json.dumps(scored), encoding="utf-8")

    promote = {
        "scan_date": stamp,
        "summary": {"added": 1, "skipped_geo": 1, "skipped_score": 0,
                    "skipped_verdict": 0, "skipped_dupe": 0},
        "skipped_rows": [
            {"reason": "geo", "company": "Acme", "title": "Risk Manager",
             "url": "https://x.co/99", "location": "NYC",
             "score": 70, "verdict": "tailor_and_apply", "note": "NYC"},
        ],
        "new_entries": [
            {"id": "auto-acme-risk-78", "tier": 1, "score": 78,
             "sector": "Banks", "company": "Acme", "title": "Risk Manager",
             "url": "https://x.co/10"},
        ],
    }
    (out_dir / f"promote_report_{stamp}.json").write_text(
        json.dumps(promote), encoding="utf-8")
    (out_dir / f"promote_report_{stamp}.md").write_text(
        "# stub", encoding="utf-8")


def test_audit_pack_round_trip():
    """Build a pack from synthetic envelopes, parse it back, check sheets."""
    import audit_pack  # type: ignore
    from openpyxl import load_workbook

    with tempfile.TemporaryDirectory() as tmp:
        synth_out = Path(tmp) / "outputs"
        _make_synth_outputs(synth_out, "29991231")

        # Point audit_pack at our temp dir.
        original_out = audit_pack.OUT_DIR
        audit_pack.OUT_DIR = synth_out
        try:
            data = audit_pack.build_audit_pack("29991231")
            assert isinstance(data, bytes) and len(data) > 1000, "tiny pack"

            wb = load_workbook(io.BytesIO(data), read_only=True)
            sheets = wb.sheetnames
            expected = {
                "Summary", "Scrape raw", "Scrape title drops",
                "Scrape geo drops", "Gmail raw", "Worklist pool",
                "Worklist merges", "Stage-1 drops", "Scored",
                "Promote skips", "Promoted",
            }
            missing = expected - set(sheets)
            assert not missing, f"missing sheets: {missing}"

            def rows(name: str) -> int:
                ws = wb[name]
                return ws.max_row - 1  # exclude header

            assert rows("Scrape raw") == 2, rows("Scrape raw")
            assert rows("Scrape title drops") == 1, rows("Scrape title drops")
            assert rows("Scrape geo drops") == 2, rows("Scrape geo drops")
            assert rows("Worklist pool") == 2, rows("Worklist pool")
            assert rows("Worklist merges") == 1, rows("Worklist merges")
            assert rows("Stage-1 drops") == 1, rows("Stage-1 drops")
            assert rows("Scored") == 2, rows("Scored")
            assert rows("Promote skips") == 1, rows("Promote skips")
            assert rows("Promoted") == 1, rows("Promoted")
            print(f"[PASS] audit_pack: all {len(expected)} sheets present, "
                  f"row counts match")
        finally:
            audit_pack.OUT_DIR = original_out


def test_audit_pack_empty_legacy_scan():
    """A scan envelope without `filter_drops` (legacy, pre-instrumentation)
    should still build a pack with empty title/geo drop sheets."""
    import audit_pack  # type: ignore
    from openpyxl import load_workbook

    with tempfile.TemporaryDirectory() as tmp:
        synth_out = Path(tmp) / "outputs"
        synth_out.mkdir(parents=True, exist_ok=True)
        legacy = {
            "scan_date": "29991230",
            "companies_scanned": 1,
            "results": [
                {"title": "T", "link": "https://x.co/1", "company": "A",
                 "sector": "B", "source": "scrape", "location": "Toronto"},
            ],
        }
        (synth_out / "scan_29991230.json").write_text(
            json.dumps(legacy), encoding="utf-8")
        original_out = audit_pack.OUT_DIR
        audit_pack.OUT_DIR = synth_out
        try:
            data = audit_pack.build_audit_pack("29991230")
            wb = load_workbook(io.BytesIO(data), read_only=True)
            assert "Scrape title drops" in wb.sheetnames
            assert "Scrape geo drops" in wb.sheetnames
            assert wb["Scrape raw"].max_row - 1 == 1
            assert wb["Scrape title drops"].max_row - 1 == 0
            print("[PASS] audit_pack: legacy scan envelope handled")
        finally:
            audit_pack.OUT_DIR = original_out


if __name__ == "__main__":
    test_audit_pack_round_trip()
    test_audit_pack_empty_legacy_scan()
    print("\nAll audit_pack tests passed.")
