"""Saber's Job Search — Streamlit Dashboard.

Run:
    streamlit run ui/app.py

Multi-page app reading the canonical JSON/MD artifacts at the project root.
Edits to tracker/CRM are written back safely with a .bak backup.
Long-running agents (scraper, scorer) run as detached background processes
via ui/scan_runner.py so the UI stays responsive.
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

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "job_tracker_data.json"
CRM = ROOT / "recruiter_crm.json"
OUT_DIR = ROOT / "automation" / "outputs"
RUNS_DIR = OUT_DIR / "runs"


# ----------------------------- helpers ------------------------------------
@st.cache_data(ttl=30)
def load_tracker():
    return json.loads(TRACKER.read_text(encoding="utf-8"))


@st.cache_data(ttl=30)
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


def human_elapsed(started_iso: str, end_iso: str | None = None) -> str:
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


# ----------------------------- page config --------------------------------
st.set_page_config(
    page_title="Saber's Job Search",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    "🏠 Dashboard",
    "🛰️ Scans",
    "📋 Jobs Kanban",
    "🔍 Scored Scan",
    "🤝 Recruiter CRM",
    "📅 Weekly Plan",
    "📝 Content & Memory",
    "⚙️ Admin",
]

page = st.sidebar.radio("Navigate", PAGES)

# Active-runs badge in sidebar
active = scan_runner.active_runs()
if active:
    st.sidebar.markdown("### 🟢 Active runs")
    for r in active:
        st.sidebar.caption(
            f"**{r['label']}** · "
            f"{human_elapsed(r['started_at'])} · pid {r['pid']}"
        )
else:
    st.sidebar.caption("No background runs")

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

    # Live run banner
    if active:
        for r in active:
            st.info(
                f"🛰️ **{r['label']}** running — started {fmt_dt(r['started_at'])} · "
                f"elapsed {human_elapsed(r['started_at'])} · pid {r['pid']}. "
                f"See Scans page for live logs.",
                icon="⚡",
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
    c4.metric("Total applied (campaign)", len(applied_all))
    c5.metric("Stale (>21d, no reply)", len(stale), delta_color="inverse")

    st.markdown("---")

    # Quick actions
    st.subheader("⚡ Quick actions")
    qa1, qa2, qa3, qa4 = st.columns(4)
    with qa1:
        if st.button("🛰️ Run full scan", use_container_width=True, type="primary"):
            rec = scan_runner.start_run(
                "full_scan",
                [sys.executable, str(ROOT / "automation" / "jd_scraper.py"), "--expansion"],
            )
            st.success(f"Started run `{rec.run_id}` (pid {rec.pid}). Go to 🛰️ Scans to monitor.")
            st.rerun()
    with qa2:
        if st.button("🔗 LinkedIn-only scan", use_container_width=True):
            rec = scan_runner.start_run(
                "linkedin_scan",
                [sys.executable, str(ROOT / "automation" / "jd_scraper.py"), "--linkedin-only"],
            )
            st.success(f"Started `{rec.run_id}`")
            st.rerun()
    with qa3:
        if st.button("🏛️ Direct ATS scan", use_container_width=True):
            rec = scan_runner.start_run(
                "ats_scan",
                [sys.executable, str(ROOT / "automation" / "jd_scraper.py"), "--workday-only"],
            )
            st.success(f"Started `{rec.run_id}`")
            st.rerun()
    with qa4:
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
        st.caption("No roles flagged for this week. Set `meta.kanban_targets_week1.apply_this_week` in tracker.")

    # Latest scan summary
    latest_scored = sorted(OUT_DIR.glob("scan_*_scored.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if latest_scored:
        st.markdown("---")
        st.subheader(f"🔎 Latest fit-scored scan: `{latest_scored[0].name}`")
        try:
            sc = json.loads(latest_scored[0].read_text(encoding="utf-8"))
            results = sc.get("results", [])
            by_verdict = {}
            for r in results:
                v = (r.get("fit") or {}).get("fit_verdict", "?")
                by_verdict[v] = by_verdict.get(v, 0) + 1
            cols = st.columns(len(by_verdict) or 1)
            for (v, n), col in zip(sorted(by_verdict.items(), key=lambda x: -x[1]), cols):
                col.metric(v, n)
            st.caption(f"Input: {sc.get('total_input')} · Stage-1 passed: {sc.get('stage1_passed')} · "
                       f"Stage-2 scored: {sc.get('stage2_scored')}")
        except Exception as e:
            st.warning(f"Could not read scored file: {e}")


# ============================================================================
# 🛰️ SCANS
# ============================================================================
elif page == "🛰️ Scans":
    st.title("🛰️ Scans")
    st.caption(
        "Run the scraper in the background. Logs persist to "
        "`automation/outputs/runs/` so you can close and reopen the UI safely."
    )

    # ---------- Launcher ----------
    st.subheader("Launch a scan")
    mode_tab, opts_tab = st.tabs(["Mode", "Advanced options"])
    with mode_tab:
        modes = {
            "🛰️ Full scan (LinkedIn + Workday + Greenhouse + Lever)":
                {"label": "full_scan", "args": []},
            "🏛️ Direct ATS only (Workday APIs — fast, no throttling)":
                {"label": "ats_scan", "args": ["--workday-only"]},
            "🔗 LinkedIn-only (skip ATS portals)":
                {"label": "linkedin_scan", "args": ["--linkedin-only"]},
            "➕ Expansion companies only (fintechs, regulators, insurers)":
                {"label": "expansion_scan", "args": ["--expansion-only"]},
        }
        choice = st.radio("Scan mode", list(modes.keys()), label_visibility="collapsed")
        base = modes[choice]

    with opts_tab:
        c1, c2 = st.columns(2)
        with c1:
            sector_filter = st.text_input(
                "Limit to sector (substring match, optional)", "",
                placeholder="e.g. Pension Funds")
            company_filter = st.text_input(
                "Limit to single company (exact name, optional)", "",
                placeholder="e.g. Scotiabank")
        with c2:
            include_expansion = st.checkbox(
                "Include expansion companies (full scan only)", value=True,
                help="Adds fintechs, insurers, regulators beyond the core 77 targets.")

        expected_min = {
            "full_scan": "20-40 min" + (" (with expansion)" if include_expansion else ""),
            "ats_scan": "3-6 min",
            "linkedin_scan": "15-25 min",
            "expansion_scan": "5-10 min",
        }
        est = expected_min.get(base["label"], "?")
        st.info(f"⏱️ Estimated runtime: **{est}**")

    # Assemble command
    cmd = [sys.executable, str(ROOT / "automation" / "jd_scraper.py")] + base["args"]
    if base["label"] == "full_scan" and include_expansion:
        cmd.append("--expansion")
    if sector_filter.strip():
        cmd += ["--sector", sector_filter.strip()]
    if company_filter.strip():
        cmd += ["--company", company_filter.strip()]

    launch_col, preview_col = st.columns([1, 3])
    with launch_col:
        if st.button("▶️ Launch scan", type="primary", use_container_width=True):
            rec = scan_runner.start_run(base["label"], cmd)
            st.success(f"Started `{rec.run_id}` (pid {rec.pid})")
            st.rerun()
    with preview_col:
        st.code(" ".join(cmd), language="bash")

    st.markdown("---")

    # ---------- Active runs (live tail) ----------
    active_now = scan_runner.active_runs()
    st.subheader(f"🟢 Active runs ({len(active_now)})")
    if not active_now:
        st.caption("No scans currently running.")
    for r in active_now:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.markdown(f"**{r['label']}**  \n`{r['run_id']}`")
            c2.markdown(f"Started: {fmt_dt(r['started_at'])}")
            c3.markdown(f"Elapsed: **{human_elapsed(r['started_at'])}**  ·  pid {r['pid']}")
            with c4:
                if st.button("⏹ Stop", key=f"stop_{r['run_id']}"):
                    if scan_runner.stop_run(r["run_id"]):
                        st.warning("Stop signal sent.")
                        st.rerun()
            with st.expander("📜 Live log tail (last 20 KB)", expanded=True):
                st.code(scan_runner.tail_log(r["log_path"]) or "(no output yet)", language="text")
            st.caption(f"Log file: `{r['log_path']}`")

    if active_now:
        auto = st.checkbox("🔄 Auto-refresh every 5s", value=True, key="scans_autorefresh")
        if auto:
            import time as _t
            _t.sleep(5)
            st.rerun()

    st.markdown("---")

    # ---------- History ----------
    st.subheader("📚 Scan history")
    runs = scan_runner.list_runs(limit=50)
    if not runs:
        st.caption("No runs recorded yet.")
    else:
        hist_rows = []
        for r in runs:
            hist_rows.append({
                "run_id": r["run_id"],
                "label": r["label"],
                "state": r.get("state", "?"),
                "started": fmt_dt(r.get("started_at")),
                "finished": fmt_dt(r.get("finished_at")),
                "duration": human_elapsed(r.get("started_at"), r.get("finished_at")),
                "pid": r.get("pid"),
            })
        hist_df = pd.DataFrame(hist_rows)
        st.dataframe(
            hist_df, hide_index=True, use_container_width=True, height=320,
            column_config={
                "state": st.column_config.TextColumn(width="small"),
                "pid": st.column_config.NumberColumn(width="small"),
            },
        )

        # Inspect one
        pick = st.selectbox("Inspect a run", [r["run_id"] for r in runs])
        sel = next((r for r in runs if r["run_id"] == pick), None)
        if sel:
            with st.container(border=True):
                mc1, mc2, mc3 = st.columns(3)
                mc1.markdown(f"**Label:** {sel['label']}")
                mc1.markdown(f"**State:** `{sel.get('state')}`")
                mc2.markdown(f"**Started:** {fmt_dt(sel.get('started_at'))}")
                mc2.markdown(f"**Finished:** {fmt_dt(sel.get('finished_at'))}")
                mc3.markdown(f"**Duration:** {human_elapsed(sel.get('started_at'), sel.get('finished_at'))}")
                mc3.markdown(f"**PID:** {sel.get('pid')}")
                st.caption("Command:")
                st.code(" ".join(sel.get("cmd", [])), language="bash")
                st.caption("Log output:")
                st.code(scan_runner.tail_log(sel["log_path"], max_bytes=100_000), language="text")

    st.markdown("---")

    # ---------- Scan output files ----------
    st.subheader("📦 Scan output files")
    scan_files = sorted(OUT_DIR.glob("scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not scan_files:
        st.caption("No scan files in `automation/outputs/`.")
    else:
        rows = []
        for p in scan_files[:20]:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if "results" in d:
                    count = len(d["results"])
                    kind = "raw"
                elif "stage2_scored" in d:
                    count = d.get("stage2_scored", "?")
                    kind = "scored"
                else:
                    count = "?"
                    kind = "?"
            except Exception:
                count, kind = "?", "?"
            rows.append({
                "file": p.name,
                "kind": kind,
                "count": count,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ============================================================================
# 📋 JOBS KANBAN
# ============================================================================
elif page == "📋 Jobs Kanban":
    st.title("📋 Jobs Tracker")

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

                # Apply-quick button
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
# 🔍 SCORED SCAN
# ============================================================================
elif page == "🔍 Scored Scan":
    st.title("🔍 Fit-Scored Scan Results")
    scored_files = sorted(OUT_DIR.glob("*_scored.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not scored_files:
        st.warning("No scored scan found. Run the fit scorer from the Admin page or:")
        st.code("python automation/fit_scorer.py", language="bash")
        st.stop()

    which = st.selectbox("Scored file", [p.name for p in scored_files])
    sc = json.loads((OUT_DIR / which).read_text(encoding="utf-8"))
    results = sc.get("results", [])
    st.caption(f"Input {sc.get('total_input')} · stage1-pass {sc.get('stage1_passed')} · scored {sc.get('stage2_scored')} · scored at {sc.get('scored_at')}")

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

    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        min_fit = st.slider("Min fit score", 1, 10, 7)
    with f2:
        verdict_filter = st.multiselect("Verdict", sorted(df["verdict"].dropna().unique()),
                                        default=["apply_now", "tailor_and_apply"])
    with f3:
        sector_filter = st.multiselect("Sector", sorted(df["sector"].dropna().unique()))

    view = df[df["fit"] >= min_fit]
    if verdict_filter:
        view = view[view["verdict"].isin(verdict_filter)]
    if sector_filter:
        view = view[view["sector"].isin(sector_filter)]

    st.caption(f"{len(view)} matches")
    st.dataframe(view, hide_index=True, use_container_width=True, height=600,
                 column_config={"url": st.column_config.LinkColumn("open")})

    st.markdown("---")
    st.subheader("Promote selected to tracker")
    st.caption("Preview or commit promotion from scored scan → tracker.")
    p1, p2, p3 = st.columns([1, 1, 2])
    with p1:
        min_promote_score = st.slider("Min score for promote", 1, 10, 7, key="promote_min")
    with p2:
        include_watch = st.checkbox("Include verdict=watch")
    with p3:
        st.caption("Dry-run = preview only. Commit = write tracker.")
        pc1, pc2 = st.columns(2)
        with pc1:
            if st.button("👀 Preview (dry-run)"):
                cmd = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                       "--scan", which, "--min-score", str(min_promote_score)]
                if include_watch:
                    cmd.append("--include-watch")
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
                st.code(result.stdout + "\n" + result.stderr)
        with pc2:
            if st.button("🚀 Commit", type="primary"):
                cmd = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                       "--scan", which, "--min-score", str(min_promote_score), "--commit"]
                if include_watch:
                    cmd.append("--include-watch")
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
                st.code(result.stdout + "\n" + result.stderr)
                st.cache_data.clear()


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
            st.info("No weekly reports yet. Run `python automation/weekly_report.py`.")


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
        # Probe likely memory locations in order of preference
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
# ⚙️ ADMIN
# ============================================================================
elif page == "⚙️ Admin":
    st.title("⚙️ Admin — run agents")
    st.caption(
        "Scrapers and scorers run in the background (see 🛰️ Scans). "
        "Fast agents (promote, weekly report, tailor) run inline."
    )

    section = st.radio(
        "Agent",
        ["🔎 Scraper (→ Scans)", "🤖 Fit scorer", "🚀 Auto-promote", "📊 Weekly report", "✏️ JD tailor"],
        horizontal=True,
    )

    if section == "🔎 Scraper (→ Scans)":
        st.info("Use the dedicated 🛰️ Scans page for scraping — it has full mode/filter controls, "
                "live log tailing, and run history.")
        if st.button("Go to Scans"):
            st.session_state.update({"_goto": "🛰️ Scans"})
            st.rerun()

    elif section == "🤖 Fit scorer":
        st.subheader("Fit scorer — score a raw scan with LLM")
        scan_files = sorted(OUT_DIR.glob("scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        scan_files = [p for p in scan_files if "_scored" not in p.name]
        if not scan_files:
            st.warning("No raw scan files found. Run a scan first.")
        else:
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                which = st.selectbox("Scan to score", [p.name for p in scan_files])
            with c2:
                concurrency = st.number_input("Concurrency", min_value=1, max_value=16, value=6)
            with c3:
                limit = st.number_input("Limit (0=all)", min_value=0, max_value=10000, value=0)
            dry = st.checkbox("Dry run (rule-stage only, no API calls)")
            if st.button("🤖 Run fit_scorer.py", type="primary"):
                cmd = [sys.executable, str(ROOT / "automation" / "fit_scorer.py"),
                       "--scan", which, "--concurrency", str(concurrency)]
                if limit:
                    cmd += ["--limit", str(limit)]
                if dry:
                    cmd.append("--dry-run")
                rec = scan_runner.start_run("fit_scorer", cmd)
                st.success(f"Started `{rec.run_id}` — monitor in 🛰️ Scans.")

    elif section == "🚀 Auto-promote":
        st.subheader("Auto-promote — scored scan → tracker")
        scored_files = sorted(OUT_DIR.glob("*_scored.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.warning("No scored scan files.")
        else:
            which = st.selectbox("Scored file", [p.name for p in scored_files], key="prom_scan")
            c1, c2, c3 = st.columns(3)
            with c1:
                min_s = st.slider("Min fit score", 1, 10, 7)
            with c2:
                inc_watch = st.checkbox("Include verdict=watch")
            with c3:
                commit = st.checkbox("COMMIT (write tracker)", help="Unchecked = dry-run preview only")
            if st.button("🚀 Run auto_promote.py", type="primary"):
                cmd = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                       "--scan", which, "--min-score", str(min_s)]
                if inc_watch:
                    cmd.append("--include-watch")
                if commit:
                    cmd.append("--commit")
                res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
                st.code((res.stdout or "") + "\n" + (res.stderr or "")[-4000:])
                if commit:
                    st.cache_data.clear()

    elif section == "📊 Weekly report":
        st.subheader("Weekly report — KPIs, stale roles, next actions")
        if st.button("📊 Generate weekly report", type="primary"):
            cmd = [sys.executable, str(ROOT / "automation" / "weekly_report.py")]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
            st.code((res.stdout or "") + "\n" + (res.stderr or "")[-2000:])
        reports = sorted(OUT_DIR.glob("weekly_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if reports:
            st.caption("Recent reports:")
            which = st.selectbox("Preview", [p.name for p in reports])
            with st.expander("Contents", expanded=True):
                st.markdown((OUT_DIR / which).read_text(encoding="utf-8"))

    elif section == "✏️ JD tailor":
        st.subheader("JD tailor — per-role resume + cover letter")
        if jobs_df.empty:
            st.warning("Tracker empty.")
        else:
            c1, c2 = st.columns([3, 1])
            with c1:
                pick = st.selectbox("Role", jobs_df["id"].tolist())
            with c2:
                dry = st.checkbox("Dry run (no API)", value=False)
            if st.button("✏️ Tailor resume + cover", type="primary"):
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

    st.markdown("---")
    st.subheader("📁 Outputs directory")
    out_files = sorted(OUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    out_files = [p for p in out_files if p.is_file()][:30]
    if out_files:
        rows = [{
            "file": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        } for p in out_files]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=320)
