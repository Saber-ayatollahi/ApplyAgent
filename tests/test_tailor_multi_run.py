"""Multi-run tailor drawer: several resume generations at once, one banner each.

Pins the _tailor_runs registry behaviour:
  - N registered jobs render N independent cards (✅ ready banners with
    downloads for finished ones, ⏳ running card for in-flight ones).
  - While a job is generating, its action-row button is a DISABLED
    "⏳ Generating…" chip — clicking ✨ Tailor twice used to spawn a twin
    process (double API spend + racy writes into the same folder).
  - The legacy single-slot key (_active_tailor_job_id) migrates into the
    registry instead of being lost.

Uses real tracker jobs whose applications/ folders exist on disk, plus a
fabricated 'running' scan_runner record pointing at THIS test process's pid
(alive ⇒ refresh_state keeps state='running'). No subprocesses, no API.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.py"
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

import pytest  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402
import scan_runner  # noqa: E402


def _slug(s: str) -> str:
    s = (s or "").replace("'", "").replace("’", "")
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


def _jobs_with_folders(n: int) -> list[str]:
    """Tracker job ids whose applications/<date>_<co>_<role>/ folder exists."""
    tracker = json.loads((ROOT / "data" / "job_tracker_data.json")
                         .read_text(encoding="utf-8"))
    folders = [d.name.lower() for d in (ROOT / "applications").glob("*/")]
    out = []
    for j in tracker.get("jobs", []):
        tgt = f"{_slug(j.get('company'))}_{_slug(j.get('title'))}"
        if tgt.strip("_") and any(f.endswith(tgt) for f in folders):
            out.append(j["id"])
        if len(out) >= n:
            break
    return out


@pytest.fixture()
def fake_running_run():
    """A scan_runner record that reads as 'running' (pid = this process)."""
    run_id = "resume_test_fake_running"
    rec_path = scan_runner.RUNS_DIR / f"{run_id}.json"
    log_path = scan_runner.RUNS_DIR / f"{run_id}.log"
    log_path.write_text("# fake tailor run\n", encoding="utf-8")
    rec_path.write_text(json.dumps({
        "run_id": run_id, "label": "resume_fake", "cmd": ["x"],
        "pid": os.getpid(), "started_at": "2026-01-01T00:00:00",
        "log_path": str(log_path), "status_path": str(rec_path),
        "state": "running", "finished_at": None, "returncode": None,
    }), encoding="utf-8")
    yield run_id
    rec_path.unlink(missing_ok=True)
    log_path.unlink(missing_ok=True)


def test_two_ready_plus_one_running_render_independent_cards(fake_running_run):
    ready = _jobs_with_folders(3)
    assert len(ready) >= 3, "test data: need 3 tracker jobs with app folders"
    ready_a, ready_b, running_job = ready[0], ready[1], ready[2]

    at = AppTest.from_file(str(APP), default_timeout=140)
    at.session_state["_applyagent_nav"] = "📋 Roles"
    at.session_state["_kb_sel_id"] = running_job   # action row for this one
    at.session_state["_tailor_runs"] = {
        ready_a: None, ready_b: None, running_job: fake_running_run,
    }
    at.run()

    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc, f"multi-card drawer raised: {exc[:2]}"
    banners = [s.value for s in at.success if "Resume ready" in (s.value or "")]
    assert len(banners) == 2, f"expected 2 ready banners, got {banners}"
    running = [i.value for i in at.info
               if "generation is running" in (i.value or "")]
    assert len(running) == 1, "expected exactly 1 running card"
    gen_chip = [b for b in at.button
                if b.label.startswith("⏳ Generating") and b.disabled]
    assert gen_chip, "in-flight job's Tailor button must be a disabled chip"


def test_ready_card_shows_ats_score_when_report_exists():
    """resume_agent._write_back drops <base>_ats_report.json into the folder;
    the ready card must surface it as a '🎯 ATS keywords: N/M' caption."""
    ready = _jobs_with_folders(1)
    assert ready, "test data: need 1 tracker job with an app folder"
    # find that job's folder and plant a temp ATS report in it
    tracker = json.loads((ROOT / "data" / "job_tracker_data.json")
                         .read_text(encoding="utf-8"))
    job = next(j for j in tracker["jobs"] if j["id"] == ready[0])
    tgt = f"{_slug(job.get('company'))}_{_slug(job.get('title'))}"
    folder = next(d for d in (ROOT / "applications").glob("*/")
                  if d.name.lower().endswith(tgt))
    ats_path = folder / "zz_test_ats_report.json"
    ats_path.write_text(json.dumps(
        {"total": 15, "matched": 13, "missing": ["alpha", "beta"]}),
        encoding="utf-8")
    try:
        at = AppTest.from_file(str(APP), default_timeout=140)
        at.session_state["_applyagent_nav"] = "📋 Roles"
        at.session_state["_tailor_runs"] = {ready[0]: None}
        at.run()
        exc = [str(getattr(e, "value", e)) for e in at.exception]
        assert not exc
        ats_caps = [c.value for c in at.caption
                    if "ATS keywords" in (c.value or "")]
        assert ats_caps and "13/15" in ats_caps[0] and "alpha" in ats_caps[0]
    finally:
        ats_path.unlink(missing_ok=True)


def test_legacy_single_slot_migrates_into_registry():
    ready = _jobs_with_folders(1)
    assert ready, "test data: need 1 tracker job with an app folder"
    at = AppTest.from_file(str(APP), default_timeout=140)
    at.session_state["_applyagent_nav"] = "📋 Roles"
    at.session_state["_active_tailor_job_id"] = ready[0]   # old key only
    at.run()
    exc = [str(getattr(e, "value", e)) for e in at.exception]
    assert not exc
    banners = [s.value for s in at.success if "Resume ready" in (s.value or "")]
    assert len(banners) == 1, "legacy slot should surface as a registry card"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
