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

try:  # absolute imports when run as a standalone script (automation/ on sys.path)
    from safe_json import mutate_json, read_json, write_json, _FileLock
    import sectors
    import brand_aliases
except ImportError:  # relative imports when loaded as automation.suppressions
    from .safe_json import mutate_json, read_json, write_json, _FileLock
    from . import sectors, brand_aliases

ROOT = Path(__file__).resolve().parent.parent
LIVE_PATH = ROOT / "data" / "suppressions.json"
EXAMPLE_PATH = ROOT / "data" / "suppressions.example.json"
EVENTS_PATH = ROOT / "data" / "suppressions_events.jsonl"
HISTORY_PATH = ROOT / "data" / "suppressions_history.json"
PENDING_ARCHIVES_PATH = ROOT / "data" / "suppressions_pending_archives.jsonl"

_EMPTY_LIVE: dict = {"version": 1, "sectors": [], "companies": [], "geos": []}
_SCOPE_KEY = {"sector": "sectors", "company": "companies", "geo": "geos"}
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
    except (ValueError, TypeError):
        # Fail-closed: malformed `until` is treated as expired so the registry
        # self-cleans on next read instead of silently keeping a stale mute alive.
        return True


def _append_event(record: dict) -> None:
    """Append one JSONL line to the events log.

    MUST be called while holding the live-file lock so the events log's order
    matches the live-file commit order. The audit trail and the rebuild
    contract both depend on this — a mismatch makes "rebuild from events"
    diverge from live state. Two writers releasing the live-file lock and
    then racing to append events would scramble the order.

    Concretely: every call site invokes this from INSIDE the `_mut` closure
    passed to `mutate_json` on LIVE_PATH, before the closure returns."""
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
    for scope_key in ("sectors", "companies", "geos"):
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
        for scope_key in ("sectors", "companies", "geos"):
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
    scope_key = _SCOPE_KEY.get(scope, "sectors")
    new_entry = _make_entry(scope, name, canonical_key, until, reason)

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("version", 1)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        kept: list[dict] = []
        old_entry: Optional[dict] = None
        for e in state.get(scope_key, []) or []:
            if e.get("canonical_key") == canonical_key:
                old_entry = e
            else:
                kept.append(e)
        kept.append(new_entry)
        state[scope_key] = kept
        # Append event INSIDE the live-file lock so events ordering matches
        # commit ordering. Two writers releasing the live-lock then racing
        # on the events file would otherwise scramble the audit trail.
        _append_event({
            "ts": _now_iso(),
            "action": "add",
            "scope": scope,
            "name": name,
            "canonical_key": canonical_key,
            "old": old_entry,
            "new": new_entry,
            "actor": "ui",
        })
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))


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


def add_geo(name: str, until: date | None, reason: str) -> None:
    """Add or replace a geo-bucket mute (e.g. US on-site (TN)). Matched
    case-insensitively against the geo tag on each row, so muting a bucket
    drops every role in it at triage, before any paid scoring."""
    n = (name or "").strip()
    if not n:
        raise ValueError("geo name required")
    _add("geo", n, n.lower(), until, reason)


def _resolve_canonical_key(scope: str, name: str) -> str | None:
    if scope == "sector":
        c = sectors.canonical(name)
        return c.lower() if c else None
    if scope == "company":
        c = brand_aliases.canonical_brand(name)
        return c.lower() if c else None
    if scope == "geo":
        n = (name or "").strip().lower()
        return n or None
    return None


def lift(scope: str, name: str) -> None:
    """Remove entry, archive to history with lifted_at; no-op if absent (logged)."""
    _ensure_live_file()
    scope_key = _SCOPE_KEY.get(scope, "sectors")
    canon = _resolve_canonical_key(scope, name)
    removed_holder: list[Optional[dict]] = [None]

    def _mut(state):
        state = state or dict(_EMPTY_LIVE)
        state.setdefault("sectors", [])
        state.setdefault("companies", [])
        kept: list[dict] = []
        removed: Optional[dict] = None
        for e in state.get(scope_key, []) or []:
            if canon is not None and e.get("canonical_key") == canon:
                removed = e
            else:
                kept.append(e)
        state[scope_key] = kept
        # Event written under the live-file lock to keep audit-trail order
        # consistent with commit order; history archive runs after the lock
        # because it touches a separate file (HISTORY_PATH).
        if removed is not None:
            _append_event({
                "ts": _now_iso(),
                "action": "lift",
                "scope": scope,
                "name": removed.get("name", name),
                "canonical_key": removed.get("canonical_key", canon or ""),
                "old": removed,
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
        removed_holder[0] = removed
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))

    if removed_holder[0] is not None:
        archived = {**removed_holder[0], "lifted_at": _now_iso(), "lift_kind": "manual"}
        _archive_to_history([archived])


def extend(scope: str, name: str, days: int) -> None:
    """Push entry's until field by `days`. Raises if not found."""
    _ensure_live_file()
    scope_key = _SCOPE_KEY.get(scope, "sectors")
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
        if old_holder[0] is not None:
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
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))
    if old_holder[0] is None:
        raise ValueError(f"no {scope} suppression for {name!r}")


def edit_reason(scope: str, name: str, new_reason: str) -> None:
    """Update reason in place. Old reason captured in events log."""
    _ensure_live_file()
    scope_key = _SCOPE_KEY.get(scope, "sectors")
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
        if old_holder[0] is not None:
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
        return state

    mutate_json(LIVE_PATH, _mut, default=dict(_EMPTY_LIVE))
    if old_holder[0] is None:
        raise ValueError(f"no {scope} suppression for {name!r}")


_geo_for_fn = None
def _geo_for_loc(loc: str) -> str:
    global _geo_for_fn
    if _geo_for_fn is None:
        try:
            from geo_tagger import geo_for as _gf
        except ImportError:
            from .geo_tagger import geo_for as _gf
        _geo_for_fn = _gf
    return _geo_for_fn(loc)


def is_suppressed(row: dict,
                  snapshot: dict | None = None) -> tuple[bool, str | None]:
    """Return (suppressed, drop_reason). drop_reason is 'suppressed_<scope>_<N>d'.

    Hot-path: called once per row in a 1,400-row scoring loop. Fast-paths
    when the snapshot has no entries (the dormant default state). Coerces
    company/sector to str so a malformed row (int, list, dict) doesn't
    crash the whole scoring run."""
    state = snapshot if snapshot is not None else load_active()
    if not state.get("sectors") and not state.get("companies") and not state.get("geos"):
        return False, None
    today = date.today()

    company_raw = str(row.get("company") or "").strip()
    if company_raw:
        company_key = brand_aliases.canonical_brand(company_raw).lower()
        if company_key:
            for e in state.get("companies", []) or []:
                if e.get("canonical_key") == company_key:
                    days = _days_left(e, today)
                    return True, f"suppressed_company_{days}d"

    sector_raw = str(row.get("sector") or "").strip()
    if sector_raw:
        sector_canon = sectors.canonical(sector_raw)
        if sector_canon is not None:
            sector_key = sector_canon.lower()
            for e in state.get("sectors", []) or []:
                if e.get("canonical_key") == sector_key:
                    days = _days_left(e, today)
                    return True, f"suppressed_sector_{days}d"

    geos_state = state.get("geos") or []
    if geos_state:
        geo_val = str(row.get("geo") or "").strip()
        if not geo_val:
            try:
                geo_val = _geo_for_loc(str(row.get("location") or ""))
            except Exception:
                geo_val = ""
        if geo_val:
            gkey = geo_val.lower()
            for e in geos_state:
                if e.get("canonical_key") == gkey:
                    return True, f"suppressed_geo_{_days_left(e, today)}d"

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
            sec = str(r.get("sector") or "").strip()
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
            comp = str(r.get("company") or "").strip()
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
    """Append one line to the partial-failure recovery queue under exclusive lock.

    Concurrent queue+drain races otherwise lose entries: drain reads then
    truncates; an append landing between the read and the truncate disappears.
    Locks mirror drain_pending_archives so the two operations serialize."""
    PENDING_ARCHIVES_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": _now_iso(), "job_id": job_id, "reason": reason, "attempts": 0}
    with _FileLock(PENDING_ARCHIVES_PATH, exclusive=True):
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
# CLI
# ---------------------------------------------------------------------------

def _resolve_until_arg(args) -> date | None:
    """Translate `--days N` / `--until YYYY-MM-DD` / neither into a date|None.

    Returns None for permanent mutes (no expiry). Raises ValueError if both
    are passed (mutually exclusive) or if --until cannot be parsed."""
    days = getattr(args, "days", None)
    until_str = getattr(args, "until", None)
    if days is not None and until_str:
        raise ValueError("--days and --until are mutually exclusive")
    if days is not None:
        if days <= 0:
            raise ValueError("--days must be positive")
        return date.today() + timedelta(days=days)
    if until_str:
        try:
            return date.fromisoformat(until_str)
        except ValueError as e:
            raise ValueError(f"--until must be YYYY-MM-DD: {e}") from e
    return None


def _format_until(entry: dict, today: date) -> str:
    u = entry.get("until")
    if not u:
        return "permanent"
    parsed = _parse_until(u)
    if parsed is None:
        return f"until {u}"
    delta = (parsed - today).days
    return f"until {parsed.isoformat()} ({max(0, delta)}d left)"


def _print_table(entries: list[dict], scope_label: str, today: date) -> None:
    if not entries:
        print(f"  (no active {scope_label} mutes)")
        return
    name_w = max((len(e.get("name") or "") for e in entries), default=4)
    name_w = max(name_w, 4)
    for e in entries:
        name = (e.get("name") or "?").ljust(name_w)
        when = _format_until(e, today)
        reason = e.get("reason") or ""
        print(f"  - {name}  {when}  reason: {reason!r}")


def _cmd_add_sector(args) -> int:
    try:
        until = _resolve_until_arg(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        add_sector(args.name, until, args.reason)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"known sectors: {', '.join(sectors.KNOWN)}", file=sys.stderr)
        return 1
    canon = sectors.canonical(args.name)
    if args.json:
        print(json.dumps({
            "ok": True, "scope": "sector", "name": canon,
            "until": until.isoformat() if until else None,
            "reason": args.reason,
        }))
    else:
        until_str = until.isoformat() if until else "permanent"
        print(f"OK: muted sector {canon!r} until {until_str} — reason: {args.reason!r}")
    return 0


def _cmd_add_company(args) -> int:
    try:
        until = _resolve_until_arg(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        add_company(args.name, until, args.reason)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({
            "ok": True, "scope": "company", "name": args.name.strip(),
            "until": until.isoformat() if until else None,
            "reason": args.reason,
        }))
    else:
        until_str = until.isoformat() if until else "permanent"
        print(f"OK: muted company {args.name.strip()!r} until {until_str} — reason: {args.reason!r}")
    return 0


def _cmd_list(args) -> int:
    today = date.today()
    if args.include_expired:
        bundle = load_all()
        active = bundle["active"]
        expired = bundle["expired"]
    else:
        active = load_active()
        expired = []

    if args.json:
        print(json.dumps({
            "active": active,
            "expired": expired if args.include_expired else None,
        }, indent=2))
        return 0

    sectors_list = active.get("sectors", []) or []
    companies_list = active.get("companies", []) or []

    if args.scope in ("all", "sector"):
        print(f"ACTIVE SECTORS ({len(sectors_list)}):")
        _print_table(sectors_list, "sector", today)
    if args.scope in ("all", "company"):
        print(f"ACTIVE COMPANIES ({len(companies_list)}):")
        _print_table(companies_list, "company", today)
    if args.include_expired:
        print(f"\nEXPIRED ({len(expired)}):")
        if not expired:
            print("  (none in history)")
        else:
            for e in expired[-20:]:
                lifted = e.get("lifted_at", "?")
                kind = e.get("lift_kind", "?")
                print(f"  - {e.get('scope','?')}/{e.get('name','?')}  lifted_at={lifted}  ({kind})")
    return 0


def _cmd_lift(args) -> int:
    if args.scope not in ("sector", "company"):
        print(f"error: scope must be 'sector' or 'company' (got {args.scope!r})", file=sys.stderr)
        return 1
    # Probe before+after so we can tell user whether anything was actually lifted.
    before = load_active()
    before_keys = {e.get("canonical_key") for e in before.get(args.scope + "s", []) or []}
    lift(args.scope, args.name)
    after = load_active()
    after_keys = {e.get("canonical_key") for e in after.get(args.scope + "s", []) or []}
    lifted = bool(before_keys - after_keys)

    if args.json:
        print(json.dumps({"ok": True, "lifted": lifted, "scope": args.scope, "name": args.name}))
    else:
        if lifted:
            print(f"OK: lifted {args.scope} mute on {args.name!r}")
        else:
            print(f"no-op: no active {args.scope} mute matched {args.name!r}")
    return 0


def _cmd_extend(args) -> int:
    if args.scope not in ("sector", "company"):
        print(f"error: scope must be 'sector' or 'company'", file=sys.stderr)
        return 1
    if args.days <= 0:
        print(f"error: --days must be positive", file=sys.stderr)
        return 1
    try:
        extend(args.scope, args.name, args.days)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, "action": "extend", "scope": args.scope,
                          "name": args.name, "days": args.days}))
    else:
        print(f"OK: extended {args.scope} mute on {args.name!r} by {args.days}d")
    return 0


def _cmd_edit_reason(args) -> int:
    if args.scope not in ("sector", "company"):
        print(f"error: scope must be 'sector' or 'company'", file=sys.stderr)
        return 1
    try:
        edit_reason(args.scope, args.name, args.reason)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, "action": "edit_reason", "scope": args.scope,
                          "name": args.name, "reason": args.reason}))
    else:
        print(f"OK: updated reason on {args.scope} mute {args.name!r}")
    return 0


def _cmd_audit(args) -> int:
    if not EVENTS_PATH.exists():
        if args.json:
            print(json.dumps({"events": []}))
        else:
            print("(no audit events yet)")
        return 0
    lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    events: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    tail = events[-args.limit:] if args.limit > 0 else events
    if args.json:
        print(json.dumps({"events": tail}, indent=2))
        return 0
    print(f"AUDIT EVENTS (last {len(tail)} of {len(events)}):")
    for e in tail:
        ts = e.get("ts", "?")
        action = (e.get("action") or "?").ljust(11)
        scope = (e.get("scope") or "?").ljust(7)
        name = e.get("name") or "?"
        new = e.get("new") or {}
        until = new.get("until") if isinstance(new, dict) else None
        suffix = f"  → until {until}" if until else ""
        print(f"  {ts}  {action} {scope} {name}{suffix}")
    return 0


def _run_smoke() -> int:
    """Original smoke harness, preserved bit-for-bit for backward compatibility.

    Redirects all paths into a temp dir so smoke leaves real data/ untouched."""
    global LIVE_PATH, EXAMPLE_PATH, EVENTS_PATH, HISTORY_PATH, PENDING_ARCHIVES_PATH  # noqa: PLW0603
    tmp = Path(tempfile.mkdtemp(prefix="suppr_smoke_"))
    LIVE_PATH = tmp / "suppressions.json"
    EXAMPLE_PATH = tmp / "suppressions.example.json"
    EVENTS_PATH = tmp / "suppressions_events.jsonl"
    HISTORY_PATH = tmp / "suppressions_history.json"
    PENDING_ARCHIVES_PATH = tmp / "suppressions_pending_archives.jsonl"
    EXAMPLE_PATH.write_text(json.dumps(_EMPTY_LIVE, indent=2), encoding="utf-8")

    add_sector("Canadian Big 6 Banks", date.today() + timedelta(days=60), "smoke test")
    lift("sector", "Canadian Big 6 Banks")

    print("events:")
    for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
        print("  " + line)

    shutil.rmtree(tmp, ignore_errors=True)
    print("OK")
    return 0


def _build_parser() -> "argparse.ArgumentParser":
    import argparse
    ap = argparse.ArgumentParser(
        prog="python -m automation.suppressions",
        description="Manage sector/company suppressions (mutes) for the scoring pipeline.",
    )
    ap.add_argument("--smoke", action="store_true",
                    help="Run the in-memory smoke test (leaves data/ untouched).")
    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND")

    p_add_sec = sub.add_parser("add-sector", help="Mute a sector for N days or until DATE.")
    p_add_sec.add_argument("name", help="Sector display name (case/punctuation lenient).")
    p_add_sec.add_argument("--days", type=int, help="TTL in days (mutually exclusive with --until).")
    p_add_sec.add_argument("--until", help="Expiry date YYYY-MM-DD (mutually exclusive with --days).")
    p_add_sec.add_argument("--reason", default="manual via CLI", help="Audit log reason.")
    p_add_sec.add_argument("--json", action="store_true", help="Machine-readable output.")
    p_add_sec.set_defaults(func=_cmd_add_sector)

    p_add_co = sub.add_parser("add-company", help="Mute a company for N days or until DATE.")
    p_add_co.add_argument("name", help="Company name (canonicalized via brand_aliases).")
    p_add_co.add_argument("--days", type=int, help="TTL in days.")
    p_add_co.add_argument("--until", help="Expiry date YYYY-MM-DD.")
    p_add_co.add_argument("--reason", default="manual via CLI", help="Audit log reason.")
    p_add_co.add_argument("--json", action="store_true")
    p_add_co.set_defaults(func=_cmd_add_company)

    p_list = sub.add_parser("list", help="Show active mutes (and optionally expired).")
    p_list.add_argument("--scope", choices=["all", "sector", "company"], default="all")
    p_list.add_argument("--include-expired", action="store_true",
                        help="Also show last 20 entries from history.")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)

    p_lift = sub.add_parser("lift", help="Remove an active mute.")
    p_lift.add_argument("scope", choices=["sector", "company"])
    p_lift.add_argument("name")
    p_lift.add_argument("--json", action="store_true")
    p_lift.set_defaults(func=_cmd_lift)

    p_ext = sub.add_parser("extend", help="Extend an active mute by N days.")
    p_ext.add_argument("scope", choices=["sector", "company"])
    p_ext.add_argument("name")
    p_ext.add_argument("--days", type=int, required=True)
    p_ext.add_argument("--json", action="store_true")
    p_ext.set_defaults(func=_cmd_extend)

    p_er = sub.add_parser("edit-reason", help="Update the reason on an active mute.")
    p_er.add_argument("scope", choices=["sector", "company"])
    p_er.add_argument("name")
    p_er.add_argument("--reason", required=True)
    p_er.add_argument("--json", action="store_true")
    p_er.set_defaults(func=_cmd_edit_reason)

    p_aud = sub.add_parser("audit", help="Print the suppressions audit-event log.")
    p_aud.add_argument("--limit", type=int, default=50,
                       help="Tail last N events (0 = all).")
    p_aud.add_argument("--json", action="store_true")
    p_aud.set_defaults(func=_cmd_audit)

    return ap


def _main(argv: list[str] | None = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.smoke:
        return _run_smoke()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(_main())
