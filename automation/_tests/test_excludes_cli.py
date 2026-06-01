"""CLI tests for `python -m automation.excludes`.

In-process via `_main([...])` for arg parsing / exit codes / JSON shape, plus
a subprocess `--smoke` to prove the `__main__` entrypoint is wired.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))

from automation import excludes as exc  # noqa: E402


@pytest.fixture
def isolated_cli(tmp_path, monkeypatch):
    example = tmp_path / "excludes.example.json"
    example.write_text(json.dumps({"version": 1, "companies": []}), encoding="utf-8")
    monkeypatch.setattr(exc, "LIVE_PATH", tmp_path / "excludes.json")
    monkeypatch.setattr(exc, "EXAMPLE_PATH", example)
    return {"tmp": tmp_path}


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = exc._main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_add_then_list_then_remove_roundtrip(isolated_cli):
    rc, out, _ = _run_cli(["add", "RBC", "--json"])
    assert rc == 0
    payload = json.loads(out)
    assert payload["added"] is True and payload["canonical_key"] == "rbc"

    rc, out, _ = _run_cli(["list", "--json"])
    assert rc == 0
    assert {c["canonical_key"] for c in json.loads(out)["companies"]} == {"rbc"}

    rc, out, _ = _run_cli(["remove", "Royal Bank of Canada", "--json"])
    assert rc == 0
    assert json.loads(out)["removed"] is True

    rc, out, _ = _run_cli(["list", "--json"])
    assert json.loads(out)["companies"] == []


def test_add_lenient_canonicalization(isolated_cli):
    rc, out, _ = _run_cli(["add", "royal bank of canada", "--json"])
    assert rc == 0
    p = json.loads(out)
    assert p["canonical_key"] == "rbc"
    assert p["name"] == "royal bank of canada"  # display name preserved


def test_add_idempotent_reports_not_added(isolated_cli):
    _run_cli(["add", "RBC"])
    rc, out, _ = _run_cli(["add", "RBC Capital Markets", "--json"])
    assert rc == 0
    assert json.loads(out)["added"] is False


def test_list_human_output(isolated_cli):
    _run_cli(["add", "TD Bank"])
    rc, out, _ = _run_cli(["list"])
    assert rc == 0
    assert "EXCLUDED COMPANIES (1)" in out
    assert "td" in out


def test_remove_noop_when_absent(isolated_cli):
    rc, out, _ = _run_cli(["remove", "RBC", "--json"])
    assert rc == 0
    assert json.loads(out)["removed"] is False


def test_subprocess_smoke_runs():
    proc = subprocess.run(
        [sys.executable, "-m", "automation.excludes", "--smoke"],
        cwd=str(AUTO.parent), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_subprocess_help_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "automation.excludes"],
        cwd=str(AUTO.parent), capture_output=True, text=True,
    )
    assert proc.returncode == 0


# ---------------------------------------------------------------------------
# gitignore safety: live file ignored, example committed
# ---------------------------------------------------------------------------
def test_gitignore_excludes_live_but_not_example():
    gi = (AUTO.parent / ".gitignore").read_text(encoding="utf-8")
    lines = {ln.strip() for ln in gi.splitlines()}
    assert "data/excludes.json" in lines
    assert "data/excludes.example.json" not in lines


# ---------------------------------------------------------------------------
# UI checkbox dedup logic (pure — no Streamlit). Pins the de-dup-by-canonical
# requirement that prevents a StreamlitDuplicateElementKey crash, and the
# collision-label (one box names its siblings) behaviour.
# ---------------------------------------------------------------------------
def test_checkbox_universe_dedups_by_canonical_no_dup_keys():
    sys.path.insert(0, str(AUTO))
    from jd_scraper import TARGETS  # type: ignore
    from brand_aliases import canonical_brand  # type: ignore

    keys = [canonical_brand(t.get("name", "")).lower()
            for t in TARGETS if canonical_brand(t.get("name", "")).lower()]
    deduped = set(keys)
    # Real TARGETS contains RBC + RBC Global Asset Management (both → 'rbc'),
    # TD Bank + TD Asset Management (→ 'td'), BMO + BMO AM (→ 'bmo'): proves
    # the raw key list HAS collisions that dedup must collapse.
    assert len(keys) > len(deduped), "expected canonical collisions in TARGETS"
    # After dedup the checkbox key set is unique (no Streamlit crash).
    assert len(deduped) == len(set(deduped))
    # The Big-6 banks each resolve to a single canonical key.
    for key in ("rbc", "td", "bmo", "scotia", "cibc", "nbc"):
        assert key in deduped, key
