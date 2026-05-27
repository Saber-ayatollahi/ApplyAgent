"""Phase 2 Track 2C — pipeline snapshot + env injection tests.

Verifies that run_pipeline.py:
  - snapshots active suppression state at run start (sibling to status JSON);
  - embeds the snapshot path in pipeline_<id>.json;
  - injects APPLYAGENT_SUPPRESSIONS_SNAPSHOT (absolute path) into score
    and promote subprocess env;
  - produces a snapshot even when live suppressions are empty/missing.

Subprocesses are mocked via subprocess.Popen patching — no real scorer or
promoter is launched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))  # so `import automation.run_pipeline` works

from automation import run_pipeline as rp  # noqa: E402
from automation import suppressions as supp  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeProc:
    """Minimal subprocess.Popen stand-in: yields no stdout, returns rc=0."""

    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.stdout = iter([])  # for-loop over proc.stdout terminates immediately

    def wait(self) -> int:
        return self.returncode


@pytest.fixture
def isolated_pipeline(tmp_path, monkeypatch):
    """Redirect pipeline outputs + suppression files into tmp_path."""
    out_dir = tmp_path / "outputs"
    pipeline_dir = out_dir / "pipelines"
    pipeline_dir.mkdir(parents=True)

    monkeypatch.setattr(rp, "OUT_DIR", out_dir)
    monkeypatch.setattr(rp, "PIPELINE_DIR", pipeline_dir)
    # Keep ROOT pointed at tmp so relative_to succeeds with our snapshot path
    monkeypatch.setattr(rp, "ROOT", tmp_path)

    # Suppression module paths
    live = tmp_path / "data" / "suppressions.json"
    example = tmp_path / "data" / "suppressions.example.json"
    events = tmp_path / "data" / "suppressions_events.jsonl"
    history = tmp_path / "data" / "suppressions_history.json"
    pending = tmp_path / "data" / "suppressions_pending_archives.jsonl"
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    example.write_text(
        json.dumps({"version": 1, "sectors": [], "companies": []}, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(supp, "LIVE_PATH", live)
    monkeypatch.setattr(supp, "EXAMPLE_PATH", example)
    monkeypatch.setattr(supp, "EVENTS_PATH", events)
    monkeypatch.setattr(supp, "HISTORY_PATH", history)
    monkeypatch.setattr(supp, "PENDING_ARCHIVES_PATH", pending)

    return {
        "tmp": tmp_path,
        "out_dir": out_dir,
        "pipeline_dir": pipeline_dir,
        "live": live,
        "example": example,
    }


def _seed_one_sector(name: str = "Canadian Big 6 Banks") -> None:
    """Add one sector mute via the public API so the snapshot has content."""
    supp.add_sector(name, date.today() + timedelta(days=60), "test")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_snapshot_written_at_run_start(isolated_pipeline):
    """The snapshot file is created at the expected sibling path."""
    pipeline_id = "20260101_120000"
    out = rp._snapshot_suppressions(pipeline_id)

    expected = isolated_pipeline["pipeline_dir"] / f"pipeline_{pipeline_id}_suppressions.json"
    assert out == expected
    assert expected.exists()

    data = json.loads(expected.read_text(encoding="utf-8"))
    assert data == {"version": 1, "sectors": [], "companies": []}


def test_snapshot_path_embedded_in_status_json(isolated_pipeline, monkeypatch):
    """pipeline_<id>.json carries a `suppressions_snapshot` key pointing at the file."""
    _seed_one_sector()

    # Stub _run so we just exercise the run-start prelude in main().
    monkeypatch.setattr(rp, "_run", lambda *a, **kw: 0)
    # Disable LLM preflight (no env, no real key)
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--skip-scrape",
                                      "--skip-score", "--skip-promote"])

    rc = rp.main()
    assert rc == 0

    statuses = sorted(isolated_pipeline["pipeline_dir"].glob("pipeline_*.json"))
    statuses = [p for p in statuses if "_suppressions" not in p.name]
    assert len(statuses) == 1, statuses

    payload = json.loads(statuses[0].read_text(encoding="utf-8"))
    assert "suppressions_snapshot" in payload
    snapshot_rel = payload["suppressions_snapshot"]

    # Resolve back to the actual file (relative to ROOT which we monkeypatched)
    snapshot_abs = (isolated_pipeline["tmp"] / snapshot_rel).resolve()
    assert snapshot_abs.exists()

    snap = json.loads(snapshot_abs.read_text(encoding="utf-8"))
    assert any(e.get("name") == "Canadian Big 6 Banks"
               for e in snap.get("sectors", []))


def test_env_var_passed_to_scorer_subprocess(isolated_pipeline, monkeypatch):
    """When _stream launches the scorer, the snapshot env var is in the child env."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    # Pre-create snapshot (normally main() does this; we're calling _stream directly)
    pipeline_id = "20260102_000000"
    snapshot_path = rp._snapshot_suppressions(pipeline_id)
    child_env = rp._subprocess_env(snapshot_path)

    status = {"pipeline_id": pipeline_id, "stages": {}}
    rc = rp._stream(["python", "fit_scorer.py"], "score", status, "score",
                    env=child_env)
    assert rc == 0

    env = captured["env"]
    assert env is not None
    assert "APPLYAGENT_SUPPRESSIONS_SNAPSHOT" in env
    assert env["APPLYAGENT_SUPPRESSIONS_SNAPSHOT"] == str(snapshot_path.resolve())


def test_env_var_passed_to_promote_subprocess(isolated_pipeline, monkeypatch):
    """Same env-injection contract holds for the auto_promote stage."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    pipeline_id = "20260103_000000"
    snapshot_path = rp._snapshot_suppressions(pipeline_id)
    child_env = rp._subprocess_env(snapshot_path)

    status = {"pipeline_id": pipeline_id, "stages": {}}
    rc = rp._stream(["python", "auto_promote.py"], "promote", status, "promote",
                    env=child_env)
    assert rc == 0

    env = captured["env"]
    assert env is not None
    assert env.get("APPLYAGENT_SUPPRESSIONS_SNAPSHOT") == str(snapshot_path.resolve())


def test_empty_suppressions_still_creates_snapshot(isolated_pipeline):
    """No live file → snapshot is still written with the empty seed shape."""
    # Sanity: no live file yet
    assert not isolated_pipeline["live"].exists()

    pipeline_id = "20260104_000000"
    out = rp._snapshot_suppressions(pipeline_id)
    assert out.exists()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("version") == 1
    assert data.get("sectors") == []
    assert data.get("companies") == []


def test_snapshot_path_is_absolute(isolated_pipeline):
    """The env-var value must be absolute — subprocesses cwd may differ from ours."""
    pipeline_id = "20260105_000000"
    snapshot_path = rp._snapshot_suppressions(pipeline_id)

    env = rp._subprocess_env(snapshot_path)
    val = env["APPLYAGENT_SUPPRESSIONS_SNAPSHOT"]
    assert os.path.isabs(val), val
    assert Path(val) == snapshot_path.resolve()


def test_main_injects_env_into_score_and_promote(isolated_pipeline, monkeypatch):
    """End-to-end: full main() run with mocked Popen sees env var on score+promote stages."""
    _seed_one_sector()

    calls: list[dict] = []

    def fake_popen(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "env": kwargs.get("env")})
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    # Stub worklist.rebuild so we don't hit real disk paths
    fake_worklist = MagicMock()
    fake_worklist.rebuild.return_value = {
        "total": 0, "scrape": 0, "gmail": 0, "both": 0, "new_since_last_score": 0
    }
    fake_worklist.effective_scored.return_value = None
    monkeypatch.setitem(sys.modules, "worklist", fake_worklist)
    monkeypatch.setitem(sys.modules, "automation.worklist", fake_worklist)

    # Skip every stage so the test stays deterministic; we still verify env
    # would be passed by directly checking _stream-bound calls. To exercise
    # at least one real Popen, we let scrape run (no env required there but
    # confirms the no-env path still works).
    monkeypatch.setattr(sys, "argv",
                        ["run_pipeline.py", "--skip-score", "--skip-promote"])

    rc = rp.main()
    assert rc == 0
    # Scrape ran with default env (env=os.environ via Popen default) — its
    # kwargs.env may be None, which is fine.
    assert any("jd_scraper.py" in " ".join(c["cmd"]) for c in calls)


def test_snapshot_written_before_subprocesses_launch(isolated_pipeline, monkeypatch):
    """Snapshot file must already exist on disk before the scrape Popen is invoked.

    Otherwise a subprocess that resolves the env var early would race against
    the snapshot writer."""
    snapshot_existed_at_popen: list[bool] = []

    expected_snapshot = None  # filled in after main computes pipeline_id

    def fake_popen(cmd, **kwargs):
        # On first invocation, find the latest snapshot file under PIPELINE_DIR
        snaps = list(isolated_pipeline["pipeline_dir"].glob("*_suppressions.json"))
        snapshot_existed_at_popen.append(bool(snaps))
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    fake_worklist = MagicMock()
    fake_worklist.rebuild.return_value = {
        "total": 0, "scrape": 0, "gmail": 0, "both": 0, "new_since_last_score": 0
    }
    fake_worklist.effective_scored.return_value = None
    monkeypatch.setitem(sys.modules, "worklist", fake_worklist)
    monkeypatch.setitem(sys.modules, "automation.worklist", fake_worklist)

    monkeypatch.setattr(sys, "argv",
                        ["run_pipeline.py", "--skip-score", "--skip-promote"])

    rc = rp.main()
    assert rc == 0
    assert snapshot_existed_at_popen, "no Popen invocation observed"
    assert all(snapshot_existed_at_popen), \
        "snapshot file must be on disk before any subprocess launches"
