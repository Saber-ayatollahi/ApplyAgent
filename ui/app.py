"""Saber's Job Search — Streamlit Dashboard.

Run:
    streamlit run ui/app.py

Agentic pipeline:  Scrape -> Score -> Triage -> Promote -> Tailor
One page, one flow. Background execution via ui/scan_runner.py.
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_runner  # noqa: E402
import api_key  # noqa: E402

# Ensure stored key is in env before anything launches a subprocess
api_key.hydrate_env()

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "job_tracker_data.json"
CRM = ROOT / "recruiter_crm.json"
OUT_DIR = ROOT / "automation" / "outputs"
RUNS_DIR = OUT_DIR / "runs"
PIPELINE_DIR = OUT_DIR / "pipelines"


# ----------------------------- helpers ------------------------------------
@st.cache_data(ttl=15)
def load_tracker():
    return json.loads(TRACKER.read_text(encoding="utf-8"))


@st.cache_data(ttl=15)
def load_crm():
    if CRM.exists():
        return json.loads(CRM.read_text(encoding="utf-8"))
    return {}


def save_tracker(d: dict):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = TRACKER.with_suffix(f".bak.{stamp}.json")
    if TRACKER.exists():
        bak.write_text(TRACKER.read_text(encoding="utf-8"), encoding="utf-8")
    TRACKER.write_text(json.dumps(d, indent=2), encoding="utf-8")
    st.cache_data.clear()


def save_crm(d: dict):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = CRM.with_suffix(f".bak.{stamp}.json")
    if CRM.exists():
        bak.write_text(CRM.read_text(encoding="utf-8"), encoding="utf-8")
    CRM.write_text(json.dumps(d, indent=2), encoding="utf-8")
    st.cache_data.clear()


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def fmt_dt(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s


def human_elapsed(started_iso: str | None, end_iso: str | None = None) -> str:
    if not started_iso:
        return "—"
    try:
        start = datetime.fromisoformat(started_iso)
    except Exception:
        return "—"
    end = datetime.fromisoformat(end_iso) if end_iso else datetime.now()
    secs = int((end - start).total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


def latest_pipeline_status() -> dict | None:
    if not PIPELINE_DIR.exists():
        return None
    files = sorted(PIPELINE_DIR.glob("pipeline_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def list_pipelines(limit: int = 20) -> list[dict]:
    if not PIPELINE_DIR.exists():
        return []
    files = sorted(PIPELINE_DIR.glob("pipeline_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def latest_scan() -> Path | None:
    files = sorted(OUT_DIR.glob("scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    files = [f for f in files if "_scored" not in f.name]
    return files[0] if files else None


def latest_scored() -> Path | None:
    files = sorted(OUT_DIR.glob("*_scored.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


# ----------------------------- page config --------------------------------
st.set_page_config(
    page_title="ApplyAgent — Saber's Job Search",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    "🏠 Dashboard",
    "🎯 Pipeline",
    "📋 Jobs Kanban",
    "🤝 Recruiter CRM",
    "📅 Weekly Plan",
    "📝 Content & Memory",
    "⚙️ Admin",
]

# API key manager — always on top of sidebar
api_key.render_sidebar()
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", PAGES)

# Active-runs badge in sidebar
active_runs = scan_runner.active_runs()
pipe = latest_pipeline_status()
pipeline_running = pipe and pipe.get("state") == "running"

if active_runs or pipeline_running:
    st.sidebar.markdown("### 🟢 Active work")
    if pipeline_running:
        st.sidebar.caption(
            f"**Pipeline** `{pipe['pipeline_id']}` · {human_elapsed(pipe.get('started_at'))}"
        )
    for r in active_runs:
        st.sidebar.caption(
            f"**{r['label']}** · {human_elapsed(r['started_at'])} · pid {r['pid']}"
        )
else:
    st.sidebar.caption("No active runs")

st.sidebar.markdown("---")
st.sidebar.caption("Project root")
st.sidebar.code(str(ROOT), language="text")

tr = load_tracker()
crm = load_crm()
jobs = tr.get("jobs", [])
jobs_df = pd.DataFrame(jobs) if jobs else pd.DataFrame()


# ============================================================================
# 🏠 DASHBOARD
# ============================================================================
if page == "🏠 Dashboard":
    st.title("🏠 Saber's Toronto Job Search")
    meta = tr.get("meta", {})
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    targets = meta.get("weekly_kpi_targets", {})

    # Live pipeline banner
    if pipeline_running:
        st.info(
            f"🎯 **Pipeline `{pipe['pipeline_id']}` running** — "
            f"elapsed {human_elapsed(pipe['started_at'])}. "
            f"Jump to 🎯 Pipeline to watch stages.",
            icon="⚡",
        )
    elif pipe and pipe.get("state") == "finished":
        st.success(
            f"✅ Last pipeline `{pipe['pipeline_id']}` finished {fmt_dt(pipe.get('finished_at'))}. "
            f"Review in 🎯 Pipeline.",
            icon="🎯",
        )

    # KPIs
    c1, c2, c3, c4, c5 = st.columns(5)
    applied_all = [j for j in jobs if parse_date(j.get("date_applied"))]
    applied_wk = [j for j in applied_all
                  if parse_date(j.get("date_applied")) and
                  week_start <= parse_date(j["date_applied"]) <= week_end]
    outreach_wk = []
    for j in jobs:
        for log in j.get("outreach_log", []):
            d = parse_date(log.get("date"))
            if d and week_start <= d <= week_end:
                outreach_wk.append(log)
    in_process = [j for j in jobs if j.get("status") in
                  ("Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite", "Offer")]
    stale_threshold = today - timedelta(days=21)
    stale = [j for j in jobs
             if parse_date(j.get("date_applied"))
             and parse_date(j["date_applied"]) < stale_threshold
             and j.get("status") in ("Applied", "Recruiter_Screen", "Phone_Screen")]

    c1.metric("This week applied", len(applied_wk),
              delta=len(applied_wk) - targets.get("tailored_applications", 8))
    c2.metric("This week outreach", len(outreach_wk),
              delta=len(outreach_wk) - targets.get("outreach_messages", 10))
    c3.metric("Active interviews", len(in_process))
    c4.metric("Total applied", len(applied_all))
    c5.metric("Stale (>21d)", len(stale), delta_color="inverse")

    st.markdown("---")

    # Quick actions
    st.subheader("⚡ Quick actions")
    key_ok = api_key.is_key_valid()
    if not key_ok:
        st.warning(
            "⚠️ Anthropic API key missing or invalid — LLM-backed pipeline actions are disabled. "
            "Set it in the sidebar.",
            icon="🔑",
        )
    qa1, qa2, qa3 = st.columns(3)
    with qa1:
        if st.button("🎯 Run full pipeline", use_container_width=True, type="primary",
                     disabled=not key_ok,
                     help="Scrape → Score → Promote preview (one-shot agent)"):
            rec = scan_runner.start_run(
                "pipeline_full",
                [sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                 "--scrape-mode", "full"],
            )
            st.session_state["last_pipeline_run"] = rec.run_id
            st.success(f"Pipeline started (`{rec.run_id}`). Monitor in 🎯 Pipeline.")
            st.rerun()
    with qa2:
        if st.button("🏛️ Fast pipeline (ATS-only)", use_container_width=True,
                     disabled=not key_ok,
                     help="Direct Workday/Greenhouse scan + score + promote preview (~10 min)"):
            rec = scan_runner.start_run(
                "pipeline_ats",
                [sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                 "--scrape-mode", "ats"],
            )
            st.success(f"Started `{rec.run_id}`")
            st.rerun()
    with qa3:
        if st.button("📊 Weekly report", use_container_width=True):
            rec = scan_runner.start_run(
                "weekly_report",
                [sys.executable, str(ROOT / "automation" / "weekly_report.py")],
            )
            st.success(f"Started `{rec.run_id}`")
            st.rerun()

    st.markdown("---")

    # Funnel
    st.subheader("📈 Pipeline by status")
    status_counts = jobs_df["status"].value_counts() if "status" in jobs_df.columns else pd.Series()
    status_order = meta.get("status_enum", list(status_counts.index))
    fd = pd.DataFrame(
        [{"status": s, "count": int(status_counts.get(s, 0))} for s in status_order]
    )
    d1, d2 = st.columns([2, 1])
    with d1:
        st.bar_chart(fd.set_index("status"))
    with d2:
        st.dataframe(fd, hide_index=True, use_container_width=True)

    st.markdown("---")

    # Apply-this-week queue
    st.subheader("🎯 Apply this week")
    apply_ids = meta.get("kanban_targets_week1", {}).get("apply_this_week", [])
    apply_rows = jobs_df[jobs_df["id"].isin(apply_ids)] if "id" in jobs_df.columns else pd.DataFrame()
    if not apply_rows.empty:
        cols = [c for c in ["id", "company", "title", "tier", "fit_score", "osfi_hook", "url"] if c in apply_rows.columns]
        st.dataframe(apply_rows[cols], hide_index=True, use_container_width=True,
                     column_config={"url": st.column_config.LinkColumn()})
    else:
        st.caption("No roles flagged for this week.")


# ============================================================================
# 🎯 PIPELINE  — the agentic flow, end-to-end
# ============================================================================
elif page == "🎯 Pipeline":
    st.title("🎯 Agentic Pipeline")
    st.caption(
        "Scrape → Score → Triage → Promote → Tailor. "
        "One flow; one click runs the whole chain. Each stage can also be run in isolation."
    )

    # ---------- Top: pipeline stepper with live status ----------
    def _stage_card(col, emoji: str, name: str, info: dict | None,
                    data_summary: str = "", running: bool = False):
        state = (info or {}).get("state", "—")
        badge = {"running": "🟡 running", "finished": "🟢 done",
                 "failed": "🔴 failed", "skipped": "⚪ skipped",
                 "—": "⚪ —"}.get(state, state)
        col.markdown(f"#### {emoji} {name}")
        col.caption(badge)
        if info and info.get("elapsed_sec"):
            col.caption(f"⏱ {info['elapsed_sec']}s")
        if data_summary:
            col.caption(data_summary)

    # Build stage summaries from latest pipeline status + filesystem
    stages_info = (pipe or {}).get("stages", {})

    # Scrape summary
    scan_f = latest_scan()
    scrape_summary = ""
    if scan_f:
        try:
            d = json.loads(scan_f.read_text(encoding="utf-8"))
            scrape_summary = f"{len(d.get('results', []))} candidates · `{scan_f.name}`"
        except Exception:
            scrape_summary = f"`{scan_f.name}`"

    # Score summary
    scored_f = latest_scored()
    score_summary = ""
    if scored_f:
        try:
            d = json.loads(scored_f.read_text(encoding="utf-8"))
            score_summary = f"{d.get('stage2_scored', '?')} scored · `{scored_f.name}`"
        except Exception:
            score_summary = f"`{scored_f.name}`"

    # Triage (user review) — uses scored file
    triage_summary = ""
    if scored_f:
        try:
            d = json.loads(scored_f.read_text(encoding="utf-8"))
            v = {}
            for r in d.get("results", []):
                fv = (r.get("fit") or {}).get("fit_verdict", "?")
                v[fv] = v.get(fv, 0) + 1
            apply_n = v.get("apply_now", 0) + v.get("tailor_and_apply", 0)
            triage_summary = f"{apply_n} actionable (apply/tailor)"
        except Exception:
            pass

    # Promote summary — count tracker Found/Watch
    promote_summary = ""
    if jobs:
        found = sum(1 for j in jobs if j.get("status") in ("Found", "Watch"))
        applied = sum(1 for j in jobs if parse_date(j.get("date_applied")))
        promote_summary = f"{found} in tracker queue · {applied} applied"

    # Tailor summary — count tailored outputs
    tailor_summary = ""
    tailored = sorted(OUT_DIR.glob("*_prompt.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if tailored:
        tailor_summary = f"{len(tailored)} tailored docs"

    s1, s2, s3, s4, s5 = st.columns(5)
    _stage_card(s1, "🛰️", "1. Scrape", stages_info.get("scrape"), scrape_summary)
    _stage_card(s2, "🤖", "2. Score", stages_info.get("score"), score_summary)
    _stage_card(s3, "👁", "3. Triage", None, triage_summary)
    _stage_card(s4, "🚀", "4. Promote", stages_info.get("promote"), promote_summary)
    _stage_card(s5, "✏️", "5. Tailor", None, tailor_summary)

    if pipeline_running:
        st.info(
            f"⏱️ Pipeline `{pipe['pipeline_id']}` running for "
            f"{human_elapsed(pipe['started_at'])}.",
            icon="🎯",
        )

    st.markdown("---")

    # ---------- Main tabs ----------
    tabs = st.tabs(
        ["🎯 Run pipeline", "🛰️ 1·Scrape", "🤖 2·Score", "👁 3·Triage", "🚀 4·Promote", "📜 History"]
    )

    # ================== TAB: Run pipeline ==================
    with tabs[0]:
        st.subheader("Run the full agentic chain")
        st.caption("Scrape → Score → Promote-preview. Review & commit happens in the 🚀 Promote tab.")

        cA, cB = st.columns([1, 1])
        with cA:
            scrape_mode = st.selectbox(
                "Scrape strategy",
                options=["full", "core", "ats", "linkedin", "expansion"],
                format_func=lambda x: {
                    "full":      "Full — all targets + expansion (20–40 min)",
                    "core":      "Core 77 targets (15–30 min)",
                    "ats":       "Direct ATS only — Workday/Greenhouse (3–6 min)",
                    "linkedin":  "LinkedIn guest search only (15–25 min)",
                    "expansion": "Expansion list only (5–10 min)",
                }[x],
            )
            sector = st.text_input("Limit to sector (optional)", placeholder="Pension Funds")
            company = st.text_input("Limit to single company (optional)", placeholder="Scotiabank")
        with cB:
            skip_scrape = st.checkbox("Skip scrape (reuse latest scan)",
                                       help=f"Latest: {scan_f.name if scan_f else '(none)'}")
            skip_score = st.checkbox("Skip score (scrape only)")
            skip_promote = st.checkbox("Skip promote (scrape + score only)", value=True)
            score_concurrency = st.slider("Scorer concurrency", 1, 12, 6)
            score_limit = st.number_input("Score limit (0 = all)", 0, 5000, 0)
            dry_score = st.checkbox("Score dry-run (rule-stage only)")

        cmd = [sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
               "--scrape-mode", scrape_mode,
               "--score-concurrency", str(score_concurrency)]
        if sector.strip():
            cmd += ["--sector", sector.strip()]
        if company.strip():
            cmd += ["--company", company.strip()]
        if skip_scrape:
            cmd.append("--skip-scrape")
        if skip_score:
            cmd.append("--skip-score")
        if skip_promote:
            cmd.append("--skip-promote")
        if score_limit:
            cmd += ["--score-limit", str(int(score_limit))]
        if dry_score:
            cmd.append("--score-dry-run")

        st.code(" ".join(cmd), language="bash")

        # Gate: LLM-backed stages (score / promote-that-needs-scored) require a valid key.
        # Pure scrape (skip_score=True) does NOT require a key.
        needs_llm = not skip_score or not skip_promote
        key_ok_here = api_key.is_key_valid()
        can_run = not pipeline_running and (key_ok_here or not needs_llm)

        if needs_llm and not key_ok_here:
            st.warning(
                "⚠️ This pipeline run will call the Anthropic API. Set a valid key in the sidebar first, "
                "or tick **Skip score** and **Skip promote** to run scrape-only (no API needed).",
                icon="🔑",
            )

        run_col, spacer = st.columns([1, 4])
        with run_col:
            if st.button("▶️ Launch pipeline", type="primary", use_container_width=True,
                         disabled=not can_run):
                rec = scan_runner.start_run("pipeline", cmd)
                st.success(f"Pipeline launched (`{rec.run_id}`, pid {rec.pid})")
                st.rerun()

        # Live log if pipeline just launched (runner log)
        if pipeline_running or active_runs:
            st.markdown("### 📜 Live log")
            current = [r for r in active_runs if r["label"].startswith("pipeline")]
            current = current[0] if current else (active_runs[0] if active_runs else None)
            if current:
                with st.expander(f"Tailing `{current['run_id']}` — pid {current['pid']}",
                                 expanded=True):
                    st.code(scan_runner.tail_log(current["log_path"]) or "(no output yet)",
                            language="text")
                    if st.button("⏹ Stop pipeline", key="stop_pipe"):
                        scan_runner.stop_run(current["run_id"])
                        st.warning("Stop signal sent.")
                        st.rerun()
                if st.checkbox("🔄 Auto-refresh every 5s", value=True, key="pipe_auto"):
                    import time as _t
                    _t.sleep(5)
                    st.rerun()

    # ================== TAB: Scrape ==================
    with tabs[1]:
        st.subheader("Stage 1 — Scrape")
        st.caption("Pull raw job postings from LinkedIn + Workday + Greenhouse + Lever.")
        if scan_f:
            try:
                d = json.loads(scan_f.read_text(encoding="utf-8"))
                ccol1, ccol2, ccol3 = st.columns(3)
                ccol1.metric("Candidates", len(d.get("results", [])))
                ccol2.metric("Sectors", len(d.get("by_sector", {})))
                ccol3.metric("Companies", d.get("companies_scanned", "—"))
                st.caption(f"File: `{scan_f.name}` · modified "
                           f"{datetime.fromtimestamp(scan_f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}")

                # By-sector breakdown
                sb = d.get("by_sector", {})
                if sb:
                    sb_df = pd.DataFrame(sorted(sb.items(), key=lambda x: -x[1]),
                                         columns=["sector", "candidates"])
                    st.bar_chart(sb_df.set_index("sector"))

                # Sample listings
                st.markdown("**Recent candidates** (first 50)")
                rows = []
                for r in d.get("results", [])[:50]:
                    rows.append({
                        "company": r.get("company"),
                        "title": r.get("title"),
                        "sector": r.get("sector"),
                        "source": r.get("source"),
                        "location": r.get("location"),
                        "url": r.get("link"),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                             column_config={"url": st.column_config.LinkColumn()})
            except Exception as e:
                st.warning(f"Could not read {scan_f.name}: {e}")
        else:
            st.info("No scan file yet. Run the pipeline or a scrape.")

        with st.expander("Run scrape only (no score/promote)"):
            m = st.selectbox("Mode", ["full", "core", "ats", "linkedin", "expansion"],
                             key="scrape_only_mode")
            if st.button("🛰️ Scrape only", key="scrape_only_btn"):
                cmd2 = [sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                        "--scrape-mode", m, "--skip-score", "--skip-promote"]
                rec = scan_runner.start_run(f"scrape_{m}", cmd2)
                st.success(f"Started `{rec.run_id}`")

    # ================== TAB: Score ==================
    with tabs[2]:
        st.subheader("Stage 2 — Score with Claude")
        st.caption(
            "Each candidate is rated 1–10 against Saber's Master Repository. "
            "Verdicts: apply_now / tailor_and_apply / watch / skip."
        )

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.warning("No scored scans yet.")
        else:
            which = st.selectbox("Scored file", [p.name for p in scored_files], key="score_file")
            sc = json.loads((OUT_DIR / which).read_text(encoding="utf-8"))
            results = sc.get("results", [])

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Input", sc.get("total_input", "—"))
            m2.metric("Stage 1 pass", sc.get("stage1_passed", "—"))
            m3.metric("Stage 2 scored", sc.get("stage2_scored", "—"))
            verdicts: dict = {}
            for r in results:
                v = (r.get("fit") or {}).get("fit_verdict", "?")
                verdicts[v] = verdicts.get(v, 0) + 1
            m4.metric("apply_now", verdicts.get("apply_now", 0))

            st.caption(f"Scored at {sc.get('scored_at', '—')}")

            # Verdict breakdown
            if verdicts:
                v_df = pd.DataFrame(sorted(verdicts.items(), key=lambda x: -x[1]),
                                    columns=["verdict", "count"])
                st.bar_chart(v_df.set_index("verdict"))

        with st.expander("Re-score an existing scan"):
            scan_choices = [p.name for p in sorted(OUT_DIR.glob("scan_*.json"),
                                                    key=lambda p: p.stat().st_mtime,
                                                    reverse=True) if "_scored" not in p.name]
            if scan_choices:
                pick = st.selectbox("Raw scan to score", scan_choices, key="score_raw_pick")
                c1, c2, c3 = st.columns(3)
                conc = c1.number_input("Concurrency", 1, 16, 6, key="score_conc")
                lim = c2.number_input("Limit (0=all)", 0, 5000, 0, key="score_lim")
                dry = c3.checkbox("Dry run", key="score_dry")
                _key_ok_score = api_key.is_key_valid() or dry
                if not _key_ok_score:
                    st.caption("🔑 API key required (or tick Dry run for rule-stage only).")
                if st.button("🤖 Run scorer", key="score_btn", disabled=not _key_ok_score):
                    cmd3 = [sys.executable, str(ROOT / "automation" / "fit_scorer.py"),
                            "--scan", pick, "--concurrency", str(conc)]
                    if lim:
                        cmd3 += ["--limit", str(int(lim))]
                    if dry:
                        cmd3.append("--dry-run")
                    rec = scan_runner.start_run("fit_scorer", cmd3)
                    st.success(f"Started `{rec.run_id}`")

    # ================== TAB: Triage ==================
    with tabs[3]:
        st.subheader("Stage 3 — Triage scored results")
        st.caption("Review Claude's scored candidates. Filter, sort, open JDs.")

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.info("No scored scan available. Run the scorer first.")
        else:
            which = st.selectbox("Scored file", [p.name for p in scored_files], key="triage_file")
            sc = json.loads((OUT_DIR / which).read_text(encoding="utf-8"))
            results = sc.get("results", [])

            # Flatten
            rows = []
            for r in results:
                f = r.get("fit") or {}
                rows.append({
                    "fit": f.get("fit_score", 0),
                    "verdict": f.get("fit_verdict", ""),
                    "tier": f.get("tier", 4),
                    "sector": r.get("sector", ""),
                    "company": r.get("company", ""),
                    "title": r.get("title", ""),
                    "osfi": f.get("osfi_hook", ""),
                    "summary": f.get("summary", ""),
                    "gaps": ", ".join(f.get("skill_gaps") or []),
                    "source": r.get("source", ""),
                    "url": r.get("link", ""),
                })
            df = pd.DataFrame(rows).sort_values(["fit", "tier"], ascending=[False, True])

            f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
            with f1:
                min_fit = st.slider("Min fit score", 1, 10, 7, key="triage_min")
            with f2:
                verdict_filter = st.multiselect(
                    "Verdict", sorted(df["verdict"].dropna().unique()),
                    default=["apply_now", "tailor_and_apply"], key="triage_verdict")
            with f3:
                sector_filter = st.multiselect(
                    "Sector", sorted(df["sector"].dropna().unique()), key="triage_sector")
            with f4:
                search = st.text_input("Search company/title", key="triage_q")

            view = df[df["fit"] >= min_fit]
            if verdict_filter:
                view = view[view["verdict"].isin(verdict_filter)]
            if sector_filter:
                view = view[view["sector"].isin(sector_filter)]
            if search:
                sl = search.lower()
                view = view[view["company"].str.lower().str.contains(sl, na=False) |
                            view["title"].str.lower().str.contains(sl, na=False)]

            st.caption(f"Showing {len(view)} of {len(df)} scored candidates")
            st.dataframe(view, hide_index=True, use_container_width=True, height=500,
                         column_config={"url": st.column_config.LinkColumn("open")})

            # Inspect one
            if not view.empty:
                titles = [f"{r.company} — {r.title[:60]}" for r in view.itertuples()]
                idx = st.selectbox("Inspect candidate", range(len(view)),
                                    format_func=lambda i: titles[i], key="triage_pick")
                row = view.iloc[idx]
                with st.container(border=True):
                    cL, cR = st.columns([3, 1])
                    with cL:
                        st.markdown(f"### {row['company']} — {row['title']}")
                        st.caption(f"Sector: {row['sector']} · Source: {row['source']}")
                        st.markdown(f"**Verdict:** `{row['verdict']}` · "
                                    f"**Fit:** {row['fit']}/10 · **Tier:** {row['tier']}")
                        st.markdown(f"**OSFI hook:** {row['osfi'] or '—'}")
                        st.markdown(f"**Summary:** {row['summary']}")
                        if row["gaps"]:
                            st.markdown(f"**Gaps:** {row['gaps']}")
                    with cR:
                        st.link_button("🔗 Open JD", row["url"], use_container_width=True)

    # ================== TAB: Promote ==================
    with tabs[4]:
        st.subheader("Stage 4 — Promote to tracker")
        st.caption("Push scored candidates into `job_tracker_data.json`. Dry-run first; commit when ready.")

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.warning("No scored scan available.")
        else:
            which = st.selectbox("Scored file to promote", [p.name for p in scored_files],
                                 key="promote_file")
            c1, c2, c3 = st.columns(3)
            with c1:
                min_s = st.slider("Min fit score", 1, 10, 7, key="promote_min")
            with c2:
                inc_watch = st.checkbox("Include verdict=watch", key="promote_watch")
            with c3:
                expire = st.checkbox("Expire stale tracker URLs", key="promote_expire")

            preview_col, commit_col = st.columns(2)
            with preview_col:
                if st.button("👀 Preview (dry-run)", use_container_width=True, key="prom_preview"):
                    cmd4 = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                            "--scan", which, "--min-score", str(min_s)]
                    if inc_watch:
                        cmd4.append("--include-watch")
                    if expire:
                        cmd4.append("--expire-stale")
                    res = subprocess.run(cmd4, capture_output=True, text=True, cwd=str(ROOT))
                    st.code(res.stdout + "\n" + (res.stderr or ""), language="text")
            with commit_col:
                if st.button("🚀 Commit to tracker", type="primary", use_container_width=True,
                             key="prom_commit"):
                    cmd4 = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                            "--scan", which, "--min-score", str(min_s), "--commit"]
                    if inc_watch:
                        cmd4.append("--include-watch")
                    if expire:
                        cmd4.append("--expire-stale")
                    res = subprocess.run(cmd4, capture_output=True, text=True, cwd=str(ROOT))
                    st.code(res.stdout + "\n" + (res.stderr or ""), language="text")
                    st.cache_data.clear()
                    st.success("Tracker updated. Check 📋 Jobs Kanban.")

    # ================== TAB: History ==================
    with tabs[5]:
        st.subheader("📜 Pipeline run history")
        pipelines = list_pipelines(50)
        if not pipelines:
            st.caption("No pipeline runs yet.")
        else:
            rows = []
            for p in pipelines:
                stages = p.get("stages", {})
                scrape = stages.get("scrape", {})
                score = stages.get("score", {})
                promote = stages.get("promote", {})
                rows.append({
                    "pipeline_id": p.get("pipeline_id"),
                    "state": p.get("state"),
                    "started": fmt_dt(p.get("started_at")),
                    "finished": fmt_dt(p.get("finished_at")),
                    "duration": human_elapsed(p.get("started_at"), p.get("finished_at")),
                    "scrape": f"{scrape.get('state', '-')} ({scrape.get('candidate_count', '?')})",
                    "score": f"{score.get('state', '-')} ({score.get('scored_count', '?')})",
                    "promote": promote.get("state", "-"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                         height=300)

            pick_id = st.selectbox("Inspect pipeline", [p["pipeline_id"] for p in pipelines])
            sel = next((p for p in pipelines if p["pipeline_id"] == pick_id), None)
            if sel:
                st.json(sel, expanded=False)

        st.markdown("---")
        st.subheader("🛠 Background run history (scan_runner)")
        runs = scan_runner.list_runs(30)
        if runs:
            rrows = [{
                "run_id": r["run_id"],
                "label": r["label"],
                "state": r.get("state"),
                "started": fmt_dt(r.get("started_at")),
                "duration": human_elapsed(r.get("started_at"), r.get("finished_at")),
                "pid": r.get("pid"),
            } for r in runs]
            st.dataframe(pd.DataFrame(rrows), hide_index=True, use_container_width=True,
                         height=260)
            sel_run = st.selectbox("Tail log", [r["run_id"] for r in runs])
            r = next((r for r in runs if r["run_id"] == sel_run), None)
            if r:
                st.code(scan_runner.tail_log(r["log_path"], max_bytes=60_000), language="text")
        else:
            st.caption("No background runs recorded.")


# ============================================================================
# 📋 JOBS KANBAN
# ============================================================================
elif page == "📋 Jobs Kanban":
    st.title("📋 Jobs Tracker")
    st.caption("Your promoted-to-tracker roles. This is Stage 4's output — update status here.")

    if jobs_df.empty:
        st.warning("Tracker is empty.")
        st.stop()

    # Filters
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    sectors = sorted(jobs_df["sector"].dropna().unique()) if "sector" in jobs_df.columns else []
    statuses = sorted(jobs_df["status"].dropna().unique()) if "status" in jobs_df.columns else []
    fits = sorted(jobs_df["fit_score"].dropna().unique()) if "fit_score" in jobs_df.columns else []
    with f1:
        sel_sector = st.multiselect("Sector", sectors, default=[])
    with f2:
        sel_status = st.multiselect("Status", statuses, default=[])
    with f3:
        sel_fit = st.multiselect("Fit", fits, default=[])
    with f4:
        sel_tier = st.multiselect("Tier", sorted(jobs_df["tier"].dropna().unique()) if "tier" in jobs_df.columns else [])
    q = st.text_input("Search (company/title)", "")

    view = jobs_df.copy()
    if sel_sector:
        view = view[view["sector"].isin(sel_sector)]
    if sel_status:
        view = view[view["status"].isin(sel_status)]
    if sel_fit:
        view = view[view["fit_score"].isin(sel_fit)]
    if sel_tier:
        view = view[view["tier"].isin(sel_tier)]
    if q:
        qlo = q.lower()
        view = view[view["company"].str.lower().str.contains(qlo, na=False) |
                    view["title"].str.lower().str.contains(qlo, na=False)]

    st.caption(f"Showing {len(view)} of {len(jobs_df)} roles")

    cols = [c for c in ["id", "company", "title", "sector", "tier", "status",
                        "fit_score", "fit_score_numeric", "osfi_hook", "urgency",
                        "date_found", "date_applied", "url"] if c in view.columns]
    st.dataframe(
        view[cols].sort_values(["tier", "fit_score_numeric"], ascending=[True, False])
        if "fit_score_numeric" in cols else view[cols],
        hide_index=True, use_container_width=True, height=500,
        column_config={"url": st.column_config.LinkColumn()},
    )

    st.markdown("---")
    st.subheader("Inspect / edit a single role")
    if len(view):
        sel_id = st.selectbox("Choose role id", view["id"].tolist())
        job = next((j for j in jobs if j["id"] == sel_id), None)
        if job:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{job['company']} — {job['title']}**")
                st.caption(f"{job.get('sector')} · Tier {job.get('tier')} · fit {job.get('fit_score')}")
                st.markdown(f"[Open posting]({job.get('url')})")
                st.write(job.get("fit_notes", ""))
                st.write("**Next action:** " + (job.get("next_action") or ""))
                # One-click tailor
                _tailor_ok = api_key.is_key_valid()
                if st.button(f"✏️ Tailor resume + cover for {sel_id}", key=f"tailor_{sel_id}",
                             disabled=not _tailor_ok,
                             help="Requires a valid Anthropic API key" if not _tailor_ok else None):
                    cmd = [sys.executable, str(ROOT / "automation" / "jd_tailor.py"),
                           "--job-id", sel_id]
                    rec = scan_runner.start_run(f"tailor_{sel_id}", cmd)
                    st.success(f"Tailor started (`{rec.run_id}`). See Admin → Outputs.")
            with c2:
                with st.form(f"edit_{sel_id}"):
                    new_status = st.selectbox(
                        "Status",
                        options=tr["meta"].get("status_enum", ["Watch", "Found", "Applied"]),
                        index=(tr["meta"].get("status_enum", []).index(job["status"])
                               if job.get("status") in tr["meta"].get("status_enum", []) else 0))
                    new_urgency = st.selectbox("Urgency", ["High", "Medium", "Low"],
                                                index=["High", "Medium", "Low"].index(job.get("urgency", "Medium")))
                    new_date_applied = st.date_input("Date applied", parse_date(job.get("date_applied")) or None,
                                                      format="YYYY-MM-DD") if job.get("date_applied") else st.date_input(
                        "Date applied (blank = not applied yet)", value=None, format="YYYY-MM-DD")
                    new_notes = st.text_area("Notes", job.get("notes", ""))
                    submitted = st.form_submit_button("Save")
                    if submitted:
                        for j in tr["jobs"]:
                            if j["id"] == sel_id:
                                j["status"] = new_status
                                j["urgency"] = new_urgency
                                if new_date_applied:
                                    j["date_applied"] = new_date_applied.isoformat()
                                    if not parse_date(j.get("date_last_followup")):
                                        j["followup_schedule"] = {
                                            "next_due": (new_date_applied + timedelta(days=3)).isoformat(),
                                            "cadence_days": [3, 10, 21]}
                                j["notes"] = new_notes
                                break
                        save_tracker(tr)
                        st.success("Saved.")
                        st.rerun()

                if st.button(f"✅ Mark Applied today (id={sel_id})"):
                    for j in tr["jobs"]:
                        if j["id"] == sel_id:
                            j["status"] = "Applied"
                            j["date_applied"] = date.today().isoformat()
                            j["followup_schedule"] = {
                                "next_due": (date.today() + timedelta(days=3)).isoformat(),
                                "cadence_days": [3, 10, 21]}
                            break
                    save_tracker(tr)
                    st.success("Marked Applied.")
                    st.rerun()


# ============================================================================
# 🤝 RECRUITER CRM
# ============================================================================
elif page == "🤝 Recruiter CRM":
    st.title("🤝 Recruiter + Warm-intro CRM")
    if not crm:
        st.warning("No recruiter_crm.json found.")
        st.stop()

    tab1, tab2, tab3 = st.tabs(["Recruiters", "Alumni warm-intros", "Templates"])
    with tab1:
        recs = crm.get("recruiters", [])
        rdf = pd.DataFrame(recs)
        if not rdf.empty:
            cols = [c for c in ["id", "firm", "firm_type", "location", "priority",
                                "status", "last_touchpoint", "next_action"] if c in rdf.columns]
            st.dataframe(rdf[cols], hide_index=True, use_container_width=True)
            sel = st.selectbox("Pick firm id", rdf["id"].tolist())
            r = next((x for x in recs if x["id"] == sel), None)
            if r:
                st.markdown(f"### {r['firm']}")
                st.caption(f"{r.get('firm_type')} · {r.get('location')}")
                st.write(r.get("notes", ""))
                st.markdown(f"**Coverage:** {r.get('coverage','')}")
                st.markdown(f"**Next action:** {r.get('next_action','')}")
                with st.form(f"rec_{sel}"):
                    new_status = st.selectbox("Status",
                        crm.get("meta", {}).get("status_enum", ["Not_Contacted", "Outreach_Sent"]),
                        index=max(0, crm.get("meta", {}).get("status_enum", []).index(r["status"]))
                        if r.get("status") in crm.get("meta", {}).get("status_enum", []) else 0)
                    new_last = st.date_input("Last touchpoint", parse_date(r.get("last_touchpoint")))
                    new_notes = st.text_area("Notes", r.get("notes", ""))
                    if st.form_submit_button("Save"):
                        for x in crm["recruiters"]:
                            if x["id"] == sel:
                                x["status"] = new_status
                                x["last_touchpoint"] = new_last.isoformat() if new_last else None
                                x["notes"] = new_notes
                                break
                        save_crm(crm)
                        st.success("Saved.")
                        st.rerun()

    with tab2:
        alumni = crm.get("alumni_warm_intros", [])
        st.dataframe(pd.DataFrame(alumni), hide_index=True, use_container_width=True)

    with tab3:
        templates = crm.get("outreach_message_templates", {})
        for name, body in templates.items():
            with st.expander(name):
                st.code(body, language="text")


# ============================================================================
# 📅 WEEKLY PLAN
# ============================================================================
elif page == "📅 Weekly Plan":
    st.title("📅 Weekly Plan")
    wp = ROOT / "this_week.md"
    cp = ROOT / "operating_cadence.md"
    t1, t2, t3 = st.tabs(["This week", "Operating cadence", "Weekly report"])
    with t1:
        st.markdown(wp.read_text(encoding="utf-8") if wp.exists() else "_(no this_week.md)_")
    with t2:
        st.markdown(cp.read_text(encoding="utf-8") if cp.exists() else "_(no operating_cadence.md)_")
    with t3:
        reports = sorted(OUT_DIR.glob("weekly_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if reports:
            which = st.selectbox("Report", [p.name for p in reports])
            st.markdown((OUT_DIR / which).read_text(encoding="utf-8"))
        else:
            st.info("No weekly reports yet.")


# ============================================================================
# 📝 CONTENT & MEMORY
# ============================================================================
elif page == "📝 Content & Memory":
    st.title("📝 Content & Memory")
    t1, t2, t3, t4 = st.tabs(["LinkedIn calendar", "Engagement log", "Master repo", "Campaign memory"])
    with t1:
        p = ROOT / "linkedin_content_engine.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no file)_")
    with t2:
        p = ROOT / "linkedin_engagement_log.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no file)_")
    with t3:
        p = ROOT / "Saber_Ayatollahi_Master_Repository.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no file)_")
    with t4:
        candidates = [
            Path.home() / ".claude" / "projects" / "C--Dev-ApplyAgent" / "memory",
            Path.home() / ".claude" / "projects" / "C--Users-ayatollS-Downloads-deep-research-report" / "memory",
        ]
        memdir = next((c for c in candidates if c.exists()), None)
        if memdir:
            st.caption(f"Source: `{memdir}`")
            for f in sorted(memdir.glob("*.md")):
                with st.expander(f.name):
                    st.markdown(f.read_text(encoding="utf-8"))
        else:
            st.info("No Claude memory directory found.")


# ============================================================================
# ⚙️ ADMIN  — direct access to individual agents and outputs
# ============================================================================
elif page == "⚙️ Admin":
    st.title("⚙️ Admin")
    st.caption("The 🎯 Pipeline page is the main entry point. This page is for running individual "
               "agents directly, or browsing raw outputs.")

    st.subheader("📁 Outputs directory")
    out_files = sorted(OUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    out_files = [p for p in out_files if p.is_file()][:40]
    if out_files:
        rows = [{
            "file": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        } for p in out_files]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=320)

    st.markdown("---")
    st.subheader("Run a single agent")

    agent = st.radio("Agent", ["Weekly report", "JD tailor"], horizontal=True)

    if agent == "Weekly report":
        if st.button("📊 Generate weekly report", type="primary"):
            cmd = [sys.executable, str(ROOT / "automation" / "weekly_report.py")]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
            st.code((res.stdout or "") + "\n" + (res.stderr or "")[-2000:])

    elif agent == "JD tailor":
        if jobs_df.empty:
            st.warning("Tracker empty.")
        else:
            c1, c2 = st.columns([3, 1])
            with c1:
                pick = st.selectbox("Role", jobs_df["id"].tolist())
            with c2:
                dry = st.checkbox("Dry run (no API)", value=False)
            _ad_tailor_ok = api_key.is_key_valid() or dry
            if not _ad_tailor_ok:
                st.caption("🔑 API key required (or tick Dry run).")
            if st.button("✏️ Tailor resume + cover", type="primary",
                         disabled=not _ad_tailor_ok):
                cmd = [sys.executable, str(ROOT / "automation" / "jd_tailor.py"),
                       "--job-id", pick]
                if dry:
                    cmd.append("--dry-run")
                res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
                st.code((res.stdout or "") + "\n" + (res.stderr or "")[-4000:])
                latest = sorted(OUT_DIR.glob(f"*_{pick.replace('-','_')}*.md"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
                if latest:
                    with st.expander(f"Output: {latest[0].name}", expanded=True):
                        st.markdown(latest[0].read_text(encoding="utf-8"))
