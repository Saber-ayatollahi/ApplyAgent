#!/usr/bin/env python3
"""load_env.py — Tiny .env loader for ApplyAgent.

Reads `.env` at the repo root and exports each KEY=VALUE pair into the
current process's environment. Skips comments and blank lines. Strips
matching surrounding quotes from values.

Used two ways:
  1. As a CLI: `python automation/load_env.py` validates the file and
     prints what would be loaded (with values redacted).
  2. As a library: `from load_env import load_env; load_env()` from any
     entrypoint that wants to pick up `.env` automatically.

Why not python-dotenv? It's a 200KB transitive dep for what is 15 lines
of code. Keeping the install footprint small.

Security: `.env` is in `.gitignore` (line 79). NEVER commit a populated
`.env`. The `.env.example` template is safe to commit (placeholder values).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = ROOT / ".env"


def load_env(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Parse a .env file and inject into os.environ.

    Returns the dict of variables that were loaded (for logging/debugging).
    `override=False` (default) means existing env vars win — safer for
    production where the env should be authoritative. `override=True` lets
    .env values overwrite, useful in dev when you're iterating on .env.
    """
    p = path or DEFAULT_ENV_PATH
    if not p.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes (single or double).
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def _redact(value: str) -> str:
    """Redact a secret-looking value for display."""
    if not value:
        return ""
    if len(value) <= 12:
        return value[:2] + "…"
    return f"{value[:8]}…{value[-4:]}"


def main() -> int:
    if not DEFAULT_ENV_PATH.exists():
        print(f"[load_env] No .env file at {DEFAULT_ENV_PATH}", file=sys.stderr)
        print(f"[load_env] Copy .env.example to .env and fill in your values.",
              file=sys.stderr)
        return 1
    loaded = load_env(override=True)
    if not loaded:
        print(f"[load_env] {DEFAULT_ENV_PATH} parsed but no variables loaded.",
              file=sys.stderr)
        return 1
    print(f"[load_env] Loaded {len(loaded)} variable(s) from {DEFAULT_ENV_PATH}:",
          file=sys.stderr)
    for k, v in loaded.items():
        print(f"  {k}={_redact(v)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
