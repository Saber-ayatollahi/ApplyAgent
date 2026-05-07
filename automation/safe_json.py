#!/usr/bin/env python3
"""
safe_json.py — Cross-process-safe JSON read/modify/write helpers.

The tracker (data/job_tracker_data.json), lifetime cost ledger, CRM, and
several automation jobs all touch the same files. Without locking, two
concurrent writers (the UI + a cron job + a manual script) can silently
lose each other's edits because each one reads, modifies in memory, then
writes the whole object back.

This module wraps those read-modify-write patterns in an exclusive file
lock (via portalocker) and writes atomically via a temp-file rename so
a crashed write never leaves a truncated JSON on disk.

Usage:
    from safe_json import read_json, write_json, mutate_json

    # Plain read — still honors a reader lock.
    data = read_json("data/job_tracker_data.json", default={"jobs": []})

    # Plain write — locks, atomic replace.
    write_json("data/job_tracker_data.json", data)

    # Read-modify-write as one critical section.
    def promote_job(jobs):
        for j in jobs["jobs"]:
            if j["id"] == "scot-001":
                j["status"] = "Applied"
        return jobs

    mutate_json("data/job_tracker_data.json", promote_job,
                default={"jobs": []})

If the file doesn't exist, `default` is returned from read_json and
created by mutate_json. If the parent directory doesn't exist, it's
created.

Schema versioning: pass `schema_version=` to write_json / mutate_json and
the helper writes `_schema_version` into the top-level object. Readers
can check it against an expected version and migrate if needed.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import portalocker  # type: ignore
    _HAVE_PORTALOCKER = True
except ImportError:
    _HAVE_PORTALOCKER = False

# Default timeout for acquiring the lock. Short by design — a healthy system
# should release locks in <50ms; if we wait 10s, something is seriously wrong
# and we'd rather fail loud than hang indefinitely.
LOCK_TIMEOUT_SEC = 10.0


class LockTimeout(RuntimeError):
    """Raised when the file lock can't be acquired within LOCK_TIMEOUT_SEC."""


def _lock_path(target: Path) -> Path:
    """Sidecar lock file path. We lock a separate `<target>.lock` file so the
    target file itself can be atomically replaced on Windows (which refuses
    rename-over-open-file, unlike POSIX)."""
    return target.with_suffix(target.suffix + ".lock")


class _FileLock:
    """Context manager that acquires an exclusive (or shared) portalocker
    lock on a sidecar `<target>.lock` file. Falls back to a no-op with a
    loud one-time warning if portalocker isn't installed."""

    def __init__(self, target: Path, exclusive: bool = True):
        self.target = target
        self.exclusive = exclusive
        self.fh = None

    def __enter__(self):
        if not _HAVE_PORTALOCKER:
            if not getattr(_FileLock, "_warned", False):
                print(
                    "[safe_json] WARN: portalocker not installed — JSON writes "
                    "are NOT cross-process safe. pip install portalocker",
                    file=sys.stderr,
                )
                _FileLock._warned = True  # type: ignore
            return self
        lp = _lock_path(self.target)
        lp.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(lp, "a+")
        lock_type = portalocker.LOCK_EX if self.exclusive else portalocker.LOCK_SH
        deadline = time.time() + LOCK_TIMEOUT_SEC
        while True:
            try:
                portalocker.lock(self.fh, lock_type | portalocker.LOCK_NB)
                return self
            except portalocker.exceptions.LockException:
                if time.time() >= deadline:
                    try:
                        self.fh.close()
                    except Exception:
                        pass
                    raise LockTimeout(
                        f"could not acquire {'EX' if self.exclusive else 'SH'} lock "
                        f"on {lp} within {LOCK_TIMEOUT_SEC}s"
                    )
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.fh is not None:
            try:
                if _HAVE_PORTALOCKER:
                    portalocker.unlock(self.fh)
            except Exception:
                pass
            try:
                self.fh.close()
            except Exception:
                pass
            self.fh = None
        return False


def _atomic_write(path: Path, data: Any, indent: int) -> None:
    """Write data to path via temp-file + os.replace. Caller must hold the
    exclusive lock on path's sidecar for cross-process safety.

    On Windows, os.replace can sporadically fail with WinError 5 / 32 when
    the target file is briefly held open by the OS itself (indexing,
    antivirus). We retry a handful of times with exponential backoff — the
    lock still guarantees single-writer semantics so retry is safe."""
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
            json.dump(data, tmp, indent=indent, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())

        # Windows: retry os.replace on transient PermissionError (AV, indexer)
        for attempt in range(8):
            try:
                os.replace(tmp_path, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.02 * (2 ** attempt))  # 20ms → 40 → 80 → ... → ~2.5s total
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read a JSON file under a shared sidecar lock. Returns `default` if
    the file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return default
    with _FileLock(p, exclusive=False):
        with p.open("r", encoding="utf-8") as fh:
            raw = fh.read()
    if not raw.strip():
        return default
    return json.loads(raw)


def write_json(
    path: str | Path,
    data: Any,
    *,
    indent: int = 2,
    schema_version: Optional[int] = None,
) -> None:
    """Write a JSON file atomically under an exclusive sidecar lock."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if schema_version is not None and isinstance(data, dict):
        data = {**data, "_schema_version": schema_version}
    with _FileLock(p, exclusive=True):
        _atomic_write(p, data, indent)


def mutate_json(
    path: str | Path,
    mutator: Callable[[Any], Any],
    *,
    default: Any = None,
    indent: int = 2,
    schema_version: Optional[int] = None,
) -> Any:
    """Read-modify-write under a single exclusive lock.

    `mutator` is called with the parsed JSON (or `default` if the file is
    missing/empty) and must return the new object to persist. Returns the
    new value."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(p, exclusive=True):
        if p.exists():
            raw = p.read_text(encoding="utf-8")
            current = json.loads(raw) if raw.strip() else default
        else:
            current = default
        new = mutator(current)
        if schema_version is not None and isinstance(new, dict):
            new = {**new, "_schema_version": schema_version}
        _atomic_write(p, new, indent)
        return new


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="Write+read a dummy file in TEMP and print the result")
    args = ap.parse_args()

    if args.smoke:
        test = Path(tempfile.gettempdir()) / "safe_json_smoke.json"
        write_json(test, {"a": 1, "b": [1, 2, 3]}, schema_version=1)
        loaded = read_json(test)
        print(f"wrote+read: {loaded}")
        new = mutate_json(test, lambda d: {**d, "c": "added"})
        print(f"mutated:    {new}")
        test.unlink()
        print("OK")
