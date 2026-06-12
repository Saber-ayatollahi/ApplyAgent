"""resume_agent._write_back — links the deliverable into the tracker and
drops the ATS report file the UI displays.

Before this, resume_file/cover_letter_file were 0/124 in the tracker: the app
could only find documents by folder-name slug matching, and the ATS keyword
score (computed on every run) was never surfaced anywhere.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import pytest  # noqa: E402
import resume_agent as RA  # noqa: E402
import jd_tailor  # noqa: E402


@pytest.fixture()
def bundle(tmp_path, monkeypatch):
    """A fake deliverable folder + tracker, with TRACKER monkeypatched."""
    folder = tmp_path / "2026-06-11_Acme_Risk-Manager"
    folder.mkdir()
    (folder / "Saber_Ayatollahi_Acme_Risk-Manager.docx").write_text("x")
    (folder / "acme_risk_manager_cover.docx").write_text("x")
    tracker = tmp_path / "tracker.json"
    tracker.write_text(json.dumps({
        "jobs": [{"id": "auto-acme-risk-manager", "company": "Acme",
                  "title": "Risk Manager", "resume_file": None,
                  "cover_letter_file": None}],
        "meta": {},
    }), encoding="utf-8")
    monkeypatch.setattr(jd_tailor, "TRACKER", tracker)
    # ROOT-relative path computation needs the folder under ROOT — fake it by
    # monkeypatching ROOT to tmp_path so relative_to() succeeds.
    monkeypatch.setattr(RA, "ROOT", tmp_path)
    rc = {"summary": "Python risk analytics specialist.",
          "target": {"jd_keywords": ["python", "zzz-not-present"]}}
    return folder, tracker, rc


def test_write_back_links_tracker_and_writes_ats(bundle):
    folder, tracker, rc = bundle
    RA._write_back("auto-acme-risk-manager", folder, "acme_risk_manager", rc)

    # ATS report file for the UI
    ats = json.loads((folder / "acme_risk_manager_ats_report.json")
                     .read_text(encoding="utf-8"))
    assert ats["total"] == 2 and ats["matched"] == 1
    assert ats["missing"] == ["zzz-not-present"]

    # tracker row linked
    job = json.loads(tracker.read_text(encoding="utf-8"))["jobs"][0]
    assert job["resume_file"].endswith("Saber_Ayatollahi_Acme_Risk-Manager.docx")
    assert "\\" not in job["resume_file"]          # repo-relative, forward slashes
    assert job["cover_letter_file"].endswith("acme_risk_manager_cover.docx")
    assert job["tailored_at"]
    assert job["ats_matched"] == 1 and job["ats_total"] == 2


def test_write_back_without_job_id_only_writes_ats(bundle):
    folder, tracker, rc = bundle
    RA._write_back(None, folder, "acme_risk_manager", rc)
    assert (folder / "acme_risk_manager_ats_report.json").exists()
    job = json.loads(tracker.read_text(encoding="utf-8"))["jobs"][0]
    assert job["resume_file"] is None              # tracker untouched


def test_write_back_never_raises_on_bad_tracker(bundle, monkeypatch):
    folder, _tracker, rc = bundle
    monkeypatch.setattr(jd_tailor, "TRACKER", Path("Z:/nonexistent/t.json"))
    # must not raise — generation success can't depend on the write-back
    RA._write_back("auto-acme-risk-manager", folder, "acme_risk_manager", rc)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
