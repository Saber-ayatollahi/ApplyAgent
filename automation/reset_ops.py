#!/usr/bin/env python3
"""
reset_ops.py — Inventory + delete helpers for the Streamlit Admin reset panel.

All destructive operations are split in half:
    *_plan(...)  -> returns a ResetPlan (dicts of what WOULD be touched) so
                    the UI can render a preview before the user confirms
    *_execute(plan) -> performs the actions recorded in the plan

This makes every destructive button two-click (preview, confirm, execute)
and keeps the UI code trivial. Also makes the operations unit-testable.

Four scopes, matching the Admin UI:
    plan_delete_scan(stem)    -> remove one scan + its artifacts
    plan_clear_scans()         -> remove all scan_*.json / *_scored.json
    plan_clear_caches()        -> empty jd_cache/ and fit_cache/
    plan_full_reset()          -> everything in outputs/ + tracker reset +
                                   CRM reset + ledger zero

Safety: no operation touches code, .git, logs/, docs/, master_repo/,
or ~/.applyagent/config.json. The tracker is backed up to
job_tracker_data.bak.<stamp>.json before any reset. Ledger is NEVER
deleted — reset-to-zero is via cost_ledger.reset() with the magic
phrase so the behavior matches the rest of the system.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
JD_CACHE = OUT_DIR / "jd_cache"
FIT_CACHE = OUT_DIR / "fit_cache"
PIPELINE_DIR = OUT_DIR / "pipelines"
RUNS_DIR = OUT_DIR / "runs"
TRACKER = ROOT / "data" / "job_tracker_data.json"
CRM = ROOT / "data" / "recruiter_crm.json"


@dataclass
class ResetPlan:
    """Description of what a reset operation would touch. The UI renders
    this as a preview; execute() only runs if the user confirms."""
    scope: str                  # "delete_scan" | "clear_scans" | ...
    files_to_delete: list[Path] = field(default_factory=list)
    dirs_to_empty: list[Path] = field(default_factory=list)
    json_to_reset: list[tuple[Path, dict]] = field(default_factory=list)
    ledger_reset: bool = False
    preserved: list[str] = field(default_factory=list)
    total_bytes: int = 0

    def summary(self) -> str:
        parts = []
        if self.files_to_delete:
            parts.append(f"{len(self.files_to_delete)} files")
        for d in self.dirs_to_empty:
            count = sum(1 for _ in d.glob("*")) if d.exists() else 0
            parts.append(f"{count} items in {d.name}/")
        if self.json_to_reset:
            parts.append(f"{len(self.json_to_reset)} JSON reset")
        if self.ledger_reset:
            parts.append("cost ledger -> 0")
        if self.total_bytes:
            mb = self.total_bytes / (1024 * 1024)
            parts.append(f"~{mb:.1f} MB freed")
        return ", ".join(parts) or "(nothing to do)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except (FileNotFoundError, OSError):
        return 0


def _backup_json(path: Path, tag: str) -> Path | None:
    """Copy `path` to `path.bak.<tag>.<stamp>.json`. Returns backup path, or
    None if the source didn't exist."""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(f".bak.{tag}.{stamp}.json")
    shutil.copy2(path, bak)
    return bak


# ---------------------------------------------------------------------------
# Inventory — what's on disk right now
# ---------------------------------------------------------------------------
def list_scans() -> list[dict]:
    """Return every `scan_*.json` (and its matching _scored.json) with
    row count + size, newest first. Used by the UI to render a picker."""
    if not OUT_DIR.exists():
        return []
    rows: list[dict] = []
    for p in sorted(OUT_DIR.glob("scan_*.json"),
                     key=lambda q: q.stat().st_mtime, reverse=True):
        if "_scored" in p.name or "checkpoint" in p.name:
            continue
        stem = p.stem  # scan_20260506 or scan_v4 or scan_gmail_20260506_142530
        scored = OUT_DIR / f"{stem}_scored.json"
        md = OUT_DIR / f"{stem}.md"
        scored_md = OUT_DIR / f"{stem}_scored.md"
        row_count = 0
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            row_count = len(data.get("results", []))
        except Exception:
            pass
        rows.append({
            "stem": stem,
            "scan_json": p,
            "scored_json": scored if scored.exists() else None,
            "scan_md": md if md.exists() else None,
            "scored_md": scored_md if scored_md.exists() else None,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime)
                        .strftime("%Y-%m-%d %H:%M"),
            "rows": row_count,
            "size_kb": (_safe_size(p) + _safe_size(scored)
                         + _safe_size(md) + _safe_size(scored_md)) // 1024,
        })
    return rows


def inventory_outputs() -> dict:
    """Top-level summary of automation/outputs/ for the Admin header row.
    Cheap — no JSON parsing, just globs + stat."""
    def _count(glob_pat: str) -> int:
        return sum(1 for _ in OUT_DIR.glob(glob_pat)) if OUT_DIR.exists() else 0

    def _dir_size_bytes(d: Path) -> int:
        if not d.exists():
            return 0
        total = 0
        for f in d.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                continue
        return total

    return {
        "scan_count": sum(1 for p in OUT_DIR.glob("scan_*.json")
                            if "_scored" not in p.name and OUT_DIR.exists()),
        "scored_count": _count("*_scored.json"),
        "tailor_docs": _count("*.md") - _count("scan_*.md"),
        "pipeline_runs": sum(1 for _ in PIPELINE_DIR.glob("pipeline_*.json"))
                            if PIPELINE_DIR.exists() else 0,
        "background_runs": sum(1 for _ in RUNS_DIR.glob("*.json"))
                              if RUNS_DIR.exists() else 0,
        "jd_cache_bytes": _dir_size_bytes(JD_CACHE),
        "fit_cache_bytes": _dir_size_bytes(FIT_CACHE),
        "outputs_bytes": _dir_size_bytes(OUT_DIR),
    }


# ---------------------------------------------------------------------------
# Scope 1: delete one scan + its artifacts
# ---------------------------------------------------------------------------
def plan_delete_scan(stem: str) -> ResetPlan:
    """Delete scan_<stem>.json + scan_<stem>_scored.json + the two .md
    siblings. Stem may include or omit the 'scan_' prefix."""
    if stem.startswith("scan_"):
        # Users may pass either "scan_20260506" or just "20260506"
        pass
    else:
        stem = f"scan_{stem}"
    candidates = [
        OUT_DIR / f"{stem}.json",
        OUT_DIR / f"{stem}_scored.json",
        OUT_DIR / f"{stem}.md",
        OUT_DIR / f"{stem}_scored.md",
    ]
    existing = [p for p in candidates if p.exists()]
    return ResetPlan(
        scope="delete_scan",
        files_to_delete=existing,
        total_bytes=sum(_safe_size(p) for p in existing),
    )


# ---------------------------------------------------------------------------
# Scope 2: clear all scans + scored artifacts
# ---------------------------------------------------------------------------
def plan_clear_scans() -> ResetPlan:
    """Remove every scan_*.json / *_scored.json / scan_*.md / *_scored.md.
    Leaves pipelines/, runs/, fit_cache/, jd_cache/, and tracker alone."""
    if not OUT_DIR.exists():
        return ResetPlan(scope="clear_scans")
    files: list[Path] = []
    for pat in ("scan_*.json", "scan_*.md", "*_scored.json", "*_scored.md"):
        for p in OUT_DIR.glob(pat):
            # Preserve the current checkpoint so pausing doesn't die
            if p.name in ("scan_checkpoint.json",):
                continue
            if p.is_file():
                files.append(p)
    return ResetPlan(
        scope="clear_scans",
        files_to_delete=files,
        total_bytes=sum(_safe_size(p) for p in files),
        preserved=["tracker", "CRM", "caches", "pipeline status",
                    "ledger", "tailor docs", "master_repo"],
    )


# ---------------------------------------------------------------------------
# Scope 3: clear caches (jd_cache + fit_cache)
# ---------------------------------------------------------------------------
def plan_clear_caches() -> ResetPlan:
    """Empty jd_cache/ and fit_cache/. Does NOT delete the directories
    themselves — the scorer and fetcher assume they exist."""
    dirs = [d for d in (JD_CACHE, FIT_CACHE) if d.exists()]
    # Files inside them — gather for size counting and so the executor
    # doesn't have to rediscover them
    files: list[Path] = []
    for d in dirs:
        for p in d.rglob("*"):
            if p.is_file():
                files.append(p)
    return ResetPlan(
        scope="clear_caches",
        files_to_delete=files,
        dirs_to_empty=dirs,
        total_bytes=sum(_safe_size(p) for p in files),
        preserved=["scans", "scored", "tracker", "CRM", "ledger"],
    )


# ---------------------------------------------------------------------------
# Scope 4: full reset (nuclear)
# ---------------------------------------------------------------------------
def _empty_tracker() -> dict:
    """Fresh tracker payload. Mirrors the schema the UI and auto_promote
    expect so a reset tracker doesn't crash on the next page load."""
    return {
        "meta": {
            "version": "2.0",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total_roles": 0,
            "changelog": [{
                "date": datetime.now().date().isoformat(),
                "event": "full_reset — tracker reinitialized",
                "roles": 0,
            }],
            "status_enum": [
                "Found", "Watch", "Applied",
                "Recruiter_Screen", "Phone_Screen", "Take_Home",
                "Onsite", "Offer", "Rejected", "Hired", "Withdrawn",
                "Expired",
            ],
            "weekly_kpi_targets": {
                "tailored_applications": 8,
                "outreach_messages": 10,
                "coffees": 3,
                "linkedin_posts": 1,
            },
        },
        "jobs": [],
    }


def _empty_crm() -> dict:
    return {
        "meta": {
            "version": "1.0",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "contacts": [],
    }


def plan_full_reset() -> ResetPlan:
    """Nuke everything in outputs/ + reset tracker + reset CRM + zero the
    ledger. Backs up tracker + CRM + ledger first. Keeps logs/, docs/,
    master_repo/, code, .git, and ~/.applyagent/config.json untouched."""
    files: list[Path] = []
    dirs: list[Path] = []
    if OUT_DIR.exists():
        for p in OUT_DIR.iterdir():
            if p.name == ".gitkeep":
                continue
            if p.is_file():
                files.append(p)
            elif p.is_dir():
                dirs.append(p)
    resets: list[tuple[Path, dict]] = []
    if TRACKER.exists():
        resets.append((TRACKER, _empty_tracker()))
    if CRM.exists():
        resets.append((CRM, _empty_crm()))

    total = sum(_safe_size(p) for p in files)
    for d in dirs:
        for f in d.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                continue

    return ResetPlan(
        scope="full_reset",
        files_to_delete=files,
        dirs_to_empty=dirs,
        json_to_reset=resets,
        ledger_reset=True,
        total_bytes=total,
        preserved=[
            "logs/", "docs/", "master_repo/", ".git/", "source code",
            "API key + Gmail config (~/.applyagent/)",
        ],
    )


# ---------------------------------------------------------------------------
# Execute — ACTUALLY DELETE. Caller MUST have shown plan to user first.
# ---------------------------------------------------------------------------
@dataclass
class ResetResult:
    scope: str
    deleted_files: int = 0
    deleted_bytes: int = 0
    json_reset: int = 0
    ledger_reset: bool = False
    errors: list[str] = field(default_factory=list)
    backups: list[Path] = field(default_factory=list)


def execute(plan: ResetPlan,
             confirm_phrase: str | None = None,
             required_phrase: str | None = None) -> ResetResult:
    """Run the plan. If `required_phrase` is set, confirm_phrase must match
    exactly — a typo returns a no-op result with an error. This gates the
    full-reset scope behind a typed confirmation."""
    res = ResetResult(scope=plan.scope)

    if required_phrase is not None:
        if (confirm_phrase or "").strip() != required_phrase:
            res.errors.append(
                f"Confirmation mismatch — expected exactly "
                f"{required_phrase!r}. Nothing was deleted."
            )
            return res

    # 1. Back up JSON targets BEFORE touching anything else
    for path, _ in plan.json_to_reset:
        try:
            bak = _backup_json(path, f"reset_{plan.scope}")
            if bak:
                res.backups.append(bak)
        except Exception as e:
            res.errors.append(f"backup {path.name}: {e}")

    # 2. Delete top-level files
    for p in plan.files_to_delete:
        try:
            size = _safe_size(p)
            p.unlink()
            res.deleted_files += 1
            res.deleted_bytes += size
        except FileNotFoundError:
            pass
        except Exception as e:
            res.errors.append(f"delete {p.name}: {e}")

    # 3. Empty dirs (NOT the dirs themselves — tools recreate them)
    for d in plan.dirs_to_empty:
        try:
            if d.exists():
                for p in list(d.rglob("*")):
                    try:
                        size = _safe_size(p)
                        if p.is_file() or p.is_symlink():
                            p.unlink()
                            res.deleted_files += 1
                            res.deleted_bytes += size
                    except Exception as e:
                        res.errors.append(f"delete {p}: {e}")
                # Then remove now-empty subdirs bottom-up
                for p in sorted(d.rglob("*"), reverse=True):
                    try:
                        if p.is_dir():
                            p.rmdir()
                    except OSError:
                        pass
        except Exception as e:
            res.errors.append(f"empty {d}: {e}")

    # 4. Reset JSON targets via safe_json if available so the locks hold
    for path, payload in plan.json_to_reset:
        try:
            try:
                from safe_json import write_json  # type: ignore
                write_json(path, payload)
            except ImportError:
                path.write_text(json.dumps(payload, indent=2),
                                 encoding="utf-8")
            res.json_reset += 1
        except Exception as e:
            res.errors.append(f"reset {path.name}: {e}")

    # 5. Ledger reset — behind the magic phrase to match cost_ledger.reset()
    if plan.ledger_reset:
        try:
            from cost_ledger import reset as _ledger_reset  # type: ignore
            ok = _ledger_reset(confirm="YES I REALLY MEAN IT")
            if ok:
                res.ledger_reset = True
            else:
                res.errors.append("ledger reset refused by cost_ledger")
        except Exception as e:
            res.errors.append(f"ledger reset: {e}")

    return res
