"""Multi-sheet xlsx export of every pipeline stage for a given scan date.

Each sheet is one stage of the pipeline. Saber uses this to give the agent
feedback on which roles got dropped where and why — silent drops in the scrape
title/geo filters or the Stage-1 triage are otherwise invisible.

Public entry point: `build_audit_pack(scan_date) -> bytes`. Returns the xlsx
file bytes (so the UI can hand it to st.download_button without a temp file).
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).parent / "outputs"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _latest_matching(pattern: str) -> Path | None:
    files = sorted(OUT_DIR.glob(pattern),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _scan_path(scan_date: str | None) -> Path | None:
    """`scan_date` is YYYYMMDD or None for latest. Returns scan_*.json path."""
    if not scan_date or scan_date == "latest":
        files = sorted(
            [p for p in OUT_DIR.glob("scan_*.json")
             if "_scored" not in p.name
             and "scan_gmail_" not in p.name
             and "scan_checkpoint" not in p.name],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        return files[0] if files else None
    p = OUT_DIR / f"scan_{scan_date}.json"
    return p if p.exists() else None


def _gmail_paths(scan_date: str | None, days: int = 7) -> list[Path]:
    """All gmail scan files in the same window as `scan_date`."""
    files = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return []
    if scan_date and scan_date != "latest":
        return [p for p in files if scan_date in p.name]
    return files[:days]


def _promote_paths(scan_date: str | None) -> tuple[Path | None, Path | None]:
    """Return (md_path, json_path) for the report. JSON may not exist for old runs."""
    if not scan_date or scan_date == "latest":
        md = _latest_matching("promote_report_*.md")
    else:
        md = OUT_DIR / f"promote_report_{scan_date}.md"
        if not md.exists():
            md = None
    if md is None:
        return None, None
    js = md.with_suffix(".json")
    return md, (js if js.exists() else None)


def _df_from_rows(rows: list[dict], columns: list[str] | None = None) -> pd.DataFrame:
    if not rows:
        df = pd.DataFrame(columns=columns or [])
        return df
    df = pd.DataFrame(rows)
    if columns:
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        df = df[columns]
    return df


def _truncate_str_cells(df: pd.DataFrame, max_len: int = 32000) -> pd.DataFrame:
    """Excel cells are capped at 32767 chars. Long JD blobs in some sources can
    exceed that and crash openpyxl mid-write."""
    if df.empty:
        return df
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(
            lambda v: (v[:max_len] + "…[truncated]")
            if isinstance(v, str) and len(v) > max_len else v
        )
    return df


def build_audit_pack(scan_date: str | None = None) -> bytes:
    """Return xlsx bytes for the given scan date (YYYYMMDD) or 'latest'.

    Sheets emitted (any with no data are still written so the structure is
    discoverable):
      Summary, Scrape raw, Scrape title drops, Scrape geo drops, Gmail raw,
      Worklist pool, Worklist merges, Stage-1 drops, Scored, Promote skips,
      Promoted (new entries).
    """
    scan_path = _scan_path(scan_date)
    scan_env = _read_json(scan_path) if scan_path else {}
    if scan_path and (not scan_date or scan_date == "latest"):
        # Resolve "latest" to its actual stamp so promote/scored lookups match.
        scan_date = scan_env.get("scan_date") or scan_path.stem.replace("scan_", "")

    gmail_paths = _gmail_paths(scan_date)

    worklist_path = OUT_DIR / "worklist.json"
    worklist_env = _read_json(worklist_path)

    scored_path = OUT_DIR / "worklist_scored.json"
    scored_env = _read_json(scored_path)

    promote_md_path, promote_json_path = _promote_paths(scan_date)
    promote_env = _read_json(promote_json_path) if promote_json_path else {}

    # ── Summary sheet ────────────────────────────────────────────────────────
    summary_rows = [
        ("Scan date", scan_date or "(none)"),
        ("Scan source file", scan_path.name if scan_path else "—"),
        ("Generated at", datetime.now().isoformat(timespec="seconds")),
        ("", ""),
        ("Scrape — companies scanned", scan_env.get("companies_scanned", "—")),
        ("Scrape — raw rows kept", len(scan_env.get("results", []))),
        ("Scrape — title drops",
         len((scan_env.get("filter_drops") or {}).get("title", []))),
        ("Scrape — geo drops",
         len((scan_env.get("filter_drops") or {}).get("geo", []))),
        ("", ""),
        ("Gmail files indexed", len(gmail_paths)),
        ("Gmail rows total",
         sum(len(_read_json(p).get("results", [])) for p in gmail_paths)),
        ("", ""),
        ("Worklist pool size",
         len(worklist_env.get("results", []))),
        ("Worklist merges (exact + near)",
         len(worklist_env.get("merged_pairs", []))),
        ("", ""),
        ("Scored — Stage-1 passed", scored_env.get("stage1_passed", "—")),
        ("Scored — Stage-1 dropped", scored_env.get("stage1_dropped", "—")),
        ("Scored — Stage-2 final rows",
         len(scored_env.get("results", []))),
        ("", ""),
        ("Promote — added", (promote_env.get("summary") or {}).get("added", "—")),
        ("Promote — skipped (verdict)",
         (promote_env.get("summary") or {}).get("skipped_verdict", "—")),
        ("Promote — skipped (score)",
         (promote_env.get("summary") or {}).get("skipped_score", "—")),
        ("Promote — skipped (geo)",
         (promote_env.get("summary") or {}).get("skipped_geo", "—")),
        ("Promote — skipped (dupe)",
         (promote_env.get("summary") or {}).get("skipped_dupe", "—")),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=["Metric", "Value"])

    # ── Scrape sheets ────────────────────────────────────────────────────────
    scrape_raw_df = _df_from_rows(
        scan_env.get("results", []),
        columns=["sector", "company", "title", "location", "source",
                 "posted_date", "found_at", "newly_seen", "link"],
    )
    title_drops_df = _df_from_rows(
        (scan_env.get("filter_drops") or {}).get("title", []),
        columns=["sector", "company", "title", "location", "source",
                 "matched_terms", "link"],
    )
    geo_drops_df = _df_from_rows(
        (scan_env.get("filter_drops") or {}).get("geo", []),
        columns=["sector", "company", "title", "location", "source", "link"],
    )

    # ── Gmail sheet — concat all matching scan_gmail_*.json ──────────────────
    gmail_rows: list[dict] = []
    for gp in gmail_paths:
        env = _read_json(gp)
        for r in env.get("results", []) or []:
            gmail_rows.append({**r, "_source_file": gp.name})
    gmail_df = _df_from_rows(
        gmail_rows,
        columns=["company", "title", "location", "posted_date",
                 "source", "_source_file", "link"],
    )

    # ── Worklist pool + merges ───────────────────────────────────────────────
    worklist_df = _df_from_rows(
        worklist_env.get("results", []),
        columns=["sector", "company", "title", "location", "source",
                 "first_seen", "in_pool_since", "is_new_since_last_score",
                 "posted_date", "link"],
    )
    merges_df = _df_from_rows(
        worklist_env.get("merged_pairs", []),
        columns=["company", "title", "reason", "kept_source",
                 "dropped_source", "kept_url", "dropped_url"],
    )

    # ── Scored + Stage-1 drops ───────────────────────────────────────────────
    scored_rows = []
    for r in scored_env.get("results", []) or []:
        f = r.get("fit") or {}
        scored_rows.append({
            "company": r.get("company", ""),
            "title": r.get("title", ""),
            "location": r.get("location", ""),
            "fit_verdict": f.get("fit_verdict", ""),
            "fit_score": f.get("fit_score", ""),
            "fit_notes": f.get("fit_notes", ""),
            "stage1_score": (r.get("_triage") or {}).get("score", ""),
            "source": r.get("source", ""),
            "link": r.get("link", ""),
        })
    scored_df = _df_from_rows(
        scored_rows,
        columns=["company", "title", "location", "fit_verdict", "fit_score",
                 "fit_notes", "stage1_score", "source", "link"],
    )

    stage1_drops = []
    for d in scored_env.get("triage_drops", []) or []:
        bd = d.get("hits_breakdown") or {}
        stage1_drops.append({
            "company": d.get("company", ""),
            "title": d.get("title", ""),
            "score": d.get("score", ""),
            "rule_reasons": "; ".join(d.get("rule_reasons", []) or []),
            "strong": ",".join(bd.get("strong", []) or []),
            "medium": ",".join(bd.get("medium", []) or []),
            "weak": ",".join(bd.get("weak", []) or []),
            "level": ",".join(bd.get("level", []) or []),
            "source": d.get("source", ""),
            "link": d.get("link", ""),
        })
    stage1_df = _df_from_rows(
        stage1_drops,
        columns=["company", "title", "score", "rule_reasons",
                 "strong", "medium", "weak", "level", "source", "link"],
    )

    # ── Promote skips + new entries ──────────────────────────────────────────
    promote_skips_df = _df_from_rows(
        promote_env.get("skipped_rows", []),
        columns=["reason", "company", "title", "location", "score",
                 "verdict", "note", "url"],
    )
    promoted_df = _df_from_rows(
        promote_env.get("new_entries", []),
        columns=["id", "tier", "score", "sector", "company", "title", "url"],
    )

    # ── Write workbook ───────────────────────────────────────────────────────
    sheets: list[tuple[str, pd.DataFrame]] = [
        ("Summary", summary_df),
        ("Scrape raw", scrape_raw_df),
        ("Scrape title drops", title_drops_df),
        ("Scrape geo drops", geo_drops_df),
        ("Gmail raw", gmail_df),
        ("Worklist pool", worklist_df),
        ("Worklist merges", merges_df),
        ("Stage-1 drops", stage1_df),
        ("Scored", scored_df),
        ("Promote skips", promote_skips_df),
        ("Promoted", promoted_df),
    ]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets:
            _truncate_str_cells(df).to_excel(xw, sheet_name=name, index=False)
    return buf.getvalue()


def list_available_scans() -> list[dict]:
    """For the UI: enumerate per-run audit candidates (newest first)."""
    out = []
    for p in sorted(OUT_DIR.glob("scan_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        if "_scored" in p.name or "scan_gmail_" in p.name or "checkpoint" in p.name:
            continue
        env = _read_json(p)
        out.append({
            "scan_date": env.get("scan_date") or p.stem.replace("scan_", ""),
            "file": p.name,
            "rows": len(env.get("results", [])),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return out


# ---------------------------------------------------------------------------
# Per-artifact xlsx builders — invoked from the inline download buttons next
# to each pipeline action (Gmail/scrape/score/promote). Keeps each click cheap
# (~50KB-2MB) vs. the full multi-sheet pack (~300KB-5MB).
# ---------------------------------------------------------------------------


def _single_sheet_xlsx(df: pd.DataFrame, sheet_name: str) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _truncate_str_cells(df).to_excel(xw, sheet_name=sheet_name, index=False)
    return buf.getvalue()


def gmail_scan_to_xlsx(path: Path) -> bytes:
    """xlsx for one scan_gmail_<stamp>.json — full input-output funnel.

    Sheets:
      Summary       — funnel counts (alerts seen → parsed → kept after each
                      filter), so the user can see exactly where rows went.
      Kept rows     — the rows that survived all filters; what the worklist
                      and scorer actually see.
      Geo drops     — rows dropped because location was outside the Toronto
                      pipeline (Raleigh, NYC, BC, etc.). Includes the raw
                      location string and link so user can spot-check.
      Quarantined   — rows the parser-regression guard rejected (title
                      starts with company prefix). Empty on healthy runs.
    """
    env = _read_json(path)
    diag = env.get("harvest_diagnostics") or {}

    kept_rows = env.get("results", []) or []
    geo_rows = diag.get("geo_dropped_rows", []) or []
    quarantine_rows = diag.get("quarantine", []) or []

    # ── Summary funnel ────────────────────────────────────────────────────
    summary = [
        ("Source file", path.name),
        ("Scan timestamp", env.get("scan_timestamp", "—")),
        ("Days window", diag.get("days_window", "—")),
        ("", ""),
        ("─── INPUT ───", ""),
        ("IMAP messages matched", diag.get("imap_messages_matched", "—")),
        ("LinkedIn alerts seen", diag.get("linkedin_alerts_seen", "—")),
        ("Digests with rows", diag.get("digests_with_rows", "—")),
        ("Digests with zero rows (parse miss)",
         diag.get("digests_without_rows", "—")),
        ("Rows extracted by parser", diag.get("rows_parsed", "—")),
        ("", ""),
        ("─── FILTERS ───", ""),
        ("Quarantined (parser-regression guard)", len(quarantine_rows)),
        ("Geo-dropped (outside Toronto pipeline)", len(geo_rows)),
        ("", ""),
        ("─── OUTPUT ───", ""),
        ("Kept rows (passed all filters)", len(kept_rows)),
    ]
    summary_df = pd.DataFrame(summary, columns=["Metric", "Value"])

    # ── Kept rows (the survivors) ─────────────────────────────────────────
    kept_df = _df_from_rows(
        kept_rows,
        columns=["company", "title", "location", "posted_date",
                 "source", "sector", "gmail_uid", "link"],
    )

    # ── Geo drops ─────────────────────────────────────────────────────────
    geo_df = _df_from_rows(
        geo_rows,
        columns=["company", "title", "location", "posted_date",
                 "source", "gmail_uid", "drop_reason", "link"],
    )

    # ── Quarantined (parser regression) ───────────────────────────────────
    q_df = _df_from_rows(
        quarantine_rows,
        columns=["company", "title", "reason", "link"],
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in [("Summary", summary_df),
                         ("Kept rows", kept_df),
                         ("Geo drops", geo_df),
                         ("Quarantined", q_df)]:
            _truncate_str_cells(df).to_excel(xw, sheet_name=name, index=False)
    return buf.getvalue()


def scan_to_xlsx(path: Path) -> bytes:
    """xlsx for one scan_<stamp>.json — three sheets: results + title/geo drops."""
    env = _read_json(path)
    rows_df = _df_from_rows(
        env.get("results", []),
        columns=["sector", "company", "title", "location", "source",
                 "posted_date", "found_at", "newly_seen", "keyword_hit", "link"],
    )
    title_df = _df_from_rows(
        (env.get("filter_drops") or {}).get("title", []),
        columns=["sector", "company", "title", "location", "source",
                 "matched_terms", "link"],
    )
    geo_df = _df_from_rows(
        (env.get("filter_drops") or {}).get("geo", []),
        columns=["sector", "company", "title", "location", "source", "link"],
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in [("Scrape rows", rows_df),
                         ("Title drops", title_df),
                         ("Geo drops", geo_df)]:
            _truncate_str_cells(df).to_excel(xw, sheet_name=name, index=False)
    return buf.getvalue()


def scored_to_xlsx(path: Path) -> bytes:
    """xlsx for worklist_scored.json — Scored sheet + Stage-1 drops sheet."""
    env = _read_json(path)
    scored_rows = []
    for r in env.get("results", []) or []:
        f = r.get("fit") or {}
        scored_rows.append({
            "company": r.get("company", ""),
            "title": r.get("title", ""),
            "location": r.get("location", ""),
            "fit_verdict": f.get("fit_verdict", ""),
            "fit_score": f.get("fit_score", ""),
            "tier": f.get("tier", ""),
            "summary": f.get("summary", ""),
            "top_3_reasons": "; ".join(f.get("top_3_reasons", []) or []),
            "skill_gaps": "; ".join(f.get("skill_gaps", []) or []),
            "stage1_score": (r.get("_triage") or {}).get("score", ""),
            "source": r.get("source", ""),
            "link": r.get("link", ""),
        })
    scored_df = _df_from_rows(
        scored_rows,
        columns=["company", "title", "location", "fit_verdict", "fit_score",
                 "tier", "summary", "top_3_reasons", "skill_gaps",
                 "stage1_score", "source", "link"],
    )
    s1_rows = []
    for d in env.get("triage_drops", []) or []:
        bd = d.get("hits_breakdown") or {}
        s1_rows.append({
            "company": d.get("company", ""),
            "title": d.get("title", ""),
            "score": d.get("score", ""),
            "rule_reasons": "; ".join(d.get("rule_reasons", []) or []),
            "strong": ",".join(bd.get("strong", []) or []),
            "medium": ",".join(bd.get("medium", []) or []),
            "weak": ",".join(bd.get("weak", []) or []),
            "level": ",".join(bd.get("level", []) or []),
            "source": d.get("source", ""),
            "link": d.get("link", ""),
        })
    s1_df = _df_from_rows(
        s1_rows,
        columns=["company", "title", "score", "rule_reasons", "strong",
                 "medium", "weak", "level", "source", "link"],
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _truncate_str_cells(scored_df).to_excel(xw, sheet_name="Scored", index=False)
        _truncate_str_cells(s1_df).to_excel(xw, sheet_name="Stage-1 drops", index=False)
    return buf.getvalue()


def worklist_to_xlsx(path: Path) -> bytes:
    """xlsx for worklist.json — pool sheet + merge-pairs sheet."""
    env = _read_json(path)
    pool_df = _df_from_rows(
        env.get("results", []),
        columns=["sector", "company", "title", "location", "source",
                 "first_seen", "in_pool_since", "is_new_since_last_score",
                 "posted_date", "link"],
    )
    merges_df = _df_from_rows(
        env.get("merged_pairs", []),
        columns=["company", "title", "reason", "kept_source",
                 "dropped_source", "kept_url", "dropped_url"],
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _truncate_str_cells(pool_df).to_excel(xw, sheet_name="Pool", index=False)
        _truncate_str_cells(merges_df).to_excel(xw, sheet_name="Merges", index=False)
    return buf.getvalue()


def promote_to_xlsx(json_path: Path) -> bytes:
    """xlsx for promote_report_<stamp>.json — new entries + skipped rows."""
    env = _read_json(json_path)
    new_df = _df_from_rows(
        env.get("new_entries", []),
        columns=["id", "tier", "score", "sector", "company", "title", "url"],
    )
    skip_df = _df_from_rows(
        env.get("skipped_rows", []),
        columns=["reason", "company", "title", "location", "score",
                 "verdict", "note", "url"],
    )
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        _truncate_str_cells(new_df).to_excel(xw, sheet_name="Promoted", index=False)
        _truncate_str_cells(skip_df).to_excel(xw, sheet_name="Skipped", index=False)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "latest"
    out = OUT_DIR / f"audit_pack_{target}.xlsx"
    out.write_bytes(build_audit_pack(target))
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
