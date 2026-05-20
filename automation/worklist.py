#!/usr/bin/env python3
"""worklist.py — the ONE job pool every consumer reads.

Replaces a tangle of half-overlapping concepts (.scrape_source pointer,
.base_scan pointer, gmail_pool.json, working_set.json, scan_base_*.json,
scan_*_merged.json) with a single contract:

  INPUTS (immutable, append-only on disk):
    automation/outputs/scan_<date>.json         ← raw web scrape
    automation/outputs/scan_gmail_<stamp>.json  ← raw Gmail harvest

  POOL (THE source of truth — derived):
    automation/outputs/worklist.json            ← scorer reads this. Period.

  DERIVED:
    automation/outputs/worklist_scored.json     ← fit_scorer output
    promote_report_<date>.md                    ← auto_promote preview

The contract: **the scorer scores `worklist.json`. Nothing else. Ever.**

`rebuild()` is the only function that produces `worklist.json`. It runs:
  - Automatically after `jd_scraper` finishes (called from there)
  - Automatically after `gmail_fetch` finishes (called from there)
  - Manually from the UI's 'Rebuild' button (rarely needed — auto covers it)

Each row carries:
  - source: "scrape" | "gmail" | "both"
  - first_seen: earliest date we saw the URL across all inputs
  - in_pool_since: when this row first appeared in the worklist
  - is_new_since_last_score: True if URL not in the previous worklist_scored

Provenance and recency are first-class — the brief, scorer, and promote
report all use them. Tracker rows promoted from a worklist entry inherit
the source tag (so a 📬 / 🛰 / 🔁 badge can render).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

try:
    from brand_aliases import canonical_brand  # type: ignore
except ImportError:
    from .brand_aliases import canonical_brand  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
TRACKER = ROOT / "data" / "job_tracker_data.json"

WORKLIST = OUT_DIR / "worklist.json"
WORKLIST_SCORED = OUT_DIR / "worklist_scored.json"
LEGACY_DIR = OUT_DIR / "_legacy"

GMAIL_WINDOW_DAYS = 30  # how far back to fold scan_gmail_*.json files

# Patterns that match scan_*.json but are NOT user-pickable web scrapes.
_NON_SCRAPE_PATTERNS = (
    "scan_gmail_", "scan_base_", "scan_checkpoint",
    "_merged", "working_set", "gmail_pool",
)

# Files we relocate to _legacy/ on first rebuild — old artifacts that
# overlapped worklist's job. Idempotent: if they're already in _legacy/
# (or never existed), the move is a no-op.
_LEGACY_FILES = (
    "gmail_pool.json",
    "working_set.json",
    ".working_set_prev_urls.json",
    ".scrape_source",
    ".base_scan",
)
_LEGACY_GLOBS = (
    "scan_base_*.json",
    "scan_*_merged.json",
)


# ---------------------------------------------------------------------------
# URL normalization — the dedup key
# ---------------------------------------------------------------------------
_LI_JOB_RE = re.compile(
    r"linkedin\.com/(?:[^/?#]*/)*jobs/view/(?:[^/?#]*?-)?(\d{6,})",
    re.IGNORECASE,
)


def norm_url(row: dict) -> str:
    """Canonical URL for dedup. LinkedIn /jobs/view/<id> collapses tracking
    redirects to the bare job id; everything else strips query/fragment
    and normalizes case + trailing slash."""
    raw = (row.get("link") or row.get("url") or row.get("job_url") or "").strip()
    if not raw:
        return ""
    m = _LI_JOB_RE.search(raw)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    base = raw.split("#", 1)[0].split("?", 1)[0]
    return base.rstrip("/").lower()


def _normalize_title(title: str) -> str:
    """Canonical title — must match jd_scraper._normalize_title so cross-scan
    near-dup detection catches Workday tile vs. LinkedIn /jobs/view/<id>
    of the same role."""
    t = (title or "").lower()
    t = re.sub(r"\s*\(\s*\d{3,6}\s*\)\s*$", "", t)
    t = re.sub(
        r"\s*\((hybrid|remote|on[- ]?site|contract|temporary|permanent|"
        r"full[- ]?time|part[- ]?time|\d+\s*month\s*contract)\)\s*",
        " ", t)
    t = re.sub(r"[-–—,]\s*(toronto|ontario|gta|canada)[^a-z]*$", "", t)
    # Seniority/abbreviation expansions: "Sr."/"Sr"/"Snr" → senior, "Vice
    # President" → vp, "&" → and. Catches Workday-vs-LinkedIn pairs that
    # picked different conventions (e.g. Citi posts the same role as
    # "Sr Analyst - AVP" and "Senior Analyst - Assistant Vice President").
    t = re.sub(r"\bsr\.?(?=\s|$)", "senior", t)
    t = re.sub(r"\bsnr(?=\s|$)", "senior", t)
    t = re.sub(r"\bassistant\s+vice[\s\-]+president\b", "avp", t)
    t = re.sub(r"\bvice[\s\-]+president\b", "vp", t)
    t = t.replace("&", "and")
    t = re.sub(r"[,/\-–—_]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _ct_key(company: str, title: str) -> tuple[str, str] | None:
    """Near-dup key: (canonical_brand_token, normalized_title).

    Brand canonicalization (via brand_aliases.canonical_brand) collapses
    "BMO" / "Bank of Montreal" / "BMO Financial Group" / "BMO Capital Markets"
    onto the same key, so the same role posted via Workday and a LinkedIn
    alert merges into one row. Without this, the gmail/scrape "both" count
    stays structurally near-zero.
    """
    co = canonical_brand(company)
    nt = _normalize_title(title)
    if not co or not nt:
        return None
    return (co, nt)


# ---------------------------------------------------------------------------
# Input discovery
# ---------------------------------------------------------------------------
def latest_web_scan() -> Path | None:
    """The freshest scan_<date>.json that's a real web scrape (not Gmail,
    not legacy merge artifacts, not the in-progress checkpoint)."""
    files = sorted(OUT_DIR.glob("scan_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if "_scored" in f.name:
            continue
        if any(t in f.name for t in _NON_SCRAPE_PATTERNS):
            continue
        return f
    return None


def recent_gmail_scans(window_days: int = GMAIL_WINDOW_DAYS) -> list[Path]:
    """All scan_gmail_*.json from the last `window_days`, newest first."""
    cutoff = datetime.now().timestamp() - (window_days * 86400)
    files = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    return [f for f in files if f.stat().st_mtime >= cutoff]


def _read_envelope(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Legacy file quarantine — runs on every rebuild, idempotent
# ---------------------------------------------------------------------------
def _collision_safe_move(src: Path, dst: Path) -> bool:
    """Move src → dst, handling Windows' quirk that shutil.move raises
    when dst already exists. Strategy: if dst exists, delete it first
    (we already quarantined the older copy in a previous run, no value
    in keeping two). Returns True if moved, False on failure."""
    try:
        if dst.exists():
            dst.unlink()
        # os.replace is atomic on the same filesystem and handles
        # cross-platform behaviour better than shutil.move when paths
        # are within the same volume.
        import os
        os.replace(str(src), str(dst))
        return True
    except Exception:
        return False


def quarantine_legacy() -> dict:
    """Move legacy artifacts (scan_base_*, _merged, gmail_pool, working_set,
    pointer files) to outputs/_legacy/ so they don't shadow the new
    worklist. Returns counts. Safe to call repeatedly — only moves what's
    still there.

    Collision handling: if the legacy directory already contains a file
    of the same name (e.g. from a prior rebuild), we replace it. The
    "newer" stale file wins because the older one was already obsoleted.
    """
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    moved = []
    for name in _LEGACY_FILES:
        src = OUT_DIR / name
        if src.exists():
            if _collision_safe_move(src, LEGACY_DIR / src.name):
                moved.append(src.name)
    for pattern in _LEGACY_GLOBS:
        for src in OUT_DIR.glob(pattern):
            if _collision_safe_move(src, LEGACY_DIR / src.name):
                moved.append(src.name)
    return {"moved": moved, "count": len(moved)}


# ---------------------------------------------------------------------------
# Rebuild — the only function that writes worklist.json
# ---------------------------------------------------------------------------
def _previous_scored_urls() -> set[str]:
    """URLs that were in the LAST worklist_scored.json. Used to mark
    rows as is_new_since_last_score so a re-score can skip them (or
    so the brief can highlight 'N new since last scoring run')."""
    if not WORKLIST_SCORED.exists():
        return set()
    try:
        data = json.loads(WORKLIST_SCORED.read_text(encoding="utf-8"))
        return {norm_url(r) for r in data.get("results", []) if norm_url(r)}
    except Exception:
        return set()


def _previous_pool_first_seen() -> dict[str, str]:
    """Map url → first_seen from the existing worklist, so a row that
    was already known keeps its earliest first_seen instead of resetting
    to today every rebuild."""
    if not WORKLIST.exists():
        return {}
    try:
        data = json.loads(WORKLIST.read_text(encoding="utf-8"))
        out = {}
        for r in data.get("results", []) or []:
            u = norm_url(r)
            if u and r.get("first_seen"):
                out[u] = str(r["first_seen"])[:10]
        return out
    except Exception:
        return {}


def rebuild(quarantine: bool = True) -> dict:
    """Rebuild worklist.json from current inputs. Returns stats.

    Steps:
      1. Move legacy files to _legacy/ (one-time, idempotent).
      2. Read latest scan_<date>.json (the scrape input).
      3. Read all scan_gmail_*.json from the last GMAIL_WINDOW_DAYS.
      4. Dedup by canonical URL; tag source ("scrape" | "gmail" | "both").
      5. Also dedup by (company, normalized_title) so the same role with
         different URLs (Workday tile vs. /jobs/view/<id>) collapses.
      6. Preserve first_seen across rebuilds (via _previous_pool_first_seen).
      7. Mark is_new_since_last_score by diffing against worklist_scored.json.
      8. Write worklist.json atomically (tmp + os.replace).

    Sources stay immutable — this function never mutates the input files.
    """
    if quarantine:
        quarantine_legacy()

    web = latest_web_scan()
    gmail_files = recent_gmail_scans()

    web_env = _read_envelope(web) if web else {}
    web_rows = web_env.get("results", []) or []

    prev_first_seen = _previous_pool_first_seen()
    prev_scored = _previous_scored_urls()

    by_url: dict[str, dict] = {}
    by_ct: dict[tuple[str, str], str] = {}  # ct_key → url (for near-dup merge)

    def _add(row: dict, src: str):
        u = norm_url(row)
        if not u:
            return
        ct = _ct_key(row.get("company", ""), row.get("title", ""))
        # Near-dup collision: same (co,title) seen via a different URL.
        # Keep the existing entry but upgrade its source tag if needed.
        if ct and ct in by_ct and by_ct[ct] != u:
            existing_url = by_ct[ct]
            existing = by_url[existing_url]
            if existing["source"] != src and existing["source"] != "both":
                existing["source"] = "both"
            return
        if u in by_url:
            entry = by_url[u]
            if entry["source"] != src and entry["source"] != "both":
                entry["source"] = "both"
            return
        new_row = dict(row)
        new_row["source"] = src
        new_row["first_seen"] = (
            prev_first_seen.get(u)
            or (str(row.get("posted_date") or "")[:10])
            or _today()
        )
        new_row["in_pool_since"] = prev_first_seen.get(u) or _today()
        by_url[u] = new_row
        if ct:
            by_ct[ct] = u

    for r in web_rows:
        _add(r, "scrape")
    # Gmail rows from older scans pre-date the parser cleanup pass. Run them
    # through _clean_alert_fields here so dedup keys match the post-fix scrape
    # rows (e.g. "BMO · Toronto, ON" → "BMO"). New scans are already clean at
    # parse time but a defensive pass is cheap and keeps replay consistent.
    try:
        from gmail_reader import _clean_alert_fields  # type: ignore
    except ImportError:
        try:
            from .gmail_reader import _clean_alert_fields  # type: ignore
        except Exception:
            _clean_alert_fields = None
    # Older scan_gmail_*.json files also pre-date the geo gate that
    # gmail_fetch.py now applies at parse time. Re-apply it here so legacy
    # rows (Raleigh / Chicago / NYC) don't leak into the pool on rebuild.
    try:
        from location_filter import keep_for_toronto_pipeline as _geo_keep  # type: ignore
    except ImportError:
        try:
            from .location_filter import keep_for_toronto_pipeline as _geo_keep  # type: ignore
        except Exception:
            _geo_keep = None
    geo_dropped = 0
    for gp in gmail_files:
        for r in _read_envelope(gp).get("results", []) or []:
            if _clean_alert_fields is not None:
                t, c, l = _clean_alert_fields(
                    r.get("title", ""), r.get("company", ""),
                    r.get("location", ""))
                r = {**r, "title": t, "company": c, "location": l}
            if _geo_keep is not None and not _geo_keep(r.get("location") or ""):
                geo_dropped += 1
                continue
            _add(r, "gmail")

    rows: list[dict] = []
    stats = {"scrape": 0, "gmail": 0, "both": 0, "total": 0,
             "new_since_last_score": 0,
             "gmail_geo_dropped": geo_dropped}
    for u, r in by_url.items():
        r["is_new_since_last_score"] = (u not in prev_scored)
        if r["is_new_since_last_score"]:
            stats["new_since_last_score"] += 1
        stats[r["source"]] = stats.get(r["source"], 0) + 1
        rows.append(r)
    stats["total"] = len(rows)

    envelope = {
        "version": 1,
        "scan_date": _today(),
        "rebuilt_at": datetime.now().isoformat(timespec="seconds"),
        "source": "worklist",
        "sources": {
            "scrape": web.name if web else None,
            "gmail_window_days": GMAIL_WINDOW_DAYS,
            "gmail_files_indexed": [p.name for p in gmail_files],
        },
        "stats": stats,
        # dedup_stats kept for back-compat with funnel UI
        "dedup_stats": {
            "input": len(web_rows) + sum(
                len(_read_envelope(p).get("results", []) or [])
                for p in gmail_files
            ),
            "output": stats["total"],
            "dropped_url": 0, "dropped_near": 0,
        },
        "results": rows,
    }
    _atomic_write_json(WORKLIST, envelope)
    return stats


def _atomic_write_json(path: Path, data: dict) -> None:
    """tmp-file-and-replace so a crash mid-write can't truncate worklist.json
    (which the scorer might be reading concurrently)."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".",
                                suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public read API — every consumer goes through these
# ---------------------------------------------------------------------------
def effective_scan() -> Path | None:
    """The file the scorer should read. Always worklist.json once it exists.
    Returns None if no inputs have been seen yet (first-time setup)."""
    if WORKLIST.exists():
        return WORKLIST
    # Bootstrap path: no rebuild has happened yet, but the user has a scan.
    web = latest_web_scan()
    if web:
        return web
    return None


def effective_scored() -> Path | None:
    """The file auto_promote should read. worklist_scored.json or None."""
    return WORKLIST_SCORED if WORKLIST_SCORED.exists() else None


def status() -> dict:
    """Cheap snapshot for UI. Doesn't trigger a rebuild."""
    out = {
        "worklist_exists": WORKLIST.exists(),
        "worklist_scored_exists": WORKLIST_SCORED.exists(),
        "latest_web_scan": (latest_web_scan().name
                             if latest_web_scan() else None),
        "recent_gmail_count": len(recent_gmail_scans()),
        "stats": None,
    }
    if WORKLIST.exists():
        env = _read_envelope(WORKLIST)
        out["stats"] = env.get("stats")
        out["rebuilt_at"] = env.get("rebuilt_at")
    return out


if __name__ == "__main__":
    # CLI: `python worklist.py` rebuilds and prints stats.
    s = rebuild()
    print(f"Worklist rebuilt: {s['total']} rows "
          f"({s['scrape']} scrape, {s['gmail']} gmail, {s['both']} both) "
          f"· {s['new_since_last_score']} new since last score")
