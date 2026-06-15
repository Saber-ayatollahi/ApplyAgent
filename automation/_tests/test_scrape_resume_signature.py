"""Resume must tolerate an ADDITIVE target-list change.

Regression (2026-06-15): a coverage expansion added ~35 companies, which changed
jd_scraper._targets_signature. scan(resume=True) then hard-refused with
{"error": "checkpoint_signature_mismatch"} and exited immediately — so the UI's
"Resume scrape" button bounced the user straight back to "paused (checkpoint)".

Because resumption skips by company NAME (not list position), an additive (or any)
target-list edit is safe to resume: added companies get scraped, removed ones are
never iterated. scan() now logs a drift NOTE and resumes instead of refusing.

Network is monkeypatched out; the tested paths resume over already-completed
companies, so the loop skips every one and makes zero HTTP calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jd_scraper as J  # type: ignore


def _co(name: str, sector: str = "Canadian Big 6 Banks") -> dict:
    return {"name": name, "sector": sector,
            "linkedin_slug": name.lower(), "workday": None}


def _seed(tmp_path: Path, completed: list[str], found: list[dict], sig: str) -> Path:
    ckpt = tmp_path / "scan_checkpoint.json"
    ckpt.write_text(json.dumps({
        "targets_signature": sig,
        "completed": completed,
        "found": found,
        "per_company": [{"name": n, "total": 1} for n in completed],
        "total_companies": len(completed),
        "completed_count": len(completed),
    }), encoding="utf-8")
    return ckpt


def _patch(monkeypatch, ckpt: Path) -> None:
    monkeypatch.setattr(J, "CHECKPOINT_PATH", ckpt)
    monkeypatch.setattr(J, "PAUSE_FLAG_PATH", ckpt.parent / "scan_pause.flag")
    monkeypatch.setattr(J, "_preflight_connectivity_check", lambda **k: None)
    monkeypatch.setattr(J, "load_tracker_urls", lambda: set())


FOUND = [{"company": "A", "link": "http://x/1"},
         {"company": "B", "link": "http://x/2"}]


def test_resume_tolerates_signature_drift(tmp_path, monkeypatch):
    """The exact bug: checkpoint sig != current sig (list grew) must NOT error."""
    ckpt = _seed(tmp_path, ["A", "B"], FOUND, sig="stale_old_sig")
    _patch(monkeypatch, ckpt)

    # The real list grew (A, B, + a new company) → signature differs.
    assert J._targets_signature([_co("A"), _co("B"), _co("C_New")]) != "stale_old_sig"

    # Resume over the already-completed set (loop skips both → no HTTP).
    found, diag = J.scan([_co("A"), _co("B")], resume=True)

    assert "error" not in diag, f"resume must not hard-refuse; got {diag.get('error')}"
    assert {f["link"] for f in found} == {"http://x/1", "http://x/2"}, \
        "checkpoint-captured results must be preserved across resume"
    assert diag["completed_count"] == 2
    assert diag["paused"] is False


def test_resume_matching_signature_still_works(tmp_path, monkeypatch):
    """No regression when the list is unchanged (signatures match)."""
    companies = [_co("A"), _co("B")]
    sig = J._targets_signature(companies)
    ckpt = _seed(tmp_path, ["A", "B"], FOUND, sig=sig)
    _patch(monkeypatch, ckpt)

    found, diag = J.scan(companies, resume=True)
    assert "error" not in diag
    assert len(found) == 2
    assert diag["completed_count"] == 2


def test_resume_clears_pause_flag(tmp_path, monkeypatch):
    """--resume is a positive intent to continue → any stale pause flag is cleared."""
    ckpt = _seed(tmp_path, ["A", "B"], FOUND, sig="whatever")
    _patch(monkeypatch, ckpt)
    pause = ckpt.parent / "scan_pause.flag"
    pause.write_text("2026-06-15T12:00:00", encoding="utf-8")

    J.scan([_co("A"), _co("B")], resume=True)
    assert not pause.exists(), "stale pause flag must be cleared on resume"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
