"""cost_ledger.py -- Lifetime token + cost ledger.

Persistent, append-only across sessions. Every successful LLM call from
fit_scorer, jd_tailor, or score_url appends tokens + estimated cost here.
The file is never reset; the UI reads it for an always-on "total spend"
sidebar widget and for the detailed ledger page.

Design notes:
  - One JSON file at data/lifetime_cost.json (not the tracker; this is our
    own ledger).
  - Atomic writes via os.replace() so a crash mid-write never corrupts the
    running totals (same pattern as jd_scraper's url_history writer).
  - Lock-guarded so concurrent scorer threads don't race.
  - Per-model breakdown, totals, rolling 30-day counters.

Schema (v1):
    {
      "schema_version": 1,
      "created_at": "ISO",
      "updated_at": "ISO",
      "totals": {
        "llm_calls": int,
        "cache_hits": int,
        "input_tokens": int,
        "output_tokens": int,
        "cache_create_tokens": int,
        "cache_read_tokens": int,
        "estimated_cost_usd": float
      },
      "per_model": {
        "<model-id>": {
          "calls": int, "in_tokens": int, "out_tokens": int, "cost_usd": float,
          "first_used": ISO, "last_used": ISO
        }
      },
      "daily": {
        "YYYY-MM-DD": {
          "calls": int, "in_tokens": int, "out_tokens": int, "cost_usd": float
        }
      }
    }

The daily breakdown lets the UI show a small sparkline / 30-day strip
without parsing a separate log. Daily entries accumulate forever but the
UI only renders the last 30 days by default.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path

# Cross-process lock + atomic writes. If safe_json isn't importable (e.g.
# cost_ledger invoked standalone in a stripped-down env), we fall back to
# the legacy in-process-only behavior with a warning.
try:
    from safe_json import mutate_json as _sj_mutate, read_json as _sj_read  # type: ignore
    _USE_SAFE_JSON = True
except ImportError:
    try:
        from .safe_json import mutate_json as _sj_mutate, read_json as _sj_read  # type: ignore
        _USE_SAFE_JSON = True
    except Exception:
        _sj_mutate = None  # type: ignore
        _sj_read = None  # type: ignore
        _USE_SAFE_JSON = False

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "data" / "lifetime_cost.json"

_write_lock = threading.Lock()

SCHEMA_VERSION = 1


def _empty_ledger() -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "totals": {
            "llm_calls": 0,
            "cache_hits": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_create_tokens": 0,
            "cache_read_tokens": 0,
            "estimated_cost_usd": 0.0,
        },
        "per_model": {},
        "daily": {},
    }


def _load() -> dict:
    """Read the ledger; return an empty one if missing/corrupt.

    We intentionally DON'T try to repair a corrupt file -- a corrupt file
    is an alarm. If it happens, the user sees a surprise reset in the UI
    and can check data/lifetime_cost.json.bak (written before any repair).
    """
    if not LEDGER_PATH.exists():
        return _empty_ledger()
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        # Defensive: ensure shape. Missing keys can happen if we later add fields.
        base = _empty_ledger()
        for k, v in base.items():
            data.setdefault(k, v)
        for k, v in base["totals"].items():
            data["totals"].setdefault(k, v)
        return data
    except Exception as e:
        # Keep the bad file around for forensic reasons, then start fresh.
        # A corrupt ledger is a loud alarm — log it so the user sees the
        # cost-panel surprise-reset has a cause, not a ghost.
        try:
            from error_log import log_error  # type: ignore
            log_error("ledger_corrupt", e, module="cost_ledger",
                      extra={"path": str(LEDGER_PATH)})
        except Exception:
            pass
        try:
            bak = LEDGER_PATH.with_suffix(".corrupt.json")
            LEDGER_PATH.rename(bak)
        except Exception:
            pass
        return _empty_ledger()


def _atomic_write(data: dict):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(LEDGER_PATH.parent),
        prefix=".lifetime_cost.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, LEDGER_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record(
    model: str,
    in_tokens: int,
    out_tokens: int,
    cost_usd: float,
    cache_create: int = 0,
    cache_read: int = 0,
    cache_hit: bool = False,
):
    """Append one LLM call (or cache hit) to the lifetime ledger.

    Call this from inside fit_scorer._cost_tick (and anywhere else we make
    a paid LLM call) -- kept cheap so it never blocks scoring. A cache hit
    records no tokens but increments the counter for observability.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = date.today().isoformat()

    def _mutator(data):
        # `data` is None the first time the ledger is written; seed it from
        # _empty_ledger() so we don't crash on the first call.
        if not isinstance(data, dict) or "totals" not in data:
            data = _empty_ledger()
        # Defensive: if the user added new keys since last write, fill them.
        base = _empty_ledger()
        for k, v in base.items():
            data.setdefault(k, v)
        for k, v in base["totals"].items():
            data["totals"].setdefault(k, v)

        if cache_hit:
            data["totals"]["cache_hits"] += 1
        else:
            t = data["totals"]
            t["llm_calls"] += 1
            t["input_tokens"] += int(in_tokens or 0)
            t["output_tokens"] += int(out_tokens or 0)
            t["cache_create_tokens"] += int(cache_create or 0)
            t["cache_read_tokens"] += int(cache_read or 0)
            t["estimated_cost_usd"] = round(
                t["estimated_cost_usd"] + float(cost_usd or 0.0), 6
            )

            mkey = model or "?"
            m = data["per_model"].setdefault(mkey, {
                "calls": 0, "in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0,
                "first_used": now_iso, "last_used": now_iso,
            })
            m["calls"] += 1
            m["in_tokens"] += int(in_tokens or 0)
            m["out_tokens"] += int(out_tokens or 0)
            m["cost_usd"] = round(m["cost_usd"] + float(cost_usd or 0.0), 6)
            m["last_used"] = now_iso

            d = data["daily"].setdefault(today, {
                "calls": 0, "in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0,
            })
            d["calls"] += 1
            d["in_tokens"] += int(in_tokens or 0)
            d["out_tokens"] += int(out_tokens or 0)
            d["cost_usd"] = round(d["cost_usd"] + float(cost_usd or 0.0), 6)

        data["updated_at"] = now_iso
        return data

    try:
        if _USE_SAFE_JSON:
            # Cross-process safe — the in-process lock is redundant but cheap
            # and avoids threading-level contention within the same PID.
            with _write_lock:
                _sj_mutate(LEDGER_PATH, _mutator, default=_empty_ledger())
        else:
            # Legacy path. Still protect against in-process races.
            with _write_lock:
                data = _load()
                data = _mutator(data)
                _atomic_write(data)
    except Exception as e:
        # Never let ledger writes crash the caller. Session-level telemetry
        # in fit_scorer is still captured separately.
        print(f"[cost_ledger] record() swallowed exception: {e}", file=sys.stderr)


def load() -> dict:
    """Read the ledger (public, read-only). UI should prefer this over
    poking LEDGER_PATH directly."""
    return _load()


def reset(confirm: str = "") -> bool:
    """Reset the ledger. Requires confirm='YES I REALLY MEAN IT'.

    The whole point of the ledger is that it never resets; this exists only
    for developer cleanup / legal purge / moving machines. The UI must NOT
    expose a one-click reset button."""
    if confirm != "YES I REALLY MEAN IT":
        return False
    with _write_lock:
        if LEDGER_PATH.exists():
            bak = LEDGER_PATH.with_name(
                f"lifetime_cost.reset-backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            LEDGER_PATH.rename(bak)
        _atomic_write(_empty_ledger())
        return True
