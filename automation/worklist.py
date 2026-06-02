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
import sys
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

# Query params that IDENTIFY a distinct posting on a shared path. For
# non-LinkedIn URLs we strip the query (tracking noise: utm_*, refId,
# trackingId), but these must survive — e.g. Greenhouse encodes the job id
# ONLY in ?gh_jid=, so two Stripe roles on .../jobs/search?gh_jid=A vs =B are
# different postings that would otherwise collapse to one key and lose a row.
_ID_QUERY_PARAMS = ("gh_jid", "jobid", "currentjobid", "jid", "id", "lever")


def norm_url(row: dict) -> str:
    """Canonical URL for dedup. LinkedIn /jobs/view/<id> collapses tracking
    redirects to the bare job id; everything else strips query/fragment
    and normalizes case + trailing slash — but PRESERVES identity query
    params (gh_jid, jobId, currentJobId, …) so distinct postings sharing a
    path stay distinct."""
    raw = (row.get("link") or row.get("url") or row.get("job_url") or "").strip()
    if not raw:
        return ""
    m = _LI_JOB_RE.search(raw)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    base = raw.split("#", 1)[0]
    path, _sep, query = base.partition("?")
    norm = path.rstrip("/").lower()
    if query:
        ids = []
        for part in query.split("&"):
            k, eq, v = part.partition("=")
            if eq and v and k.lower() in _ID_QUERY_PARAMS:
                ids.append(f"{k.lower()}={v}")
        if ids:
            norm += "?" + "&".join(sorted(ids))
    return norm


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


# A normalized title made of ONLY these tokens carries no role specialization;
# it must NOT be used as a standalone near-dup key, or two genuinely different
# reqs at the same company (e.g. distinct "Senior Manager" postings) collapse
# into one. Such rows fall back to URL-only dedup (distinct LinkedIn ids stay
# distinct). Mirrors the over-merge the title-dash truncation used to cause.
_DEGENERATE_TITLES = frozenset({
    "senior manager", "manager", "director", "senior director",
    "vp", "avp", "associate", "analyst", "senior analyst",
    "risk management", "consultant", "specialist", "advisor", "lead",
    "associate director", "managing director", "officer",
})


def _is_degenerate_title(normalized_title: str) -> bool:
    """True if the normalized title is a bare seniority/role stem with no
    specialization — unsafe as a sole near-dup key."""
    return normalized_title in _DEGENERATE_TITLES


# LinkedIn-alert section headers / parser artifacts that arrive shaped like a
# job row (company field holds the header text). These are NOT jobs and must be
# dropped BEFORE the misparse-repair step, or repair would turn the header into
# a bogus company. Matched case-insensitively against the company field.
_ARTIFACT_COMPANY_PREFIXES = (
    "jobs similar to", "people also viewed", "more jobs", "similar jobs",
    "recommended for you", "jobs you may be interested in",
)


def _is_artifact_row(company: str) -> bool:
    c = (company or "").strip().lower()
    return any(c.startswith(p) for p in _ARTIFACT_COMPANY_PREFIXES)


def _is_linkedin_url(u: str) -> bool:
    """True if a canonical URL is a LinkedIn /jobs/view/<id> key — used to
    decide whether two distinct ids are genuinely different postings."""
    return u.startswith("https://www.linkedin.com/jobs/view/")


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

    # Permanent exclude-list (source-level block; distinct from triage
    # suppressions). THIS is the can't-leak chokepoint: rebuild() replays the
    # latest web scan + the last 30 days of scan_gmail_*.json on every run, so
    # without filtering HERE an excluded company's rows already sitting on disk
    # would be re-materialized into worklist.json for ~30 days after the user
    # excludes it. Snapshot loaded once (per-row is_excluded is a hot path).
    try:
        import excludes  # type: ignore
    except ImportError:
        from . import excludes  # type: ignore
    _excl = excludes.load()
    excluded_dropped = 0

    by_url: dict[str, dict] = {}
    by_ct: dict[tuple[str, str], str] = {}  # ct_key → url (for near-dup merge)
    # Audit-pack trail. Records every collision we silently merge so users can
    # see WHICH gmail/scrape URL pair collapsed into one row, with company +
    # title context. Consumed by audit_pack.py.
    merged_pairs: list[dict] = []
    # Disposition row-lists (audit fix): every dropped row is RETAINED as a
    # record so the worklist reconciles exactly (input == kept + every drop
    # bucket) and the 3-sheet export can show real rows, not just counts.
    excluded_rows: list[dict] = []     # blocked by the permanent exclude-list
    geo_rows: list[dict] = []          # outside the Toronto/Canada-remote gate
    no_url_dropped: list[dict] = []    # no canonical URL (was a silent drop)

    def _add(row: dict, src: str):
        u = norm_url(row)
        if not u:
            # No canonical URL → previously dropped with NO trace. Retain it as
            # a record so the row is auditable and the funnel reconciles.
            no_url_dropped.append({
                "company": row.get("company", ""),
                "title": row.get("title", ""),
                "link": (row.get("link") or row.get("url")
                         or row.get("job_url") or ""),
                "source": src,
                "reason": "no_canonical_url",
            })
            return
        ct = _ct_key(row.get("company", ""), row.get("title", ""))
        nt = _normalize_title(row.get("title", ""))
        # Near-dup collision: same (co,title) seen via a different URL.
        # Keep the existing entry but upgrade its source tag if needed.
        if ct and ct in by_ct and by_ct[ct] != u:
            existing_url = by_ct[ct]
            existing = by_url[existing_url]
            # REVERSIBILITY GUARD (audit fix #3): if BOTH rows are distinct
            # LinkedIn job ids AND the title is a degenerate stem (no
            # specialization), they are NOT safely the same role — keep both
            # rather than silently dropping the second. Distinct reqs with only
            # a bare "Senior Manager" title must not collapse.
            if (_is_degenerate_title(nt)
                    and _is_linkedin_url(u) and _is_linkedin_url(existing_url)):
                pass  # fall through to insert as a separate row
            else:
                merged_pairs.append({
                    "kept_url": existing_url,
                    "kept_source": existing.get("source", ""),
                    "kept_title": existing.get("title", ""),
                    "dropped_url": u,
                    "dropped_source": src,
                    "dropped_title": row.get("title", ""),
                    "company": row.get("company", ""),
                    "title": row.get("title", ""),
                    "reason": "near_dup_company_title",
                })
                if existing["source"] != src and existing["source"] != "both":
                    existing["source"] = "both"
                return
        if u in by_url:
            entry = by_url[u]
            merged_pairs.append({
                "kept_url": u,
                "kept_source": entry.get("source", ""),
                "kept_title": entry.get("title", ""),
                "dropped_url": u,
                "dropped_source": src,
                "dropped_title": row.get("title", ""),
                "company": row.get("company", ""),
                "title": row.get("title", ""),
                "reason": "exact_url",
            })
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
        # Only claim the ct_key for future near-dup merges when the title is
        # specific. A degenerate stem must not "own" the key, or the next
        # distinct role at this company would merge into it.
        if ct and not _is_degenerate_title(nt):
            by_ct[ct] = u

    for r in web_rows:
        if excludes.is_excluded(r.get("company"), _excl):
            excluded_rows.append({
                "company": r.get("company", ""), "title": r.get("title", ""),
                "link": r.get("link", ""), "source": "scrape",
                "reason": "excluded_company",
            })
            continue
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
    quarantine_dropped: list[dict] = []  # unrepairable misparse / artifacts
    repaired_count = 0
    for gp in gmail_files:
        for r in _read_envelope(gp).get("results", []) or []:
            if _clean_alert_fields is not None:
                t, c, l = _clean_alert_fields(
                    r.get("title", ""), r.get("company", ""),
                    r.get("location", ""))
                r = {**r, "title": t, "company": c, "location": l}
            _c = (r.get("company") or "").strip()
            _t = (r.get("title") or "").strip()
            # Parser-artifact rows (LinkedIn section headers like "Jobs similar
            # to …") arrive shaped like a job with the header in `company`.
            # They are NOT jobs — drop BEFORE repair so we never fabricate a
            # company out of a header.
            if _is_artifact_row(_c):
                quarantine_dropped.append({
                    "source_file": gp.name, "company": _c, "title": _t,
                    "link": r.get("link", ""), "reason": "parser_artifact",
                })
                continue
            # MISPARSE REPAIR (audit fix #1): the May-2026 corruption swaps the
            # fields — `company` holds the ROLE and `title` is "<role> <RealCo>"
            # (e.g. company="Treasury Manager", title="Treasury Manager KOHO").
            # The real company is the trailing remainder of the title. Recover
            # it and re-add the role rather than discarding ~119 genuine jobs.
            if (len(_c) > 5 and _t.startswith(_c)
                    and len(_t) > len(_c) + 2):
                real_company = _t[len(_c):].strip(" -–—·,|").strip()
                # Repair only if the recovered company looks like a real
                # company (short-ish, not itself a role stem). Otherwise the
                # row is genuinely corrupt — quarantine it.
                if (real_company
                        and len(real_company) <= 60
                        and not _is_degenerate_title(_normalize_title(real_company))):
                    r = {**r, "company": real_company, "title": _c}
                    _c = real_company
                    repaired_count += 1
                else:
                    quarantine_dropped.append({
                        "source_file": gp.name, "company": _c, "title": _t,
                        "link": r.get("link", ""), "reason": "misparse_unrepairable",
                    })
                    continue
            if _geo_keep is not None and not _geo_keep(r.get("location") or ""):
                geo_rows.append({
                    "company": _c, "title": _t, "link": r.get("link", ""),
                    "location": r.get("location", ""), "source": "gmail",
                    "reason": "outside_geo",
                })
                continue
            # Exclude-list check AFTER _clean_alert_fields so canonicalization
            # sees the cleaned company name (e.g. "BMO · Toronto, ON" → "BMO").
            if excludes.is_excluded(r.get("company"), _excl):
                excluded_rows.append({
                    "company": _c, "title": _t, "link": r.get("link", ""),
                    "source": "gmail", "reason": "excluded_company",
                })
                continue
            _add(r, "gmail")
    if repaired_count:
        print(f"[worklist] repaired {repaired_count} misparsed gmail row(s) "
              f"(recovered company from swapped title field)", file=sys.stderr)
    if quarantine_dropped:
        print(f"[worklist] quarantined {len(quarantine_dropped)} unrepairable "
              f"gmail row(s) — see quarantine in worklist.json", file=sys.stderr)

    rows: list[dict] = []
    geo_dropped = len(geo_rows)
    excluded_dropped = len(excluded_rows)
    stats = {"scrape": 0, "gmail": 0, "both": 0, "total": 0,
             "new_since_last_score": 0,
             "gmail_geo_dropped": geo_dropped,
             "excluded_dropped": excluded_dropped,
             "repaired": repaired_count}
    for u, r in by_url.items():
        r["is_new_since_last_score"] = (u not in prev_scored)
        if r["is_new_since_last_score"]:
            stats["new_since_last_score"] += 1
        stats[r["source"]] = stats.get(r["source"], 0) + 1
        rows.append(r)
    stats["total"] = len(rows)

    # Total input = every raw row read from sources. Counted directly from the
    # disposition buckets (every input row lands in exactly one) so the figure
    # is self-consistent with what we retained — no re-reading the files.
    input_total = (len(web_rows)
                   + sum(len(_read_envelope(p).get("results", []) or [])
                         for p in gmail_files))
    # RECONCILIATION (audit guarantee): every input row must land in exactly one
    # disposition bucket. If accounted != input, a silent-loss path exists.
    accounted = (stats["total"] + len(merged_pairs) + len(quarantine_dropped)
                 + geo_dropped + excluded_dropped + len(no_url_dropped))
    reconciliation = {
        "input": input_total,
        "kept": stats["total"],
        "merged": len(merged_pairs),
        "quarantined": len(quarantine_dropped),
        "geo_dropped": geo_dropped,
        "excluded": excluded_dropped,
        "no_url_dropped": len(no_url_dropped),
        "repaired": repaired_count,
        "accounted": accounted,
        "balanced": accounted == input_total,
        "unaccounted": input_total - accounted,
    }
    if not reconciliation["balanced"]:
        print(f"[worklist] WARNING: reconciliation off by "
              f"{reconciliation['unaccounted']} row(s) "
              f"(input={input_total}, accounted={accounted}) — a disposition "
              f"path is losing rows silently.", file=sys.stderr)

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
            "input": input_total,
            "output": stats["total"],
            "dropped_url": sum(1 for m in merged_pairs if m["reason"] == "exact_url"),
            "dropped_near": sum(1 for m in merged_pairs if m["reason"] == "near_dup_company_title"),
        },
        # Full disposition ledger — every input row is in results[] or exactly
        # one of these lists. reconciliation.balanced proves no silent loss.
        "reconciliation": reconciliation,
        "merged_pairs": merged_pairs,
        # Misparse quarantine: unrepairable corruption + parser artifacts.
        # Empty list on healthy runs. (Repairable field-swaps are now FIXED
        # and re-added to results[], not dropped here.)
        "quarantine": quarantine_dropped,
        # Rows blocked by the permanent company exclude-list (retained for audit).
        "excluded": excluded_rows,
        # Rows dropped by the Toronto/Canada-remote geo gate (retained for audit).
        "geo_dropped": geo_rows,
        # Rows with no canonical URL — formerly a silent drop, now traceable.
        "no_url_dropped": no_url_dropped,
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
