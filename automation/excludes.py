"""excludes.py — permanent, source-level company exclude-list.

Unlike `suppressions.py` (a TTL'd sector/company *mute* applied at triage, with
an audit log and history), this is a flat, **permanent** set of excluded company
canonical keys. A company on this list is dropped at the SOURCE — the web scrape
never queries it, both Gmail paths drop its alert rows, and `worklist.rebuild()`
never re-materializes its rows from on-disk envelopes. That saves scrape time AND
scoring API cost, and it stops the row from ever reaching the user.

Design (deliberately simpler than suppressions):
  - No TTL / `until` — permanent until the user un-checks it.
  - No reason field, no audit/event log, no history, no pending-archive queue.
  - One file, `data/excludes.json`, lazy-created from `data/excludes.example.json`.
  - Lock-safe writes via the same `safe_json.mutate_json` portalocker primitive.
  - Matching is by `brand_aliases.canonical_brand()` everywhere (scrape, Gmail,
    worklist) so RBC ⇄ Royal Bank of Canada ⇄ RBC Capital Markets ⇄ RBC Global
    Asset Management all collapse onto one key, and excluding a bank also excludes
    asset-management siblings that share a Workday tenant.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Dual-import so this module loads BOTH as a package member
# (`from automation import excludes`, `python -m automation.excludes`) AND as a
# bare top-level module. The latter is load-bearing: the UI and run_pipeline.py
# launch jd_scraper.py / gmail_fetch.py / worklist.py as bare scripts
# (`python automation/X.py`, __package__ == ''), and those modules import
# `excludes` with no degradation path — so a hard relative import here would
# crash a real scrape/rebuild. Mirrors worklist.py's brand_aliases import.
try:
    from .safe_json import mutate_json, read_json, write_json
    from . import brand_aliases
except ImportError:  # bare-script context (automation/ on sys.path)
    from safe_json import mutate_json, read_json, write_json  # type: ignore
    import brand_aliases  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
LIVE_PATH = ROOT / "data" / "excludes.json"
EXAMPLE_PATH = ROOT / "data" / "excludes.example.json"

def _empty_live() -> dict:
    """Fresh empty-state dict with a FRESH inner list every call.

    Must be a factory, not a module-level constant: a shared
    `{"version": 1, "companies": []}` handed out via `dict(...)` (a SHALLOW
    copy) would share the inner `companies` list, so the first `add()` on a
    not-yet-created file would `.append` into the shared list and silently
    poison every later 'empty' default — in tests AND in the long-lived
    Streamlit process that keeps this module resident."""
    return {"version": 1, "companies": []}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _ensure_live_file() -> None:
    """Lazy-create the live file from the example seed on first read."""
    if LIVE_PATH.exists():
        return
    LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if EXAMPLE_PATH.exists():
        seed = read_json(EXAMPLE_PATH, default=_empty_live())
    else:
        seed = _empty_live()
    write_json(LIVE_PATH, seed)


def _canon(name: Any) -> str:
    """Canonical lowercase key for a company name, or '' when unusable.

    Only genuine strings are canonicalized. A malformed company field
    (int/list/dict/None) returns '' rather than being str()'d first — otherwise
    `str(["RBC"])` → "['RBC']" and canonical_brand's substring match would
    falsely resolve a list to 'rbc' and wrongly exclude the row."""
    if not isinstance(name, str):
        return ""
    return brand_aliases.canonical_brand(name.strip()).lower()


def load() -> set[str]:
    """Return the set of excluded canonical_key strings.

    Lazy-creates the live file from the example seed on first read. An empty
    set is falsy, so every hot-path caller can fast-path on it. Reads under
    the shared sidecar lock (same primitive suppressions uses)."""
    _ensure_live_file()
    state = read_json(LIVE_PATH, default=_empty_live()) or _empty_live()
    return {
        e.get("canonical_key")
        for e in state.get("companies", []) or []
        if e.get("canonical_key")
    }


def list_excluded() -> list[dict]:
    """Ordered display rows [{name, canonical_key, added_at}] for the admin UI.

    Insertion order preserved (append order from `add`)."""
    _ensure_live_file()
    state = read_json(LIVE_PATH, default=_empty_live()) or _empty_live()
    return list(state.get("companies", []) or [])


def is_excluded(company_name: Any, snapshot: set[str] | None = None) -> bool:
    """True when `company_name` canonicalizes to an excluded key.

    Hot-path: called once per row in scrape/Gmail/worklist loops. The
    empty-set check comes BEFORE `canonical_brand` so a dormant (nothing
    excluded) loop over thousands of rows pays zero canonicalization cost.
    Coerces a malformed company field (int/list/dict/None) to '' → False, so
    one bad row never crashes a fetch.

    Pass `snapshot=load()` once and reuse it across a loop; calling without a
    snapshot does a locked disk read PER CALL and is for one-off use only."""
    s = snapshot if snapshot is not None else load()
    if not s:
        return False
    key = _canon(company_name)
    if not key:
        return False
    return key in s


def add(name: str) -> bool:
    """Exclude a company. Idempotent on canonical key.

    Returns True if a new entry was appended, False if the canonical key was
    already excluded. Raises ValueError on a blank name / un-canonicalizable
    input (mirrors suppressions.add_company)."""
    if not name or not str(name).strip():
        raise ValueError("company name required")
    canon = _canon(name)
    if not canon:
        raise ValueError(f"could not canonicalize company: {name!r}")
    new_entry = {
        "name": str(name).strip(),
        "canonical_key": canon,
        "added_at": _now_iso(),
    }
    appended_holder = [False]

    def _mut(state):
        state = state or _empty_live()
        state.setdefault("version", 1)
        state.setdefault("companies", [])
        for e in state.get("companies", []) or []:
            if e.get("canonical_key") == canon:
                return state  # already excluded — no-op
        state["companies"].append(new_entry)
        appended_holder[0] = True
        return state

    mutate_json(LIVE_PATH, _mut, default=_empty_live())
    return appended_holder[0]


def remove(name: str) -> bool:
    """Un-exclude the company whose canonical key matches `name`.

    Hard delete (permanent-until-unchecked = no archive/history). Returns
    True if an entry was removed, False on a clean no-op."""
    canon = _canon(name)
    if not canon:
        return False
    removed_holder = [False]

    def _mut(state):
        state = state or _empty_live()
        state.setdefault("version", 1)
        state.setdefault("companies", [])
        kept = []
        for e in state.get("companies", []) or []:
            if e.get("canonical_key") == canon:
                removed_holder[0] = True
            else:
                kept.append(e)
        state["companies"] = kept
        return state

    mutate_json(LIVE_PATH, _mut, default=_empty_live())
    return removed_holder[0]


def filter_targets(targets: list[dict],
                   snapshot: set[str] | None = None) -> list[dict]:
    """Scrape-side filter: drop excluded TARGETS by canonical key.

    Matches on `canonical_brand(t['name'])`, NOT the raw name — so excluding
    'TD Bank' (key 'td') also drops 'TD Asset Management' (key 'td'), which is
    REQUIRED because they share a Workday tenant: if the sibling survived it
    would query the excluded bank's board and re-tag the jobs.

    Identity-returns `targets` when nothing is excluded, so `_targets_signature`
    is unchanged in the dormant case and `--resume` keeps working."""
    s = snapshot if snapshot is not None else load()
    if not s:
        return targets
    return [t for t in targets if _canon(t.get("name")) not in s]


def filter_rows(rows: list[dict],
                snapshot: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Gmail/worklist-side filter. Returns (kept, dropped).

    A row is dropped when its `company` canonicalizes to an excluded key.
    Empty set → (rows, []) fast path (no per-row canonicalization)."""
    s = snapshot if snapshot is not None else load()
    if not s:
        return rows, []
    kept: list[dict] = []
    dropped: list[dict] = []
    for r in rows:
        if is_excluded(r.get("company"), s):
            dropped.append(r)
        else:
            kept.append(r)
    return kept, dropped


# ---------------------------------------------------------------------------
# CLI (operator UX) — mirrors suppressions' argparse style, minus TTL/reason.
# ---------------------------------------------------------------------------

def _cmd_add(args) -> int:
    try:
        appended = add(args.name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    canon = _canon(args.name)
    if args.json:
        print(json.dumps({"ok": True, "added": appended,
                          "name": str(args.name).strip(), "canonical_key": canon}))
    elif appended:
        print(f"OK: excluded company {str(args.name).strip()!r} (key {canon!r})")
    else:
        print(f"no-op: company {str(args.name).strip()!r} (key {canon!r}) already excluded")
    return 0


def _cmd_remove(args) -> int:
    removed = remove(args.name)
    canon = _canon(args.name)
    if args.json:
        print(json.dumps({"ok": True, "removed": removed,
                          "name": str(args.name).strip(), "canonical_key": canon}))
    elif removed:
        print(f"OK: un-excluded company {str(args.name).strip()!r} (key {canon!r})")
    else:
        print(f"no-op: no exclude matched {str(args.name).strip()!r} (key {canon!r})")
    return 0


def _cmd_list(args) -> int:
    entries = list_excluded()
    if args.json:
        print(json.dumps({"companies": entries}, indent=2))
        return 0
    print(f"EXCLUDED COMPANIES ({len(entries)}):")
    if not entries:
        print("  (none — nothing is excluded)")
        return 0
    name_w = max((len(e.get("name") or "") for e in entries), default=4)
    name_w = max(name_w, 4)
    for e in entries:
        name = (e.get("name") or "?").ljust(name_w)
        key = e.get("canonical_key") or "?"
        added = e.get("added_at") or "?"
        print(f"  - {name}  key={key!r}  added={added}")
    return 0


def _run_smoke() -> int:
    """In-memory smoke harness; redirects paths into a temp dir so it leaves
    real data/ untouched."""
    global LIVE_PATH, EXAMPLE_PATH  # noqa: PLW0603
    tmp = Path(tempfile.mkdtemp(prefix="excludes_smoke_"))
    LIVE_PATH = tmp / "excludes.json"
    EXAMPLE_PATH = tmp / "excludes.example.json"
    EXAMPLE_PATH.write_text(json.dumps(_empty_live(), indent=2), encoding="utf-8")

    assert load() == set()
    assert add("RBC") is True
    assert add("Royal Bank of Canada") is False          # same canonical key
    assert load() == {"rbc"}
    assert is_excluded("RBC Capital Markets") is True
    assert is_excluded("Acme Corp") is False
    assert remove("RBC") is True
    assert load() == set()

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("OK")
    return 0


def _build_parser():
    import argparse
    ap = argparse.ArgumentParser(
        prog="python -m automation.excludes",
        description="Manage the permanent company exclude-list (source-level "
                    "block; distinct from TTL'd triage suppressions).",
    )
    ap.add_argument("--smoke", action="store_true",
                    help="Run the in-memory smoke test (leaves data/ untouched).")
    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND")

    p_add = sub.add_parser("add", help="Exclude a company (permanent).")
    p_add.add_argument("name", help="Company name (canonicalized via brand_aliases).")
    p_add.add_argument("--json", action="store_true")
    p_add.set_defaults(func=_cmd_add)

    p_rm = sub.add_parser("remove", help="Un-exclude a company.")
    p_rm.add_argument("name", help="Company name (canonicalized via brand_aliases).")
    p_rm.add_argument("--json", action="store_true")
    p_rm.set_defaults(func=_cmd_remove)

    p_list = sub.add_parser("list", help="Show excluded companies.")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_list)

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
