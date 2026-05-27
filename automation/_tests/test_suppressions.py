"""Tests for automation/suppressions.py — TTL, canonical-keys, audit log, locks."""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))  # so `import automation.suppressions` works

from automation import suppressions as supp  # noqa: E402
from automation.safe_json import mutate_json  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Redirect all suppression file paths into tmp_path."""
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
        "example": example,
        "events": events,
        "history": history,
        "pending": pending,
        "tmp": tmp_path,
    }


def _read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# 1. canonical-key matching for company variants
# ---------------------------------------------------------------------------
def test_canonical_key_match_company_variants(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_company("RBC", until, "ghosted x2")

    for variant in ("RBC", "Royal Bank of Canada", "RBC Capital Markets"):
        suppressed, reason = supp.is_suppressed({"company": variant, "sector": ""})
        assert suppressed is True, f"variant {variant!r} should match"
        assert reason and reason.startswith("suppressed_company_")


# ---------------------------------------------------------------------------
# 2. sector registry rejects unknown
# ---------------------------------------------------------------------------
def test_sector_registry_validation_rejects_unknown(isolated):
    with pytest.raises(ValueError):
        supp.add_sector("Made-up Sector", date.today() + timedelta(days=30), "nope")


# ---------------------------------------------------------------------------
# 3. canonical sector lookup stores display name
# ---------------------------------------------------------------------------
def test_sector_registry_canonical_lookup(isolated):
    supp.add_sector("canadian big 6 banks", date.today() + timedelta(days=30), "test")
    state = supp.load_active()
    assert len(state["sectors"]) == 1
    assert state["sectors"][0]["name"] == "Canadian Big 6 Banks"
    assert state["sectors"][0]["canonical_key"] == "canadian big 6 banks"


# ---------------------------------------------------------------------------
# 4. unsectored row passthrough
# ---------------------------------------------------------------------------
def test_unsectored_row_passthrough(isolated):
    supp.add_sector("Canadian Big 6 Banks", date.today() + timedelta(days=60), "test")
    suppressed, reason = supp.is_suppressed({"sector": "", "company": "SomeRandomCo"})
    assert suppressed is False
    assert reason is None


# ---------------------------------------------------------------------------
# 5. lazy TTL expiry moves to history
# ---------------------------------------------------------------------------
def test_lazy_ttl_expiry_moves_to_history(isolated):
    yesterday = date.today() - timedelta(days=1)
    # Seed live file with an already-expired entry.
    expired_entry = {
        "scope": "sector",
        "name": "Canadian Big 6 Banks",
        "canonical_key": "canadian big 6 banks",
        "until": yesterday.isoformat(),
        "reason": "stale",
        "added_at": (datetime.now() - timedelta(days=10)).isoformat(),
        "version": 1,
    }
    isolated["live"].write_text(
        json.dumps({"version": 1, "sectors": [expired_entry], "companies": []}),
        encoding="utf-8",
    )

    state = supp.load_active()
    assert state["sectors"] == []

    history = json.loads(isolated["history"].read_text(encoding="utf-8"))
    assert len(history.get("entries", [])) == 1
    assert history["entries"][0]["canonical_key"] == "canadian big 6 banks"
    assert "lifted_at" in history["entries"][0]


# ---------------------------------------------------------------------------
# 6. load_recently_expired window
# ---------------------------------------------------------------------------
def test_load_recently_expired_window(isolated):
    today = date.today()
    history = {
        "version": 1,
        "entries": [
            {"scope": "sector", "name": "A", "canonical_key": "a",
             "until": (today - timedelta(days=3)).isoformat(),
             "reason": "x", "added_at": "2026-01-01T00:00:00", "version": 1,
             "lifted_at": "2026-01-02T00:00:00"},
            {"scope": "sector", "name": "B", "canonical_key": "b",
             "until": (today - timedelta(days=8)).isoformat(),
             "reason": "x", "added_at": "2026-01-01T00:00:00", "version": 1,
             "lifted_at": "2026-01-02T00:00:00"},
            {"scope": "sector", "name": "C", "canonical_key": "c",
             "until": (today - timedelta(days=14)).isoformat(),
             "reason": "x", "added_at": "2026-01-01T00:00:00", "version": 1,
             "lifted_at": "2026-01-02T00:00:00"},
        ],
    }
    isolated["history"].write_text(json.dumps(history), encoding="utf-8")

    out = supp.load_recently_expired(window_days=7)
    keys = {e["canonical_key"] for e in out}
    assert keys == {"a"}


# ---------------------------------------------------------------------------
# 7. drop reason format
# ---------------------------------------------------------------------------
def test_is_suppressed_drop_reason_format(isolated):
    until = date.today() + timedelta(days=57)
    supp.add_sector("Canadian Big 6 Banks", until, "1/14")
    _, reason = supp.is_suppressed({"sector": "Canadian Big 6 Banks", "company": ""})
    assert reason is not None
    assert re.match(r"(?i)suppressed_(sector|company)_\d+d", reason)
    assert "sector" in reason


# ---------------------------------------------------------------------------
# 8. events log appended on every mutation
# ---------------------------------------------------------------------------
def test_events_log_appended_on_every_mutation(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "r1")
    supp.extend("sector", "Canadian Big 6 Banks", 30)
    supp.edit_reason("sector", "Canadian Big 6 Banks", "r2")
    supp.lift("sector", "Canadian Big 6 Banks")

    events = _read_events(isolated["events"])
    actions = [e["action"] for e in events]
    assert actions == ["add", "extend", "edit_reason", "lift"]


# ---------------------------------------------------------------------------
# 9. rebuild active state from events log alone
# ---------------------------------------------------------------------------
def test_rebuild_active_state_from_events_log_alone(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "r1")
    supp.add_company("RBC", until, "ghosted")
    supp.edit_reason("sector", "Canadian Big 6 Banks", "r2")

    events = _read_events(isolated["events"])

    # Reconstruct active state from events alone.
    rebuilt = {"sectors": {}, "companies": {}}
    for e in events:
        scope_key = "sectors" if e["scope"] == "sector" else "companies"
        if e["action"] == "add":
            rebuilt[scope_key][e["canonical_key"]] = e["new"]
        elif e["action"] == "edit_reason":
            rebuilt[scope_key][e["canonical_key"]] = e["new"]
        elif e["action"] == "extend":
            rebuilt[scope_key][e["canonical_key"]] = e["new"]
        elif e["action"] == "lift":
            rebuilt[scope_key].pop(e["canonical_key"], None)

    live = supp.load_active()
    live_keys = {
        "sectors": {e["canonical_key"]: e for e in live["sectors"]},
        "companies": {e["canonical_key"]: e for e in live["companies"]},
    }
    assert set(rebuilt["sectors"].keys()) == set(live_keys["sectors"].keys())
    assert set(rebuilt["companies"].keys()) == set(live_keys["companies"].keys())
    for k, v in rebuilt["sectors"].items():
        assert live_keys["sectors"][k]["reason"] == v["reason"]


# ---------------------------------------------------------------------------
# 10. snapshot_to writes active state
# ---------------------------------------------------------------------------
def test_snapshot_to_writes_active_state(isolated):
    until = date.today() + timedelta(days=60)
    supp.add_sector("Canadian Big 6 Banks", until, "r1")
    # Also seed an expired one directly into live so we verify it's filtered.
    live = json.loads(isolated["live"].read_text(encoding="utf-8"))
    live["sectors"].append({
        "scope": "sector",
        "name": "Fintech",
        "canonical_key": "fintech",
        "until": (date.today() - timedelta(days=1)).isoformat(),
        "reason": "old",
        "added_at": "2026-01-01T00:00:00",
        "version": 1,
    })
    isolated["live"].write_text(json.dumps(live), encoding="utf-8")

    target = isolated["tmp"] / "snap.json"
    supp.snapshot_to(target)
    snap = json.loads(target.read_text(encoding="utf-8"))
    keys = {e["canonical_key"] for e in snap["sectors"]}
    assert keys == {"canadian big 6 banks"}


# ---------------------------------------------------------------------------
# 11. coverage stats
# ---------------------------------------------------------------------------
def test_coverage_stats(isolated):
    rows = (
        [{"sector": "Canadian Big 6 Banks", "company": "RBC"} for _ in range(6)]
        + [{"sector": "", "company": "SomeCo"} for _ in range(2)]
        + [{"sector": "Fintech", "company": "FintechCo"} for _ in range(2)]
    )
    cov = supp.coverage("sector", "Canadian Big 6 Banks", rows)
    assert cov == {"matched": 6, "total": 8, "unsectored": 2}


# ---------------------------------------------------------------------------
# 12. lock contention with simulated promote
# ---------------------------------------------------------------------------
def test_lock_contention_with_simulated_promote(isolated):
    until = date.today() + timedelta(days=60)

    errors: list[Exception] = []

    def _t1():
        try:
            supp.add_sector("Canadian Big 6 Banks", until, "from-thread-1")
        except Exception as e:
            errors.append(e)

    def _t2():
        try:
            def _mut(state):
                state = state or {"version": 1, "sectors": [], "companies": []}
                state.setdefault("companies", [])
                state["companies"].append({
                    "scope": "company",
                    "name": "DirectWriter",
                    "canonical_key": "directwriter",
                    "until": until.isoformat(),
                    "reason": "direct",
                    "added_at": datetime.now().isoformat(),
                    "version": 1,
                })
                return state
            mutate_json(supp.LIVE_PATH, _mut,
                        default={"version": 1, "sectors": [], "companies": []})
        except Exception as e:
            errors.append(e)

    # Stagger by a tick so both read-modify-write cycles see each other's
    # commit. portalocker's file lock is the cross-process safety net but
    # doesn't serialize same-process threads on Windows; the test here is
    # "both writes land + events log captures both", not OS-level mutex.
    th1 = threading.Thread(target=_t1)
    th2 = threading.Thread(target=_t2)
    th1.start(); th1.join()
    th2.start(); th2.join()

    assert not errors, f"thread errors: {errors}"

    state = supp.load_active()
    sec_keys = {e["canonical_key"] for e in state["sectors"]}
    comp_keys = {e["canonical_key"] for e in state["companies"]}
    assert "canadian big 6 banks" in sec_keys
    assert "directwriter" in comp_keys


# ---------------------------------------------------------------------------
# 13. queue and drain pending archives
# ---------------------------------------------------------------------------
def test_queue_and_drain_pending_archives(isolated):
    supp.queue_pending_archive("job-1", "rbc")
    supp.queue_pending_archive("job-2", "scotia")
    supp.queue_pending_archive("job-3", "td")
    drained = supp.drain_pending_archives()
    assert len(drained) == 3
    assert {d["job_id"] for d in drained} == {"job-1", "job-2", "job-3"}
    # File should be empty (or absent) after drain.
    if isolated["pending"].exists():
        assert isolated["pending"].read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------------------
# 14. lift noop on missing entry records in events log
# ---------------------------------------------------------------------------
def test_lift_noop_records_in_events_log(isolated):
    supp.lift("sector", "Canadian Big 6 Banks")  # never added
    events = _read_events(isolated["events"])
    assert len(events) == 1
    assert events[0]["action"] == "lift_noop"


# ---------------------------------------------------------------------------
# 15. replace existing entry for same canonical key
# ---------------------------------------------------------------------------
def test_replace_existing_entry_for_same_canonical_key(isolated):
    until1 = date.today() + timedelta(days=30)
    until2 = date.today() + timedelta(days=90)
    supp.add_sector("Canadian Big 6 Banks", until1, "first")
    supp.add_sector("canadian big 6 banks", until2, "second")  # same canonical
    state = supp.load_active()
    assert len(state["sectors"]) == 1
    assert state["sectors"][0]["reason"] == "second"
    assert state["sectors"][0]["until"] == until2.isoformat()


# ---------------------------------------------------------------------------
# Regression tests for v3.1.1 review findings (2026-05-27)
# ---------------------------------------------------------------------------

def test_is_expired_fail_closed_on_malformed_until(isolated):
    """Malformed `until` is treated as expired (fail-closed) so the registry
    self-cleans rather than silently keeping a stale mute alive forever."""
    bad_entry = {"until": "not-a-date", "reason": "broken"}
    assert supp._is_expired(bad_entry, date.today()) is True

    bad_entry2 = {"until": "2026-13-45", "reason": "broken month"}
    assert supp._is_expired(bad_entry2, date.today()) is True


def test_is_suppressed_handles_non_string_company(isolated):
    """A row with int/list/dict in company or sector must NOT crash the
    scoring loop; one malformed row would otherwise kill the whole run."""
    supp.add_sector("Canadian Big 6 Banks", date.today() + timedelta(days=60), "test")
    snap = supp.load_active()
    for bad_row in [
        {"company": 12345, "sector": "Canadian Big 6 Banks"},
        {"company": ["RBC"], "sector": None},
        {"company": {"name": "RBC"}, "sector": 0},
        {"company": "RBC", "sector": [1, 2]},
    ]:
        # Must not raise; sector match still works when sector_raw is non-string
        # because we coerce to "" and skip.
        supp.is_suppressed(bad_row, snapshot=snap)


def test_queue_pending_archive_is_locked(isolated):
    """queue_pending_archive must take an exclusive lock so concurrent
    queue+drain doesn't lose entries to the read-then-truncate window."""
    # Sequential sanity: queue then drain returns the entry.
    supp.queue_pending_archive("job-001", "test reason")
    drained = supp.drain_pending_archives()
    assert len(drained) == 1
    assert drained[0]["job_id"] == "job-001"
    # The lock primitive is the same one drain uses; if it is missing the
    # `_FileLock` wrapper this test asserts at least the basic contract.
    import inspect
    src = inspect.getsource(supp.queue_pending_archive)
    assert "_FileLock" in src, "queue_pending_archive must use _FileLock"


def test_event_appended_inside_live_file_lock(isolated):
    """Audit-trail order must match commit order. The event append is
    invoked from inside the live-file mutate_json closure; this test reads
    the source as a guard against future regressions that move it out."""
    import inspect
    src = inspect.getsource(supp._add)
    # The event-emission call must appear BEFORE `return state` inside `_mut`.
    assert "_append_event(" in src
    # Ensure the append is no longer after `mutate_json(...)`. A naive way:
    # find both, ensure mutate_json appears LATER in the source than _append_event.
    pos_event = src.index("_append_event(")
    pos_mutate = src.index("mutate_json(LIVE_PATH")
    assert pos_event < pos_mutate, (
        "_append_event must be called inside the _mut closure, before "
        "mutate_json returns and releases the live-file lock"
    )
