"""Saber's Job Search — Streamlit Dashboard.

Run:
    streamlit run ui/app.py

Agentic pipeline:  Scrape -> Score -> Triage -> Promote -> Tailor
One page, one flow. Background execution via ui/scan_runner.py.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# Auto-refresh component — polling, not websocket. Only installed as a dep
# when streamlit-autorefresh is listed in requirements.txt. If missing we
# degrade to no-auto-refresh (user clicks Refresh manually).
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    _HAVE_AUTOREFRESH = True
except ImportError:
    _HAVE_AUTOREFRESH = False

    def st_autorefresh(interval: int = 2000, limit: int = 0, key: str = ""):
        """No-op shim when streamlit-autorefresh isn't installed."""
        return 0

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_runner  # noqa: E402
import api_key  # noqa: E402
import gmail_ui  # noqa: E402

# The lifetime cost ledger lives in automation/ so it can be imported by
# scorer/tailor without those having a sibling dependency on ui/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "automation"))
import cost_ledger  # noqa: E402

# Error log — populated by the automation modules. Guarded import so the
# UI still loads even if the module was renamed / broken.
try:
    import error_log  # noqa: E402
except Exception:
    error_log = None  # type: ignore

# Ensure stored key is in env before anything launches a subprocess
api_key.hydrate_env()

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "job_tracker_data.json"
CRM = ROOT / "data" / "recruiter_crm.json"
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


# ---------------------------------------------------------------------------
# Follow-up nudge logic — reads job_tracker_data.json
# followup_schedule = {"next_due": "YYYY-MM-DD", "cadence_days": [3, 10, 21]}
# A role enters the follow-up loop when it gets date_applied. On each follow-up,
# next_due advances through cadence_days until the last rung, then we stop nudging.
# ---------------------------------------------------------------------------
FOLLOWUP_TERMINAL_STATUSES = {
    "Rejected", "Offer", "Hired", "Withdrawn", "Expired", "Declined",
}


def followup_buckets(jobs: list[dict], today_date: date | None = None) -> dict:
    """Partition jobs into overdue/due-today/due-this-week/upcoming/idle buckets.

    A job is in the follow-up loop if:
      - it has date_applied
      - its status is not terminal (not Rejected/Offer/Hired/Withdrawn/Expired)
      - it has followup_schedule.next_due set

    Returns:
      {"overdue": [(days_overdue, job), ...],
       "due_today": [job, ...],
       "due_this_week": [(days_until, job), ...],
       "upcoming": [(days_until, job), ...],
       "no_schedule": [job, ...]   # applied but no next_due — likely needs first follow-up}
    """
    today_date = today_date or date.today()
    buckets = {
        "overdue": [],
        "due_today": [],
        "due_this_week": [],
        "upcoming": [],
        "no_schedule": [],
    }
    for j in jobs:
        if not j.get("date_applied"):
            continue
        if j.get("status") in FOLLOWUP_TERMINAL_STATUSES:
            continue
        sched = j.get("followup_schedule") or {}
        next_due = parse_date(sched.get("next_due"))
        if not next_due:
            buckets["no_schedule"].append(j)
            continue
        delta = (next_due - today_date).days
        if delta < 0:
            buckets["overdue"].append((-delta, j))
        elif delta == 0:
            buckets["due_today"].append(j)
        elif delta <= 7:
            buckets["due_this_week"].append((delta, j))
        else:
            buckets["upcoming"].append((delta, j))
    buckets["overdue"].sort(key=lambda t: -t[0])  # most overdue first
    buckets["due_this_week"].sort(key=lambda t: t[0])
    buckets["upcoming"].sort(key=lambda t: t[0])
    return buckets


def advance_followup(job: dict, today_date: date | None = None) -> None:
    """Advance a job's next_due one cadence step. Mutates the job in place.
    Called when the user logs a follow-up, so the next nudge lands on the
    right day. When the cadence is exhausted, clears next_due (no more nudges)."""
    today_date = today_date or date.today()
    sched = job.setdefault("followup_schedule", {"cadence_days": [3, 10, 21]})
    cadence = sched.get("cadence_days") or [3, 10, 21]
    applied = parse_date(job.get("date_applied"))
    if not applied:
        return
    # Find the next cadence step after today
    for days in cadence:
        candidate = applied + timedelta(days=days)
        if candidate > today_date:
            sched["next_due"] = candidate.isoformat()
            return
    # Cadence exhausted — stop nudging
    sched["next_due"] = None


def seed_followup(job: dict, applied_on: date | None = None) -> None:
    """Seed followup_schedule.next_due when a role first becomes Applied."""
    applied_on = applied_on or date.today()
    sched = job.setdefault("followup_schedule", {"cadence_days": [3, 10, 21]})
    cadence = sched.get("cadence_days") or [3, 10, 21]
    if cadence:
        sched["next_due"] = (applied_on + timedelta(days=cadence[0])).isoformat()
    job["date_applied"] = applied_on.isoformat()


# ---------------------------------------------------------------------------
# Outreach digest — computes staleness from CRM last_touchpoint
# ---------------------------------------------------------------------------
CRM_STALE_DAYS = 14  # past this, contacts get flagged as "nudge-worthy"
CRM_DEAD_DAYS = 35   # past this, contacts get flagged as "probably cold"
CRM_TERMINAL_STATUSES = {"Do_Not_Contact", "Past_Rep", "On_Hold"}


def outreach_digest(crm: dict, today_date: date | None = None) -> dict:
    """Score each CRM contact by staleness + priority. Returns:
      {"never_contacted": [contacts],
       "active":          [(days_since, contact)],
       "stale":           [(days_since, contact)],
       "cold":            [(days_since, contact)],
       "weekly_sent":     count sent in the last 7 days}
    """
    today_date = today_date or date.today()
    week_ago = today_date - timedelta(days=7)
    out = {"never_contacted": [], "active": [], "stale": [], "cold": [],
           "weekly_sent": 0}

    # Combine recruiters + alumni as "contacts" — treat uniformly
    contacts = []
    for r in crm.get("recruiters", []):
        contacts.append({**r, "_kind": "recruiter"})
    for a in crm.get("alumni_warm_intros", []):
        contacts.append({**a, "_kind": "alumni"})

    for c in contacts:
        if c.get("status") in CRM_TERMINAL_STATUSES:
            continue
        last = parse_date(c.get("last_touchpoint"))
        if last is None:
            out["never_contacted"].append(c)
            continue
        if last >= week_ago:
            out["weekly_sent"] += 1
        days = (today_date - last).days
        if days <= CRM_STALE_DAYS:
            out["active"].append((days, c))
        elif days <= CRM_DEAD_DAYS:
            out["stale"].append((days, c))
        else:
            out["cold"].append((days, c))

    # Count this-week touchpoints from outreach_log too (structured log)
    for entry in crm.get("outreach_log") or []:
        d = parse_date(entry.get("date"))
        if d and d >= week_ago:
            out["weekly_sent"] += 1

    # Sort by priority (High > Medium > Low), then days-since desc for stale
    prio_rank = {"High": 0, "Medium": 1, "Low": 2}
    out["never_contacted"].sort(key=lambda c: prio_rank.get(c.get("priority"), 3))
    out["active"].sort(key=lambda t: -t[0])
    out["stale"].sort(key=lambda t: -t[0])
    out["cold"].sort(key=lambda t: -t[0])
    return out


def render_template(body: str, contact: dict) -> str:
    """Substitute {{placeholder}} variables in a CRM outreach template."""
    out = body
    subs = {
        "{{name}}": (contact.get("contacts") or [{}])[0].get("name", "") if contact.get("_kind") == "recruiter" else contact.get("name", ""),
        "{{firm}}": contact.get("firm", "") or contact.get("company_targeted", ""),
        "{{coverage}}": contact.get("coverage", "") or contact.get("notes", ""),
        "{{next_action}}": contact.get("next_action", ""),
    }
    for k, v in subs.items():
        out = out.replace(k, str(v or ""))
    return out


_CRM_STOPWORDS = {"bank", "financial", "canadian", "canada", "global", "group",
                    "capital", "management", "investments", "pension", "plan",
                    "corp", "inc", "ltd", "company", "the", "and"}


_GTA_AREAS = [
    ("Toronto", ("toronto", "north york", "scarborough", "etobicoke", "east york",
                  "york, on", "downtown")),
    ("Mississauga", ("mississauga",)),
    ("Markham", ("markham", "unionville")),
    ("Vaughan", ("vaughan", "concord", "woodbridge", "thornhill")),
    ("Brampton", ("brampton",)),
    ("Oakville", ("oakville",)),
    ("Burlington", ("burlington",)),
    ("Milton", ("milton",)),
    ("Richmond Hill", ("richmond hill",)),
    ("Durham", ("pickering", "ajax", "whitby", "oshawa")),
    ("York Region", ("aurora", "newmarket", "stouffville", "king city")),
    ("Waterloo/Kitchener", ("waterloo", "kitchener", "cambridge")),
    ("Remote Canada", ("remote - canada", "canada - remote", "remote canada",
                        "remote, canada")),
    ("Ottawa", ("ottawa",)),
    ("Montreal", ("montreal", "montréal")),
]


def gta_area_for(location: str | None) -> str:
    """Classify a location string into a GTA area bucket. Returns '—' if unknown.
    Used for Kanban column + filter so Saber can slice newly-unblocked
    non-Toronto GTA roles (Mississauga, Markham etc.)."""
    if not location:
        return "—"
    loc = str(location).lower()
    for label, tokens in _GTA_AREAS:
        if any(tok in loc for tok in tokens):
            return label
    # Last resort — anything with "on" or "ontario" is likely GTA-adjacent
    if "ontario" in loc or ", on" in loc or " on," in loc or loc.endswith(", on"):
        return "Other Ontario"
    return "—"


def crm_contacts_at_company(crm: dict, company: str) -> list[dict]:
    """Match CRM recruiters + alumni entries to a given company name.
    Bidirectional token-overlap: 'Scotiabank' matches 'Scotia' (prefix) and
    'Scotia' matches 'Scotiabank'. Covers abbreviations + full legal names."""
    if not company:
        return []
    co_tokens = [t for t in re.split(r"[^a-z0-9]+", company.lower())
                 if len(t) >= 4 and t not in _CRM_STOPWORDS]
    if not co_tokens:
        return []

    def _match(hay: str) -> bool:
        hay_tokens = [h for h in re.split(r"[^a-z0-9]+", hay.lower()) if len(h) >= 4]
        for co_tok in co_tokens:
            for h in hay_tokens:
                # Bidirectional prefix match — 'scotia' ⇔ 'scotiabank'
                if co_tok == h or co_tok.startswith(h) or h.startswith(co_tok):
                    return True
        return False

    matches = []
    for rec in (crm or {}).get("recruiters", []):
        hay = (rec.get("firm", "") + " " + rec.get("coverage", "") + " "
               + rec.get("notes", ""))
        if _match(hay):
            matches.append({**rec, "_kind": "recruiter"})
    for al in (crm or {}).get("alumni_warm_intros", []):
        hay = (al.get("company_targeted", "") + " "
               + al.get("current_firm", "") + " "
               + al.get("notes", ""))
        if _match(hay):
            matches.append({**al, "_kind": "alumni"})
    return matches


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


def hours_since_posted(posted_date: str | None) -> float | None:
    """Return hours elapsed since posted_date. None if unparseable.
    Accepts 'YYYY-MM-DD' or any ISO8601 string."""
    if not posted_date:
        return None
    s = str(posted_date).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:
            return None
    # Drop tz for uniform comparison; we only need hour-level precision.
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    delta = datetime.now() - dt
    return max(0.0, delta.total_seconds() / 3600.0)


def urgent_from_brief(brief: dict | None, hours_threshold: int = 48) -> list[dict]:
    """Return brief rows posted within the threshold, newest first.
    Used to power the Dashboard's '🔴 Urgent' widget."""
    if not brief:
        return []
    out: list[tuple[float, dict]] = []
    for r in brief.get("top") or []:
        hrs = hours_since_posted(r.get("posted_date"))
        if hrs is None or hrs > hours_threshold:
            continue
        out.append((hrs, r))
    out.sort(key=lambda t: t[0])
    return [r for _, r in out]


def freshness_badge(posted_date: str | None, found_at: str | None) -> str:
    """Return a short badge combining posted/found freshness.
    Emoji indicates 'how hot is this role right now':
      🔥  posted in last 48h
      🟢  posted in last 7d
      🟡  posted 8-21d ago
      ⚪  >21d or unknown
    """
    label_post = ""
    label_found = ""
    now = date.today()
    if posted_date:
        try:
            d = datetime.fromisoformat(str(posted_date).replace("Z", "")).date()
            days = (now - d).days
            if days <= 2:
                label_post = f"🔥 posted {days}d ago"
            elif days <= 7:
                label_post = f"🟢 posted {days}d ago"
            elif days <= 21:
                label_post = f"🟡 posted {days}d ago"
            else:
                label_post = f"⚪ posted {days}d ago"
        except Exception:
            pass
    if found_at:
        try:
            d = datetime.fromisoformat(str(found_at)).date()
            days = (now - d).days
            label_found = "found today" if days == 0 else f"found {days}d ago"
        except Exception:
            pass
    parts = [p for p in (label_post, label_found) if p]
    return " · ".join(parts) if parts else "—"


def load_morning_brief() -> dict | None:
    """Read the most recent brief_YYYYMMDD.json. Returns None if missing."""
    files = sorted(OUT_DIR.glob("brief_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def load_scorer_progress() -> dict | None:
    """Read outputs/fit_scorer_progress.json if present. Returns None if missing.

    A progress file with state='running' but an `updated_at` older than
    ~5 minutes is treated as STALE — that usually means the scorer process
    was killed (terminal closed, crash, OOM) without calling progress_end().
    Stale files get rewritten to state='stale' so the banner clears and
    future dashboards don't keep showing a phantom 'Scoring in progress'.
    """
    p = OUT_DIR / "fit_scorer_progress.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Freshness guard. Only matters when state is "running" — finished/failed
    # states are permanent records.
    if data.get("state") == "running":
        updated = data.get("updated_at") or data.get("started_at")
        stale = False
        if not updated:
            stale = True
        else:
            try:
                # Stored as ISO with trailing 'Z'; strip it for fromisoformat.
                u = updated.rstrip("Z")
                dt = datetime.fromisoformat(u)
                # updated_at is UTC; use utcnow for the comparison.
                if (datetime.utcnow() - dt).total_seconds() > 300:
                    stale = True
            except Exception:
                stale = True

        if stale:
            # Also verify the producer PID (if we have one) isn't alive.
            # The progress file doesn't carry a PID directly, but scan_runner
            # tracks active runs. If there are NO running fit_scorer runs,
            # the progress file is definitively orphaned.
            try:
                _active = [r for r in scan_runner.active_runs()
                            if "fit_scorer" in (r.get("label") or "")]
            except Exception:
                _active = []
            if not _active:
                data["state"] = "stale"
                data["finished_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                try:
                    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass
    return data


def _fmt_eta(secs: float | None) -> str:
    if not secs or secs <= 0:
        return "—"
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


def render_scorer_progress(container=None, title: str = "🤖 Scoring in progress"):
    """Render a live progress bar + ETA + recent candidates table for the fit scorer.

    Only renders when state=='running' (live). Finished/failed/stale progress
    files are skipped so the dashboard doesn't falsely claim scoring is in
    progress when the scraper (or nothing at all) is running.
    """
    prog = load_scorer_progress()
    if not prog:
        return False
    state = prog.get("state", "idle")
    if state != "running":
        return False
    target = container or st
    cur = prog.get("current", 0)
    total = prog.get("total", 0) or 1
    frac = min(1.0, cur / total)

    with target.container(border=True):
        st.markdown(f"### {title}")
        cost = prog.get("cost") or {}
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Progress", f"{cur}/{total}", f"{frac*100:.0f}%")
        c2.metric("Elapsed", _fmt_eta(prog.get("elapsed_sec")))
        c3.metric("ETA", _fmt_eta(prog.get("eta_sec")))
        c4.metric("Cache hits", prog.get("cache_hits", 0))
        c5.metric("Est. cost (USD)",
                  f"${cost.get('estimated_cost_usd', 0):.3f}" if cost else "—",
                  f"{cost.get('llm_calls', 0)} calls" if cost else None)
        st.progress(frac, text=f"Scored {cur} of {total} candidates · scan=`{prog.get('scan')}`")

        # Verdict breakdown so far
        vc = prog.get("verdict_counts") or {}
        if vc:
            apply_n = vc.get("apply_now", 0)
            tailor_n = vc.get("tailor_and_apply", 0)
            watch_n = vc.get("watch", 0)
            skip_n = vc.get("skip", 0)
            err_n = vc.get("error", 0) + prog.get("errors", 0)
            bc1, bc2, bc3, bc4, bc5 = st.columns(5)
            bc1.metric("apply_now", apply_n)
            bc2.metric("tailor_and_apply", tailor_n)
            bc3.metric("watch", watch_n)
            bc4.metric("skip", skip_n)
            bc5.metric("errors", err_n, delta_color="inverse")

        recent = prog.get("recent") or []
        if recent:
            st.caption("**Most recent candidates** (newest last)")
            rows = []
            for r in recent:
                rows.append({
                    "company": r.get("company", ""),
                    "title": r.get("title", ""),
                    "verdict": r.get("verdict", ""),
                    "score": r.get("score", ""),
                    "cache": "💾" if r.get("from_cache") else "🌐",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch',
                         height=min(40 + 36 * len(rows), 300))

        # Per-model cost breakdown
        per_model = (cost or {}).get("per_model") or {}
        if per_model:
            with st.expander(f"💰 Token/cost breakdown ({cost.get('llm_calls', 0)} LLM calls, "
                             f"${cost.get('estimated_cost_usd', 0):.4f} est)"):
                rows = []
                for model, m in per_model.items():
                    rows.append({
                        "model": model,
                        "calls": m.get("calls", 0),
                        "input_tokens": m.get("in_tokens", 0),
                        "output_tokens": m.get("out_tokens", 0),
                        "est_cost_usd": round(m.get("cost_usd", 0), 4),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
                st.caption(
                    f"Cache reads: {cost.get('cache_read_tokens', 0):,} tokens · "
                    f"Cache writes: {cost.get('cache_create_tokens', 0):,} tokens. "
                    f"Pricing from Anthropic public rates — invoice is authoritative."
                )

        status_caption = {
            "running": f"🟡 Running · updated {prog.get('updated_at', '—')}",
            "finished": f"🟢 Finished at {prog.get('finished_at', '—')}",
            "failed": f"🔴 Failed at {prog.get('finished_at', '—')}",
        }.get(state, f"State: {state}")
        st.caption(status_caption)
    return state == "running"


def _resolve_pipeline_staleness(data: dict, path: Path) -> dict:
    """Rewrite a pipeline status that claims `state=running` but is obviously
    orphaned. Mirror of fit_scorer_progress.json's stale-detection logic.

    A pipeline is stale when:
      - state is 'running'
      - AND file hasn't been touched in >10 minutes (pipelines heartbeat
        via _write_status after every stage transition)
      - AND no scan_runner job whose label contains 'pipeline' is alive

    When all three are true, the producer is dead — the process either
    crashed before hitting the try/finally guard, was kill-treed, or the
    machine was rebooted. We flip state to 'stale' in-place so the UI
    stops showing a phantom 'pipeline running' banner forever."""
    if data.get("state") != "running":
        return data
    try:
        age_s = datetime.now().timestamp() - path.stat().st_mtime
    except Exception:
        return data
    if age_s < 600:  # <10 min: still plausibly alive, don't touch
        return data
    try:
        alive = any("pipeline" in (r.get("label") or "")
                     for r in scan_runner.active_runs())
    except Exception:
        alive = False
    if alive:
        return data
    # Orphan. Rewrite the file.
    data["state"] = "stale"
    data["finished_at"] = datetime.now().isoformat(timespec="seconds")
    data["stale_reason"] = (
        f"No active pipeline subprocess and status file idle for "
        f"{int(age_s/60)} minutes."
    )
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
    return data


def latest_pipeline_status() -> dict | None:
    if not PIPELINE_DIR.exists():
        return None
    files = sorted(PIPELINE_DIR.glob("pipeline_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None
    return _resolve_pipeline_staleness(data, files[0])


def list_pipelines(limit: int = 20) -> list[dict]:
    if not PIPELINE_DIR.exists():
        return []
    files = sorted(PIPELINE_DIR.glob("pipeline_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(_resolve_pipeline_staleness(data, p))
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
    "📜 Scan History",
    "⚙️ Admin",
]

# API key manager — always on top of sidebar
api_key.render_sidebar()
gmail_ui.render_sidebar()

# -------- Lifetime LLM spend (never-reset ledger) --------
# Reads data/lifetime_cost.json; written by fit_scorer._cost_tick (and any
# future scorer/tailor calls that import cost_ledger). Always visible so the
# user has an anchor on cumulative spend across sessions + machines.
try:
    _ledger = cost_ledger.load()
    _lt_tot = _ledger.get("totals", {})
    _lt_cost = _lt_tot.get("estimated_cost_usd", 0.0) or 0.0
    _lt_calls = _lt_tot.get("llm_calls", 0) or 0
    _lt_in = _lt_tot.get("input_tokens", 0) or 0
    _lt_out = _lt_tot.get("output_tokens", 0) or 0
    _lt_tokens = _lt_in + _lt_out
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💰 Lifetime LLM spend")
    _lsc1, _lsc2 = st.sidebar.columns(2)
    _lsc1.metric("Total", f"${_lt_cost:.2f}")
    _lsc2.metric("Calls", f"{_lt_calls:,}")
    st.sidebar.caption(
        f"{_lt_tokens:,} tokens ({_lt_in:,} in · {_lt_out:,} out) · "
        f"never resets · see ⚙️ Admin → Cost ledger for details"
    )
except Exception as _e:
    st.sidebar.caption(f"Ledger unavailable: {_e}")

# ---------------------------- Error log badge ----------------------------
# logs/errors.jsonl records silent failures from scorer/tracker/scraper
# (progress-write hiccups, fit-cache corruption, ledger writes, etc.).
# Before this badge, users had no way to know something was degrading
# silently. Now: green if quiet, yellow if recent errors, red if
# accumulating. Click-through opens the Admin page.
if error_log is not None:
    try:
        _err_last_hour = error_log.count_recent(since_minutes=60)
        _err_last_day = error_log.count_recent(since_minutes=60 * 24)
        st.sidebar.markdown("### 🪵 Error log")
        if _err_last_hour == 0 and _err_last_day == 0:
            st.sidebar.success("No errors logged", icon="✅")
        elif _err_last_hour == 0:
            st.sidebar.info(f"{_err_last_day} in last 24h · 0 in last hour",
                             icon="ℹ️")
        elif _err_last_hour < 5:
            st.sidebar.warning(
                f"{_err_last_hour} in last hour · {_err_last_day} in 24h",
                icon="⚠️",
            )
        else:
            st.sidebar.error(
                f"{_err_last_hour} in last hour · {_err_last_day} in 24h",
                icon="🔴",
            )
        st.sidebar.caption("See ⚙️ Admin → Error log for details.")
    except Exception as _ee:
        st.sidebar.caption(f"Error log unavailable: {_ee}")

st.sidebar.markdown("---")

page = st.sidebar.radio("Navigate", PAGES)

# Active-runs badge in sidebar
active_runs = scan_runner.active_runs()
pipe = latest_pipeline_status()
pipeline_running = pipe and pipe.get("state") == "running"

# Scorer progress is live if the progress file is <60s old and state=running.
# We check this before deciding to auto-refresh so an idle page doesn't ping
# the filesystem every 5s unnecessarily.
def _scorer_progress_live() -> bool:
    try:
        p = OUT_DIR / "fit_scorer_progress.json"
        if not p.exists():
            return False
        age = (datetime.now().timestamp() - p.stat().st_mtime)
        if age > 60:
            return False
        state = json.loads(p.read_text(encoding="utf-8")).get("state")
        return state == "running"
    except Exception:
        return False


scorer_running = _scorer_progress_live()
any_work_active = bool(active_runs or pipeline_running or scorer_running)

# Auto-refresh: poll every 5s ONLY when something is actively running. An
# idle dashboard stays idle (no rerun thrash, no battery drain). The user
# can also hit 🔄 Refresh manually — see sidebar below. `key` is distinct
# per page so Streamlit doesn't treat them as one counter.
if any_work_active and _HAVE_AUTOREFRESH:
    st_autorefresh(interval=5000, key=f"_autorefresh_{page}")

if any_work_active:
    st.sidebar.markdown("### 🟢 Active work")
    if pipeline_running:
        st.sidebar.caption(
            f"**Pipeline** `{pipe['pipeline_id']}` · {human_elapsed(pipe.get('started_at'))}"
        )
    if scorer_running:
        st.sidebar.caption("**Scorer** running — progress updates every 5s")
    for r in active_runs:
        st.sidebar.caption(
            f"**{r['label']}** · {human_elapsed(r['started_at'])} · pid {r['pid']}"
        )
    if _HAVE_AUTOREFRESH:
        st.sidebar.caption("↻ auto-refresh every 5s while work is active")
    else:
        st.sidebar.caption(
            "⚠️ streamlit-autorefresh not installed — pages won't auto-refresh. "
            "pip install streamlit-autorefresh"
        )
else:
    st.sidebar.caption("No active runs")

# Global manual refresh — clears data caches so tracker/CRM reload. Works
# whether or not streamlit-autorefresh is installed. Distinct from the
# backend-log refresh below, which only touches the session log.
if st.sidebar.button("🔄 Refresh now", key="sidebar_refresh_now",
                      width='stretch',
                      help="Clear data caches and re-read tracker, CRM, "
                           "progress, and run state."):
    st.cache_data.clear()
    st.rerun()

# -------- Backend session log (written by start.ps1) --------
# `logs/current.log` is a pointer file with the path to the active session
# log. If the app was launched via start.ps1 we'll tail it here so the user
# has one place to see everything stdout/stderr that Streamlit + backend
# subprocesses have printed.
_LOGS_DIR = ROOT / "logs"
_pointer = _LOGS_DIR / "current.log"
_session_log = None
if _pointer.exists():
    try:
        _p = _pointer.read_text(encoding="utf-8").strip()
        if _p and Path(_p).exists():
            _session_log = Path(_p)
    except Exception:
        _session_log = None

st.sidebar.markdown("---")
with st.sidebar.expander("🪵 Backend log", expanded=False):
    if _session_log is None:
        st.caption(
            "No active session log. Launch via `start.ps1` to capture "
            "Streamlit + backend stdout/stderr here."
        )
    else:
        st.caption(f"`{_session_log.name}`")
        try:
            _size = _session_log.stat().st_size
            _cap = 12_000  # keep the sidebar render fast
            with open(_session_log, "rb") as _lf:
                if _size > _cap:
                    _lf.seek(_size - _cap)
                    _txt = b"...[truncated - full log on disk]...\n" + _lf.read()
                else:
                    _txt = _lf.read()
            st.code(_txt.decode("utf-8", errors="replace") or "(empty)",
                    language="text")
        except Exception as _e:
            st.caption(f"(read error: {_e})")
        if st.button("🔄 Refresh log", key="sidebar_log_refresh",
                     width='stretch'):
            st.rerun()

# -------- Recent background runs (agent subprocesses) --------
with st.sidebar.expander("📜 Recent background runs", expanded=False):
    _recent = scan_runner.list_runs(limit=8)
    if not _recent:
        st.caption("No runs recorded yet.")
    else:
        for _r in _recent:
            _state = _r.get("state", "?")
            _icon = {"running": "🟢", "finished": "✅",
                     "failed": "❌", "stopped": "⚪"}.get(_state, "•")
            st.caption(
                f"{_icon} **{_r.get('label', '?')}** · {_r.get('started_at', '')}"
            )
        if st.button("Open Admin → Runs for details",
                     key="sidebar_go_admin_runs",
                     width='stretch'):
            # Streamlit doesn't have programmatic page switching for radios;
            # nudge the user.
            st.info("Pick ⚙️ Admin from the navigator above.")

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

    # Scorer progress banner (shown whether pipeline or standalone)
    _sp = load_scorer_progress()
    if _sp and _sp.get("state") == "running":
        cur = _sp.get("current", 0); tot = _sp.get("total", 0) or 1
        frac = min(1.0, cur / tot)
        st.progress(
            frac,
            text=(
                f"🤖 Scoring {cur}/{tot} candidates · "
                f"elapsed {_fmt_eta(_sp.get('elapsed_sec'))} · "
                f"ETA {_fmt_eta(_sp.get('eta_sec'))} · "
                f"apply_now={(_sp.get('verdict_counts') or {}).get('apply_now', 0)}"
            ),
        )

    if not pipeline_running and pipe and pipe.get("state") == "finished":
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

    # ---------- Attention queue — consolidated 'needs your eyes today' ----------
    # Five buckets, each with a default action the user can see at a glance:
    #   1. Tier-1 Found without tailor draft → run tailor
    #   2. Tier-1 promoted with CRM contact at company → warm intro before cold apply
    #   3. High-scored roles with no/short JD → verify JD, consider rescore
    #   4. Tracker entries that errored during scoring → rescore
    #   5. Tracker entries missing primary_variant (pre-variant-upgrade) → rescore
    # This is the "first thing you should look at" list — all other widgets support it.

    # Bucket 1 — Tier-1 Found, no tailor draft.
    # jd_tailor.py writes {safe_company}_{safe_role}_{stamp}.md — it does NOT
    # embed the job_id. The old job_id substring-glob returned [] for almost
    # every role (false NEGATIVE — said "no draft" when a draft existed, or
    # said "draft exists" when another role's company name collided). Reproduce
    # jd_tailor's safe-name transform and check for the final .md (dry-run
    # previews with _prompt.md suffix don't count as a real draft).
    def _tailor_safe_dash(s: str, cap: int | None = None) -> str:
        out = re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_")
        return out[:cap] if cap else out

    def _tailor_draft_exists(company: str, title: str) -> bool:
        sc = _tailor_safe_dash(company, None)
        sr = _tailor_safe_dash(title, 60)
        if not sc or not sr:
            return False
        matches = list(OUT_DIR.glob(f"{sc}_{sr}_*.md"))
        return any(not p.name.endswith("_prompt.md") for p in matches)

    tier1_no_draft = [
        j for j in jobs
        if j.get("tier") == 1
        and j.get("status") in ("Found", "Watch")
        and not _tailor_draft_exists(j.get("company", ""), j.get("title", ""))
    ]

    # Bucket 2 — Tier-1 Found with CRM contact at the same company
    tier1_warm_intro = []
    for j in jobs:
        if j.get("tier") != 1 or j.get("status") not in ("Found", "Watch"):
            continue
        contacts = crm_contacts_at_company(crm, j.get("company", ""))
        if contacts:
            tier1_warm_intro.append((j, contacts))

    # Bucket 3 — High-scored (≥7) with missing JD signal
    # Use fit_notes length as a proxy when _jd_len isn't persisted
    high_score_thin_jd = [
        j for j in jobs
        if int(j.get("fit_score_numeric") or 0) >= 7
        and j.get("status") in ("Found", "Watch")
        and len(j.get("fit_notes", "") or "") < 80
    ]

    # Bucket 4 — Scoring errors (fit_score_numeric=0 on Found/Watch)
    scoring_errors = [
        j for j in jobs
        if int(j.get("fit_score_numeric") or 0) == 0
        and j.get("status") in ("Found", "Watch")
        and j.get("tier", 4) <= 2  # only flag top-tier broken entries
    ]

    # Bucket 5 — Missing primary_variant (pre-variant-upgrade entries)
    missing_variant = [
        j for j in jobs
        if j.get("status") in ("Found", "Watch")
        and j.get("tier", 4) == 1
        and not j.get("primary_variant")
    ]

    attention_total = (len(tier1_no_draft) + len(tier1_warm_intro)
                        + len(high_score_thin_jd) + len(scoring_errors)
                        + len(missing_variant))

    if attention_total:
        st.subheader(f"🎯 Needs your attention ({attention_total})")
        ac1, ac2, ac3, ac4, ac5 = st.columns(5)
        ac1.metric("📄 Need draft", len(tier1_no_draft),
                   help="Tier-1 roles in Found/Watch without a jd_tailor output yet.")
        ac2.metric("⚡ Warm intro", len(tier1_warm_intro),
                   help="Tier-1 roles at companies where you have CRM contacts — "
                        "reach out before applying cold.")
        ac3.metric("⚠ Thin JD", len(high_score_thin_jd),
                   help="High-scored roles (≥7) where scoring had little JD text. "
                        "Consider rescoring or verifying the JD live.")
        ac4.metric("🔧 Rescore", len(scoring_errors),
                   help="Top-tier tracker entries with fit_score_numeric=0 — "
                        "scoring errored. Rerun fit_scorer.")
        ac5.metric("📌 Missing variant", len(missing_variant),
                   help="Tier-1 roles from before the resume-variants feature. "
                        "Rescore to populate primary_variant.")

        # Tier-1 needing draft — most actionable
        if tier1_no_draft:
            with st.expander(f"📄 Tier-1 needing draft ({len(tier1_no_draft)}) — "
                              "tailor runs cost ~$0.15 each", expanded=True):
                tdf = pd.DataFrame([{
                    "id": j.get("id", ""),
                    "company": j.get("company", ""),
                    "title": j.get("title", "")[:70],
                    "variant": j.get("primary_variant", "—"),
                    "fit": j.get("fit_score_numeric", 0),
                    "url": j.get("url", ""),
                } for j in tier1_no_draft[:20]])
                st.dataframe(tdf, hide_index=True, width='stretch',
                              column_config={"url": st.column_config.LinkColumn("open")})
                _td_key = api_key.is_key_valid()
                td_pick = st.selectbox("Tailor which role?",
                                        [j.get("id") for j in tier1_no_draft],
                                        key="attention_tailor_pick")
                if st.button("✏️ Run tailor now", key="attention_tailor_btn",
                              disabled=not _td_key,
                              width='content'):
                    cmd = [sys.executable, str(ROOT / "automation" / "jd_tailor.py"),
                           "--job-id", td_pick]
                    rec = scan_runner.start_run(f"tailor_{td_pick}", cmd)
                    st.success(f"Tailor started (`{rec.run_id}`). "
                               "Draft will land in outputs/ in ~60s.")

        # Warm-intro opportunities
        if tier1_warm_intro:
            with st.expander(f"⚡ Warm-intro opportunities ({len(tier1_warm_intro)}) — "
                              "70% of Director hiring is referral-driven",
                              expanded=True):
                for j, contacts in tier1_warm_intro[:10]:
                    with st.container(border=True):
                        cols = st.columns([3, 1])
                        cols[0].markdown(
                            f"**{j.get('company', '')}** — {j.get('title', '')}"
                            f"  \n_Tier {j.get('tier', '?')} · fit {j.get('fit_score_numeric', 0)}/10"
                            f" · variant {j.get('primary_variant') or '—'}_"
                        )
                        contact_lines = []
                        for c in contacts[:3]:
                            if c["_kind"] == "recruiter":
                                contact_lines.append(
                                    f"  • **{c.get('firm', '?')}** ({c.get('firm_type', '')}) "
                                    f"— last touch: {c.get('last_touchpoint', 'never')}"
                                )
                            else:
                                contact_lines.append(
                                    f"  • **{c.get('name', '?')}** at "
                                    f"{c.get('current_firm', '?')} "
                                    f"— {c.get('relationship', '')}"
                                )
                        cols[0].markdown("\n".join(contact_lines))
                        cols[1].link_button("🔗 Open JD", j.get("url", ""),
                                             width='stretch')

        # Other buckets — combined, lower priority
        other_n = len(high_score_thin_jd) + len(scoring_errors) + len(missing_variant)
        if other_n:
            with st.expander(f"⚙ Scoring / data issues ({other_n})"):
                if high_score_thin_jd:
                    st.markdown(f"**⚠ Thin JD** ({len(high_score_thin_jd)}) — "
                                "these were scored on title/short text; consider rescoring:")
                    thin_df = pd.DataFrame([{
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "title": j.get("title", "")[:70],
                        "fit": j.get("fit_score_numeric", 0),
                        "url": j.get("url", ""),
                    } for j in high_score_thin_jd[:10]])
                    st.dataframe(thin_df, hide_index=True, width='stretch',
                                  column_config={"url": st.column_config.LinkColumn()})
                if scoring_errors:
                    st.markdown(f"**🔧 Scoring errors** ({len(scoring_errors)}) — "
                                "fit_score_numeric=0 (LLM call failed or cache poisoned):")
                    err_df = pd.DataFrame([{
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "title": j.get("title", "")[:70],
                        "url": j.get("url", ""),
                    } for j in scoring_errors[:10]])
                    st.dataframe(err_df, hide_index=True, width='stretch',
                                  column_config={"url": st.column_config.LinkColumn()})
                if missing_variant:
                    st.markdown(f"**📌 Missing variant** ({len(missing_variant)}) — "
                                "pre-variant-upgrade; rescore to populate:")
                    mv_df = pd.DataFrame([{
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "title": j.get("title", "")[:70],
                        "tier": j.get("tier"),
                    } for j in missing_variant[:10]])
                    st.dataframe(mv_df, hide_index=True, width='stretch')

        st.markdown("---")

    # ---------- Pipeline health — freshness + coverage gaps ----------
    # Surfaces scan age, zero-result companies, scored-file health so Saber
    # can see if data is stale or the scraper is quietly failing somewhere.
    scan_p = latest_scan()
    scored_p = latest_scored()
    scan_age_days = None
    scored_age_days = None
    scan_zero_cos: list[str] = []
    scan_total_results: int | None = None
    scan_total_companies: int | None = None
    scored_verdicts: dict = {}
    scored_errors = 0
    if scan_p:
        try:
            scan_age_days = (datetime.now() - datetime.fromtimestamp(
                scan_p.stat().st_mtime)).days
            d = json.loads(scan_p.read_text(encoding="utf-8"))
            scan_total_results = len(d.get("results", []))
            scan_total_companies = d.get("companies_scanned")
            scan_zero_cos = (d.get("diagnostics") or {}).get("zero_result_companies") or []
        except Exception:
            pass
    if scored_p:
        try:
            scored_age_days = (datetime.now() - datetime.fromtimestamp(
                scored_p.stat().st_mtime)).days
            sd = json.loads(scored_p.read_text(encoding="utf-8"))
            for r in sd.get("results", []):
                v = (r.get("fit") or {}).get("fit_verdict", "?")
                scored_verdicts[v] = scored_verdicts.get(v, 0) + 1
            scored_errors = scored_verdicts.get("error", 0)
        except Exception:
            pass

    health_issues = []
    if scan_age_days is None:
        health_issues.append("⚫ No scan on file — run the pipeline.")
    elif scan_age_days >= 7:
        health_issues.append(f"🔴 Scan is **{scan_age_days}d old** — run nightly refresh.")
    elif scan_age_days >= 2:
        health_issues.append(f"🟡 Scan is {scan_age_days}d old — consider refreshing.")
    if scored_errors >= 10:
        health_issues.append(
            f"🔴 **{scored_errors} scoring errors** in the latest run — "
            "check API key / credits."
        )
    zero_frac = (len(scan_zero_cos) / scan_total_companies) if scan_total_companies else 0
    if zero_frac > 0.3:
        health_issues.append(
            f"🟡 {len(scan_zero_cos)}/{scan_total_companies} companies "
            f"returned 0 candidates ({zero_frac:.0%}) — some ATS adapters "
            "may be down."
        )

    if health_issues or (scan_age_days is not None and scan_age_days <= 1):
        st.subheader("📊 Pipeline health")
        hc1, hc2, hc3, hc4 = st.columns(4)
        hc1.metric("Scan age",
                   f"{scan_age_days}d" if scan_age_days is not None else "—",
                   delta=None if scan_age_days is None else (
                       "fresh" if scan_age_days == 0 else f"-{scan_age_days}d"
                   ))
        hc2.metric("Scored age",
                   f"{scored_age_days}d" if scored_age_days is not None else "—")
        hc3.metric("Scan roles", scan_total_results or "—",
                   help=f"{scan_total_companies or '—'} companies scanned")
        hc4.metric("Zero-result cos", len(scan_zero_cos),
                   delta=None if not scan_zero_cos else f"of {scan_total_companies}",
                   delta_color="inverse")
        for issue in health_issues:
            if "🔴" in issue:
                st.error(issue, icon="⚠️")
            elif "🟡" in issue:
                st.warning(issue, icon="📊")
            else:
                st.info(issue, icon="📊")
        if scan_zero_cos:
            with st.expander(
                f"⚠ {len(scan_zero_cos)} companies returned 0 candidates "
                "— possible ATS gaps"
            ):
                st.caption(
                    "Companies where the scraper found nothing this run. "
                    "Usually means: (a) the ATS adapter isn't configured, "
                    "(b) LinkedIn guest search hides their listings, or "
                    "(c) LinkedIn rate-limited the run. If one recurs weekly, "
                    "it's worth adding a dedicated ATS adapter."
                )
                # Group by sector if we have the per-company diag
                try:
                    diag = json.loads(scan_p.read_text(encoding="utf-8"))\
                                .get("diagnostics") or {}
                    per_co = {pc["name"]: pc for pc in (diag.get("per_company") or [])}
                except Exception:
                    per_co = {}
                rows = []
                for name in scan_zero_cos:
                    pc = per_co.get(name, {})
                    rows.append({
                        "company": name,
                        "sector": pc.get("sector", "?"),
                        "has_workday": "✓" if pc.get("has_workday_config") else "",
                        "has_greenhouse": "✓" if pc.get("has_greenhouse_config") else "",
                        "has_phenom": "✓" if pc.get("has_phenom_config") else "",
                        "has_sf": "✓" if pc.get("has_successfactors_config") else "",
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                              width='stretch', height=min(400, 40 + 30 * len(rows)))
        st.markdown("---")

    # ---------- Urgent widget — roles posted in the last 48h ----------
    # Union of (brief top N) + (tracker Found/Watch entries with posted_date).
    brief_preview = load_morning_brief()
    urgent_rows: list[tuple[float, dict, str]] = []  # (hours, row, kind)
    for r in urgent_from_brief(brief_preview, 48):
        urgent_rows.append((hours_since_posted(r.get("posted_date")) or 0.0, r, "brief"))
    for j in jobs:
        if j.get("status") not in ("Found", "Watch"):
            continue
        hrs = hours_since_posted(j.get("posted_date"))
        if hrs is None or hrs > 48:
            continue
        # Avoid double-counting: skip if already in urgent_rows by URL
        if any(r.get("link") == j.get("url") for _, r, _ in urgent_rows):
            continue
        urgent_rows.append((hrs, j, "tracker"))
    urgent_rows.sort(key=lambda t: t[0])

    if urgent_rows:
        st.error(
            f"🔴 **{len(urgent_rows)} urgent role(s) posted in the last 48h** — "
            "apply-speed matters; callback rate drops sharply after 72h.",
            icon="⚡",
        )
        with st.expander(f"⚡ Urgent queue ({len(urgent_rows)})",
                          expanded=len(urgent_rows) <= 5):
            urgent_table = []
            for hrs, r, kind in urgent_rows:
                if kind == "brief":
                    fit = r.get("fit") or {}
                    urgent_table.append({
                        "source": "🌅 brief",
                        "hours_ago": f"{hrs:.0f}h",
                        "company": r.get("company", ""),
                        "title": r.get("title", "")[:70],
                        "verdict": fit.get("fit_verdict", ""),
                        "fit": fit.get("fit_score", ""),
                        "url": r.get("link", ""),
                    })
                else:
                    urgent_table.append({
                        "source": f"📋 {r.get('status', '')}",
                        "hours_ago": f"{hrs:.0f}h",
                        "company": r.get("company", ""),
                        "title": r.get("title", "")[:70],
                        "verdict": r.get("fit_score", ""),
                        "fit": r.get("fit_score_numeric", ""),
                        "url": r.get("url", ""),
                    })
            st.dataframe(
                pd.DataFrame(urgent_table),
                hide_index=True, width='stretch',
                column_config={"url": st.column_config.LinkColumn("open")},
            )
        st.markdown("---")

    # ---------- Morning brief widget — today's 2-3 fresh matches ----------
    brief = load_morning_brief()
    if brief:
        brief_date_raw = brief.get("brief_date", "")
        try:
            brief_date_parsed = datetime.strptime(brief_date_raw, "%Y%m%d").date()
        except ValueError:
            brief_date_parsed = None
        top = brief.get("top") or []
        # Stale after 1 day — brief is meant to be daily.
        is_stale = brief_date_parsed and (date.today() - brief_date_parsed).days >= 1
        staleness = "" if not brief_date_parsed else (
            f" · {(date.today() - brief_date_parsed).days}d old"
            if is_stale else " · today"
        )
        st.subheader(f"🌅 Today's fresh matches{staleness}")
        if is_stale:
            st.caption(
                f"⚠ Latest brief is from `{brief_date_raw}`. "
                "Run the nightly scrape + morning brief to refresh. "
                "See bottom of Pipeline → Run for a one-click button."
            )

        # Distinguish API-failure from genuinely quiet day
        error_count = brief.get("error_count", 0)
        sample_errors = brief.get("sample_errors") or []
        total_scored = brief.get("scored", 0) or 0
        mostly_errors = error_count > 0 and error_count >= max(1, total_scored * 0.5)
        if mostly_errors:
            st.error(
                f"⛔ Brief may be incomplete — {error_count}/{total_scored} roles "
                f"errored during scoring (likely API/credit issue). "
                f"Fix your Anthropic key in the sidebar and re-run the nightly "
                f"refresh.\n\n"
                + ("\n".join(f"• {e[:180]}" for e in sample_errors) if sample_errors else ""),
                icon="🔑",
            )

        if not top:
            if mostly_errors:
                pass  # already showed the error banner
            else:
                st.info(
                    f"No fresh matches in today's delta "
                    f"(triaged {brief.get('triaged', '?')}, scored {brief.get('scored', '?')}, "
                    f"0 actionable). No API errors — this is a genuinely quiet day."
                )
        else:
            st.caption(
                f"Ranked from **{brief.get('total_new', 0)} jobs new since yesterday**. "
                f"Apply to the top 1-2 today; the pipeline queue is already saturated."
            )
            for i, r in enumerate(top, 1):
                f = r.get("fit") or {}
                verdict = f.get("fit_verdict", "?")
                badge = "🟢" if verdict == "apply_now" else "🟡"
                fb = freshness_badge(r.get("posted_date"), r.get("found_at"))
                with st.container(border=True):
                    cols = st.columns([6, 1])
                    # Freshness now sits in the header line — first thing you see.
                    header = (
                        f"### {badge} {i}. [{f.get('fit_score', '?')}/10 · "
                        f"Tier {f.get('tier', '?')}] {r.get('company', '')} — "
                        f"{r.get('title', '')}"
                    )
                    if fb and fb != "—":
                        header += f"  \n<span style='font-size:0.85em; opacity:0.9'>{fb}</span>"
                        cols[0].markdown(header, unsafe_allow_html=True)
                    else:
                        cols[0].markdown(header)
                    variants = f.get("applicable_resume_variants") or []
                    variants_str = " · ".join(variants) if variants else "—"
                    cols[0].caption(
                        f"📄 Lead-with: **{variants_str}** · "
                        f"Sector: {r.get('sector', '')} · "
                        f"Source: {r.get('source', '')}"
                    )
                    cols[0].markdown(f"**{f.get('summary', '')}**")
                    reasons = f.get("top_3_reasons") or []
                    if reasons:
                        with cols[0].expander("Why it fits"):
                            for reason in reasons:
                                st.markdown(f"- {reason}")
                            gaps = f.get("skill_gaps") or []
                            if gaps:
                                st.markdown("**Gaps:** " + "; ".join(gaps))
                    with cols[1]:
                        st.link_button("🔗 Open JD", r.get("link", ""),
                                       width='stretch')
                        # Quick-add to tracker button
                        if st.button("➕ Add to tracker", key=f"brief_add_{i}",
                                     width='stretch'):
                            # Generate a tracker id
                            from uuid import uuid4
                            new_id = f"brief-{datetime.now().strftime('%Y%m%d')}-{str(uuid4())[:6]}"
                            _v = f.get("applicable_resume_variants") or []
                            # Mirror auto_promote / morning_brief: fit_score is
                            # a High/Medium/Low category so the Kanban filter
                            # works; numeric lives in fit_score_numeric.
                            _num = int(f.get("fit_score") or 0)
                            _cat = "High" if _num >= 8 else ("Medium" if _num >= 6 else "Low")
                            new_entry = {
                                "id": new_id,
                                "company": r.get("company", ""),
                                "title": r.get("title", ""),
                                "sector": r.get("sector", ""),
                                "location": r.get("location", ""),
                                "url": r.get("link", ""),
                                "source": r.get("source", ""),
                                "tier": f.get("tier", 3),
                                "fit_score": _cat,
                                "fit_score_numeric": _num,
                                "fit_verdict": verdict,
                                "fit_notes": f.get("summary", ""),
                                "resume_variants": _v,
                                "primary_variant": _v[0] if _v else "",
                                "status": "Found" if verdict == "apply_now" else "Watch",
                                "urgency": "High" if verdict == "apply_now" else "Medium",
                                "date_found": date.today().isoformat(),
                                "next_action": f.get("top_3_reasons", [""])[0][:160] if f.get("top_3_reasons") else "",
                                "followup_schedule": {"next_due": None,
                                                       "cadence_days": [3, 10, 21]},
                            }
                            # Avoid duplicates
                            if not any(j.get("url") == r.get("link") for j in tr["jobs"]):
                                tr["jobs"].append(new_entry)
                                save_tracker(tr)
                                st.success(f"Added {new_id} to tracker.")
                                st.rerun()
                            else:
                                st.warning("Already in tracker.")
        st.markdown("---")

    # ---------- Inbox signals widget (Gmail) ----------
    if gmail_ui.is_connected():
        # Cache for 2 min so page reruns don't hammer IMAP
        @st.cache_data(ttl=120)
        def _load_inbox(days: int):
            sys.path.insert(0, str(ROOT / "automation"))
            import gmail_reader as gr
            msgs = gr.fetch_inbox_signals(days=days, limit=50)
            return [
                {"uid": m.uid, "date": m.date, "kind": m.kind,
                 "sender": m.sender or m.sender_email,
                 "sender_email": m.sender_email,
                 "subject": m.subject, "snippet": m.snippet}
                for m in msgs
            ]
        try:
            inbox = _load_inbox(14)
        except Exception as e:
            inbox = []
            st.caption(f"Gmail load failed: {e}")
        alerts = [x for x in inbox if x["kind"] == "alert"]
        recruiters = [x for x in inbox if x["kind"] == "recruiter"]

        # Build a quick "which tracker roles plausibly sent this email" lookup.
        # Match on either (a) tracker URL host matches sender domain, or
        # (b) tracker company name token appears in subject/sender text.
        # Generic ATS hosts (myworkdayjobs.com, greenhouse.io, lever.co) are
        # NOT used as domain matches — they'd match every company.
        _GENERIC_ATS_HOSTS = {
            "myworkdayjobs.com", "workdayjobs.com", "wd3.myworkdayjobs.com",
            "greenhouse.io", "lever.co", "icims.com", "successfactors.com",
            "linkedin.com",
        }
        from urllib.parse import urlparse

        def _registrable(host: str) -> str:
            parts = (host or "").lower().split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return host or ""

        tracker_index: list[dict] = []  # {"job": j, "domains": set, "tokens": set}
        for j in jobs:
            domains: set[str] = set()
            url = j.get("url") or ""
            if url:
                try:
                    host = urlparse(url).hostname or ""
                    reg = _registrable(host)
                    if reg and reg not in _GENERIC_ATS_HOSTS:
                        domains.add(reg)
                except Exception:
                    pass
            name = (j.get("company") or "").lower()
            tokens = {t for t in re.split(r"[^a-z0-9]+", name)
                      if len(t) >= 4 and t not in {"bank", "financial", "canada",
                                                   "canadian", "group", "capital",
                                                   "global", "asset", "management",
                                                   "investments", "pension", "plan"}}
            tracker_index.append({"job": j, "domains": domains, "tokens": tokens})

        def _match_mail_to_tracker(sender_email: str, subject: str) -> list[dict]:
            """Return tracker jobs plausibly related to this email."""
            se = (sender_email or "").lower()
            subj_l = (subject or "").lower()
            hits: list[dict] = []
            for entry in tracker_index:
                if any(se.endswith("@" + d) or se.endswith("." + d)
                       for d in entry["domains"]):
                    hits.append(entry["job"])
                    continue
                if any(tok in subj_l or tok in se for tok in entry["tokens"]):
                    hits.append(entry["job"])
            return hits

        st.subheader(f"📬 Inbox signals (14d)")
        ic1, ic2, ic3, ic4 = st.columns(4)
        # Pre-compute matches so we can report how many recruiter emails
        # plausibly map to applied roles.
        recruiter_matches = [
            (r, _match_mail_to_tracker(r["sender_email"], r["subject"]))
            for r in recruiters
        ]
        matched_n = sum(1 for _, hits in recruiter_matches if hits)
        ic1.metric("Recruiter/ATS mail", len(recruiters))
        ic2.metric("→ match tracker", matched_n,
                   help="Recruiter emails whose sender domain or subject "
                        "matches a role in your tracker.")
        ic3.metric("Job alerts", len(alerts))
        ic4.metric("Total", len(inbox))

        # Highlight: recruiter emails matched to Applied roles are likely
        # status-change signals.
        applied_matches = [
            (r, [j for j in hits if j.get("status") in (
                "Applied", "Recruiter_Screen", "Phone_Screen",
                "Take_Home", "Onsite")])
            for r, hits in recruiter_matches
        ]
        applied_matches = [(r, hs) for r, hs in applied_matches if hs]
        if applied_matches:
            st.warning(
                f"⚡ **{len(applied_matches)} recruiter email(s) match active "
                "applications** — likely status change. Open Kanban to update.",
                icon="📨",
            )

        with st.expander("👀 Recent recruiter mail (likely status changes)",
                         expanded=bool(recruiter_matches)):
            if not recruiters:
                st.caption("Nothing from recruiters in the last 14d.")
            else:
                rec_rows = []
                for r, hits in recruiter_matches[:30]:
                    match_str = ""
                    if hits:
                        match_str = ", ".join(
                            f"{h.get('id', '?')} [{h.get('status', '?')}]"
                            for h in hits[:3]
                        )
                        if len(hits) > 3:
                            match_str += f" (+{len(hits) - 3} more)"
                    rec_rows.append({
                        "date": r["date"],
                        "from": r["sender"],
                        "subject": r["subject"][:80],
                        "tracker_match": match_str or "—",
                        "snippet": r["snippet"][:120],
                    })
                st.dataframe(pd.DataFrame(rec_rows), hide_index=True,
                              width='stretch')
                st.caption("Tip: rows with a `tracker_match` are likely status-change "
                           "signals — open Kanban and move the role accordingly.")
        st.markdown("---")

    # ---------- Follow-up nudge widget ----------
    fb = followup_buckets(jobs)
    overdue_n = len(fb["overdue"])
    today_n = len(fb["due_today"])
    week_n = len(fb["due_this_week"])
    needs_seed_n = len(fb["no_schedule"])
    total_active = overdue_n + today_n + week_n + needs_seed_n

    if total_active:
        if overdue_n or today_n:
            st.error(
                f"🔔 **Follow-ups needed** — "
                + (f"**{overdue_n} overdue**" if overdue_n else "")
                + (f" · {today_n} due today" if today_n else "")
                + (f" · {week_n} due this week" if week_n else "")
                + (f" · {needs_seed_n} need a schedule" if needs_seed_n else ""),
                icon="⚠️",
            )
        else:
            st.info(
                f"🔔 {week_n} follow-up(s) due this week"
                + (f" · {needs_seed_n} need a schedule" if needs_seed_n else ""),
                icon="📅",
            )

        with st.expander(f"👀 Follow-up queue ({total_active} active)", expanded=bool(overdue_n or today_n)):
            t_overdue, t_today, t_week, t_noschd = st.tabs([
                f"🔴 Overdue ({overdue_n})",
                f"🟡 Due today ({today_n})",
                f"🟢 This week ({week_n})",
                f"⚪ No schedule ({needs_seed_n})",
            ])

            def _render_followup_rows(items, tab, mode):
                if not items:
                    tab.caption("Nothing here. 🎉")
                    return
                # Build rows
                rows = []
                for item in items:
                    if isinstance(item, tuple):
                        days, j = item
                    else:
                        days, j = 0, item
                    sched = j.get("followup_schedule") or {}
                    rows.append({
                        "id": j["id"],
                        "company": j.get("company", ""),
                        "title": j.get("title", "")[:60],
                        "applied": j.get("date_applied", ""),
                        "next_due": sched.get("next_due") or "(not set)",
                        "days": (f"+{days} overdue" if mode == "overdue"
                                 else f"in {days}d" if mode == "upcoming"
                                 else "today" if mode == "today"
                                 else "—"),
                        "url": j.get("url", ""),
                    })
                tab.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True, width='stretch',
                    column_config={"url": st.column_config.LinkColumn("open")},
                )
                # Action row — log follow-up on N selected
                pick = tab.selectbox("Log follow-up for", [r["id"] for r in rows],
                                      key=f"fu_pick_{mode}")
                msg = tab.text_input("Note (optional, saved to outreach_log)",
                                      key=f"fu_note_{mode}",
                                      placeholder="Emailed recruiter re: status")
                ca, cb = tab.columns(2)
                if ca.button(f"✅ Log follow-up & advance cadence",
                             key=f"fu_log_{mode}", width='stretch'):
                    for j in tr["jobs"]:
                        if j["id"] == pick:
                            j.setdefault("outreach_log", []).append({
                                "date": date.today().isoformat(),
                                "type": "followup",
                                "note": msg or "followup",
                            })
                            advance_followup(j)
                            break
                    save_tracker(tr)
                    st.success(f"Logged follow-up on {pick} and advanced next_due.")
                    st.rerun()
                if cb.button(f"⏭ Skip this rung (push +7d)",
                             key=f"fu_skip_{mode}", width='stretch'):
                    for j in tr["jobs"]:
                        if j["id"] == pick:
                            sched = j.setdefault("followup_schedule", {"cadence_days": [3, 10, 21]})
                            cur = parse_date(sched.get("next_due")) or date.today()
                            sched["next_due"] = (cur + timedelta(days=7)).isoformat()
                            break
                    save_tracker(tr)
                    st.success(f"Pushed {pick} +7 days.")
                    st.rerun()

            _render_followup_rows(fb["overdue"], t_overdue, "overdue")
            _render_followup_rows(fb["due_today"], t_today, "today")
            _render_followup_rows(fb["due_this_week"], t_week, "upcoming")
            _render_followup_rows(fb["no_schedule"], t_noschd, "noschedule")

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
        if st.button("🎯 Run full pipeline", width='stretch', type="primary",
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
        if st.button("🏛️ Fast pipeline (ATS-only)", width='stretch',
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
        if st.button("📊 Weekly report", width='stretch'):
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
        st.dataframe(fd, hide_index=True, width='stretch')

    st.markdown("---")

    # Apply-this-week queue
    st.subheader("🎯 Apply this week")
    apply_ids = meta.get("kanban_targets_week1", {}).get("apply_this_week", [])
    apply_rows = jobs_df[jobs_df["id"].isin(apply_ids)] if "id" in jobs_df.columns else pd.DataFrame()
    if not apply_rows.empty:
        cols = [c for c in ["id", "company", "title", "tier", "fit_score", "url"] if c in apply_rows.columns]
        st.dataframe(apply_rows[cols], hide_index=True, width='stretch',
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

    # ---------- Data freshness headline: latest scan, latest Gmail -------
    # Three compact metrics so the user sees at-a-glance what data they're
    # working with BEFORE they decide whether to refresh anything.
    def _latest_by_prefix(prefix: str):
        files = sorted(OUT_DIR.glob(f"{prefix}*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        # Exclude *_scored.json in the scan search so we don't show the
        # scored artifact as if it were a fresh scrape.
        files = [f for f in files if "_scored" not in f.name
                 and "scan_checkpoint" not in f.name]
        return files[0] if files else None

    def _age_label(p: Path | None) -> str:
        if p is None:
            return "—"
        age_s = datetime.now().timestamp() - p.stat().st_mtime
        if age_s < 3600:
            return f"{int(age_s / 60)}m ago"
        if age_s < 86400:
            return f"{int(age_s / 3600)}h ago"
        return f"{int(age_s / 86400)}d ago"

    _latest_web = _latest_by_prefix("scan_v4")
    _latest_gm = _latest_by_prefix("scan_gmail_")
    _latest_scored = _latest_by_prefix("scan_") if False else None
    _latest_scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                                    key=lambda p: p.stat().st_mtime, reverse=True)
    _latest_scored = _latest_scored_files[0] if _latest_scored_files else None

    def _count_rows(p: Path | None) -> int:
        if not p or not p.exists():
            return 0
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return len(d.get("results", []))
        except Exception:
            return 0

    fh1, fh2, fh3, fh4 = st.columns(4)
    fh1.metric("Latest web scan", _age_label(_latest_web),
                f"{_count_rows(_latest_web):,} roles" if _latest_web else "—")
    fh2.metric("Latest Gmail pull", _age_label(_latest_gm),
                f"{_count_rows(_latest_gm):,} alerts" if _latest_gm else "—")
    fh3.metric("Latest scored", _age_label(_latest_scored),
                _latest_scored.name if _latest_scored else "—")
    fh4.metric("Tracker roles", f"{len(jobs):,}",
                f"{sum(1 for j in jobs if j.get('status') == 'Found')} Found")
    st.markdown("---")

    # ---------- Pause / resume / checkpoint status ----------
    # The scraper drops scan_checkpoint.json after each company and watches for
    # scan_pause.flag. These controls let the user pause a long scrape and
    # resume it later (e.g., after closing the laptop, a reboot, or moving
    # to a personal network for Gmail).
    _ckpt_path = OUT_DIR / "scan_checkpoint.json"
    _pause_path = OUT_DIR / "scan_pause.flag"
    _ckpt = None
    if _ckpt_path.exists():
        try:
            _ckpt = json.loads(_ckpt_path.read_text(encoding="utf-8"))
        except Exception:
            _ckpt = None

    _pause_requested = _pause_path.exists()

    # Determine if a scraper is currently running
    try:
        _scraper_active = any(
            "jd_scraper" in (r.get("label") or "") or
            "scrape" in (r.get("label") or "")
            for r in scan_runner.active_runs()
        )
    except Exception:
        _scraper_active = False

    if _ckpt or _pause_requested or _scraper_active:
        with st.container(border=True):
            st.markdown("#### ⏸ Scrape pause / resume")
            pc = _ckpt or {}
            done = pc.get("completed_count", 0)
            tot = pc.get("total_companies", 0) or 1
            found_so_far = len(pc.get("found", []))
            cx1, cx2, cx3, cx4 = st.columns(4)
            cx1.metric("State",
                       "🔴 running (pause pending)" if (_scraper_active and _pause_requested)
                       else "🟢 running" if _scraper_active
                       else "⏸ paused (checkpoint)" if _ckpt
                       else "⚪ idle")
            cx2.metric("Companies", f"{done}/{tot}" if tot else "—",
                        f"{(done/tot*100):.0f}%" if tot else None)
            cx3.metric("Captured so far", found_so_far)
            cx4.metric("Checkpoint age",
                       human_elapsed(pc.get("updated_at")) if pc.get("updated_at") else "—")

            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                _can_pause = _scraper_active and not _pause_requested
                if st.button("⏸ Request pause", disabled=not _can_pause,
                              width='stretch', key="scrape_pause_btn",
                              help="Creates scan_pause.flag. The scraper checks "
                                   "between companies and exits cleanly after "
                                   "the current one finishes."):
                    _pause_path.parent.mkdir(parents=True, exist_ok=True)
                    _pause_path.write_text(datetime.now().isoformat(), encoding="utf-8")
                    st.success("Pause flag set. Scraper will stop after the "
                                "company it's currently scanning.")
                    st.rerun()
            with bc2:
                _key_ok_resume = api_key.is_key_valid()
                _can_resume = bool(_ckpt) and not _scraper_active
                if st.button("▶ Resume scrape", disabled=not _can_resume,
                              width='stretch', type="primary",
                              key="scrape_resume_btn",
                              help="Launches jd_scraper.py --resume with the "
                                   "same options as the checkpointed run."):
                    opts = (pc.get("options") or {})
                    cmd = [sys.executable, str(ROOT / "automation" / "jd_scraper.py"),
                           "--resume", "--expansion"]
                    if opts.get("linkedin_only"):
                        cmd.append("--linkedin-only")
                    if opts.get("workday_only"):
                        cmd.append("--workday-only")
                    try:
                        if _pause_path.exists():
                            _pause_path.unlink()
                    except Exception:
                        pass
                    rec = scan_runner.start_run("scrape_resume", cmd)
                    st.success(f"Resumed as `{rec.run_id}`. "
                               "Watch progress on Admin → Runs.")
                    st.rerun()
            with bc3:
                if st.button("🗑 Discard checkpoint",
                              disabled=not bool(_ckpt) or _scraper_active,
                              width='stretch', key="scrape_ckpt_clear_btn",
                              help="Delete the checkpoint file. The next scan "
                                   "starts fresh. Use this if the target list "
                                   "changed or you want to re-scan from scratch."):
                    try:
                        _ckpt_path.unlink()
                        if _pause_path.exists():
                            _pause_path.unlink()
                        st.success("Checkpoint discarded.")
                    except Exception as _e:
                        st.error(f"Could not delete: {_e}")
                    st.rerun()

            if _pause_requested and _scraper_active:
                st.caption("⏳ Pause requested — waiting for the current company to finish.")
            elif _ckpt:
                st.caption(f"Checkpoint file: `{_ckpt_path}` · signature {_ckpt.get('targets_signature', '?')}")

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

    # ---------- Funnel data collection ----------
    scan_f = latest_scan()
    scored_f = latest_scored()

    scrape_count = None
    scrape_raw = None
    dedup_dropped_url = dedup_dropped_near = None
    zero_companies: list[str] = []
    per_company_diag: list[dict] = []
    if scan_f:
        try:
            d = json.loads(scan_f.read_text(encoding="utf-8"))
            scrape_count = len(d.get("results", []))
            dedup = d.get("dedup_stats") or {}
            scrape_raw = dedup.get("input", scrape_count)
            dedup_dropped_url = dedup.get("dropped_url", 0)
            dedup_dropped_near = dedup.get("dropped_near", 0)
            diag = d.get("diagnostics") or {}
            zero_companies = diag.get("zero_result_companies") or []
            per_company_diag = diag.get("per_company") or []
        except Exception:
            pass

    score_input = score_pass = score_count = None
    verdict_counts: dict = {}
    if scored_f:
        try:
            d = json.loads(scored_f.read_text(encoding="utf-8"))
            score_input = d.get("total_input")
            score_pass = d.get("stage1_passed")
            score_count = d.get("stage2_scored")
            for r in d.get("results", []):
                fv = (r.get("fit") or {}).get("fit_verdict", "?")
                verdict_counts[fv] = verdict_counts.get(fv, 0) + 1
        except Exception:
            pass

    apply_n = verdict_counts.get("apply_now", 0)
    tailor_n = verdict_counts.get("tailor_and_apply", 0)
    actionable_n = apply_n + tailor_n

    tracker_found = sum(1 for j in jobs if j.get("status") in ("Found", "Watch"))
    tracker_applied = sum(1 for j in jobs if parse_date(j.get("date_applied")))
    tailored_docs = len(list(OUT_DIR.glob("*_prompt.md")))

    # ---------- Funnel visualization ----------
    # Row 1: stage cards with counts
    # Row 2: transition captions between cards
    st.markdown("#### Pipeline funnel")
    cols = st.columns([3, 1, 3, 1, 3, 1, 3, 1, 3])

    def _big_number(col, emoji, label, value, sub=""):
        col.markdown(f"<div style='text-align:center'>"
                     f"<div style='font-size:1.6em'>{emoji}</div>"
                     f"<div style='font-size:2em; font-weight:600'>{value if value is not None else '—'}</div>"
                     f"<div style='font-size:0.85em; opacity:0.8'>{label}</div>"
                     f"<div style='font-size:0.75em; opacity:0.6'>{sub}</div>"
                     f"</div>",
                     unsafe_allow_html=True)

    def _arrow(col, label=""):
        col.markdown(f"<div style='text-align:center; padding-top:18px'>"
                     f"<div style='font-size:1.8em; opacity:0.4'>→</div>"
                     f"<div style='font-size:0.75em; opacity:0.7'>{label}</div>"
                     f"</div>",
                     unsafe_allow_html=True)

    _big_number(cols[0], "🛰️", "Scraped", scrape_raw if scrape_raw else scrape_count,
                sub=f"across {len(per_company_diag)} cos" if per_company_diag else "")
    _arrow(cols[1], f"-{(dedup_dropped_url or 0) + (dedup_dropped_near or 0)} dupe"
                    if dedup_dropped_url is not None else "")
    _big_number(cols[2], "✂️", "Unique", scrape_count,
                sub=f"-{dedup_dropped_url} URL, -{dedup_dropped_near} near"
                    if dedup_dropped_url is not None else "")
    _arrow(cols[3], f"-{(score_input or scrape_count or 0) - (score_pass or 0)} off-profile"
                    if score_input and score_pass else "")
    _big_number(cols[4], "🎯", "Triaged", score_pass,
                sub=f"stage-1 pass" if score_pass else "")
    _arrow(cols[5], f"-{(score_pass or 0) - (score_count or 0)} err"
                    if score_pass is not None and score_count is not None and score_pass != score_count else "")
    _big_number(cols[6], "🤖", "Scored", score_count,
                sub=f"apply_now:{apply_n} tailor:{tailor_n}" if score_count else "")
    _arrow(cols[7], f"-{(actionable_n or 0) - tracker_found} pending" if actionable_n else "")
    _big_number(cols[8], "📋", "Tracker",
                tracker_found if tracker_found else "—",
                sub=f"{tracker_applied} applied · {tailored_docs} tailored")

    if pipeline_running:
        st.info(
            f"⏱️ Pipeline running — elapsed {human_elapsed(pipe['started_at'])}",
            icon="🎯",
        )
    if zero_companies:
        with st.expander(f"⚠️ {len(zero_companies)} companies returned 0 candidates — click to inspect"):
            st.caption(
                "These targets produced no candidates. Common causes: "
                "LinkedIn guest search doesn't surface their Toronto listings (Goldman, Deutsche, PIMCO), "
                "regulator careers pages aren't on Workday (OSFI, OSC, FSRA), "
                "or LinkedIn rate-limited the scan. "
                "Config fix: add a Workday/Greenhouse tenant, or rely on manual adds."
            )
            st.code("\n".join(f"  • {n}" for n in zero_companies), language="text")

    if pipeline_running:
        st.info(
            f"⏱️ Pipeline `{pipe['pipeline_id']}` running for "
            f"{human_elapsed(pipe['started_at'])}.",
            icon="🎯",
        )

    st.markdown("---")

    # ---------- Main tabs ----------
    tabs = st.tabs(
        ["🎯 Run pipeline", "🔗 Score a URL", "🛰️ 1·Scrape", "🤖 2·Score",
         "👁 3·Triage", "🚀 4·Promote", "📜 History"]
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

        run_col, brief_col, gmail_col, spacer = st.columns([1, 1, 1, 2])
        with run_col:
            if st.button("▶️ Launch pipeline", type="primary", width='stretch',
                         disabled=not can_run):
                rec = scan_runner.start_run("pipeline", cmd)
                st.success(f"Pipeline launched (`{rec.run_id}`, pid {rec.pid})")
                st.rerun()
        with brief_col:
            # One-click: scrape + delta + morning brief.
            # Much cheaper than the full pipeline — scores only what's new.
            brief_key_ok = api_key.is_key_valid()
            if st.button("🌅 Nightly refresh", width='stretch',
                         disabled=(not brief_key_ok) or bool(pipeline_running),
                         help="Scrape + find new roles since last scan + score only "
                              "those + emit top-3 brief. Cheap (~$0.03) and fast (~25 min)."):
                # Platform-aware: use the PS1 on Windows, chained bash elsewhere
                if sys.platform == "win32":
                    ps = ROOT / "automation" / "nightly_refresh.ps1"
                    nightly_cmd_list = [
                        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(ps),
                    ]
                else:
                    chained = (
                        f"{sys.executable} {ROOT / 'automation' / 'jd_scraper.py'} --expansion --gmail && "
                        f"{sys.executable} {ROOT / 'automation' / 'scan_delta.py'} && "
                        f"{sys.executable} {ROOT / 'automation' / 'morning_brief.py'} --top 5 --auto-add 3 --auto-tailor"
                    )
                    nightly_cmd_list = ["bash", "-c", chained]
                rec = scan_runner.start_run("nightly_refresh", nightly_cmd_list)
                st.success(f"Nightly refresh started (`{rec.run_id}`). "
                           f"Dashboard will show fresh matches when done.")
                st.rerun()
        with gmail_col:
            # Standalone Gmail alert fetch — pulls LinkedIn/Indeed job alert
            # emails from the last 14 days, writes scan_gmail_<stamp>.json.
            # Separate button so the user can refresh alerts daily in ~10s
            # without kicking off a full web scrape.
            _gmail_ok = gmail_ui.is_connected()
            if st.button("📬 Pull Gmail alerts", width='stretch',
                         disabled=(not _gmail_ok) or bool(pipeline_running),
                         help="Fetch the last 14 days of LinkedIn/Indeed job "
                              "alert emails, dedupe against tracker, and write "
                              "scan_gmail_<stamp>.json. ~10-30s. Doesn't call "
                              "the API. Run fit_scorer on the output after."):
                rec = scan_runner.start_run("gmail_fetch", [
                    sys.executable,
                    str(ROOT / "automation" / "gmail_fetch.py"),
                    "--days", "14",
                ])
                st.success(
                    f"Gmail fetch started (`{rec.run_id}`). "
                    f"Output lands in `automation/outputs/scan_gmail_*.json`. "
                    f"Then score it from the 2·Score tab."
                )
                st.rerun()
            if not _gmail_ok:
                st.caption("🔌 Connect Gmail in the sidebar first.")

        # Scorer progress bar (visible whenever fit_scorer is running,
        # whether invoked directly or as part of a pipeline)
        scorer_running = render_scorer_progress()

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
        elif scorer_running:
            # Scorer running standalone (not pipeline) — still auto-refresh
            if st.checkbox("🔄 Auto-refresh every 3s", value=True, key="score_auto_pipe"):
                import time as _t
                _t.sleep(3)
                st.rerun()

    # ================== TAB: Score a URL ==================
    with tabs[1]:
        st.subheader("🔗 Score a URL")
        st.caption(
            "Paste any job URL (jobs.citi.com, OSFI careers, company career site, "
            "even a LinkedIn you found outside the scan) and get a fresh LLM fit score "
            "against your Master Repository. Takes ~5s and costs ~$0.001."
        )
        url_key_ok = api_key.is_key_valid()
        if not url_key_ok:
            st.warning("🔑 API key required. Set it in the sidebar.")
        url_in = st.text_input(
            "JD URL",
            placeholder="https://jobs.citi.com/job/mississauga/non-trading-market-risk-officer-vice-president/287/93536402784",
            key="url_score_input",
        )
        u1, u2, u3 = st.columns([2, 2, 1])
        with u1:
            company_in = st.text_input("Company (optional — inferred from URL)",
                                        key="url_score_company")
        with u2:
            title_in = st.text_input("Title (optional — inferred from JD)",
                                      key="url_score_title")
        with u3:
            add_to_tr = st.checkbox("Add to tracker",
                                     help="If result is actionable, append to "
                                          "job_tracker_data.json",
                                     key="url_score_add")
        rescore = st.checkbox("Bypass cache (force fresh LLM call)",
                               key="url_score_rescore")
        if st.button("🤖 Score this URL", type="primary",
                     disabled=not (url_key_ok and url_in.strip()),
                     key="url_score_btn"):
            cmd = [sys.executable, str(ROOT / "automation" / "score_url.py"),
                   url_in.strip(), "--json-only"]
            if company_in.strip():
                cmd += ["--company", company_in.strip()]
            if title_in.strip():
                cmd += ["--title", title_in.strip()]
            if rescore:
                cmd.append("--rescore")
            if add_to_tr:
                cmd.append("--add-to-tracker")
            with st.spinner("Fetching JD and scoring..."):
                res = subprocess.run(cmd, capture_output=True, text=True,
                                      cwd=str(ROOT), timeout=60)
            if res.returncode != 0:
                st.error(f"Scoring failed (exit {res.returncode}):")
                st.code(res.stderr[-2000:], language="text")
            else:
                try:
                    fit = json.loads(res.stdout)
                except json.JSONDecodeError:
                    st.error("Scorer did not return JSON:")
                    st.code(res.stdout[-1000:], language="text")
                else:
                    verdict = fit.get("fit_verdict", "?")
                    score = fit.get("fit_score", "?")
                    tier = fit.get("tier", "?")
                    variants = fit.get("applicable_resume_variants") or []
                    badge = {"apply_now": "🟢", "tailor_and_apply": "🟡",
                             "watch": "⚪", "skip": "🔴", "error": "❌"}.get(verdict, "⚪")
                    st.markdown(
                        f"### {badge} Verdict: `{verdict}` · "
                        f"Score: **{score}/10** · Tier {tier}"
                    )
                    cA, cB = st.columns(2)
                    with cA:
                        st.markdown("**Lead-with resume(s):** "
                                    + (" · ".join(variants) if variants else "—"))
                        st.markdown("**Summary:** " + fit.get("summary", "—"))
                    with cB:
                        reasons = fit.get("top_3_reasons") or []
                        if reasons:
                            st.markdown("**Why it fits:**")
                            for r in reasons:
                                st.markdown(f"- {r}")
                        gaps = fit.get("skill_gaps") or []
                        if gaps:
                            st.markdown("**Gaps:** " + "; ".join(gaps))
                    if add_to_tr and "Added" in (res.stderr or ""):
                        st.success("✅ Added to tracker. Reload the Kanban to see it.")
                        st.cache_data.clear()
                    with st.expander("Raw scorer output"):
                        st.code(json.dumps(fit, indent=2), language="json")

    # ================== TAB: Scrape ==================
    with tabs[2]:
        st.subheader("Stage 1 — Scrape")
        st.caption("Pull raw job postings from LinkedIn + Workday + Greenhouse + Lever.")
        if scan_f:
            try:
                d = json.loads(scan_f.read_text(encoding="utf-8"))
                ds = d.get("dedup_stats") or {}
                ccol1, ccol2, ccol3, ccol4 = st.columns(4)
                ccol1.metric("Raw", ds.get("input", "—"))
                ccol2.metric("After dedup", len(d.get("results", [])),
                             delta=-(ds.get("dropped_url", 0) + ds.get("dropped_near", 0))
                             if ds else None)
                ccol3.metric("Sectors", len(d.get("by_sector", {})))
                ccol4.metric("Companies", d.get("companies_scanned", "—"))
                st.caption(f"File: `{scan_f.name}` · modified "
                           f"{datetime.fromtimestamp(scan_f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}"
                           + (f" · dedup removed {ds.get('dropped_url',0)} dup URLs + "
                              f"{ds.get('dropped_near',0)} near-dups" if ds else ""))

                # By-sector breakdown
                sb = d.get("by_sector", {})
                if sb:
                    sb_df = pd.DataFrame(sorted(sb.items(), key=lambda x: -x[1]),
                                         columns=["sector", "candidates"])
                    st.bar_chart(sb_df.set_index("sector"))

                # Per-company diagnostics
                diag = d.get("diagnostics") or {}
                pc = diag.get("per_company") or []
                if pc:
                    pc_df = pd.DataFrame(pc)
                    pc_df = pc_df.sort_values("total", ascending=False)
                    with st.expander(f"🔍 Per-company breakdown ({len(pc_df)} targets)"):
                        st.caption(
                            "Filter: rows with `total=0` are companies that returned nothing. "
                            "Check `has_workday_config` — if False, company relies on LinkedIn only."
                        )
                        show_zero = st.checkbox("Show only 0-result companies", value=False,
                                                 key="scrape_zero_only")
                        view = pc_df[pc_df["total"] == 0] if show_zero else pc_df
                        st.dataframe(view, hide_index=True, width='stretch', height=400)

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
                st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch',
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
    with tabs[3]:
        st.subheader("Stage 2 — Score with Claude")
        st.caption(
            "Each candidate is rated 1–10 against Saber's Master Repository. "
            "Verdicts: apply_now / tailor_and_apply / watch / skip."
        )

        # Live progress if scorer is running
        scorer_running_here = render_scorer_progress()
        if scorer_running_here:
            if st.checkbox("🔄 Auto-refresh every 3s", value=True, key="score_auto_tab"):
                import time as _t
                _t.sleep(3)
                st.rerun()

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.warning("No scored scans yet.")
        else:
            which = st.selectbox("Scored file", [p.name for p in scored_files], key="score_file")
            sc = json.loads((OUT_DIR / which).read_text(encoding="utf-8"))
            results = sc.get("results", [])

            # ── API error / failed-run warning ──────────────────────────────
            api_err = sc.get("api_error")
            verdicts: dict = {}
            for r in results:
                v = (r.get("fit") or {}).get("fit_verdict", "?")
                verdicts[v] = verdicts.get(v, 0) + 1
            all_skip = verdicts and set(verdicts.keys()) <= {"skip", "error", "?"}

            if api_err:
                st.error(
                    f"⛔ **Scorer failed — API error detected.**\n\n"
                    f"`{api_err[:300]}`\n\n"
                    f"Fix your API key / credits, then re-score.",
                    icon="🔑",
                )
            elif all_skip and sc.get("stage2_scored", 0) > 10:
                st.warning(
                    "⚠️ **All jobs scored as 'skip'** — this usually means the LLM calls "
                    "failed silently (no API credits, wrong key, or network issue). "
                    "Check your `ANTHROPIC_API_KEY` and billing, then re-score.",
                    icon="⚠️",
                )
            # ────────────────────────────────────────────────────────────────

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Input", sc.get("total_input", "—"))
            m2.metric("Stage 1 pass", sc.get("stage1_passed", "—"))
            m3.metric("Stage 2 scored", sc.get("stage2_scored", "—"))
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
    with tabs[4]:
        st.subheader("Stage 3 — Triage")
        st.caption("Inspect the scoring funnel: which roles were dropped and why, "
                   "vs. which made it to Claude. Sub-tabs below.")

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.info("No scored scan available. Run the scorer first.")
        else:
            which = st.selectbox("Scored file", [p.name for p in scored_files], key="triage_file")
            sc = json.loads((OUT_DIR / which).read_text(encoding="utf-8"))
            results = sc.get("results", [])

            # --- Funnel headline metrics ------------------------------------
            total_input = sc.get("total_input", len(results))
            passed = sc.get("stage1_passed", 0)
            dropped = sc.get("stage1_dropped", 0)
            only_filt = sc.get("stage1_only_filtered", 0)
            scored_n = sc.get("stage2_scored", len(results))
            fm1, fm2, fm3, fm4 = st.columns(4)
            fm1.metric("Total input", f"{total_input:,}")
            fm2.metric("Dropped (rule)", f"{dropped:,}",
                        f"{(100*dropped/max(total_input,1)):.0f}%",
                        delta_color="inverse")
            fm3.metric("Passed stage-1", f"{passed:,}",
                        f"{(100*passed/max(total_input,1)):.0f}%")
            fm4.metric("LLM-scored", f"{scored_n:,}")

            triage_tabs = st.tabs([
                "🎯 Scored candidates",
                "🚫 Dropped (rule-triage)",
                "🏢 By company",
            ])

            # --- Sub-tab 1: scored candidates -------------------------------
            with triage_tabs[0]:
                if not results:
                    st.info("No scored candidates in this file — "
                            "either the scorer was dry-run, the API key "
                            "preflight failed, or all roles dropped at stage 1.")
                else:
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
                            "variants": "/".join(f.get("applicable_resume_variants") or []),
                            "summary": f.get("summary", ""),
                            "gaps": ", ".join(f.get("skill_gaps") or []),
                            "source": r.get("source", ""),
                            "posted": r.get("posted_date", ""),
                            "found": r.get("found_at", ""),
                            "url": r.get("link", ""),
                        })
                    df = pd.DataFrame(rows).sort_values(["fit", "tier"],
                                                         ascending=[False, True])

                    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
                    with f1:
                        min_fit = st.slider("Min fit score", 1, 10, 7, key="triage_min")
                    with f2:
                        _verdict_opts = sorted(df["verdict"].dropna().unique())
                        _verdict_defaults = [v for v in ["apply_now", "tailor_and_apply"]
                                              if v in _verdict_opts]
                        verdict_filter = st.multiselect(
                            "Verdict", _verdict_opts,
                            default=_verdict_defaults, key="triage_verdict")
                    with f3:
                        sector_filter = st.multiselect(
                            "Sector", sorted(df["sector"].dropna().unique()),
                            key="triage_sector")
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
                    st.dataframe(view, hide_index=True, width='stretch', height=500,
                                 column_config={"url": st.column_config.LinkColumn("open")})

                    # Inspect one
                    if not view.empty:
                        titles = [f"{r.company} — {r.title[:60]}" for r in view.itertuples()]
                        idx = st.selectbox("Inspect candidate", range(len(view)),
                                            format_func=lambda i: titles[i],
                                            key="triage_pick")
                        row = view.iloc[idx]
                        with st.container(border=True):
                            cL, cR = st.columns([3, 1])
                            with cL:
                                st.markdown(f"### {row['company']} — {row['title']}")
                                st.caption(f"Sector: {row['sector']} · Source: {row['source']}")
                                st.markdown(f"**Verdict:** `{row['verdict']}` · "
                                            f"**Fit:** {row['fit']}/10 · **Tier:** {row['tier']}")
                                st.markdown(f"**Summary:** {row['summary']}")
                                if row["gaps"]:
                                    st.markdown(f"**Gaps:** {row['gaps']}")
                            with cR:
                                st.link_button("🔗 Open JD", row["url"], width='stretch')

            # --- Sub-tab 2: dropped (rule-triage) ---------------------------
            with triage_tabs[1]:
                drops = sc.get("triage_drops") or []
                if not drops:
                    st.info(
                        "No triage-drop records in this scored file. "
                        "This usually means the scored file was produced by "
                        "an older version of fit_scorer. Re-run the scorer "
                        "(or a dry-run) to populate the triage audit trail."
                    )
                else:
                    # Reason histogram
                    from collections import Counter as _Counter
                    _reason_ct = _Counter()
                    _neg_term_ct = _Counter()
                    for d in drops:
                        for rr in d.get("rule_reasons", []):
                            # "neg:intern" → show negative terms separately
                            if rr.startswith("neg:"):
                                _neg_term_ct[rr[4:]] += 1
                                _reason_ct["neg_title_match"] += 1
                            else:
                                # strip the hit list so we group by type
                                key = rr.split("=", 1)[0]
                                _reason_ct[key] += 1

                    rm1, rm2 = st.columns([1, 1])
                    with rm1:
                        st.markdown("**Drop reasons (histogram)**")
                        _reason_df = pd.DataFrame(
                            [{"reason": k, "count": v} for k, v in _reason_ct.most_common()]
                        )
                        if not _reason_df.empty:
                            st.dataframe(_reason_df, hide_index=True, width='stretch',
                                         height=200)
                    with rm2:
                        st.markdown("**Top negative-title terms**")
                        st.caption("Phrases that hard-failed stage-1 "
                                    "(e.g. 'intern', 'teller', 'software engineer'). "
                                    "Tune fit_scorer.NEG_TITLE_TERMS to change.")
                        _neg_df = pd.DataFrame(
                            [{"term": k, "hits": v} for k, v in _neg_term_ct.most_common(20)]
                        )
                        if not _neg_df.empty:
                            st.dataframe(_neg_df, hide_index=True, width='stretch',
                                         height=200)
                        else:
                            st.caption("_(no hard-fail negative terms — all drops were "
                                       "insufficient-signal)_")

                    st.markdown("---")
                    st.markdown(f"**All {len(drops):,} dropped roles**")
                    _drop_q = st.text_input(
                        "Search company/title in drops",
                        key="triage_drop_q",
                        placeholder="scotiabank / data engineer / ...",
                    )
                    _drop_rows = []
                    for d in drops:
                        co, ti = d.get("company", ""), d.get("title", "")
                        if _drop_q:
                            q = _drop_q.lower()
                            if q not in co.lower() and q not in ti.lower():
                                continue
                        _drop_rows.append({
                            "company": co,
                            "title": ti,
                            "why": ", ".join(d.get("rule_reasons", []))[:120],
                            "score": d.get("score", 0),
                            "source": d.get("source", ""),
                            "url": d.get("link", ""),
                        })
                    st.caption(f"Showing {len(_drop_rows):,} of {len(drops):,}")
                    if _drop_rows:
                        st.dataframe(
                            pd.DataFrame(_drop_rows),
                            hide_index=True, width='stretch', height=420,
                            column_config={"url": st.column_config.LinkColumn("open")},
                        )

            # --- Sub-tab 3: by-company breakdown ----------------------------
            with triage_tabs[2]:
                st.caption(
                    "Roles per company at each stage of the funnel. "
                    "'Scraped' is the raw count before triage; 'Passed' made "
                    "it to LLM scoring; 'Dropped' were filtered by rule_triage."
                )
                from collections import Counter as _Counter
                _passed_ct = _Counter(r.get("company", "?") for r in results)
                _dropped_ct = _Counter((d.get("company") or "?") for d in sc.get("triage_drops") or [])
                _all_companies = set(_passed_ct) | set(_dropped_ct)
                by_co = []
                for co in sorted(_all_companies):
                    p = _passed_ct.get(co, 0)
                    d = _dropped_ct.get(co, 0)
                    tot = p + d
                    by_co.append({
                        "company": co,
                        "scraped": tot,
                        "passed": p,
                        "dropped": d,
                        "pass_rate": f"{(100*p/tot):.0f}%" if tot else "—",
                    })
                by_co_df = pd.DataFrame(by_co).sort_values("scraped", ascending=False)
                st.dataframe(by_co_df, hide_index=True, width='stretch', height=500)

    # ================== TAB: Promote ==================
    with tabs[5]:
        st.subheader("Stage 4 — Promote to tracker")
        st.caption("Push scored candidates into `job_tracker_data.json`. Dry-run first; commit when ready.")

        scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                              key=lambda p: p.stat().st_mtime, reverse=True)
        if not scored_files:
            st.warning("No scored scan available.")
        else:
            which = st.selectbox("Scored file to promote", [p.name for p in scored_files],
                                 key="promote_file")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                min_s = st.slider("Min fit score", 1, 10, 7, key="promote_min")
            with c2:
                inc_watch = st.checkbox("Include verdict=watch", key="promote_watch")
            with c3:
                expire = st.checkbox("Expire stale tracker URLs", key="promote_expire")
            with c4:
                auto_tailor = st.checkbox("🎯 Auto-tailor Tier-1 docs",
                                           key="promote_autotailor",
                                           help="After commit, generate resume+cover "
                                                "letter drafts for every new Tier-1 "
                                                "role (requires API key; "
                                                "~$0.10-0.30 per Tier-1 role)")

            preview_col, commit_col = st.columns(2)
            with preview_col:
                if st.button("👀 Preview (dry-run)", width='stretch', key="prom_preview"):
                    cmd4 = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                            "--scan", which, "--min-score", str(min_s)]
                    if inc_watch:
                        cmd4.append("--include-watch")
                    if expire:
                        cmd4.append("--expire-stale")
                    res = subprocess.run(cmd4, capture_output=True, text=True, cwd=str(ROOT))
                    st.code(res.stdout + "\n" + (res.stderr or ""), language="text")
            with commit_col:
                _at_ok = (not auto_tailor) or api_key.is_key_valid()
                if not _at_ok:
                    st.caption("🔑 API key required when auto-tailor is on.")
                if st.button("🚀 Commit to tracker", type="primary", width='stretch',
                             key="prom_commit", disabled=not _at_ok):
                    cmd4 = [sys.executable, str(ROOT / "automation" / "auto_promote.py"),
                            "--scan", which, "--min-score", str(min_s), "--commit"]
                    if inc_watch:
                        cmd4.append("--include-watch")
                    if expire:
                        cmd4.append("--expire-stale")
                    if auto_tailor:
                        cmd4.append("--auto-tailor")
                    res = subprocess.run(cmd4, capture_output=True, text=True, cwd=str(ROOT))
                    st.code(res.stdout + "\n" + (res.stderr or ""), language="text")
                    st.cache_data.clear()
                    msg = "Tracker updated. Check 📋 Jobs Kanban."
                    if auto_tailor:
                        msg += " Tailor drafts will land in automation/outputs/ over the next ~2 min."
                    st.success(msg)

    # ================== TAB: History ==================
    with tabs[6]:
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
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch',
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
            st.dataframe(pd.DataFrame(rrows), hide_index=True, width='stretch',
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

    # Derive gta_area for every row — prefer explicit location, fall back to
    # URL slug inference (for pre-location-field tracker entries).
    def _area_for_row(row) -> str:
        loc = row.get("location") if isinstance(row, dict) else getattr(row, "location", None)
        url = row.get("url") if isinstance(row, dict) else getattr(row, "url", None)
        if loc:
            a = gta_area_for(loc)
            if a != "—":
                return a
        if url:
            # Extract city slug from /job/<city>/... (Phenom etc.) or location token in URL
            m = re.search(r"/job/([a-z\-]+)/", str(url).lower())
            if m:
                a = gta_area_for(m.group(1).replace("-", " "))
                if a != "—":
                    return a
            # Any GTA city token in the URL at large
            for label, toks in _GTA_AREAS:
                for t in toks:
                    if t.replace(" ", "-") in str(url).lower() or t in str(url).lower():
                        return label
        return "—"

    if not jobs_df.empty:
        jobs_df = jobs_df.assign(gta_area=jobs_df.apply(_area_for_row, axis=1))

    # Filters
    f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 2])
    sectors = sorted(jobs_df["sector"].dropna().unique()) if "sector" in jobs_df.columns else []
    statuses = sorted(jobs_df["status"].dropna().unique()) if "status" in jobs_df.columns else []
    fits = sorted(jobs_df["fit_score"].dropna().unique()) if "fit_score" in jobs_df.columns else []
    areas = sorted(jobs_df["gta_area"].dropna().unique()) if "gta_area" in jobs_df.columns else []
    with f1:
        sel_sector = st.multiselect("Sector", sectors, default=[])
    with f2:
        sel_status = st.multiselect("Status", statuses, default=[])
    with f3:
        sel_fit = st.multiselect("Fit", fits, default=[])
    with f4:
        sel_tier = st.multiselect("Tier", sorted(jobs_df["tier"].dropna().unique()) if "tier" in jobs_df.columns else [])
    with f5:
        sel_area = st.multiselect("GTA area", areas, default=[])
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
    if sel_area:
        view = view[view["gta_area"].isin(sel_area)]
    if q:
        qlo = q.lower()
        view = view[view["company"].str.lower().str.contains(qlo, na=False) |
                    view["title"].str.lower().str.contains(qlo, na=False)]

    st.caption(f"Showing {len(view)} of {len(jobs_df)} roles")

    # Enrich view with a "draft" indicator based on whether a tailor output
    # exists for this role. jd_tailor.py writes:
    #   {safe_company}_{safe_role}_{YYYYMMDD}.md        (final, real run)
    #   {safe_company}_{safe_role}_{YYYYMMDD}_prompt.md (dry-run preview)
    # where safe_company/safe_role use re.sub(r"[^a-zA-Z0-9]+", "_", ...).
    # Job_id is NOT in the filename — the previous implementation globbed on
    # a job_id substring, which almost always returned [] (false NEGATIVE).
    # Fix: reproduce jd_tailor's safe-name transform from the tracker's
    # company + title and match exact-prefix, preferring final over dry-run.
    def _tailor_safe(s: str, cap: int | None = None) -> str:
        out = re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_")
        return out[:cap] if cap else out

    def _has_draft_for(company: str, title: str) -> str:
        sc = _tailor_safe(company, None)
        sr = _tailor_safe(title, 60)
        if not sc or not sr:
            return ""
        # Final runs write <sc>_<sr>_YYYYMMDD.md (no _prompt suffix)
        final = list(OUT_DIR.glob(f"{sc}_{sr}_*.md"))
        final = [p for p in final if not p.name.endswith("_prompt.md")]
        if final:
            return "📄 ready"
        # Dry-run only — preview exists but no real tailor output
        if list(OUT_DIR.glob(f"{sc}_{sr}_*_prompt.md")):
            return "📝 preview"
        return ""

    # Load url_history once and enrich rows with posted/found
    _url_hist_path = OUT_DIR / "url_history.json"
    try:
        _url_hist = json.loads(_url_hist_path.read_text(encoding="utf-8")) if _url_hist_path.exists() else {}
    except Exception:
        _url_hist = {}

    def _freshness(url: str) -> str:
        entry = _url_hist.get(url or "") or {}
        return freshness_badge(None, entry.get("found_at"))

    if "company" in view.columns and "title" in view.columns:
        view = view.assign(
            draft=view.apply(
                lambda row: _has_draft_for(row.get("company", ""), row.get("title", "")),
                axis=1,
            )
        )
    if "url" in view.columns:
        view = view.assign(freshness=view["url"].apply(_freshness))

    cols = [c for c in ["id", "draft", "freshness", "company", "title", "gta_area",
                        "sector", "tier", "status", "fit_score", "fit_score_numeric",
                        "primary_variant", "urgency",
                        "date_found", "date_applied", "url"]
            if c in view.columns]
    st.dataframe(
        view[cols].sort_values(["tier", "fit_score_numeric"], ascending=[True, False])
        if "fit_score_numeric" in cols else view[cols],
        hide_index=True, width='stretch', height=500,
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
                variants = job.get("resume_variants") or ([job["primary_variant"]]
                    if job.get("primary_variant") else [])
                variant_str = " · ".join(variants) if variants else "—"
                st.caption(
                    f"{job.get('sector')} · Tier {job.get('tier')} · "
                    f"fit {job.get('fit_score')} ({job.get('fit_score_numeric', '?')}/10) · "
                    f"📄 {variant_str}"
                )
                st.markdown(f"[Open posting]({job.get('url')})")
                st.write(job.get("fit_notes", ""))
                st.write("**Next action:** " + (job.get("next_action") or ""))

                # CRM cross-reference — "you have N contacts at this company"
                _crm_hits = crm_contacts_at_company(crm, job.get("company", ""))
                if _crm_hits:
                    with st.container(border=True):
                        st.markdown(
                            f"⚡ **{len(_crm_hits)} CRM contact(s) at {job['company']}** "
                            "— warm-intro pathway before cold apply:"
                        )
                        for c in _crm_hits[:5]:
                            if c["_kind"] == "recruiter":
                                st.markdown(
                                    f"- 🎯 **{c.get('firm', '?')}** "
                                    f"({c.get('firm_type', '')}) · "
                                    f"priority={c.get('priority', '?')} · "
                                    f"last-touch {c.get('last_touchpoint', 'never')}"
                                )
                            else:
                                st.markdown(
                                    f"- 🎓 **{c.get('name', '?')}** at "
                                    f"{c.get('current_firm', '?')} · "
                                    f"{c.get('relationship', '')}"
                                )
                        if len(_crm_hits) > 5:
                            st.caption(f"…and {len(_crm_hits) - 5} more — see CRM page.")
                        st.caption("Jump to 🤝 Recruiter CRM to draft an outreach message.")

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
                                # Seed follow-up schedule on first Applied date
                                if new_date_applied and not parse_date(j.get("date_applied")):
                                    seed_followup(j, new_date_applied)
                                elif new_date_applied:
                                    j["date_applied"] = new_date_applied.isoformat()
                                j["notes"] = new_notes
                                break
                        save_tracker(tr)
                        st.success("Saved.")
                        st.rerun()

                if st.button(f"✅ Mark Applied today (id={sel_id})"):
                    for j in tr["jobs"]:
                        if j["id"] == sel_id:
                            j["status"] = "Applied"
                            seed_followup(j, date.today())
                            break
                    save_tracker(tr)
                    st.success("Marked Applied; first follow-up in 3 days.")
                    st.rerun()


# ============================================================================
# 🤝 RECRUITER CRM
# ============================================================================
elif page == "🤝 Recruiter CRM":
    st.title("🤝 Recruiter + Warm-intro CRM")
    if not crm:
        st.warning("No recruiter_crm.json found.")
        st.stop()

    # ---------- Weekly outreach digest ----------
    digest = outreach_digest(crm)
    weekly_target = (crm.get("meta", {}).get("weekly_target", {}).get("new_outreach")) or 10
    weekly_sent = digest["weekly_sent"]
    pct = int(min(100, weekly_sent / weekly_target * 100)) if weekly_target else 0

    dc1, dc2, dc3, dc4, dc5 = st.columns(5)
    dc1.metric("This week sent", f"{weekly_sent} / {weekly_target}",
               delta=weekly_sent - weekly_target)
    dc2.metric("Never contacted", len(digest["never_contacted"]))
    dc3.metric("Active (≤14d)", len(digest["active"]))
    dc4.metric("Stale (15–35d)", len(digest["stale"]), delta_color="inverse")
    dc5.metric("Cold (>35d)", len(digest["cold"]), delta_color="inverse")
    st.progress(pct / 100.0, text=f"Weekly outreach progress: {weekly_sent}/{weekly_target} "
                                  f"({pct}%)")

    with st.expander(f"📬 Outreach digest — prioritized nudges "
                     f"({len(digest['never_contacted']) + len(digest['stale']) + len(digest['cold'])} pending)"):
        st.caption(
            "Priority order: 🆕 never-contacted (High priority first) → "
            "⏰ stale (15–35d, reply-chase) → 🧊 cold (>35d, reactivate or retire). "
            "Use templates below to draft in-voice nudges."
        )
        tn, ts, tc = st.tabs([
            f"🆕 Never ({len(digest['never_contacted'])})",
            f"⏰ Stale ({len(digest['stale'])})",
            f"🧊 Cold ({len(digest['cold'])})",
        ])

        def _render_digest_rows(items, tab, mode):
            if not items:
                tab.caption("Nothing here. 🎉")
                return
            rows = []
            for item in items:
                if isinstance(item, tuple):
                    days, c = item
                else:
                    days, c = None, item
                rows.append({
                    "id": c.get("id"),
                    "kind": c.get("_kind", "?"),
                    "firm_or_name": c.get("firm") or c.get("name", ""),
                    "priority": c.get("priority", ""),
                    "status": c.get("status", ""),
                    "last_touch": c.get("last_touchpoint") or "(never)",
                    "days_since": days if days is not None else "—",
                    "next_action": (c.get("next_action") or "")[:80],
                })
            tab.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
            # Draft a message
            pick = tab.selectbox("Contact to draft for", [r["id"] for r in rows],
                                  key=f"dig_pick_{mode}")
            contact = next(({**c, "_kind": c.get("_kind", "?")} for item in items
                           for c in ([item[1]] if isinstance(item, tuple) else [item])
                           if c.get("id") == pick), None)
            if contact:
                templates = crm.get("outreach_message_templates", {})
                tpl_key = tab.selectbox(
                    "Template",
                    list(templates.keys()) if templates else ["(none)"],
                    key=f"dig_tpl_{mode}",
                )
                body = templates.get(tpl_key, "")
                rendered = render_template(body, contact)
                tab.text_area("Drafted message (edit before sending)", rendered,
                              height=200, key=f"dig_msg_{mode}")
                if tab.button(f"📝 Log as sent today",
                              key=f"dig_log_{mode}", width='stretch'):
                    # Update the contact's last_touchpoint + append to structured log
                    for r in crm.get("recruiters", []):
                        if r["id"] == pick:
                            r["last_touchpoint"] = date.today().isoformat()
                            if r.get("status") == "Not_Contacted":
                                r["status"] = "Outreach_Sent"
                    for a in crm.get("alumni_warm_intros", []):
                        if a["id"] == pick:
                            a["last_touchpoint"] = date.today().isoformat()
                            if a.get("status") == "Not_Contacted":
                                a["status"] = "Outreach_Sent"
                    crm.setdefault("outreach_log", []).append({
                        "date": date.today().isoformat(),
                        "contact_id": pick,
                        "template": tpl_key,
                        "channel": "linkedin",
                    })
                    save_crm(crm)
                    st.success(f"Logged outreach to {pick}.")
                    st.rerun()

        _render_digest_rows(digest["never_contacted"], tn, "never")
        _render_digest_rows(digest["stale"], ts, "stale")
        _render_digest_rows(digest["cold"], tc, "cold")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["Recruiters", "Alumni warm-intros", "Templates"])
    with tab1:
        recs = crm.get("recruiters", [])
        rdf = pd.DataFrame(recs)
        if not rdf.empty:
            cols = [c for c in ["id", "firm", "firm_type", "location", "priority",
                                "status", "last_touchpoint", "next_action"] if c in rdf.columns]
            st.dataframe(rdf[cols], hide_index=True, width='stretch')
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
        st.dataframe(pd.DataFrame(alumni), hide_index=True, width='stretch')

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
    wp = ROOT / "docs" / "this_week.md"
    cp = ROOT / "docs" / "operating_cadence.md"
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
        p = ROOT / "docs" / "linkedin_content_engine.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no file)_")
    with t2:
        p = ROOT / "docs" / "linkedin_engagement_log.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no file)_")
    with t3:
        p = ROOT / "docs" / "Saber_Ayatollahi_Master_Repository.md"
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
# 📜 SCAN HISTORY — cumulative record of every scan + pipeline run
# ============================================================================
elif page == "📜 Scan History":
    st.title("📜 Scan History")
    st.caption(
        "Cumulative record of every scan the pipeline has produced. Scrape "
        "outputs (`scan_*.json`), scored outputs (`scan_*_scored.json`), and "
        "pipeline runs (`pipeline_*.json`) are all logged here forever."
    )

    # -------- Pipeline runs (from PIPELINE_DIR/*.json) --------
    st.markdown("### Pipeline runs")
    pipelines = list_pipelines(limit=200)
    if not pipelines:
        st.info("No pipeline runs yet. Launch one from the 🎯 Pipeline page.")
    else:
        pipe_rows = []
        for p in pipelines:
            stages = p.get("stages") or {}
            scrape_s = stages.get("scrape") or {}
            score_s = stages.get("score") or {}
            verdicts = (score_s.get("verdicts") or {})
            pipe_rows.append({
                "pipeline_id": p.get("pipeline_id", "?"),
                "started": p.get("started_at", ""),
                "finished": p.get("finished_at", ""),
                "state": p.get("state", "?"),
                "mode": (p.get("args") or {}).get("scrape_mode", "?"),
                "candidates": scrape_s.get("candidate_count", "—"),
                "scored": score_s.get("scored_count", "—"),
                "apply_now": verdicts.get("apply_now", 0),
                "tailor": verdicts.get("tailor_and_apply", 0),
                "watch": verdicts.get("watch", 0),
                "skip": verdicts.get("skip", 0),
                "scan_file": scrape_s.get("scan_file", ""),
            })
        st.dataframe(pd.DataFrame(pipe_rows), hide_index=True, width='stretch',
                     height=min(40 + 36 * len(pipe_rows), 400))

    st.markdown("---")

    # -------- Scan files (raw scraper outputs) --------
    st.markdown("### Raw scan files")
    scan_files = sorted(
        [f for f in OUT_DIR.glob("scan_*.json") if "_scored" not in f.name],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not scan_files:
        st.info("No scan files. Run the scraper.")
    else:
        scan_rows = []
        for f in scan_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                count = len(data.get("results", []))
                scan_date = data.get("scan_date", "")
                sectors = data.get("sector_counts") or {}
            except Exception:
                count = "?"
                scan_date = ""
                sectors = {}
            scan_rows.append({
                "file": f.name,
                "scan_date": scan_date,
                "candidates": count,
                "sectors": len(sectors),
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        st.dataframe(pd.DataFrame(scan_rows), hide_index=True, width='stretch',
                     height=min(40 + 36 * len(scan_rows), 300))

        # Inspector
        pick = st.selectbox("Inspect scan", [r["file"] for r in scan_rows],
                            key="scan_hist_pick")
        if pick:
            try:
                d = json.loads((OUT_DIR / pick).read_text(encoding="utf-8"))
                cols = st.columns(4)
                cols[0].metric("Candidates", len(d.get("results", [])))
                cols[1].metric("Scan date", d.get("scan_date", "—"))
                diag = d.get("diagnostics") or {}
                cols[2].metric("Zero-result cos", len(diag.get("zero_result_companies", [])))
                cols[3].metric("LI throttled", "yes" if diag.get("linkedin_throttled") else "no")
                # Sector distribution
                sc = d.get("sector_counts") or {}
                if sc:
                    st.markdown("**By sector**")
                    st.dataframe(
                        pd.DataFrame(
                            [{"sector": k, "count": v} for k, v in sorted(sc.items(), key=lambda kv: -kv[1])]
                        ),
                        hide_index=True, width='stretch',
                    )
                # Paired scored file if it exists
                scored = OUT_DIR / (Path(pick).stem + "_scored.json")
                if scored.exists():
                    st.success(f"📊 Scored counterpart: `{scored.name}` "
                               f"({round(scored.stat().st_size / 1024, 1)} KB)")
            except Exception as e:
                st.error(f"Could not read {pick}: {e}")

    st.markdown("---")

    # -------- Scored files --------
    st.markdown("### Scored scans")
    scored_files = sorted(OUT_DIR.glob("*_scored.json"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
    if not scored_files:
        st.info("No scored files yet.")
    else:
        scored_rows = []
        for f in scored_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results = data.get("results") or []
                verdicts: dict = {}
                for r in results:
                    v = (r.get("fit") or {}).get("fit_verdict", "?")
                    verdicts[v] = verdicts.get(v, 0) + 1
            except Exception:
                results = []
                verdicts = {}
            scored_rows.append({
                "file": f.name,
                "scored": len(results),
                "apply_now": verdicts.get("apply_now", 0),
                "tailor": verdicts.get("tailor_and_apply", 0),
                "watch": verdicts.get("watch", 0),
                "skip": verdicts.get("skip", 0),
                "error": verdicts.get("error", 0),
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            })
        st.dataframe(pd.DataFrame(scored_rows), hide_index=True, width='stretch',
                     height=min(40 + 36 * len(scored_rows), 300))


# ============================================================================
# ⚙️ ADMIN  — direct access to individual agents and outputs
# ============================================================================
elif page == "⚙️ Admin":
    st.title("⚙️ Admin")
    st.caption("The 🎯 Pipeline page is the main entry point. This page is for running individual "
               "agents directly, or browsing raw outputs.")

    # ---------- Cost ledger ----------
    st.subheader("💰 Cost ledger (lifetime)")
    st.caption(
        "Every LLM call from fit_scorer (and any future scorer/tailor that "
        "imports `cost_ledger`) is recorded here. Cumulative, never resets "
        "across sessions or machines (per this machine's `data/` folder)."
    )
    try:
        _ledger = cost_ledger.load()
        _tot = _ledger.get("totals", {}) or {}
        _pm = _ledger.get("per_model", {}) or {}
        _daily = _ledger.get("daily", {}) or {}

        cL1, cL2, cL3, cL4 = st.columns(4)
        cL1.metric("Total spend", f"${_tot.get('estimated_cost_usd', 0):.4f}")
        cL2.metric("LLM calls", f"{_tot.get('llm_calls', 0):,}")
        cL3.metric("Cache hits", f"{_tot.get('cache_hits', 0):,}")
        _in = _tot.get("input_tokens", 0) or 0
        _out = _tot.get("output_tokens", 0) or 0
        cL4.metric("Tokens", f"{(_in + _out):,}",
                   f"in {_in:,} · out {_out:,}")

        if _pm:
            st.markdown("**Per-model breakdown**")
            rows = []
            for model, m in sorted(_pm.items(), key=lambda kv: -kv[1].get("cost_usd", 0)):
                rows.append({
                    "model": model,
                    "calls": m.get("calls", 0),
                    "in_tokens": m.get("in_tokens", 0),
                    "out_tokens": m.get("out_tokens", 0),
                    "cost_usd": round(m.get("cost_usd", 0), 4),
                    "first_used": m.get("first_used", ""),
                    "last_used": m.get("last_used", ""),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

        if _daily:
            st.markdown("**Last 30 days**")
            # Sort by date desc, show top 30
            recent = sorted(_daily.items(), key=lambda kv: kv[0], reverse=True)[:30]
            drows = []
            for d, v in recent:
                drows.append({
                    "date": d,
                    "calls": v.get("calls", 0),
                    "in_tokens": v.get("in_tokens", 0),
                    "out_tokens": v.get("out_tokens", 0),
                    "cost_usd": round(v.get("cost_usd", 0), 4),
                })
            st.dataframe(pd.DataFrame(drows), hide_index=True, width='stretch',
                         height=min(40 + 36 * len(drows), 300))

        st.caption(f"Ledger file: `{cost_ledger.LEDGER_PATH}` · "
                   f"created {_ledger.get('created_at', '—')} · "
                   f"updated {_ledger.get('updated_at', '—')}")
    except Exception as _le:
        st.error(f"Ledger read failed: {_le}")
    st.markdown("---")

    # ---------- Error log ----------
    st.subheader("🪵 Error log")
    st.caption(
        "Silent failures (progress-file writes, fit-cache corruption, "
        "HTTP retries exhausted, ledger writes) land in "
        "`logs/errors.jsonl`. One JSONL record per error — module, "
        "context, error_type, message, and traceback."
    )
    if error_log is None:
        st.info("`automation/error_log.py` isn't importable — skipping.")
    else:
        try:
            recent = error_log.recent_errors(limit=200)
        except Exception as _ree:
            st.error(f"Error log read failed: {_ree}")
            recent = []

        # Top metric row
        _last_hour = error_log.count_recent(since_minutes=60) if error_log else 0
        _last_day = error_log.count_recent(since_minutes=60 * 24) if error_log else 0
        em1, em2, em3, em4 = st.columns(4)
        em1.metric("Total recent", f"{len(recent):,}")
        em2.metric("Last hour", f"{_last_hour:,}")
        em3.metric("Last 24h", f"{_last_day:,}")
        em4.metric("Log file",
                   f"{(error_log.LOG_PATH.stat().st_size // 1024):,} KB"
                   if error_log.LOG_PATH.exists() else "—")

        if not recent:
            st.success("✅ No errors in the log.")
        else:
            # Filter row
            mods = sorted({r.get("module", "?") for r in recent})
            ctxs = sorted({r.get("context", "?") for r in recent})
            fe1, fe2, fe3 = st.columns([2, 2, 2])
            with fe1:
                pick_mod = st.multiselect("Module", mods, default=mods,
                                            key="err_mod")
            with fe2:
                pick_ctx = st.multiselect("Context", ctxs, default=[],
                                            key="err_ctx",
                                            help="Leave empty to show all")
            with fe3:
                err_q = st.text_input("Search message/traceback",
                                        key="err_q")

            def _match(rec):
                if rec.get("module") not in pick_mod:
                    return False
                if pick_ctx and rec.get("context") not in pick_ctx:
                    return False
                if err_q:
                    q = err_q.lower()
                    hay = (rec.get("message", "") + " "
                           + rec.get("traceback", "")).lower()
                    if q not in hay:
                        return False
                return True

            filtered = [r for r in recent if _match(r)]
            st.caption(f"Showing {len(filtered):,} of {len(recent):,} records")

            # Table view
            rows = [{
                "when": r.get("timestamp", ""),
                "module": r.get("module", "?"),
                "context": r.get("context", "?"),
                "error_type": r.get("error_type", "?"),
                "message": r.get("message", "")[:120],
            } for r in filtered]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                             width='stretch', height=300)

            # Drill-down on one record
            if filtered:
                labels = [
                    f"{r.get('timestamp','?')} · {r.get('module','?')} · "
                    f"{r.get('context','?')} · {r.get('error_type','?')}"
                    for r in filtered
                ]
                idx = st.selectbox("Inspect record", range(len(filtered)),
                                    format_func=lambda i: labels[i],
                                    key="err_pick")
                rec = filtered[idx]
                with st.container(border=True):
                    st.markdown(f"**{rec.get('error_type','?')}** "
                                f"in `{rec.get('module','?')}` / "
                                f"`{rec.get('context','?')}`")
                    st.caption(rec.get("timestamp", ""))
                    st.markdown(f"**Message:** {rec.get('message','')}")
                    if rec.get("traceback"):
                        st.code(rec["traceback"], language="text")
                    # Extra fields beyond the core schema
                    extra_keys = [k for k in rec
                                   if k not in {"timestamp", "module", "context",
                                                 "error_type", "message",
                                                 "traceback"}]
                    if extra_keys:
                        st.markdown("**Extra fields**")
                        st.json({k: rec[k] for k in extra_keys})

        # Archive-current-log button. Never deletes; renames the current
        # errors.jsonl to errors.archived_<stamp>.jsonl so the badge goes
        # back to green but the forensic record is preserved.
        st.markdown("---")
        ac1, ac2 = st.columns([1, 3])
        with ac1:
            if st.button("🗄 Archive current log", key="err_archive",
                          disabled=(error_log is None
                                    or not error_log.LOG_PATH.exists())):
                try:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest = error_log.LOG_PATH.with_name(
                        f"errors.archived_{stamp}.jsonl")
                    error_log.LOG_PATH.rename(dest)
                    st.success(f"Archived to {dest.name}")
                    st.rerun()
                except Exception as _ae:
                    st.error(f"Archive failed: {_ae}")
        with ac2:
            st.caption(
                "Archiving renames `errors.jsonl` to "
                "`errors.archived_<stamp>.jsonl`. The current log goes back "
                "to empty; the archive file stays in `logs/` for forensics."
            )
    st.markdown("---")

    # ---------- Nightly schedule ----------
    st.subheader("🌙 Nightly schedule")
    st.caption(
        "Install a Windows scheduled task that runs scrape + delta + brief at 6:30 AM "
        "daily. You wake up to fresh matches on the Dashboard."
    )
    sch_col1, sch_col2 = st.columns(2)
    with sch_col1:
        st.code(
            "# One-time install (from PowerShell, not as admin):\n"
            f"cd {ROOT}\n"
            "powershell -ExecutionPolicy Bypass -File automation\\install_schedule.ps1",
            language="powershell",
        )
    with sch_col2:
        st.code(
            "# Check status / run now / uninstall:\n"
            "schtasks /query /tn ApplyAgent_NightlyRefresh /v /fo LIST\n"
            "schtasks /run   /tn ApplyAgent_NightlyRefresh\n"
            "schtasks /delete /tn ApplyAgent_NightlyRefresh /f",
            language="powershell",
        )
    if st.button("🌅 Run nightly refresh now (background)", width='content'):
        ps = ROOT / "automation" / "nightly_refresh.ps1"
        rec = scan_runner.start_run(
            "nightly_refresh",
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps)],
        )
        st.success(f"Nightly refresh launched (`{rec.run_id}`). Dashboard will show "
                   f"fresh matches when it finishes (~25 min).")

    st.markdown("---")

    st.subheader("📁 Outputs directory")
    out_files = sorted(OUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    out_files = [p for p in out_files if p.is_file()][:40]
    if out_files:
        rows = [{
            "file": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        } for p in out_files]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=320)

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
