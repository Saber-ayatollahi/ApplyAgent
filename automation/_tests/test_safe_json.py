"""Characterization tests for safe_json — the locked read-modify-write utility
EVERY tracker/suppression/worklist mutation depends on. A silent bug here
corrupts shared state, so these pin the core contract: default handling,
round-trip, atomic replace, schema stamping, and that the RMW composes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AUTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO))

import safe_json as S  # noqa: E402


def test_read_missing_returns_default(tmp_path):
    p = tmp_path / "nope.json"
    assert S.read_json(p) is None
    assert S.read_json(p, default={"x": 1}) == {"x": 1}


def test_write_then_read_roundtrip(tmp_path):
    p = tmp_path / "rt.json"
    S.write_json(p, {"a": 1, "b": [1, 2, 3]})
    assert S.read_json(p) == {"a": 1, "b": [1, 2, 3]}


def test_write_stamps_schema_version(tmp_path):
    p = tmp_path / "sv.json"
    S.write_json(p, {"a": 1}, schema_version=3)
    assert S.read_json(p)["_schema_version"] == 3


def test_mutate_applies_and_persists_and_returns(tmp_path):
    p = tmp_path / "m.json"
    S.write_json(p, {"n": 1})
    out = S.mutate_json(p, lambda d: {**d, "n": d["n"] + 1})
    assert out == {"n": 2}
    assert S.read_json(p) == {"n": 2}          # persisted, not just returned


def test_mutate_missing_file_uses_default(tmp_path):
    p = tmp_path / "fresh.json"
    out = S.mutate_json(p, lambda d: {**d, "added": True},
                        default={"jobs": []})
    assert out == {"jobs": [], "added": True}
    assert p.exists()


def test_mutate_empty_file_uses_default(tmp_path):
    # Whitespace-only file must fall back to default, not raise on json.loads.
    p = tmp_path / "empty.json"
    p.write_text("   \n", encoding="utf-8")
    out = S.mutate_json(p, lambda d: d or {"seeded": 1}, default={})
    assert out == {"seeded": 1}


def test_mutate_composes_under_lock(tmp_path):
    # Sequential RMW must accumulate — exercises read→mutate→atomic-write path.
    p = tmp_path / "acc.json"
    S.write_json(p, {"jobs": []})
    for i in range(5):
        S.mutate_json(p, lambda d: {"jobs": d["jobs"] + [i]})
    assert S.read_json(p)["jobs"] == [0, 1, 2, 3, 4]


def test_mutate_schema_version_injected(tmp_path):
    p = tmp_path / "ms.json"
    out = S.mutate_json(p, lambda d: {"k": "v"}, default={}, schema_version=2)
    assert out["_schema_version"] == 2 and out["k"] == "v"


def test_atomic_write_leaves_no_tmp_litter(tmp_path):
    p = tmp_path / "atom.json"
    S.write_json(p, {"a": 1})
    S.mutate_json(p, lambda d: {**d, "b": 2})
    # No leftover *.tmp from the atomic replace (a .lock sidecar is expected).
    tmp_litter = [f.name for f in tmp_path.iterdir()
                  if f.name != "atom.json" and not f.name.endswith(".lock")]
    assert tmp_litter == [], f"atomic write left tmp litter: {tmp_litter}"
    # and the file is valid JSON (not a half-written truncation)
    json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
