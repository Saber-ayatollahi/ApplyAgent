"""CLI tests for `python -m automation.suppressions`.

We exercise the CLI two ways:

1. **In-process via `_main([...])`** — fast, lets us monkeypatch the module's
   path globals so the CLI hits a tmp_path instead of real `data/`.
2. **Subprocess for `--smoke`** — proves the `__main__` entrypoint is wired
   correctly end-to-end.

The in-process path is the one that catches CLI regressions (arg parsing,
exit codes, JSON output shape, mutual-exclusion guards). The subprocess test
exists because a broken `if __name__ == "__main__":` block would otherwise
slip through every in-process test.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))

from automation import suppressions as supp  # noqa: E402


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    """Redirect every suppressions file path into tmp_path.

    Mirrors the fixture in test_suppressions.py but is independent so this
    file can be read/run on its own."""
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
    return {
        "live": live,
        "events": events,
        "history": history,
        "tmp": tmp_path,
    }


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Invoke `_main(argv)` capturing stdout/stderr."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = supp._main(argv)
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# 1. Round-trip: add → list → lift
# ---------------------------------------------------------------------------

def test_add_sector_then_list_then_lift_roundtrip(isolated_cli):
    rc, out, err = _run_cli([
        "add-sector", "Canadian Big 6 Banks",
        "--days", "30", "--reason", "Q2 cooldown", "--json",
    ])
    assert rc == 0, err
    payload = json.loads(out.strip())
    assert payload["ok"] is True
    assert payload["scope"] == "sector"
    assert payload["name"] == "Canadian Big 6 Banks"
    assert payload["until"] == (date.today() + timedelta(days=30)).isoformat()

    rc, out, _ = _run_cli(["list", "--json"])
    assert rc == 0
    listed = json.loads(out)
    assert len(listed["active"]["sectors"]) == 1
    assert listed["active"]["sectors"][0]["name"] == "Canadian Big 6 Banks"

    rc, out, _ = _run_cli(["lift", "sector", "Canadian Big 6 Banks", "--json"])
    assert rc == 0
    lift_payload = json.loads(out.strip())
    assert lift_payload["lifted"] is True

    rc, out, _ = _run_cli(["list", "--json"])
    final = json.loads(out)
    assert final["active"]["sectors"] == []


def test_add_sector_lenient_canonicalization(isolated_cli):
    """User types lowercase / sloppy; CLI canonicalizes to display name."""
    rc, out, err = _run_cli([
        "add-sector", "canadian big 6 banks",
        "--days", "14", "--json",
    ])
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["name"] == "Canadian Big 6 Banks"  # canonicalized


def test_add_sector_unknown_returns_error(isolated_cli):
    rc, out, err = _run_cli([
        "add-sector", "Not A Real Sector",
        "--days", "10", "--json",
    ])
    assert rc != 0
    assert "unknown sector" in err.lower()
    # State must not be mutated.
    assert not isolated_cli["live"].exists() or \
        json.loads(isolated_cli["live"].read_text())["sectors"] == []


# ---------------------------------------------------------------------------
# 2. add-company
# ---------------------------------------------------------------------------

def test_add_company_with_until_date(isolated_cli):
    target = (date.today() + timedelta(days=45)).isoformat()
    rc, out, err = _run_cli([
        "add-company", "Acme Corp",
        "--until", target, "--reason", "Bad recruiter exp", "--json",
    ])
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["scope"] == "company"
    assert payload["until"] == target


def test_add_company_permanent_when_no_ttl(isolated_cli):
    rc, out, _ = _run_cli([
        "add-company", "PermaMute Inc",
        "--reason", "permanent", "--json",
    ])
    assert rc == 0
    payload = json.loads(out)
    assert payload["until"] is None


# ---------------------------------------------------------------------------
# 3. Mutual-exclusion guards
# ---------------------------------------------------------------------------

def test_days_and_until_are_mutually_exclusive(isolated_cli):
    rc, _, err = _run_cli([
        "add-sector", "Canadian Big 6 Banks",
        "--days", "30", "--until", "2027-01-01",
    ])
    assert rc != 0
    assert "mutually exclusive" in err.lower()


def test_negative_days_rejected(isolated_cli):
    rc, _, err = _run_cli([
        "add-sector", "Canadian Big 6 Banks",
        "--days", "-5",
    ])
    assert rc != 0
    assert "must be positive" in err.lower()


def test_bad_until_format_rejected(isolated_cli):
    rc, _, err = _run_cli([
        "add-sector", "Canadian Big 6 Banks",
        "--until", "not-a-date",
    ])
    assert rc != 0
    assert "yyyy-mm-dd" in err.lower()


# ---------------------------------------------------------------------------
# 4. lift no-op semantics
# ---------------------------------------------------------------------------

def test_lift_noop_when_not_present(isolated_cli):
    rc, out, _ = _run_cli([
        "lift", "company", "Never Muted Inc", "--json",
    ])
    # The underlying lift() is intentionally a no-op-with-event when absent;
    # the CLI surfaces lifted=False so callers can detect it.
    assert rc == 0
    assert json.loads(out.strip())["lifted"] is False


# ---------------------------------------------------------------------------
# 5. extend / edit-reason
# ---------------------------------------------------------------------------

def test_extend_pushes_until_forward(isolated_cli):
    base_iso = (date.today() + timedelta(days=10)).isoformat()
    _run_cli(["add-sector", "Canadian Big 6 Banks", "--until", base_iso])
    rc, out, err = _run_cli([
        "extend", "sector", "Canadian Big 6 Banks", "--days", "20", "--json",
    ])
    assert rc == 0, err
    after = json.loads(_run_cli(["list", "--json"])[1])
    new_until = after["active"]["sectors"][0]["until"]
    assert new_until == (date.today() + timedelta(days=30)).isoformat()


def test_extend_unknown_entry_errors(isolated_cli):
    rc, _, err = _run_cli([
        "extend", "company", "Ghost Co", "--days", "5",
    ])
    assert rc != 0
    assert "no company suppression" in err.lower()


def test_edit_reason_updates_in_place(isolated_cli):
    _run_cli(["add-company", "Acme Corp", "--days", "30", "--reason", "old"])
    rc, _, err = _run_cli([
        "edit-reason", "company", "Acme Corp", "--reason", "new reason",
    ])
    assert rc == 0, err
    listed = json.loads(_run_cli(["list", "--json"])[1])
    assert listed["active"]["companies"][0]["reason"] == "new reason"


# ---------------------------------------------------------------------------
# 6. audit log
# ---------------------------------------------------------------------------

def test_audit_returns_jsonl_tail(isolated_cli):
    _run_cli(["add-sector", "Canadian Big 6 Banks", "--days", "30",
              "--reason", "first"])
    _run_cli(["add-company", "Acme Corp", "--days", "30", "--reason", "second"])
    rc, out, _ = _run_cli(["audit", "--json", "--limit", "10"])
    assert rc == 0
    payload = json.loads(out)
    assert len(payload["events"]) >= 2
    # Most recent event is the company add.
    last = payload["events"][-1]
    assert last["action"] == "add"
    assert last["scope"] == "company"


def test_audit_when_no_events_yet(isolated_cli):
    rc, out, _ = _run_cli(["audit", "--json"])
    assert rc == 0
    assert json.loads(out)["events"] == []


# ---------------------------------------------------------------------------
# 7. list output table (human format) and --include-expired
# ---------------------------------------------------------------------------

def test_list_human_output_mentions_active_count(isolated_cli):
    _run_cli(["add-sector", "Canadian Big 6 Banks", "--days", "30"])
    rc, out, _ = _run_cli(["list"])
    assert rc == 0
    assert "ACTIVE SECTORS (1)" in out
    assert "Canadian Big 6 Banks" in out


def test_list_include_expired_pulls_from_history(isolated_cli):
    _run_cli(["add-sector", "Canadian Big 6 Banks", "--days", "30"])
    _run_cli(["lift", "sector", "Canadian Big 6 Banks"])
    rc, out, _ = _run_cli(["list", "--include-expired", "--json"])
    payload = json.loads(out)
    assert payload["expired"] is not None
    assert len(payload["expired"]) >= 1


# ---------------------------------------------------------------------------
# 8. Subprocess: prove the __main__ block invokes the parser
# ---------------------------------------------------------------------------

def test_subprocess_smoke_runs(tmp_path):
    """The --smoke path uses its own private tmp dir, so we can run it with
    the real module path. This guards against the __main__ block silently
    drifting from _main()."""
    result = subprocess.run(
        [sys.executable, "-m", "automation.suppressions", "--smoke"],
        cwd=str(AUTO.parent),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_subprocess_help_exits_zero(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "automation.suppressions", "--help"],
        cwd=str(AUTO.parent),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "add-sector" in result.stdout
    assert "add-company" in result.stdout
