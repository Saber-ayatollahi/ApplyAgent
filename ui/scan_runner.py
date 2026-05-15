"""Background scan/agent runner for the Streamlit UI.

Launches long-running automation scripts (jd_scraper, fit_scorer, etc.) as
detached subprocesses so the UI stays responsive. Each run gets:
  - a unique run_id (timestamp-based)
  - a log file under automation/outputs/runs/<run_id>.log
  - a status JSON under automation/outputs/runs/<run_id>.json (pid, args, state)

The UI polls the status JSON and tails the log. On Windows we use
CREATE_NEW_PROCESS_GROUP so the child survives Streamlit reruns.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "automation" / "outputs" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class RunRecord:
    run_id: str
    label: str
    cmd: list[str]
    pid: int
    started_at: str
    log_path: str
    status_path: str
    state: str = "running"      # running | finished | failed | stopped
    finished_at: Optional[str] = None
    returncode: Optional[int] = None

    def save(self):
        Path(self.status_path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _new_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def start_run(label: str, cmd: list[str], cwd: Optional[Path] = None) -> RunRecord:
    """Launch `cmd` in the background, return a RunRecord (already persisted)."""
    run_id = _new_run_id(label.replace(" ", "_").lower())
    log_path = RUNS_DIR / f"{run_id}.log"
    status_path = RUNS_DIR / f"{run_id}.json"

    log_f = open(log_path, "wb")
    try:
        log_f.write(f"# {label}\n# cmd: {' '.join(cmd)}\n# started: {datetime.now().isoformat()}\n\n".encode())
        log_f.flush()

        kwargs = dict(
            stdout=log_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=str(cwd or ROOT),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd, **kwargs)
    finally:
        # Subprocess.Popen has duplicated the fd into the child; the parent's
        # handle is now redundant. Without this close, Streamlit (long-lived
        # parent) leaks one fd per launch — eventually OS-limit out.
        try:
            log_f.close()
        except Exception:
            pass

    rec = RunRecord(
        run_id=run_id,
        label=label,
        cmd=cmd,
        pid=proc.pid,
        started_at=datetime.now().isoformat(timespec="seconds"),
        log_path=str(log_path),
        status_path=str(status_path),
    )
    rec.save()
    return rec


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            # GetExitCodeProcess returning STILL_ACTIVE (259) is unreliable —
            # 259 is also a perfectly legal exit code, so a real exited
            # process that happened to return 259 reads as "alive" forever.
            # WaitForSingleObject(handle, 0) returns WAIT_TIMEOUT (258) when
            # the process is still running, and WAIT_OBJECT_0 (0) once it's
            # signaled (exited). That's an unambiguous answer.
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
            if not h:
                return False
            try:
                WAIT_TIMEOUT = 0x00000102
                rc = ctypes.windll.kernel32.WaitForSingleObject(h, 0)
                return rc == WAIT_TIMEOUT
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def refresh_state(rec_path: Path) -> dict:
    """Read a run record; if it claims 'running' but the PID is dead, mark finished."""
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    if rec.get("state") == "running" and not _pid_alive(rec.get("pid", 0)):
        rec["state"] = "finished"
        rec["finished_at"] = datetime.now().isoformat(timespec="seconds")
        rec_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def list_runs(limit: int = 50) -> list[dict]:
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [refresh_state(p) for p in files[:limit]]


def tail_log(log_path: str, max_bytes: int = 20_000) -> str:
    p = Path(log_path)
    if not p.exists():
        return ""
    size = p.stat().st_size
    with open(p, "rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            data = b"...[truncated]...\n" + f.read()
        else:
            data = f.read()
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return repr(data)


def stop_run(run_id: str) -> bool:
    status_path = RUNS_DIR / f"{run_id}.json"
    if not status_path.exists():
        return False
    rec = json.loads(status_path.read_text(encoding="utf-8"))
    pid = rec.get("pid", 0)
    if not _pid_alive(pid):
        rec["state"] = "finished"
        status_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        return True
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        return False
    rec["state"] = "stopped"
    rec["finished_at"] = datetime.now().isoformat(timespec="seconds")
    status_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return True


def active_runs() -> list[dict]:
    return [r for r in list_runs(limit=20) if r.get("state") == "running"]
