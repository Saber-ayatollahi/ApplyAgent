#!/usr/bin/env python3
"""
error_log.py — Central error log at logs/errors.jsonl.

Replace `except Exception: pass` with `log_error(context, e)` so bugs that
used to silently degrade features (cached files never writing, scrapers
dropping companies, progress updates vanishing) surface in one searchable
place.

One JSONL record per error:
    {
      "timestamp": "2026-05-06T18:23:00Z",
      "module": "fit_scorer",
      "context": "progress_write",
      "error_type": "PermissionError",
      "message": "[Errno 13] Permission denied: 'outputs/fit_scorer_progress.json'",
      "traceback": "...up to 2000 chars..."
    }

Usage:
    from error_log import log_error

    try:
        something_that_might_fail()
    except Exception as e:
        log_error("context_tag", e, module="fit_scorer")
        # return a safe default, keep the app running

Rotation: the log append-only. When size exceeds MAX_SIZE_BYTES, we
rename it to errors.<YYYYMMDD>.jsonl and start a fresh file. Keeps the
latest file small enough to tail; old files stay for forensics.

Reading for UI: `recent_errors(limit=50)` returns the most recent N
entries as dicts, newest first. The UI uses this for a sidebar badge +
drill-down page.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "errors.jsonl"
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_TRACEBACK_CHARS = 2000

_write_lock = Lock()

# Secret patterns to scrub from messages and tracebacks before writing them
# to disk. Anthropic SDK 401 responses include the offending key; HTTP libs
# may include Authorization headers in retry messages. Order matters — the
# explicit-prefix patterns run before the env-key fallback so we don't
# double-redact.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "sk-ant-***REDACTED***"),
    (re.compile(r"sk-proj-[A-Za-z0-9_\-]{8,}"), "sk-proj-***REDACTED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)['\"]?[^\s'\"]+"),
     r"\1***REDACTED***"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)['\"]?[A-Za-z0-9._\-]{8,}"),
     r"\1***REDACTED***"),
)
# Env vars whose VALUES we should also scrub if they happen to appear
# verbatim in a message — catches custom keys we don't pattern-match above.
_SECRET_ENV_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GMAIL_APP_PASSWORD")


def _scrub(text: str) -> str:
    """Redact known secret shapes from a string before persisting it."""
    if not text:
        return text
    out = text
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    for var in _SECRET_ENV_VARS:
        val = os.environ.get(var)
        if val and len(val) >= 8 and val in out:
            out = out.replace(val, f"***{var}_REDACTED***")
    return out


def _rotate_if_needed() -> None:
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_SIZE_BYTES:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            LOG_PATH.rename(LOG_DIR / f"errors.{stamp}.jsonl")
    except Exception:
        # Rotation is best-effort; never block the caller over it.
        pass


def log_error(
    context: str,
    exc: BaseException,
    *,
    module: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Append one error record. Safe to call from any thread; writes are
    line-buffered + flushed, so a crash immediately after the call still
    persists the record."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        tb = ""
        try:
            tb = "".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__
            ))[:MAX_TRACEBACK_CHARS]
        except Exception:
            pass

        record = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "module": module or "?",
            "context": context,
            "error_type": type(exc).__name__,
            "message": _scrub(str(exc)[:500]),
            "traceback": _scrub(tb),
        }
        if extra:
            # Don't override our fixed fields. Scrub string values too — extra
            # often carries request bodies or response payloads that may
            # contain secrets.
            for k, v in extra.items():
                if k in record:
                    continue
                record[k] = _scrub(v) if isinstance(v, str) else v

        line = json.dumps(record, ensure_ascii=False)
        with _write_lock:
            _rotate_if_needed()
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
    except Exception as e:
        # Last-resort: if even the error-log fails, at least stderr it so
        # the developer sees something. Never raise from log_error.
        try:
            print(f"[error_log] log_error failed: {e}", file=sys.stderr)
        except Exception:
            pass


def recent_errors(limit: int = 50) -> list[dict]:
    """Return the most recent N error records, newest first. Reads only the
    current (post-rotation) errors.jsonl; older rotated files are not
    scanned (use the filesystem directly for that)."""
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict] = []
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


def count_recent(since_minutes: int = 60) -> int:
    """Count errors in the last `since_minutes` — useful for a UI badge."""
    if not LOG_PATH.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - since_minutes * 60
    n = 0
    try:
        for ln in LOG_PATH.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
                ts = rec.get("timestamp", "")
                # Parse ISO-Z timestamp
                dt = datetime.strptime(ts.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
                if dt.timestamp() >= cutoff:
                    n += 1
            except Exception:
                continue
    except Exception:
        pass
    return n


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--recent", type=int, default=0,
                    help="Print the most recent N error records")
    ap.add_argument("--count-recent", type=int, default=0,
                    help="Count errors in the last N minutes")
    args = ap.parse_args()

    if args.smoke:
        try:
            raise ValueError("smoke test — ignore this record")
        except Exception as e:
            log_error("smoke_test", e, module="error_log", extra={"tag": "ok"})
        recs = recent_errors(limit=1)
        print(json.dumps(recs, indent=2))

    if args.recent:
        recs = recent_errors(limit=args.recent)
        for r in recs:
            print(f"{r['timestamp']}  {r['module']:16s}  {r['context']:24s}  "
                  f"{r['error_type']}: {r['message'][:80]}")

    if args.count_recent:
        n = count_recent(since_minutes=args.count_recent)
        print(f"{n} errors in last {args.count_recent} minutes")
