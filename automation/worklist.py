#!/usr/bin/env python3
"""worklist.py — source-of-truth job pool management.

Replaces the old "merge everything into one base file" approach (destructive,
loses provenance) with three clearly separated concepts:

  1. SCRAPE SOURCE  — one pinned web scrape, the stable pool for this search
     cycle. Set explicitly; rescrapes never overwrite it. Pointer: .scrape_source
     (falls back to legacy .base_scan for migration).

  2. GMAIL POOL     — gmail_pool.json. An accumulating, deduped pool of jobs
     harvested from Gmail alerts. Each fetch unions in NEW unique rows and
     stamps first_seen. Rolling 30-day window: rows older than 30 days are
     pruned UNLESS the URL is already in the tracker.

  3. WORKING SET    — working_set.json. DERIVED: dedup(scrape ∪ gmail). Each
     row tagged source ("scrape" | "gmail" | "both"), first_seen, and is_new
     (URL not present in the previous working-set snapshot). This is what the
     scorer consumes. It is regenerated from the two sources — never edited.

Sources stay immutable inputs; the working set is a pure function of them.
Provenance and recency are first-class so the nightly brief can highlight
"N new from web scrape, M new from Gmail".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
TRACKER = ROOT / "data" / "job_tracker_data.json"

SCRAPE_SOURCE_POINTER = OUT_DIR / ".scrape_source"
LEGACY_BASE_POINTER = OUT_DIR / ".base_scan"
GMAIL_POOL = OUT_DIR / "gmail_pool.json"
WORKING_SET = OUT_DIR / "working_set.json"
PREV_URLS = OUT_DIR / ".working_set_prev_urls.json"

POOL_WINDOW_DAYS = 30

# Files that match scan_*.json but are NOT user-pickable web scrapes.
# "_merged" excludes the legacy one-off merge hack (superseded by working set).
_NON_SOURCE = ("scan_gmail_", "scan_base_", "scan_checkpoint",
               "working_set", "gmail_pool", "_merged")


# ---------------------------------------------------------------------------
# URL normalization — the dedup key
# ---------------------------------------------------------------------------
_LI_JOB_RE = re.compile(r"linkedin\.com/.*?/jobs/view/(\d+)", re.IGNORECASE)


def norm_url(row: dict) -> str:
    raw = (row.get("link") or row.get("url") or row.get("job_url") or "").strip()
    if not raw:
        return ""
    m = _LI_JOB_RE.search(raw)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    # Strip tracking query/fragment for everything else
    base = raw.split("#", 1)[0].split("?", 1)[0]
    return base.rstrip("/").lower()


def _tracker_urls() -> set[str]:
    try:
        data = json.loads(TRACKER.read_text(encoding="utf-8"))
        out = set()
        for j in data.get("jobs", []):
            u = (j.get("url") or "").strip()
            if u:
                out.add(norm_url({"url": u}))
        return out
    except Exception:
        return set()


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read_envelope(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Scrape source pointer
# ---------------------------------------------------------------------------
def scan_candidates() -> list[Path]:
    """Real, user-pickable web scrapes, newest first."""
    files = sorted(OUT_DIR.glob("scan_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return [f for f in files
            if "_scored" not in f.name
            and not any(t in f.name for t in _NON_SOURCE)]


def get_scrape_source() -> Path | None:
    for ptr in (SCRAPE_SOURCE_POINTER, LEGACY_BASE_POINTER):
        try:
            if ptr.exists():
                name = ptr.read_text(encoding="utf-8").strip()
                if name:
                    p = OUT_DIR / name
                    if p.exists():
                        return p
        except Exception:
            pass
    return None


def set_scrape_source(path) -> None:
    try:
        SCRAPE_SOURCE_POINTER.write_text(Path(path).name, encoding="utf-8")
    except Exception:
        pass


def clear_scrape_source() -> None:
    for ptr in (SCRAPE_SOURCE_POINTER, LEGACY_BASE_POINTER):
        try:
            ptr.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Gmail pool — accumulate + rolling 30d prune
# ---------------------------------------------------------------------------
def update_gmail_pool() -> dict:
    """Fold every scan_gmail_*.json harvest into gmail_pool.json, dedup by URL
    (keep earliest first_seen), then prune rows older than POOL_WINDOW_DAYS
    UNLESS the URL is in the tracker. Returns stats."""
    stats = {"harvests": 0, "added": 0, "pruned": 0, "pool_total": 0}
    pool_env = _read_envelope(GMAIL_POOL)
    by_url: dict[str, dict] = {}
    for r in pool_env.get("results", []) or []:
        u = norm_url(r)
        if u:
            by_url[u] = r

    harvests = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                      key=lambda p: p.stat().st_mtime)
    for h in harvests:
        stats["harvests"] += 1
        for r in _read_envelope(h).get("results", []) or []:
            u = norm_url(r)
            if not u:
                continue
            if u in by_url:
                continue  # already pooled, keep original first_seen
            r = dict(r)
            r["source"] = "gmail"
            r.setdefault("first_seen", r.get("posted_date") or _today())
            by_url[u] = r
            stats["added"] += 1

    # Rolling-window prune
    cutoff = (datetime.now() - timedelta(days=POOL_WINDOW_DAYS)).date()
    keep_urls = _tracker_urls()
    kept: list[dict] = []
    for u, r in by_url.items():
        fs = str(r.get("first_seen", ""))[:10]
        try:
            fs_date = datetime.strptime(fs, "%Y-%m-%d").date()
        except Exception:
            fs_date = datetime.now().date()
        if fs_date >= cutoff or u in keep_urls:
            kept.append(r)
        else:
            stats["pruned"] += 1

    stats["pool_total"] = len(kept)
    GMAIL_POOL.write_text(json.dumps({
        "scan_date": _today(),
        "source": "gmail_pool",
        "window_days": POOL_WINDOW_DAYS,
        "results": kept,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats


# ---------------------------------------------------------------------------
# Working set — derived view
# ---------------------------------------------------------------------------
def _prev_urls() -> set[str]:
    try:
        return set(json.loads(PREV_URLS.read_text(encoding="utf-8")))
    except Exception:
        return set()


def rebuild_working_set() -> dict:
    """working_set = dedup(scrape_source ∪ gmail_pool). Tag source / first_seen
    / is_new (vs previous snapshot). Returns stats incl. per-source new counts."""
    stats = {"scrape": 0, "gmail": 0, "both": 0, "unique": 0,
             "new_total": 0, "new_scrape": 0, "new_gmail": 0,
             "has_baseline": PREV_URLS.exists()}

    src = get_scrape_source()
    scrape_env = _read_envelope(src) if src else {}
    pool_env = _read_envelope(GMAIL_POOL)

    merged: dict[str, dict] = {}
    for r in scrape_env.get("results", []) or []:
        u = norm_url(r)
        if not u:
            continue
        r = dict(r)
        r["source"] = "scrape"
        r.setdefault("first_seen", r.get("posted_date") or _today())
        merged[u] = r

    for r in pool_env.get("results", []) or []:
        u = norm_url(r)
        if not u:
            continue
        if u in merged:
            merged[u]["source"] = "both"
            # earliest first_seen wins
            a = str(merged[u].get("first_seen", ""))[:10]
            b = str(r.get("first_seen", ""))[:10]
            if b and (not a or b < a):
                merged[u]["first_seen"] = b
        else:
            r = dict(r)
            r["source"] = "gmail"
            r.setdefault("first_seen", r.get("posted_date") or _today())
            merged[u] = r

    prev = _prev_urls()
    rows: list[dict] = []
    for u, r in merged.items():
        is_new = bool(prev) and u not in prev
        r["is_new"] = is_new
        rows.append(r)
        s = r["source"]
        stats[s] = stats.get(s, 0) + 1
        if is_new:
            stats["new_total"] += 1
            if s in ("scrape", "both"):
                stats["new_scrape"] += 1
            if s in ("gmail", "both"):
                stats["new_gmail"] += 1

    stats["unique"] = len(rows)

    envelope = dict(scrape_env) if scrape_env else {}
    envelope["results"] = rows
    envelope["scan_date"] = _today()
    envelope["source"] = "working_set"
    envelope["working_set_stats"] = stats
    envelope["dedup_stats"] = {
        "input": (stats["scrape"] + stats["gmail"] + stats["both"]),
        "output": stats["unique"], "dropped_url": 0, "dropped_near": 0,
    }
    WORKING_SET.write_text(json.dumps(envelope, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    # Snapshot for next-time delta
    PREV_URLS.write_text(json.dumps(sorted(merged.keys())), encoding="utf-8")
    return stats


def scrape_delta_vs_source() -> dict:
    """How many URLs a fresh scrape would ADD vs the pinned source.
    Informational only — the source stays weekly-pinned by design."""
    src = get_scrape_source()
    cands = scan_candidates()
    newest = next((c for c in cands if not src or c.name != src.name), None)
    if not src or not newest:
        return {"newest": newest.name if newest else None, "new": 0,
                "source": src.name if src else None}
    src_urls = {norm_url(r) for r in _read_envelope(src).get("results", []) or []}
    new_n = sum(1 for r in _read_envelope(newest).get("results", []) or []
                if norm_url(r) and norm_url(r) not in src_urls)
    return {"newest": newest.name, "new": new_n, "source": src.name}


def effective_scan() -> Path | None:
    """What the scorer/funnel should read: working set → scrape source →
    newest raw scan (legacy fallback)."""
    if WORKING_SET.exists():
        return WORKING_SET
    src = get_scrape_source()
    if src:
        return src
    cands = scan_candidates()
    return cands[0] if cands else None
