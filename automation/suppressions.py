"""suppressions.py — sector/company mute registry with TTL, audit log, and lock-safe writes."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .safe_json import mutate_json, read_json, write_json, _FileLock
from . import sectors, brand_aliases

ROOT = Path(__file__).resolve().parent.parent
LIVE_PATH = ROOT / "data" / "suppressions.json"
EXAMPLE_PATH = ROOT / "data" / "suppressions.example.json"
EVENTS_PATH = ROOT / "data" / "suppressions_events.jsonl"
HISTORY_PATH = ROOT / "data" / "suppressions_history.json"
PENDING_ARCHIVES_PATH = ROOT / "data" / "suppressions_pending_archives.jsonl"

_EMPTY_LIVE: dict = {"version": 1, "sectors": [], "companies": []}
_EMPTY_HISTORY: dict = {"version": 1, "entries": []}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _today(now: date | None = None) -> date:
    return now if now is not None else date.today()


def _ensure_live_file() -> None:
    """Lazy-create live file from example on first read."""
    if LIVE_PATH.exists():
        return
    LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if EXAMPLE_PATH.exists():
        seed = read_json(EXAMPLE_PATH, default=_EMPTY_LIVE)
    else:
        seed = dict(_EMPTY_LIVE)
    write_json(LIVE_PATH, seed)


def _parse_until(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _is_expired(entry: dict, today: date) -> bool:
    u = entry.get("until")
    if not u:
        return False
    try:
        return _parse_until(u) <= today  # type: ignore[operator]
    except Exception:
        return False


def _append_event(record: dict) -> None:
    """Append one JSONL line to events log; caller already holds live-file lock."""
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _make_entry(scope: str, name: str, canonical_key: str,
                until: date | None, reason: str) -> dict:
    return {
        "scope": scope,
        "name": name,
        "canonical_key": canonical_key,
        "until": until.isoformat() if until else None,
        "reason": reason,
        "added_at": _now_iso(),
        "version": 1,
    }


def _prune_expired(state: dict, today: date) -> tuple[dict, list[dict]]:
    """Return (live_state_minus_expired, expired_entries)."""
    expired: list[dict] = []
    for scope_key in ("sectors", "companies"):
        kept: list[dict] = []
        for e in state.get(scope_key, []) or []:
            if _is_expired(e, today):
                expired.append({**e, "lifted_at": _now_iso(), "lift_kind": "expired"})
            else:
                kept.append(e)
        state[scope_key] = kept
    return state, expired


def _archive_to_history(expired: list[dict]) -> None:
    if not expired:
        return

    def _mut(h):
        h = h or dict(_EMPTY_HISTORY)
        if "entries" not in h:
            h["entries"] = []
        h["entries"].extend(expired)
        return h

    mutate_json(HISTORY_PATH, _mut, default=dict(_EMPTY_HISTORY))


def load_active(now: date | None = None) -> dict:
    """Return live state with expired entries filtered out; lazy-prune on read."""
    _ensure_live_file()
    today = _today(now)
    expired_holder: list[dict] = []

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("version", 1)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        new_state, expired = _prune_expired(state, today)
        expired_holder.extend(expired)
        return new_state

    pruned = mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))
    if expired_holder:
        _archive_to_history(expired_holder)
    return pruned


def load_recently_expired(window_days: int = 7,
                          now: date | None = None) -> list[dict]:
    """Entries that lapsed within `window_days` from history + still-live-but-expired."""
    today = _today(now)
    cutoff = today - timedelta(days=window_days)
    out: list[dict] = []

    history = read_json(HISTORY_PATH, default=dict(_EMPTY_HISTORY)) or dict(_EMPTY_HISTORY)
    for e in history.get("entries", []) or []:
        u = _parse_until(e.get("until"))
        if u is not None and cutoff <= u <= today:
            out.append(e)

    if LIVE_PATH.exists():
        live = read_json(LIVE_PATH, default=dict(_EMPTY_LIVE)) or dict(_EMPTY_LIVE)
        for scope_key in ("sectors", "companies"):
            for e in live.get(scope_key, []) or []:
                u = _parse_until(e.get("until"))
                if u is not None and cutoff <= u <= today:
                    out.append(e)
    return out


def load_all() -> dict:
    """Active + expired (history snapshot) for admin views."""
    active = load_active()
    history = read_json(HISTORY_PATH, default=dict(_EMPTY_HISTORY)) or dict(_EMPTY_HISTORY)
    return {"active": active, "expired": history.get("entries", []) or []}


def _add(scope: str, name: str, canonical_key: str,
         until: date | None, reason: str) -> None:
    _ensure_live_file()
    scope_key = "sectors" if scope == "sector" else "companies"
    new_entry = _make_entry(scope, name, canonical_key, until, reason)
    old_holder: list[Optional[dict]] = [None]

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("version", 1)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        kept: list[dict] = []
        for e in state.get(scope_key, []) or []:
            if e.get("canonical_key") == canonical_key:
                old_holder[0] = e
            else:
                kept.append(e)
        kept.append(new_entry)
        state[scope_key] = kept
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))
    _append_event({
        "ts": _now_iso(),
        "action": "add",
        "scope": scope,
        "name": name,
        "canonical_key": canonical_key,
        "old": old_holder[0],
        "new": new_entry,
        "actor": "ui",
    })


def add_sector(name: str, until: date | None, reason: str) -> None:
    """Add or replace a sector mute. Validates name via sectors registry."""
    canon = sectors.canonical(name)
    if canon is None:
        raise ValueError(f"unknown sector: {name!r}")
    _add("sector", canon, canon.lower(), until, reason)


def add_company(name: str, until: date | None, reason: str) -> None:
    """Add or replace a company mute. Canonical key via brand_aliases."""
    if not name or not name.strip():
        raise ValueError("company name required")
    canon = brand_aliases.canonical_brand(name).lower()
    if not canon:
        raise ValueError(f"could not canonicalize company: {name!r}")
    _add("company", name.strip(), canon, until, reason)


def _resolve_canonical_key(scope: str, name: str) -> str | None:
    if scope == "sector":
        c = sectors.canonical(name)
        return c.lower() if c else None
    if scope == "company":
        c = brand_aliases.canonical_brand(name)
        return c.lower() if c else None
    return None


def lift(scope: str, name: str) -> None:
    """Remove entry, archive to history with lifted_at; no-op if absent (logged)."""
    _ensure_live_file()
    scope_key = "sectors" if scope == "sector" else "companies"
    canon = _resolve_canonical_key(scope, name)
    removed_holder: list[Optional[dict]] = [None]

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        kept: list[dict] = []
        for e in state.get(scope_key, []) or []:
            if canon is not None and e.get("canonical_key") == canon:
                removed_holder[0] = e
            else:
                kept.append(e)
        state[scope_key] = kept
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))

    if removed_holder[0] is not None:
        archived = {**removed_holder[0], "lifted_at": _now_iso(), "lift_kind": "manual"}
        _archive_to_history([archived])
        _append_event({
            "ts": _now_iso(),
            "action": "lift",
            "scope": scope,
            "name": removed_holder[0].get("name", name),
            "canonical_key": removed_holder[0].get("canonical_key", canon or ""),
            "old": removed_holder[0],
            "new": None,
            "actor": "ui",
        })
    else:
        _append_event({
            "ts": _now_iso(),
            "action": "lift_noop",
            "scope": scope,
            "name": name,
            "canonical_key": canon or "",
            "old": None,
            "new": None,
            "actor": "ui",
        })


def extend(scope: str, name: str, days: int) -> None:
    """Push entry's until field by `days`. Raises if not found."""
    _ensure_live_file()
    scope_key = "sectors" if scope == "sector" else "companies"
    canon = _resolve_canonical_key(scope, name)
    old_holder: list[Optional[dict]] = [None]
    new_holder: list[Optional[dict]] = [None]

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        for e in state.get(scope_key, []) or []:
            if canon is not None and e.get("canonical_key") == canon:
                old_holder[0] = dict(e)
                base = _parse_until(e.get("until")) or date.today()
                e["until"] = (base + timedelta(days=days)).isoformat()
                new_holder[0] = dict(e)
                break
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))
    if old_holder[0] is None:
        raise ValueError(f"no {scope} suppression for {name!r}")
    _append_event({
        "ts": _now_iso(),
        "action": "extend",
        "scope": scope,
        "name": old_holder[0].get("name", name),
        "canonical_key": canon or "",
        "old": old_holder[0],
        "new": new_holder[0],
        "actor": "ui",
    })


def edit_reason(scope: str, name: str, new_reason: str) -> None:
    """Update reason in place. Old reason captured in events log."""
    _ensure_live_file()
    scope_key = "sectors" if scope == "sector" else "companies"
    canon = _resolve_canonical_key(scope, name)
    old_holder: list[Optional[dict]] = [None]
    new_holder: list[Optional[dict]] = [None]

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        for e in state.get(scope_key, []) or []:
            if canon is not None and e.get("canonical_key") == canon:
                old_holder[0] = dict(e)
                e["reason"] = new_reason
                new_holder[0] = dict(e)
                break
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))
    if old_holder[0] is None:
        raise ValueError(f"no {scope} suppression for {name!r}")
    _append_event({
        "ts": _now_iso(),
        "action": "edit_reason",
        "scope": scope,
        "name": old_holder[0].get("name", name),
        "canonical_key": canon or "",
        "old": old_holder[0],
        "new": new_holder[0],
        "actor": "ui",
    })


def is_suppressed(row: dict,
                  snapshot: dict | None = None) -> tuple[bool, str | None]:
    """Return (suppressed, drop_reason). drop_reason is 'suppressed_<scope>_<N>d'."""
    state = snapshot if snapshot is not None else load_active()
    today = date.today()

    company_raw = (row.get("company") or "").strip()
    if company_raw:
        company_key = brand_aliases.canonical_brand(company_raw).lower()
        if company_key:
            for e in state.get("companies", []) or []:
                if e.get("canonical_key") == company_key:
                    days = _days_left(e, today)
                    return True, f"suppressed_company_{days}d"

    sector_raw = (row.get("sector") or "").strip()
    if sector_raw:
        sector_canon = sectors.canonical(sector_raw)
        if sector_canon is not None:
            sector_key = sector_canon.lower()
            for e in state.get("sectors", []) or []:
                if e.get("canonical_key") == sector_key:
                    days = _days_left(e, today)
                    return True, f"suppressed_sector_{days}d"

    return False, None


def _days_left(entry: dict, today: date) -> int:
    u = _parse_until(entry.get("until"))
    if u is None:
        return 9999
    delta = (u - today).days
    return max(0, delta)


def snapshot_to(path: Path) -> Path:
    """Write load_active() to `path` for run-time consistency."""
    state = load_active()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, state)
    return p


def coverage(scope: str, name: str, rows: list[dict]) -> dict:
    """Return {matched, total, unsectored} for the given mute against rows."""
    matched = 0
    total = 0
    unsectored = 0
    if scope == "sector":
        target = sectors.canonical(name)
        target_key = target.lower() if target else None
        for r in rows:
            sec = (r.get("sector") or "").strip()
            if not sec:
                unsectored += 1
                continue
            sec_canon = sectors.canonical(sec)
            if sec_canon is None:
                continue
            if sec_canon.lower() == target_key:
                matched += 1
                total += 1
            else:
                total += 1
    elif scope == "company":
        target_key = brand_aliases.canonical_brand(name).lower()
        for r in rows:
            comp = (r.get("company") or "").strip()
            if not comp:
                continue
            comp_key = brand_aliases.canonical_brand(comp).lower()
            if not comp_key:
                continue
            total += 1
            if comp_key == target_key:
                matched += 1
    return {"matched": matched, "total": total, "unsectored": unsectored}


def queue_pending_archive(job_id: str, reason: str) -> None:
    """Append one line to the partial-failure recovery queue."""
    PENDING_ARCHIVES_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": _now_iso(), "job_id": job_id, "reason": reason, "attempts": 0}
    with PENDING_ARCHIVES_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def drain_pending_archives() -> list[dict]:
    """Read and clear PENDING_ARCHIVES_PATH; return entries."""
    if not PENDING_ARCHIVES_PATH.exists():
        return []
    with _FileLock(PENDING_ARCHIVES_PATH, exclusive=True):
        try:
            raw = PENDING_ARCHIVES_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        entries: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        # Truncate atomically by writing empty
        PENDING_ARCHIVES_PATH.write_text("", encoding="utf-8")
    return entries


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if not args.smoke:
        ap.print_help()
        sys.exit(0)

    # Redirect all paths into a temp dir so smoke leaves real data/ untouched.
    tmp = Path(tempfile.mkdtemp(prefix="suppr_smoke_"))
    LIVE_PATH = tmp / "suppressions.json"  # type: ignore[misc]
    EXAMPLE_PATH = tmp / "suppressions.example.json"  # type: ignore[misc]
    EVENTS_PATH = tmp / "suppressions_events.jsonl"  # type: ignore[misc]
    HISTORY_PATH = tmp / "suppressions_history.json"  # type: ignore[misc]
    PENDING_ARCHIVES_PATH = tmp / "suppressions_pending_archives.jsonl"  # type: ignore[misc]
    # Re-bind the module globals so internal calls hit the temp paths.
    import automation.suppressions as _self
    _self.LIVE_PATH = LIVE_PATH
    _self.EXAMPLE_PATH = EXAMPLE_PATH
    _self.EVENTS_PATH = EVENTS_PATH
    _self.HISTORY_PATH = HISTORY_PATH
    _self.PENDING_ARCHIVES_PATH = PENDING_ARCHIVES_PATH
    EXAMPLE_PATH.write_text(json.dumps(_EMPTY_LIVE, indent=2), encoding="utf-8")

    add_sector("Canadian Big 6 Banks", date.today() + timedelta(days=60), "smoke test")
    lift("sector", "Canadian Big 6 Banks")

    print("events:")
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        print("  " + line)

    shutil.rmtree(tmp, ignore_errors=True)
    print("OK")
