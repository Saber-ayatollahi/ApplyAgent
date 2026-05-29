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
            # CREATE_NO_WINDOW (not DETACHED_PROCESS): we want the child to
            # have no visible console, but still have a valid (hidden) one
            # so its stdio works. DETACHED_PROCESS strips the console
            # entirely, which on some Win11 configs flashes an empty
            # terminal and can confuse children that expect stdio handles.
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
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


def _process_returncode(pid: int) -> Optional[int]:
    """Return the exit code of `pid` if it has exited, else None.

    The detach pattern in start_run() means we can't proc.wait() — the OS
    cleans up the parent handle. Re-open the process by PID and read the
    exit code directly. Windows: GetExitCodeProcess. POSIX: not generally
    possible without ptrace; we fall back to the log-grep heuristic there.
    """
    if pid <= 0:
        return None
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return None
            try:
                code = wintypes.DWORD()
                ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                if not ok:
                    return None
                rc = int(code.value)
                # If still active OR the slot was recycled, treat as unknown.
                # _pid_alive() should have already returned True in that case.
                if rc == STILL_ACTIVE:
                    return None
                return rc
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            return None
    return None


def refresh_state(rec_path: Path) -> dict:
    """Read a run record; if it claims 'running' but the PID is dead, mark finished/failed.

    State detection priority:
      1. Recorded `returncode` from the OS (authoritative when available).
      2. Log-tail markers (legacy fallback for cases where we can't read
         the returncode — different Windows API failure, POSIX, etc).

    Previously this used ONLY the log-tail check, which falsely flagged
    gmail_fetch + jd_scraper runs as 'failed' because their final log line
    doesn't contain the magic strings the pipeline driver emits.
    """
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    if rec.get("state") == "running" and not _pid_alive(rec.get("pid", 0)):
        rc = _process_returncode(rec.get("pid", 0))
        if rc is not None:
            rec["returncode"] = rc
            rec["state"] = "finished" if rc == 0 else "failed"
        else:
            # Fallback when the OS returncode is unreadable (POSIX, or a
            # different Windows API failure). Default to finished; only call
            # it a crash if the log tail carries an obvious failure signal.
            # The older 'failed unless a hardcoded success marker matches'
            # default falsely flagged every short script (gmail_fetch, etc.).
            log_path = rec.get("log_path", "")
            crashed = False
            if log_path and Path(log_path).exists():
                try:
                    tail = Path(log_path).read_bytes()[-4096:]
                    if (b"Traceback (most recent call last)" in tail
                            or b"\nFATAL:" in tail
                            or b"\nABORT:" in tail):
                        crashed = True
                except OSError:
                    pass
            rec["state"] = "failed" if crashed else "finished"
        rec["finished_at"] = datetime.now().isoformat(timespec="seconds")
        rec_path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return rec


def list_runs(limit: int = 50) -> list[dict]:
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [refresh_state(p) for p in files[:limit]]


def tail_log(log_path: str, max_bytes: int = 50_000) -> str:
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
