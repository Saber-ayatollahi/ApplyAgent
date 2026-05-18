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
from datetime import date, datetime, timedelta, timezone
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
    # Atomic write under portalocker lock — protects against concurrent
    # writers (auto_promote CLI, score_url CLI) and against truncation if
    # the process dies mid-write.
    try:
        from safe_json import write_json as _sj_write
        _sj_write(TRACKER, d)
    except ImportError:
        TRACKER.write_text(json.dumps(d, indent=2), encoding="utf-8")
    st.cache_data.clear()


def save_crm(d: dict):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = CRM.with_suffix(f".bak.{stamp}.json")
    if CRM.exists():
        bak.write_text(CRM.read_text(encoding="utf-8"), encoding="utf-8")
    # Atomic write under portalocker lock — protects against concurrent
    # writers and against truncation if the process dies mid-write.
    try:
        from safe_json import write_json as _sj_write
        _sj_write(CRM, d)
    except ImportError:
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

# ---------------------------------------------------------------------------
# AI inline helpers — lightweight Claude Haiku calls for drafts & prep notes
# Cached by a caller-supplied cache_key so reruns don't re-call the API.
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def _ai_draft(cache_key: str, prompt: str) -> str:
    """Call Claude Haiku and return text. Returns error string if key missing."""
    try:
        import anthropic as _ant
        _k = api_key.load_key()
        if not _k:
            return "⚠️ API key not configured — add it in the sidebar."
        _client = _ant.Anthropic(api_key=_k)
        _msg = _client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        return _msg.content[0].text.strip()
    except Exception as _e:
        return f"⚠️ Draft failed: {_e}"


def _email_draft_prompt(job: dict, touch_num: int = 1) -> str:
    """Build an email-draft prompt from a tracker job dict."""
    co       = job.get("company", "the company")
    title    = job.get("title", "the role")
    applied  = job.get("date_applied", "recently")
    osfi     = job.get("osfi_hook", "")
    fit      = (job.get("fit_notes") or "")[:300]
    kw       = ", ".join((job.get("keywords") or [])[:6])
    rec_name = (job.get("contact") or {}).get("recruiter_name") or ""
    greeting = f"Hi {rec_name}," if rec_name else "Hi,"

    ordinal = {1: "first", 2: "second", 3: "third"}.get(touch_num, f"{touch_num}th")
    return f"""You are writing a {ordinal} follow-up email for Saber Ayatollahi (CFA, dual MSc, 7+ years ALM/IRRBB/Moody's Analytics).

Role: {title} at {co}
Applied: {applied}
Key skills: {kw}
OSFI regulatory angle: {osfi}
Fit summary: {fit}

Write a concise, confident follow-up email (120–160 words).
- Open with {greeting}
- Reference the specific role
- Lead with one concrete value-add (IRRBB, OSFI B-12, ALM modelling, or vendor-platform expertise)
- End with a clear, non-pushy CTA
- Tone: professional, direct, not sycophantic
- Output ONLY the email body — no subject line, no sign-off name"""


def _interview_prep_prompt(job: dict) -> str:
    """Build an interview prep prompt from a tracker job dict."""
    co    = job.get("company", "the company")
    title = job.get("title", "the role")
    sec   = job.get("sector", "financial services")
    osfi  = job.get("osfi_hook", "")
    fit   = (job.get("fit_notes") or "")[:400]
    kw    = ", ".join((job.get("keywords") or [])[:8])
    level = job.get("level", "Director")
    return f"""Generate interview prep notes for Saber Ayatollahi interviewing for:
Role: {level} — {title} at {co} ({sec})
Keywords: {kw}
OSFI/regulatory angle: {osfi}
Fit context: {fit}

Produce a structured prep brief in markdown with these exact sections:
## Technical Questions (5 likely questions with 1-line answer starters)
## Behavioural Questions (3 questions with STAR talking-point bullets)
## Key Selling Points (3 compelling angles specific to this role)
## Questions to Ask Them (2 smart questions that signal domain depth)

Be specific to the role — reference IRRBB/ALM/OSFI where relevant."""


def _find_tailor_docs(job: dict) -> list:
    """Return list of tailored doc Paths for this job (resume/CL markdown files)."""
    jid = job.get("id", "")
    co  = (job.get("company") or "").replace(" ", "_")
    ttl = (job.get("title") or "").replace(" ", "_").replace("/", "_")
    # Pattern 1: *_{job_id_underscored}*.md  (jd_tailor standard output)
    pat1 = f"*_{jid.replace('-', '_')}*.md"
    # Pattern 2: {Company}_{Title}*.md  (prompt files also useful as context)
    pat2 = f"{co}_{ttl[:30]}*.md"
    found = list(OUT_DIR.glob(pat1)) + list(OUT_DIR.glob(pat2))
    # Exclude raw scan/delta/brief/report files
    skip = {"scan_", "delta_", "brief_", "promote_", "SCAN_", "scorer_", "weekly_"}
    return sorted(
        {p for p in found if not any(p.name.startswith(s) for s in skip)
         and "_prompt." not in p.name},
        key=lambda p: p.stat().st_mtime, reverse=True,
    )


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
    Accepts 'YYYY-MM-DD' (treated as UTC midnight) or any ISO8601 string.

    Both sides of the subtraction are kept tz-aware. Earlier this naively
    stripped tz and compared to local-naive datetime.now() — on a Toronto
    laptop that shifted every elapsed-hours value by 4-5 hours, breaking
    the 48-hour urgent-role threshold."""
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
    # Date-only or naive ISO — treat as UTC. Don't silently coerce to local;
    # job-board timestamps are almost always UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
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
                # updated_at is UTC; compare in UTC.
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                if (now_utc - dt).total_seconds() > 300:
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
                data["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def render_gmail_trash_panel(container=None) -> bool:
    """If the most recent scan_gmail_*.json has alert UIDs that haven't been
    moved to Trash yet, render a confirm/delete panel. Returns True if it
    rendered (UI shifted), False otherwise so the caller can collapse layout.

    The panel only ever offers to delete alerts that produced rows. If a
    parse returned 0 rows from a digest, the UID is not in
    `gmail_alerts.contributing_uids` and survives — that protects unparsed
    leads from being lost when we extend the parser later.
    """
    target = container or st
    files = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return False
    latest = files[0]
    try:
        env = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return False
    alerts = env.get("gmail_alerts") or {}
    uids = alerts.get("contributing_uids") or []
    if not uids:
        return False
    if alerts.get("deleted"):
        # One-time success caption so the user knows the previous click
        # actually moved messages — but no big banner.
        dr = alerts.get("delete_result") or {}
        moved = dr.get("moved", 0)
        when = alerts.get("deleted_at") or ""
        target.caption(
            f"🗑 {moved} Gmail alert(s) moved to Trash at {when} "
            f"(from `{latest.name}`)."
        )
        return True

    n_rows = len(env.get("results") or [])
    with target.container(border=True):
        st.markdown(
            f"#### 🗑 Clean up Gmail · {len(uids)} alert email"
            f"{'s' if len(uids) != 1 else ''} ready to delete"
        )
        st.caption(
            f"`{latest.name}` extracted **{n_rows} job row"
            f"{'s' if n_rows != 1 else ''}** from these alerts. "
            "Moving them to Gmail Trash declutters your inbox; Gmail "
            "auto-purges Trash after 30 days, and you can restore them "
            "manually from there if needed. Read-only stays the default — "
            "this is the only operation that mutates mail."
        )
        col1, col2 = st.columns([1, 3])
        with col1:
            do_delete = st.button(
                f"🗑 Move {len(uids)} to Trash",
                width='stretch',
                type="primary",
                key=f"gmail_trash_{latest.stem}",
                help="Opens a read-write IMAP session and moves the listed "
                     "UIDs to [Gmail]/Trash. Reversible from Gmail UI.",
            )
        with col2:
            if st.button(
                "🙈 Hide for this scan",
                width='stretch',
                key=f"gmail_trash_hide_{latest.stem}",
                help="Mark this scan as 'don't ask again' without deleting "
                     "any mail. The next scan_gmail_ run will offer again.",
            ):
                env.setdefault("gmail_alerts", {})
                env["gmail_alerts"]["deleted"] = True
                env["gmail_alerts"]["delete_result"] = {
                    "moved": 0, "failed": 0,
                    "errors": ["User dismissed without deleting."],
                }
                env["gmail_alerts"]["deleted_at"] = datetime.now().isoformat(timespec="seconds")
                latest.write_text(
                    json.dumps(env, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                st.rerun()

        if do_delete:
            try:
                # Lazy import — gmail_reader pulls in imaplib + bs4. Keep it
                # off the page-load critical path.
                sys.path.insert(0, str(ROOT / "automation"))
                import gmail_reader as _gr  # type: ignore
                with st.spinner(f"Moving {len(uids)} alert(s) to Trash…"):
                    res = _gr.delete_messages(uids)
            except Exception as e:
                st.error(f"Delete failed before IMAP call: {e}")
                return True
            env.setdefault("gmail_alerts", {})
            env["gmail_alerts"]["deleted"] = True
            env["gmail_alerts"]["deleted_at"] = datetime.now().isoformat(timespec="seconds")
            env["gmail_alerts"]["delete_result"] = {
                "moved": res.moved,
                "failed": res.failed,
                "errors": list(res.errors or [])[:10],
            }
            try:
                latest.write_text(
                    json.dumps(env, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                st.warning(f"Trash succeeded but persisting result failed: {e}")
            if res.failed == 0:
                st.success(
                    f"✅ Moved {res.moved} alert(s) to Gmail Trash. "
                    "They'll auto-purge after 30 days."
                )
            else:
                st.warning(
                    f"Moved {res.moved}, failed {res.failed}. "
                    f"Errors: {res.errors[:3]}"
                )
            st.rerun()
    return True


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
    "📥 Outcome Inbox",
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

# -------- Grouped sidebar nav --------
# Sidebar radio with visual section dividers. Streamlit's radio doesn't
# support true section headers natively, so we use non-selectable separator
# strings inserted between groups. If the user somehow lands on one,
# page-routing treats it as Dashboard so nothing breaks.
# Pre-load CRM before nav so we can show urgency badge in sidebar.
# load_crm() is @st.cache_data(ttl=15) so this call is cheap on reruns.
_crm_early = load_crm()
_crm_early_all = (_crm_early.get("recruiters") or []) + (_crm_early.get("alumni_warm_intros") or [])
# High-priority contacts not yet reached — this is the "call to action" count
_crm_badge_count = sum(
    1 for c in _crm_early_all
    if c.get("priority") == "High"
    and c.get("status") in ("Not_Contacted",)
    and not c.get("last_touchpoint")
)

_SEP_WORK    = "── Work ──"
_SEP_TRACKER = "── Tracker ──"
_SEP_ADMIN   = "── Admin ──"
_SEPARATORS = {_SEP_WORK, _SEP_TRACKER, _SEP_ADMIN}

_NAV_OPTIONS = [
    _SEP_WORK,
    "🏠 Dashboard",
    "🎯 Pipeline",
    "📥 Outcome Inbox",
    "📊 Analytics",
    _SEP_TRACKER,
    "🔔 Follow-ups",
    "📬 Review Queue",
    "📋 Jobs Kanban",
    "🤝 Recruiter CRM",
    _SEP_ADMIN,
    "📅 Weekly Plan",
    "📝 Content & Memory",
    "📜 Scan History",
    "⚙️ Admin",
]

# ── Campaign quick stats in sidebar ──────────────────────────────────────
try:
    _sb_meta = load_tracker().get("meta", {})
    _sb_camp_start = _sb_meta.get("campaign_start", "")
    _sb_camp_end   = _sb_meta.get("campaign_end", "")
    _sb_today = date.today()
    if _sb_camp_start and _sb_camp_end:
        _sb_cs = datetime.strptime(_sb_camp_start, "%Y-%m-%d").date()
        _sb_ce = datetime.strptime(_sb_camp_end,   "%Y-%m-%d").date()
        _sb_total = max((_sb_ce - _sb_cs).days, 1)
        _sb_done  = max(min((_sb_today - _sb_cs).days, _sb_total), 0)
        _sb_pct   = int(_sb_done / _sb_total * 100)
        _sb_left  = max((_sb_ce - _sb_today).days, 0)
        st.sidebar.markdown("---")
        st.sidebar.markdown(
            f"<div style='font-size:11px;opacity:0.7;margin-bottom:3px'>Campaign · {_sb_pct}% · {_sb_left}d left</div>",
            unsafe_allow_html=True,
        )
        st.sidebar.progress(_sb_pct / 100)
except Exception:
    pass

# ── Targeting lanes strip ─────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div style='font-size:11px;color:var(--text-color);opacity:0.75;margin-bottom:4px'>"
    "<strong>Active search lanes</strong></div>"
    "<div style='font-size:11px;padding:4px 8px;margin:2px 0;"
    "background:rgba(59,130,246,0.12);border-left:2px solid #3b82f6;border-radius:3px'>"
    "🔵 <strong>PRIMARY</strong> — ALM / IRRBB / Model Governance</div>"
    "<div style='font-size:11px;padding:4px 8px;margin:2px 0;"
    "background:rgba(245,158,11,0.12);border-left:2px solid #f59e0b;border-radius:3px'>"
    "🟡 SECONDARY — Vendor-Platform / Client Solutions</div>",
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")

_nav_pick = st.sidebar.radio(
    "Navigate",
    _NAV_OPTIONS,
    index=1,                                    # default: Dashboard
    label_visibility="collapsed",
    key="_applyagent_nav",
)
# If the user somehow picks a separator, fall back to Dashboard so the
# if/elif page-router below always matches something.
page = _nav_pick if _nav_pick not in _SEPARATORS else "🏠 Dashboard"

# ── Sidebar urgency strip ──────────────────────────────────────────────
# Surfaces the most time-sensitive action counts so they're visible from
# any page without navigating to CRM.
if _crm_badge_count > 0:
    st.sidebar.markdown(
        f"<div style='margin:4px 0 6px 0;padding:7px 10px;"
        f"background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);"
        f"border-radius:6px;font-size:12px;color:#f87171;line-height:1.4'>"
        f"🤝 <strong>{_crm_badge_count}</strong> high-priority recruiter"
        f"{'s' if _crm_badge_count != 1 else ''} awaiting outreach</div>",
        unsafe_allow_html=True,
    )

# Follow-up due badge (overdue + due today)
try:
    _fu_jobs_early = load_tracker().get("jobs", [])
    _fu_buckets_early = followup_buckets(_fu_jobs_early)
    _fu_badge_count = len(_fu_buckets_early["overdue"]) + len(_fu_buckets_early["due_today"])
    if _fu_badge_count > 0:
        st.sidebar.markdown(
            f"<div style='margin:4px 0 6px 0;padding:7px 10px;"
            f"background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);"
            f"border-radius:6px;font-size:12px;color:#fbbf24;line-height:1.4'>"
            f"🔔 <strong>{_fu_badge_count}</strong> follow-up"
            f"{'s' if _fu_badge_count != 1 else ''} due — check Follow-ups</div>",
            unsafe_allow_html=True,
        )
except Exception:
    _fu_badge_count = 0

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

# @st.fragment — available in Streamlit ≥1.33. When present, the live
# pipeline panel re-runs itself every 3s without flashing the entire page.
# When absent, we fall back to the existing st_autorefresh approach.
_HAS_FRAGMENT = hasattr(st, "fragment")

# Auto-refresh: poll every 5s ONLY when something is actively running. An
# idle dashboard stays idle (no rerun thrash, no battery drain). The user
# can also hit 🔄 Refresh manually — see sidebar below. `key` is distinct
# per page so Streamlit doesn't treat them as one counter.
# Only use the page-wide autorefresh when @st.fragment isn't available.
# With fragments, only the live-output widget rerenders every 3s — the
# rest of the page stays perfectly still while a job runs.
if any_work_active and _HAVE_AUTOREFRESH and not _HAS_FRAGMENT:
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
        _p = _pointer.read_text(encoding="utf-8-sig").strip()  # utf-8-sig strips BOM
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
            import re as _re
            _size = _session_log.stat().st_size
            _cap = 12_000  # keep the sidebar render fast
            with open(_session_log, "rb") as _lf:
                if _size > _cap:
                    _lf.seek(_size - _cap)
                    _raw = b"...[truncated]\n" + _lf.read()
                else:
                    _raw = _lf.read()
            _txt = _raw.decode("utf-8", errors="replace")
            # Strip ANSI escape codes (colors, cursor moves, etc.)
            _txt = _re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', _txt)
            # Strip carriage returns left by Windows line endings
            _txt = _txt.replace('\r', '')
            st.code(_txt or "(empty)", language="text", height=300)
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
# Live pipeline monitor — must be defined BEFORE the if/elif page chain so
# it can be optionally wrapped with @st.fragment (Streamlit ≥1.33), which
# makes only this widget rerender every 3s instead of the entire page.
# Falls back gracefully to a plain function (+ global autorefresh) if older.
# ============================================================================
def _pipeline_live_panel_inner():
    """Core render logic — called by both fragment and non-fragment variants."""
    _live_runs = scan_runner.active_runs()
    _live_pipeline = latest_pipeline_status()
    _live_pipeline_running = _live_pipeline and _live_pipeline.get("state") == "running"

    render_scorer_progress()

    if _live_pipeline_running or _live_runs:
        st.markdown("---")
        _current = next(
            (r for r in _live_runs if r.get("label", "").startswith("pipeline")),
            _live_runs[0] if _live_runs else None,
        )
        if _current:
            with st.container(border=True):
                _lh1, _lh2, _lh3 = st.columns([4, 2, 1])
                _lh1.markdown(
                    f"#### 📡 Live · `{_current['label']}` · pid {_current['pid']}"
                )
                _lh2.metric("Running", human_elapsed(_current["started_at"]))
                if _lh3.button("⏹ Stop", key="frag_stop_pipe",
                               help="Send stop signal — process exits after current step"):
                    scan_runner.stop_run(_current["run_id"])
                    st.warning(
                        "⏹ Stop signal sent — process will exit after the current step."
                    )
                _log_text = scan_runner.tail_log(_current["log_path"]) or ""
                # Surface current stage from log
                _stage_match = None
                for _ll in reversed((_log_text or "").splitlines()):
                    if any(tag in _ll for tag in ("[0/3]", "[1/3]", "[2/3]", "[3/3]")):
                        _stage_match = _ll.strip()
                        break
                if _stage_match:
                    st.caption(f"⚙️ {_stage_match}")
                st.code(
                    _log_text if _log_text else "⏳ Starting — waiting for first output…",
                    language="text",
                    height=400,
                )
                _refresh_note = (
                    "↻ live (every 3s — no page flash)"
                    if _HAS_FRAGMENT else "↻ auto-refreshes every 5s"
                )
                st.caption(
                    f"Run ID: `{_current['run_id']}` · {_refresh_note} · "
                    f"log: `{Path(_current['log_path']).name}`"
                )


if _HAS_FRAGMENT:
    @st.fragment(run_every=3)
    def _pipeline_live_panel():
        """Fragment version: only this widget rerenders every 3s — no page flash."""
        _pipeline_live_panel_inner()
else:
    def _pipeline_live_panel():
        """Fallback: plain function, page-wide autorefresh handles timing."""
        _pipeline_live_panel_inner()


# ============================================================================
# 🏠 DASHBOARD
# ============================================================================
if page == "🏠 Dashboard":
    meta = tr.get("meta", {})
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    targets = meta.get("weekly_kpi_targets", {})

    # ── Personalized greeting ─────────────────────────────────────────────
    _now = datetime.now()
    _greet = ("Good morning" if _now.hour < 12
              else "Good afternoon" if _now.hour < 17 else "Good evening")

    # Pull brief data early for the stat row (load_morning_brief is cached)
    _brief_now = load_morning_brief()
    _brief_entries_top = (_brief_now.get("top") or []) if _brief_now else []
    _brief_date_raw_top = (_brief_now.get("brief_date", "") if _brief_now else "")
    _brief_is_today = False
    if _brief_date_raw_top:
        try:
            _brief_is_today = (
                datetime.strptime(_brief_date_raw_top, "%Y%m%d").date() == date.today()
            )
        except ValueError:
            pass
    _new_matches_today = len(_brief_entries_top) if _brief_is_today else 0
    _top_score_val = None
    _top_score_tip = "No brief today — run nightly refresh"
    if _brief_entries_top:
        try:
            _top_score_val = int(
                _brief_entries_top[0].get("fit", {}).get("fit_score", 0) or 0
            )
            _top_company = _brief_entries_top[0].get("company", "?")
            _top_title = _brief_entries_top[0].get("title", "?")
            _top_score_tip = f"{_top_company} — {_top_title}"
        except (TypeError, ValueError):
            pass

    _applied_this_week = sum(
        1 for j in jobs
        if j.get("date_applied") and parse_date(j.get("date_applied")) is not None
        and parse_date(j.get("date_applied")) >= week_start
    )

    # Last brief timestamp
    _brief_files_top = sorted(
        OUT_DIR.glob("brief_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    _brief_ts_str = ""
    if _brief_files_top:
        _bts = datetime.fromtimestamp(_brief_files_top[0].stat().st_mtime)
        _brief_ts_str = f"Brief refreshed {_bts.strftime('%b %d at %I:%M %p')}"

    # Greeting row
    _gh1, _gh2 = st.columns([3, 1])
    with _gh1:
        st.markdown(f"## {_greet}, Saber 👋")
        st.caption(
            f"{today.strftime('%A, %B %d')} · {_brief_ts_str}"
            if _brief_ts_str else today.strftime('%A, %B %d')
        )
    with _gh2:
        if any_work_active and active_runs:
            _running_lbl = active_runs[0].get("label", "job")
            st.info(f"🟡 **{_running_lbl}** is running", icon="🚀")
        elif any_work_active:
            st.info("🟡 Pipeline running", icon="🚀")

    # Stat row
    _sc1, _sc2, _sc3, _sc4 = st.columns(4)
    _sc1.metric(
        "New matches today",
        _new_matches_today,
        help=("Top picks from today's morning brief."
              if _brief_is_today else "Run nightly refresh to get today's picks."),
    )
    _sc2.metric("Applied this week", _applied_this_week)
    _sc3.metric(
        "Top score",
        f"{_top_score_val}/10" if _top_score_val else "—",
        help=_top_score_tip,
    )
    _sc4.metric(
        "CRM: outreach due",
        _crm_badge_count,
        delta="high priority" if _crm_badge_count > 0 else None,
        delta_color="inverse" if _crm_badge_count > 0 else "normal",
        help="High-priority recruiters not yet contacted. Go to 🤝 Recruiter CRM.",
    )

    # ── Campaign progress + pipeline funnel ──────────────────────────────────
    _camp_start_str = meta.get("campaign_start", "2026-05-03")
    _camp_end_str   = meta.get("campaign_end", "2026-07-12")
    try:
        _camp_start = datetime.strptime(_camp_start_str, "%Y-%m-%d").date()
        _camp_end   = datetime.strptime(_camp_end_str,   "%Y-%m-%d").date()
        _camp_total = max((_camp_end - _camp_start).days, 1)
        _camp_done  = max(min((today - _camp_start).days, _camp_total), 0)
        _camp_pct   = int(_camp_done / _camp_total * 100)
        _camp_left  = max((_camp_end - today).days, 0)
    except Exception:
        _camp_pct = 0; _camp_left = 0

    # Pipeline funnel — quick glance at jobs in each active stage
    _stage_counts = {}
    _ACTIVE_STAGES = ["Tailoring", "Applied", "Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite", "Offer"]
    for _j in jobs:
        _s = _j.get("status", "")
        if _s in _ACTIVE_STAGES:
            _stage_counts[_s] = _stage_counts.get(_s, 0) + 1

    _cprog_col, _funnel_col = st.columns([1, 1], gap="large")
    with _cprog_col:
        with st.container(border=True):
            st.markdown("##### 📅 Campaign Progress")
            st.progress(_camp_pct / 100, text=f"{_camp_pct}% · {_camp_left} days remaining")
            st.caption(
                f"{_camp_start_str} → {_camp_end_str}  ·  "
                f"Week {(_camp_done // 7) + 1} of {(_camp_total // 7) + 1}"
            )
    with _funnel_col:
        with st.container(border=True):
            st.markdown("##### 🔽 Active Pipeline")
            if _stage_counts:
                _stage_labels = {
                    "Tailoring": "✍️ Tailoring",
                    "Applied": "📤 Applied",
                    "Recruiter_Screen": "📞 Recruiter",
                    "Phone_Screen": "📱 Phone Screen",
                    "Take_Home": "💻 Take-Home",
                    "Onsite": "🏢 Onsite",
                    "Offer": "🎉 Offer",
                }
                _funnel_parts = []
                for _st_key in _ACTIVE_STAGES:
                    if _st_key in _stage_counts:
                        _funnel_parts.append(
                            f"**{_stage_labels.get(_st_key, _st_key)}** {_stage_counts[_st_key]}"
                        )
                st.markdown("  ·  ".join(_funnel_parts))
            else:
                st.caption("No jobs in active stages yet — start applying!")

    # ── 7-day activity strip ──────────────────────────────────────────────────
    _act_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    _act_applied  = {d: 0 for d in _act_days}
    _act_outreach = {d: 0 for d in _act_days}
    for _aj in jobs:
        _ad = parse_date(_aj.get("date_applied"))
        if _ad and _ad in _act_applied:
            _act_applied[_ad] += 1
        for _ol in (_aj.get("outreach_log") or []):
            _od = parse_date(_ol.get("date"))
            if _od and _od in _act_outreach:
                _act_outreach[_od] += 1
    with st.container(border=True):
        st.markdown("##### 📆 Last 7 days")
        _sp_cols = st.columns(7)
        for _di, _dd in enumerate(_act_days):
            _n_app = _act_applied[_dd]
            _n_out = _act_outreach[_dd]
            _lbl = "**Today**" if _dd == today else f"{_dd.strftime('%a')} {_dd.day}"
            _delta_str = f"+{_n_out} outreach" if _n_out else None
            _sp_cols[_di].metric(
                _lbl,
                f"{_n_app} app{'s' if _n_app != 1 else ''}",
                delta=_delta_str,
                delta_color="normal" if _n_out else "off",
                help=f"{_dd.strftime('%B %d')}: {_n_app} applied, {_n_out} outreach",
            )

    st.markdown("---")

    # ── Today's Game Plan ─────────────────────────────────────────────────
    # Action-first band: surfaces the highest-priority things to do RIGHT NOW
    # before the informational sections. Overdue follow-ups first, then review
    # queue, then weekly progress. Empty = nothing to do = great news.
    _gp_fu = followup_buckets(jobs)
    _gp_overdue    = len(_gp_fu["overdue"])
    _gp_due_today  = len(_gp_fu["due_today"])
    _gp_no_sched   = len(_gp_fu["no_schedule"])
    _gp_review_ct  = sum(1 for _j in jobs if _j.get("status") == "Found")
    _gp_target_wk  = targets.get("applications_per_week", 5)
    _gp_applied_wk = _applied_this_week

    _gp_items = []
    if _gp_overdue:
        _gp_items.append(("#ef4444", "OVERDUE",
            f"{_gp_overdue} follow-up{'s' if _gp_overdue!=1 else ''} past due — send a note today",
            "🔔 Follow-ups"))
    if _gp_due_today:
        _gp_items.append(("#f59e0b", "TODAY",
            f"{_gp_due_today} follow-up{'s' if _gp_due_today!=1 else ''} due today",
            "🔔 Follow-ups"))
    if _gp_no_sched:
        _gp_items.append(("#f59e0b", "ACTION",
            f"{_gp_no_sched} applied job{'s' if _gp_no_sched!=1 else ''} with no follow-up scheduled",
            "🔔 Follow-ups"))
    if _gp_review_ct:
        _gp_items.append(("#8b5cf6", "QUEUE",
            f"{_gp_review_ct} unreviewed match{'es' if _gp_review_ct!=1 else ''} waiting for triage",
            "📬 Review Queue"))
    _gp_remaining = max(0, _gp_target_wk - _gp_applied_wk)
    if _gp_remaining > 0:
        _gp_items.append(("#10b981", "GOAL",
            f"{_gp_applied_wk}/{_gp_target_wk} applications this week — {_gp_remaining} to go",
            "📬 Review Queue"))

    if _gp_items:
        with st.container(border=True):
            st.markdown("#### 🎯 Today's game plan")
            for _gp_col, _gp_pri, _gp_text, _gp_dest in _gp_items:
                st.markdown(
                    f"<div style='padding:7px 12px;margin:3px 0;"
                    f"background:{_gp_col}15;border-left:3px solid {_gp_col};"
                    f"border-radius:4px;display:flex;justify-content:space-between;'"
                    f"><span><span style='font-size:10px;font-weight:700;"
                    f"color:{_gp_col};letter-spacing:.05em'>{_gp_pri}</span> "
                    f"<span style='font-size:13px;margin-left:6px'>{_gp_text}</span></span>"
                    f"<span style='font-size:11px;opacity:.55'>→ {_gp_dest}</span></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.success(
            "🎉 All caught up — no overdue follow-ups, review queue empty, weekly goal met!",
            icon="✅"
        )
    st.markdown("")
    st.markdown("---")

    # ── Today's top picks preview ─────────────────────────────────────────
    # Shows the top 3 brief entries as compact action cards RIGHT at the top
    # so the user sees what to work on the moment they open the Dashboard.
    if _brief_is_today and _brief_entries_top:
        st.markdown("#### 🌅 Today's top picks")
        _VERDICT_COLOR = {"apply_now": "#10b981", "tailor_and_apply": "#f59e0b", "watch": "#6366f1"}
        _VERDICT_LABEL = {"apply_now": "✅ Apply now", "tailor_and_apply": "✍️ Tailor & apply", "watch": "👀 Watch"}
        for _bi, _br in enumerate(_brief_entries_top, 1):
            _bf = _br.get("fit") or {}
            _bscore = int(_bf.get("fit_score") or 0)
            _bverdict = _bf.get("fit_verdict", "")
            _bcolor = _VERDICT_COLOR.get(_bverdict, "#6b7280")
            _bvlabel = _VERDICT_LABEL.get(_bverdict, _bverdict)
            _bfb = freshness_badge(_br.get("posted_date"), _br.get("found_at"))
            _bsummary = _bf.get("summary", "")
            _bgaps = _bf.get("gaps", "")
            _blink = _br.get("link", "")
            with st.container(border=True):
                _hcol, _scol, _acol = st.columns([6, 2, 1])
                with _hcol:
                    st.markdown(
                        f"<div style='font-size:1.05em;font-weight:600;margin-bottom:2px'>"
                        f"<span style='color:{_bcolor};font-size:1.3em;margin-right:6px'>{_bi}.</span>"
                        f"{_br.get('company','')} — {_br.get('title','')}</div>"
                        f"<div style='font-size:0.82em;opacity:0.65'>{_bfb}</div>",
                        unsafe_allow_html=True,
                    )
                    if _bsummary:
                        st.caption(_bsummary)
                    if _bgaps:
                        st.caption(f"⚠️ Gaps: {_bgaps}")
                with _scol:
                    st.metric("Fit score", f"{_bscore}/10")
                    st.markdown(
                        f"<div style='font-size:0.78em;color:{_bcolor};font-weight:600'>"
                        f"{_bvlabel}</div>",
                        unsafe_allow_html=True,
                    )
                with _acol:
                    if _blink:
                        st.link_button("🔗 Open", _blink, width='stretch')
        st.caption(
            "↓ Scroll to **Today's fresh matches** below for full detail, "
            "gap analysis, and tracker actions."
        )
        st.markdown("---")

    elif not _brief_is_today:
        # No today brief — clear call to action
        _brief_age_msg = ""
        if _brief_now and _brief_date_raw_top:
            try:
                _bd = datetime.strptime(_brief_date_raw_top, "%Y%m%d").date()
                _days_old = (date.today() - _bd).days
                _brief_age_msg = f" (last brief: {_days_old}d ago)"
            except ValueError:
                pass
        elif not _brief_now:
            _brief_age_msg = " — no brief on file yet"
        st.info(
            f"No brief for today{_brief_age_msg}. "
            "Hit **🌅 Nightly refresh** below to generate today's picks.",
            icon="🌅",
        )
        st.markdown("---")

    # ── CRM urgency alert ─────────────────────────────────────────────────
    if _crm_badge_count > 0:
        _crm_high_list = [
            c for c in _crm_early_all
            if c.get("priority") == "High"
            and c.get("status") == "Not_Contacted"
            and not c.get("last_touchpoint")
        ][:5]  # show at most 5
        with st.expander(
            f"🤝 {_crm_badge_count} high-priority recruiter"
            f"{'s' if _crm_badge_count != 1 else ''} awaiting outreach",
            expanded=False,
        ):
            st.caption(
                "Recruiter relationships drive ~70% of Director+ moves in Toronto finance. "
                "These high-priority firms haven't been contacted yet:"
            )
            for _crec in _crm_high_list:
                _cname = _crec.get("firm") or _crec.get("name") or "?"
                _cnext = _crec.get("next_action") or "—"
                st.markdown(f"**{_cname}** — {_crec.get('firm_type','').replace('_',' ')}")
                st.caption(f"Next action: {_cnext[:200]}")
            st.caption("→ Navigate to 🤝 Recruiter CRM in the sidebar to log outreach.")
        st.markdown("---")

    # ---------- Quick actions — one-click entry points ----------
    # Before this, the landing page had metrics and banners but no way
    # to START work without navigating to 🎯 Pipeline first. Now the
    # three most-used agents are one click from load. Disabled states
    # and tooltips explain why a button is unavailable (key missing,
    # pipeline already running, Gmail not connected).
    _dash_key_ok = api_key.is_key_valid()
    _dash_gmail_ok = gmail_ui.is_connected()
    _dash_can_run_llm = _dash_key_ok and not pipeline_running
    # --- Active-run banner in main content (persists across reruns) ---
    _last = st.session_state.get("_last_launch")
    if _last:
        _banner_run = next((r for r in active_runs if r["run_id"] == _last["run_id"]), None)
        if _banner_run:
            _bc = st.container()
            with _bc:
                st.info(
                    f"🟡 **{_last['label']}** is running — pid {_banner_run['pid']} · "
                    f"{human_elapsed(_banner_run['started_at'])} elapsed. "
                    f"Go to **🎯 Pipeline** to see live output and stop it.",
                    icon="🚀",
                )
        else:
            # Run finished — clear the banner
            del st.session_state["_last_launch"]

    with st.container(border=True):
        st.markdown("#### ⚡ Quick actions")
        qa1, qa2, qa3, qa4, qa5 = st.columns([2, 2, 2, 2, 2])
        with qa1:
            _help_core = ("Scrape the 77 core targets (no expansion list). "
                          "~15-30 min. Writes scan_<date>.json only; no LLM "
                          "call until you score. No API key needed.")
            if st.button("🛰 Core scrape", width='stretch',
                          disabled=bool(pipeline_running or any_work_active),
                          help=_help_core, key="dash_qa_core"):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable,
                    str(ROOT / "automation" / "run_pipeline.py"),
                    "--scrape-mode", "core",
                    "--skip-score", "--skip-promote",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Core scrape"}
                st.toast("🛰 Core scrape launched!", icon="🚀")
                st.rerun()
        with qa2:
            _help_gmail = (
                "Pull LinkedIn/Indeed job alert emails from the last 14 "
                "days. ~10-30s. Doesn't call the API. Produces "
                "scan_gmail_<stamp>.json that you can score or promote."
            )
            if st.button("📬 Pull Gmail alerts", width='stretch',
                          disabled=(not _dash_gmail_ok) or bool(any_work_active),
                          help=_help_gmail, key="dash_qa_gmail"):
                rec = scan_runner.start_run("gmail_fetch", [
                    sys.executable,
                    str(ROOT / "automation" / "gmail_fetch.py"),
                    "--days", "14",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Gmail fetch"}
                st.toast("📬 Gmail fetch launched!", icon="🚀")
                st.rerun()
            if not _dash_gmail_ok:
                st.caption("🔌 Connect Gmail in the sidebar.")
        with qa3:
            _help_nightly = ("Scrape + find new roles since last scan + "
                              "score only those + emit top-3 brief. "
                              "Cheap (~$0.03), ~25 min. Needs API key.")
            if st.button("🌅 Nightly refresh", width='stretch',
                          disabled=(not _dash_can_run_llm) or bool(any_work_active),
                          help=_help_nightly, key="dash_qa_nightly"):
                nightly_cmd_list = [sys.executable, str(ROOT / "automation" / "nightly_refresh.py")]
                rec = scan_runner.start_run("nightly_refresh", nightly_cmd_list)
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Nightly refresh"}
                st.toast("🌅 Nightly refresh launched!", icon="🚀")
                st.rerun()
            if not _dash_key_ok:
                st.caption("🔑 Set API key in the sidebar.")
        with qa4:
            _help_pipe = ("Go to the 🎯 Pipeline page to configure and launch "
                          "a full end-to-end run (choose scrape strategy, "
                          "sector/company filter, scorer concurrency, etc.)")
            st.markdown(
                "<div style='padding-top:6px'></div>", unsafe_allow_html=True)
            st.caption(_help_pipe)
        with qa5:
            # At-a-glance data freshness so the user can gauge whether they
            # even NEED to re-scrape. Mirrors the Pipeline-page header but
            # compacted to a single cell.
            # jd_scraper writes scan_YYYYMMDD.json; earlier runs sometimes
            # produced scan_v4.json. Glob both, exclude scored/gmail/checkpoint.
            _ds_web = sorted([f for f in OUT_DIR.glob("scan_*.json")
                                if "_scored" not in f.name
                                and "scan_gmail_" not in f.name
                                and "scan_checkpoint" not in f.name],
                              key=lambda p: p.stat().st_mtime, reverse=True)
            _ds_gm = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                             key=lambda p: p.stat().st_mtime, reverse=True)

            def _age(p):
                if not p:
                    return "—"
                age = datetime.now().timestamp() - p.stat().st_mtime
                if age < 3600:
                    return f"{int(age/60)}m ago"
                if age < 86400:
                    return f"{int(age/3600)}h ago"
                return f"{int(age/86400)}d ago"

            st.markdown(f"**Web scan:** {_age(_ds_web[0] if _ds_web else None)}")
            st.markdown(f"**Gmail pull:** {_age(_ds_gm[0] if _ds_gm else None)}")
    st.markdown("")

    # Gmail trash panel: only renders if the most recent scan_gmail_*.json
    # has UIDs that haven't been moved to Trash yet. Lives right under
    # Quick Actions so a freshly-pulled scan surfaces the cleanup prompt
    # at the natural next-step location.
    render_gmail_trash_panel()

    # ---------- Compact status strip ----------
    # Previously three stacked banners. Now: one caption line if nothing is
    # running, or a progress bar for live scoring, or a one-line "X running"
    # banner. Eliminates 3 banners' worth of vertical chrome on every page
    # load when nothing interesting is happening.
    _sp = load_scorer_progress()
    _scorer_live = bool(_sp and _sp.get("state") == "running")
    if _scorer_live:
        cur = _sp.get("current", 0); tot = _sp.get("total", 0) or 1
        frac = min(1.0, cur / tot)
        st.progress(
            frac,
            text=(
                f"🤖 Scoring {cur}/{tot} · "
                f"elapsed {_fmt_eta(_sp.get('elapsed_sec'))} · "
                f"ETA {_fmt_eta(_sp.get('eta_sec'))} · "
                f"apply_now={(_sp.get('verdict_counts') or {}).get('apply_now', 0)}"
            ),
        )
    elif pipeline_running:
        st.info(
            f"🎯 Pipeline `{pipe['pipeline_id']}` running · "
            f"elapsed {human_elapsed(pipe['started_at'])} — "
            f"jump to Pipeline to watch stages.",
            icon="⚡",
        )
    elif pipe and pipe.get("state") == "finished":
        st.caption(
            f"✅ Last pipeline `{pipe['pipeline_id']}` "
            f"finished {fmt_dt(pipe.get('finished_at'))} · "
            f"Inspect tab on Pipeline for results."
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
                              "tailor runs cost ~$0.15 each", expanded=False):
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
                              expanded=False):
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

    # Only render the health block when there is a genuine ISSUE. A fresh
    # scan with no problems used to trigger the full 4-metric widget; now
    # it stays silent. Sidebar auto-refresh and freshness on Quick-actions
    # already show "fresh scan" without taking a full row.
    if health_issues:
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
    # Today's brief is always-visible (no expander). Stale briefs (>0 days)
    # are collapsed into a small expander to save space.
    brief = load_morning_brief()
    if brief:
        brief_date_raw = brief.get("brief_date", "")
        try:
            brief_date_parsed = datetime.strptime(brief_date_raw, "%Y%m%d").date()
        except ValueError:
            brief_date_parsed = None
        top = brief.get("top") or []
        is_stale = brief_date_parsed and (date.today() - brief_date_parsed).days >= 1

        if is_stale:
            # Stale: collapsed expander so it doesn't crowd the page
            _days_old = (date.today() - brief_date_parsed).days if brief_date_parsed else "?"
            _brief_outer = st.expander(
                f"🌅 Fresh matches · {_days_old}d old — run nightly refresh to update"
                f" ({len(top)} match(es))",
                expanded=False,
            )
        else:
            # Today's brief: always-visible card header, no click required
            st.markdown("#### 🌅 Today's fresh matches")
            _brief_outer = st.container()
    else:
        _brief_outer = None

    if brief and _brief_outer is not None:
      with _brief_outer:
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

        # Pre-compute matches so we can report how many recruiter emails
        # plausibly map to applied roles.
        recruiter_matches = [
            (r, _match_mail_to_tracker(r["sender_email"], r["subject"]))
            for r in recruiters
        ]
        matched_n = sum(1 for _, hits in recruiter_matches if hits)

        # Highlight: recruiter emails matched to Applied roles are likely
        # status-change signals. ONLY render the banner when there are real
        # matches — otherwise the Inbox section stays collapsed and quiet.
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

        # Compact: single outer expander, metrics inside. When there are
        # no applied-matches the whole section stays collapsed.
        _inbox_title = (f"📬 Inbox signals (14d) · "
                         f"{len(recruiters)} recruiter · "
                         f"{matched_n} tracker-match · "
                         f"{len(alerts)} alerts")
        with st.expander(_inbox_title, expanded=bool(applied_matches)):
            ic1, ic2, ic3, ic4 = st.columns(4)
            ic1.metric("Recruiter/ATS", len(recruiters))
            ic2.metric("→ match tracker", matched_n,
                       help="Recruiter emails whose sender domain or "
                            "subject matches a role in your tracker.")
            ic3.metric("Job alerts", len(alerts))
            ic4.metric("Total", len(inbox))

            st.markdown("**Recent recruiter mail (likely status changes)**")
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

    # ---------- Collapsed: pipeline bar-chart + apply-this-week ----------
    # Both are reference-only. Fold into a single expander so they don't
    # chew two full screens of vertical space on load. Quick-actions block
    # at the top of the page already covers the "run something" need; the
    # older duplicate set (Run full / Fast / Weekly report) was removed.
    with st.expander("📈 Pipeline chart · apply-this-week queue", expanded=False):
        status_counts = (jobs_df["status"].value_counts()
                           if "status" in jobs_df.columns else pd.Series())
        status_order = meta.get("status_enum", list(status_counts.index))
        fd = pd.DataFrame(
            [{"status": s, "count": int(status_counts.get(s, 0))}
             for s in status_order]
        )
        d1, d2 = st.columns([2, 1])
        with d1:
            st.bar_chart(fd.set_index("status"))
        with d2:
            st.dataframe(fd, hide_index=True, width='stretch')

        st.markdown("**🎯 Apply this week**")
        apply_ids = meta.get("kanban_targets_week1", {}).get("apply_this_week", [])
        apply_rows = (jobs_df[jobs_df["id"].isin(apply_ids)]
                       if "id" in jobs_df.columns else pd.DataFrame())
        if not apply_rows.empty:
            cols = [c for c in ["id", "company", "title", "tier",
                                  "fit_score", "url"]
                    if c in apply_rows.columns]
            st.dataframe(apply_rows[cols], hide_index=True, width='stretch',
                         column_config={"url": st.column_config.LinkColumn()})
        else:
            st.caption("No roles flagged for this week.")


# ============================================================================
# 📥 OUTCOME INBOX  — recruiter-email + dead-URL proposals → tracker
# ============================================================================
# Surfaces every pending outcome_proposals.json entry (from gmail_outcome.py
# AND url_check.py — both write the same file under safe_json locks) so the
# user can accept / reject status transitions in one place. Turns the
# tracker from write-only into a learning loop: replies become Phone_Screen,
# dead URLs become Expired, all without manual JSON editing.
elif page == "📥 Outcome Inbox":
    st.title("📥 Outcome Inbox")
    st.caption(
        "Pending status-transition proposals from Gmail (recruiter replies) "
        "and URL-liveness checks. Accept individually, accept all "
        "high-confidence in bulk, or reject the noise."
    )

    _OI_PROPOSALS_PATH = OUT_DIR / "outcome_proposals.json"

    # --- Load proposals (reads via safe_json lock so a concurrent gmail
    # ---  fetch doesn't tear the file under us). ---
    try:
        from safe_json import read_json as _oi_read, mutate_json as _oi_mutate
    except ImportError:
        # Fallback to plain read if safe_json missing — file may still be
        # readable but we surrender concurrent-safety. Make that visible.
        st.warning("safe_json not importable — proposals may race with the "
                   "scanner. `pip install portalocker`.", icon="⚠️")
        _oi_read = lambda p, default=None: (
            json.loads(Path(p).read_text(encoding="utf-8"))
            if Path(p).exists() and Path(p).read_text(encoding="utf-8").strip()
            else default
        )
        _oi_mutate = None  # type: ignore

    _oi_proposals = _oi_read(_OI_PROPOSALS_PATH, default=[]) or []
    if not isinstance(_oi_proposals, list):
        _oi_proposals = []

    # --- Last-run header ---
    _oi_h1, _oi_h2, _oi_h3 = st.columns([2, 2, 1])
    with _oi_h1:
        if _OI_PROPOSALS_PATH.exists():
            _oi_age = datetime.now().timestamp() - _OI_PROPOSALS_PATH.stat().st_mtime
            if _oi_age < 60:
                _oi_age_lbl = f"{int(_oi_age)}s ago"
            elif _oi_age < 3600:
                _oi_age_lbl = f"{int(_oi_age / 60)}m ago"
            elif _oi_age < 86400:
                _oi_age_lbl = f"{int(_oi_age / 3600)}h ago"
            else:
                _oi_age_lbl = f"{int(_oi_age / 86400)}d ago"
            st.metric("Pending proposals", len(_oi_proposals),
                      help=f"File: {_OI_PROPOSALS_PATH.name}")
            st.caption(f"Last update: {_oi_age_lbl}")
        else:
            st.metric("Pending proposals", 0)
            st.caption("No file yet — pull latest to create it")

    # --- Pull-latest button (Gmail outcome) ---
    _oi_gmail_ok = gmail_ui.is_connected()
    _oi_key_ok = api_key.is_key_valid()
    _oi_can_run = _oi_gmail_ok and _oi_key_ok
    with _oi_h2:
        if st.button(
            "📥 Pull latest from Gmail",
            type="primary" if _oi_can_run else "secondary",
            disabled=not _oi_can_run,
            width='stretch',
            help=(
                "Runs `automation/gmail_outcome.py --days 7` in the "
                "background. Pulls recruiter emails, classifies via "
                "Haiku, appends new proposals to this list. "
                "~$0.001 per email; capped at $0.20/run."
            ),
        ):
            _oi_cmd = [sys.executable,
                       str(ROOT / "automation" / "gmail_outcome.py"),
                       "--days", "7"]
            _oi_rec = scan_runner.start_run("gmail_outcome", _oi_cmd)
            st.toast("📥 gmail_outcome launched!", icon="🚀")
            st.session_state["_oi_last_launch"] = _oi_rec.run_id
            st.rerun()

        if not _oi_gmail_ok and not _oi_key_ok:
            st.caption("🔌 Connect Gmail + API key in sidebar")
        elif not _oi_gmail_ok:
            st.caption("🔌 Connect Gmail in sidebar")
        elif not _oi_key_ok:
            st.caption("🔑 Set API key in sidebar")

    with _oi_h3:
        if st.button("🔄 Refresh", width='stretch',
                      help="Re-read the proposals file. Useful right after "
                           "a Gmail pull or url_check finishes."):
            st.rerun()

    # --- If a recent run was launched, tail its log ---
    _oi_last_run_id = st.session_state.get("_oi_last_launch")
    if _oi_last_run_id:
        _oi_status_path = ROOT / "automation" / "outputs" / "runs" / f"{_oi_last_run_id}.json"
        if _oi_status_path.exists():
            try:
                _oi_rec = scan_runner.refresh_state(_oi_status_path)
                _oi_state = _oi_rec.get("state", "?")
                _oi_state_emoji = {"running": "🟡", "finished": "✅",
                                    "failed": "❌", "stopped": "⏹"}.get(_oi_state, "❓")
                with st.expander(
                    f"{_oi_state_emoji} Recent run `{_oi_last_run_id}` · {_oi_state}",
                    expanded=(_oi_state == "running"),
                ):
                    _oi_log = scan_runner.tail_log(_oi_rec.get("log_path", ""), 6000)
                    st.code(_oi_log or "(no output yet)", language="text")
                    if _oi_state == "running":
                        st.caption("↻ refreshing while running")
                        # Light auto-refresh while the job is in flight
                        st_autorefresh(interval=3000, key="_oi_log_autorefresh")
            except Exception:
                pass

    if not _oi_can_run:
        if not _oi_gmail_ok:
            st.info(
                "**Gmail not configured.** Open the sidebar Gmail panel "
                "and save your address + Google app password. The "
                "tracker stays read-only until then; existing proposals "
                "below remain actionable.",
                icon="📬",
            )

    st.markdown("---")

    # --- Empty state ---
    if not _oi_proposals:
        st.success("Inbox is empty — no pending proposals.", icon="📭")
        st.caption(
            "When `gmail_outcome.py` or `url_check.py` runs, new "
            "transition proposals will appear here. Click **Pull latest** "
            "above to scan Gmail now."
        )
        st.stop()

    # --- Bulk actions ---
    _oi_b1, _oi_b2, _oi_b3 = st.columns([2, 2, 2])
    _oi_high_conf = [
        p for p in _oi_proposals
        if int((p.get("evidence") or {}).get("confidence", 0)) >= 8
    ]
    _oi_low_conf = [
        p for p in _oi_proposals
        if int((p.get("evidence") or {}).get("confidence", 0)) < 6
    ]

    with _oi_b1:
        if st.button(
            f"✅ Accept all ≥8 confidence ({len(_oi_high_conf)})",
            disabled=not _oi_high_conf,
            width='stretch',
            help="Apply every proposal whose evidence.confidence >= 8 to "
                 "the tracker. Each transition is backed up + atomic.",
        ):
            from safe_json import mutate_json as _oi_mut2
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = TRACKER.with_suffix(f".bak.{stamp}.json")
            if TRACKER.exists():
                bak.write_text(TRACKER.read_text(encoding="utf-8"),
                                encoding="utf-8")
            _oi_by_id = {p["job_id"]: p for p in _oi_high_conf if p.get("job_id")}
            _oi_terminal = {"Hired", "Withdrawn", "Declined"}
            _oi_changed: list[str] = []

            def _oi_apply(tracker):
                if not isinstance(tracker, dict) or "jobs" not in tracker:
                    return tracker
                for j in tracker["jobs"]:
                    jid = j.get("id")
                    if jid not in _oi_by_id:
                        continue
                    if j.get("status") in _oi_terminal:
                        continue
                    j["status"] = _oi_by_id[jid]["proposed_status"]
                    j["status_changed_by"] = "outcome_inbox_bulk"
                    j["status_changed_on"] = date.today().isoformat()
                    _oi_changed.append(jid)
                return tracker

            _oi_mut2(TRACKER, _oi_apply, default={"jobs": []})

            # Remove accepted proposals from the file
            _oi_accepted_keys = {(p.get("job_id"),
                                  p.get("proposed_status"),
                                  (p.get("evidence") or {}).get("source", ""),
                                  (p.get("evidence") or {}).get("email_id", ""))
                                 for p in _oi_high_conf}
            _oi_mut2(_OI_PROPOSALS_PATH,
                      lambda cur: [
                          p for p in (cur or [])
                          if (p.get("job_id"), p.get("proposed_status"),
                              (p.get("evidence") or {}).get("source", ""),
                              (p.get("evidence") or {}).get("email_id", ""))
                          not in _oi_accepted_keys
                      ],
                      default=[])
            st.cache_data.clear()
            st.toast(f"✅ Accepted {len(_oi_changed)} transition(s)", icon="📨")
            st.rerun()

    with _oi_b2:
        if st.button(
            f"🧹 Clear low-confidence noise ({len(_oi_low_conf)})",
            disabled=not _oi_low_conf,
            width='stretch',
            help="Remove proposals with confidence < 6. Marks them as "
                 "reviewed-and-ignored without touching the tracker.",
        ):
            from safe_json import mutate_json as _oi_mut3
            _oi_keep = [p for p in _oi_proposals
                         if int((p.get("evidence") or {}).get("confidence", 0))
                            >= 6]
            _oi_mut3(_OI_PROPOSALS_PATH, lambda cur: _oi_keep, default=[])
            st.toast(f"🧹 Cleared {len(_oi_low_conf)} low-conf proposal(s)",
                      icon="🧼")
            st.rerun()

    with _oi_b3:
        st.metric("Total pending", len(_oi_proposals),
                  help="Includes ALL sources — Gmail + URL check.")

    st.markdown("---")

    # --- Per-row table with action buttons ---
    # We render rows manually rather than st.dataframe so the action
    # buttons sit inline. Capped at 50 rows for render speed; the
    # bulk-accept covers the rest.
    _oi_rows = list(_oi_proposals)
    # Sort: highest confidence first, then most recent evidence.
    _oi_rows.sort(
        key=lambda p: (
            -int((p.get("evidence") or {}).get("confidence", 0)),
            -(0 if not (p.get("evidence") or {}).get("checked_at")
              else hash((p.get("evidence") or {}).get("checked_at", ""))),
        )
    )
    _oi_visible = _oi_rows[:50]
    if len(_oi_rows) > 50:
        st.caption(f"Showing top 50 of {len(_oi_rows)} — use bulk accept "
                    f"to clear the long tail.")

    # Build a tracker-jobs lookup for company name display
    _oi_jobs = (load_tracker() or {}).get("jobs", []) or []
    _oi_job_by_id = {j.get("id"): j for j in _oi_jobs}

    for _oi_idx, _oi_p in enumerate(_oi_visible):
        _oi_jid = _oi_p.get("job_id", "")
        _oi_ev = _oi_p.get("evidence") or {}
        _oi_src_raw = _oi_ev.get("source", "")
        _oi_src = "📥 Gmail" if "gmail_outcome" in _oi_src_raw else (
            "🔗 URL check" if "url_check" in _oi_src_raw else _oi_src_raw or "?"
        )
        _oi_conf = _oi_ev.get("confidence")
        _oi_cur = _oi_p.get("current_status", "?")
        _oi_prop = _oi_p.get("proposed_status", "?")
        _oi_company = (
            _oi_p.get("company")
            or (_oi_job_by_id.get(_oi_jid) or {}).get("company", "")
            or _oi_ev.get("extracted_company", "?")
        )
        _oi_role = (
            _oi_ev.get("extracted_role")
            or (_oi_job_by_id.get(_oi_jid) or {}).get("title", "")
            or "(unknown role)"
        )
        _oi_when = _oi_ev.get("date") or _oi_ev.get("checked_at", "")[:10] or "—"

        with st.container(border=True):
            _oi_c1, _oi_c2, _oi_c3, _oi_c4 = st.columns([4, 3, 1, 2])
            with _oi_c1:
                st.markdown(f"**{_oi_company}** — _{_oi_role[:80]}_")
                _oi_meta_bits = [_oi_src]
                if _oi_when:
                    _oi_meta_bits.append(_oi_when)
                if _oi_conf is not None:
                    _oi_meta_bits.append(f"conf {_oi_conf}/10")
                if _oi_jid:
                    _oi_meta_bits.append(f"`{_oi_jid}`")
                st.caption(" · ".join(_oi_meta_bits))
                if _oi_ev.get("quote"):
                    st.markdown(
                        f"<div style='font-size:12px;opacity:0.85;"
                        f"padding:6px 10px;border-left:2px solid #6366f1;"
                        f"background:rgba(99,102,241,0.08);"
                        f"border-radius:3px;margin:4px 0'>"
                        f"\"{_oi_ev['quote']}\"</div>",
                        unsafe_allow_html=True,
                    )
                if _oi_ev.get("subject"):
                    st.caption(f"📧 {_oi_ev['subject'][:120]}")
                elif _oi_ev.get("url"):
                    st.caption(f"🔗 {_oi_ev['url'][:120]}")
            with _oi_c2:
                st.markdown(f"**Status** `{_oi_cur}` → `{_oi_prop}`")
                st.caption(_oi_p.get("reason", ""))
            with _oi_c3:
                _oi_acc_key = f"_oi_accept_{_oi_idx}_{_oi_jid}"
                if st.button("✅", key=_oi_acc_key,
                              help="Accept this transition — applies to "
                                   "tracker + removes from inbox",
                              use_container_width=True):
                    from safe_json import mutate_json as _oi_mut4
                    if not _oi_jid:
                        st.error("Proposal has no job_id; cannot apply.")
                    else:
                        # Backup tracker before write
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        bak = TRACKER.with_suffix(f".bak.{stamp}.json")
                        if TRACKER.exists():
                            bak.write_text(TRACKER.read_text(encoding="utf-8"),
                                            encoding="utf-8")

                        def _oi_apply_one(tracker):
                            if not isinstance(tracker, dict) or "jobs" not in tracker:
                                return tracker
                            for j in tracker["jobs"]:
                                if j.get("id") != _oi_jid:
                                    continue
                                if j.get("status") in {"Hired", "Withdrawn",
                                                         "Declined"}:
                                    return tracker
                                j["status"] = _oi_prop
                                j["status_changed_by"] = "outcome_inbox"
                                j["status_changed_on"] = date.today().isoformat()
                                break
                            return tracker

                        _oi_mut4(TRACKER, _oi_apply_one, default={"jobs": []})

                        # Remove this proposal from the file
                        _oi_my_key = (_oi_jid, _oi_prop, _oi_src_raw,
                                       _oi_ev.get("email_id", ""))

                        def _oi_drop_one(cur):
                            return [p for p in (cur or [])
                                    if (p.get("job_id"),
                                        p.get("proposed_status"),
                                        (p.get("evidence") or {}).get("source", ""),
                                        (p.get("evidence") or {}).get("email_id", ""))
                                    != _oi_my_key]

                        _oi_mut4(_OI_PROPOSALS_PATH, _oi_drop_one, default=[])
                        st.cache_data.clear()
                        st.toast(f"✅ {_oi_company}: {_oi_cur} → {_oi_prop}",
                                  icon="📨")
                        st.rerun()
            with _oi_c4:
                _oi_rej_key = f"_oi_reject_{_oi_idx}_{_oi_jid}"
                if st.button("❌ Reject", key=_oi_rej_key,
                              help="Drop this proposal. Tracker unchanged.",
                              use_container_width=True):
                    from safe_json import mutate_json as _oi_mut5
                    _oi_my_key = (_oi_jid, _oi_prop, _oi_src_raw,
                                   _oi_ev.get("email_id", ""))

                    def _oi_drop_one(cur):
                        return [p for p in (cur or [])
                                if (p.get("job_id"),
                                    p.get("proposed_status"),
                                    (p.get("evidence") or {}).get("source", ""),
                                    (p.get("evidence") or {}).get("email_id", ""))
                                != _oi_my_key]

                    _oi_mut5(_OI_PROPOSALS_PATH, _oi_drop_one, default=[])
                    st.toast(f"❌ Rejected {_oi_company}", icon="🗑")
                    st.rerun()

    with st.expander("ℹ️  How this works"):
        st.markdown(
            "- **Sources.** Two scripts append to "
            "`automation/outputs/outcome_proposals.json`:\n"
            "  - `automation/gmail_outcome.py` — classifies recruiter "
            "emails into status transitions.\n"
            "  - `automation/url_check.py` — flags dead URLs as `Expired`.\n"
            "  Both writes are atomic + cross-process safe via `safe_json.mutate_json`.\n"
            "- **Accept.** Applies the proposed status, takes a tracker "
            "backup, then removes the proposal from this list.\n"
            "- **Reject.** Removes the proposal only. Tracker untouched.\n"
            "- **Confidence.** Gmail proposals carry an LLM confidence "
            "1-10. URL-check proposals are deterministic (no number; we "
            "treat them as 8 by convention).\n"
            "- **Auto-commit.** Run `gmail_outcome.py --commit` from the "
            "CLI to auto-apply >=9 confidence non-terminal transitions "
            "(Recruiter_Screen / Phone_Screen / Take_Home / Onsite). "
            "Offers + Rejections always wait for your eyes."
        )


# ============================================================================
# 🎯 PIPELINE  — the agentic flow, end-to-end
# ============================================================================
elif page == "🎯 Pipeline":
    st.title("🎯 Agentic Pipeline")
    st.caption(
        "Scrape → Score → Triage → Promote → Tailor. "
        "One flow; one click runs the whole chain. Each stage can also be run in isolation."
    )

    # ---------- Data freshness + last activity summary ---------
    def _latest_web_scan():
        files = sorted(OUT_DIR.glob("scan_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        files = [f for f in files
                 if "_scored" not in f.name
                 and "scan_gmail_" not in f.name
                 and "scan_checkpoint" not in f.name]
        return files[0] if files else None

    def _latest_gmail_scan():
        files = sorted(OUT_DIR.glob("scan_gmail_*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
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

    _latest_web = _latest_web_scan()
    _latest_gm = _latest_gmail_scan()
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

    # --- Last activity block: what happened most recently? ---
    # The single most important piece of info on this page: what ran last,
    # did it work, and what should the user do next.
    _last_pipe = latest_pipeline_status()
    _last_runs = scan_runner.list_runs(limit=5)
    _last_run = _last_runs[0] if _last_runs else None

    # Determine the most recent event (pipeline or background run)
    _last_event_time = None
    _last_event_label = None
    _last_event_state = None
    _last_event_detail = ""
    if _last_pipe:
        t = _last_pipe.get("finished_at") or _last_pipe.get("started_at")
        if t:
            _last_event_time = t
            _last_event_label = f"Pipeline ({_last_pipe.get('pipeline_id', '?')})"
            _last_event_state = _last_pipe.get("state", "?")
            stages = _last_pipe.get("stages") or {}
            parts = []
            if stages.get("scrape", {}).get("candidate_count"):
                parts.append(f"scraped {stages['scrape']['candidate_count']}")
            if stages.get("score", {}).get("scored_count"):
                parts.append(f"scored {stages['score']['scored_count']}")
            if not stages:
                cr = _last_pipe.get("crash_reason") or ""
                if "preflight" in cr.lower() or "api" in cr.lower():
                    parts.append("failed at API preflight — key/credits issue")
                elif cr:
                    parts.append(cr[:100])
                else:
                    parts.append("no stages completed")
            _last_event_detail = " · ".join(parts)

    if _last_run:
        t = _last_run.get("finished_at") or _last_run.get("started_at")
        if t and (not _last_event_time or t > _last_event_time):
            _last_event_time = t
            _last_event_label = _last_run.get("label", "background run")
            _last_event_state = _last_run.get("state", "?")
            _last_event_detail = f"pid {_last_run.get('pid', '?')}"

    # Render last-activity strip
    with st.container(border=True):
        la1, la2, la3 = st.columns([2, 3, 2])
        with la1:
            st.markdown("**Last activity**")
            if _last_event_label:
                _state_icon = {"finished": "✅", "failed": "❌", "running": "🟡",
                               "stale": "⚪", "crashed": "💥", "stopped": "⏹"
                               }.get(_last_event_state or "", "❓")
                st.markdown(f"{_state_icon} **{_last_event_label}**")
                st.caption(f"{_last_event_state} · {fmt_dt(_last_event_time)}")
            else:
                st.caption("No runs recorded yet.")
        with la2:
            if _last_event_detail:
                st.caption(_last_event_detail)
            # Show file names so user knows what's real
            if _latest_web:
                st.caption(f"📁 Scan: `{_latest_web.name}` ({_age_label(_latest_web)})")
            if _latest_scored:
                st.caption(f"📁 Scored: `{_latest_scored.name}` ({_age_label(_latest_scored)})")
        with la3:
            # "What to do next" — the key question
            _scored_matches_scan = False
            if _latest_web and _latest_scored:
                _scored_matches_scan = _latest_web.stem in _latest_scored.name
            _has_real_scores = False
            if _latest_scored:
                try:
                    _sd = json.loads(_latest_scored.read_text(encoding="utf-8"))
                    _has_real_scores = bool(_sd.get("stage2_scored"))
                except Exception:
                    pass

            st.markdown("**Next step**")
            if not _latest_web:
                st.caption("🔴 No scan — run a scrape first")
            elif not _latest_scored or not _scored_matches_scan:
                st.caption(
                    f"🟡 Scan exists but not scored yet. "
                    f"Run scorer on `{_latest_web.name}`"
                )
            elif not _has_real_scores:
                st.caption(
                    "🟡 Only rule-triaged (dry-run) — "
                    "run with API key to get LLM scores"
                )
            elif _last_event_state == "failed":
                st.caption("🔴 Last run failed — check error, fix, re-run")
            else:
                st.caption("🟢 Scan + score complete — review Inspect tab")

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

    # Determine if a scraper is currently running.
    # A "pipeline" job also runs jd_scraper internally, so treat pipeline_running
    # as scraper-active too — otherwise the state shows "paused" while scraping.
    try:
        _scraper_active = pipeline_running or any(
            "jd_scraper" in (r.get("label") or "") or
            "scrape" in (r.get("label") or "") or
            "pipeline" in (r.get("label") or "")
            for r in scan_runner.active_runs()
        )
    except Exception:
        _scraper_active = pipeline_running

    if _ckpt or _pause_requested or _scraper_active:
        with st.container(border=True):
            _section_title = (
                "#### 🟢 Scrape in progress"
                if _scraper_active
                else "#### ⏸ Scrape paused — checkpoint saved"
            )
            st.markdown(_section_title)
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
                _can_resume = bool(_ckpt) and not _scraper_active and not any_work_active
                if st.button("▶ Resume scrape", disabled=not _can_resume,
                              width='stretch', type="primary",
                              key="scrape_resume_btn",
                              help="Launches jd_scraper.py --resume with the "
                                   "same options as the checkpointed run."):
                    opts = (pc.get("options") or {})
                    cmd = [sys.executable, str(ROOT / "automation" / "jd_scraper.py"),
                           "--resume"]
                    # Use the same scrape mode as the original run so the
                    # checkpoint signature matches. Hardcoding --expansion here
                    # caused a signature mismatch that wiped scraped results.
                    _ckpt_mode = opts.get("scrape_mode") or opts.get("mode") or "expansion"
                    cmd.append(f"--scrape-mode={_ckpt_mode}")
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
    # Explain what state the pipeline is in, then show the numbers.
    # The funnel reads from the latest scan file + latest scored file, which
    # may be from DIFFERENT runs. Make that explicit.
    _funnel_scan_name = scan_f.name if scan_f else None
    _funnel_scored_name = scored_f.name if scored_f else None
    _scored_matches_funnel_scan = (
        scan_f and scored_f and scan_f.stem in scored_f.name
    )

    with st.expander(
        f"📊 Pipeline funnel"
        + (f" — `{_funnel_scan_name}`" if _funnel_scan_name else " — no scan")
        + (" ✅ scored" if score_count else
           " ⚠️ not scored" if scan_f else ""),
        expanded=True,
    ):
        # Source attribution so user knows where numbers come from
        if _funnel_scan_name and _funnel_scored_name and not _scored_matches_funnel_scan:
            st.warning(
                f"Numbers below mix two files: scan from `{_funnel_scan_name}` "
                f"but scores from `{_funnel_scored_name}`. "
                f"Run the scorer on your latest scan to unify them.",
                icon="⚠️",
            )

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

        # While a scrape is running the scan file isn't written yet — fall back
        # to the checkpoint's live count so the funnel isn't stuck at 0.
        _ckpt_live = None
        if _scraper_active and _ckpt:
            _ckpt_live = len(_ckpt.get("found", []))
        _scraped_display = scrape_raw if scrape_raw else scrape_count if scrape_count else _ckpt_live
        _scraped_sub = (f"across {len(per_company_diag)} cos" if per_company_diag
                        else f"in progress — {_ckpt.get('completed_count',0)}/{_ckpt.get('total_companies','?')} cos"
                        if _ckpt_live is not None else "")
        _big_number(cols[0], "🛰️", "Scraped", _scraped_display,
                    sub=_scraped_sub)
        # Dedup pass rate
        _dedup_in = scrape_raw or scrape_count or 0
        _dedup_out = scrape_count or 0
        _dedup_pct = (f"{int(100*_dedup_out/_dedup_in)}% kept"
                      if _dedup_in else f"-{(dedup_dropped_url or 0) + (dedup_dropped_near or 0)} dupe"
                      if dedup_dropped_url is not None else "")
        _arrow(cols[1], _dedup_pct)
        _big_number(cols[2], "✂️", "Unique", scrape_count,
                    sub=f"-{dedup_dropped_url} URL, -{dedup_dropped_near} near"
                        if dedup_dropped_url is not None else "")
        # Triage pass rate
        _triage_in = score_input or scrape_count or 0
        _triage_out = score_pass or 0
        _triage_pct = (f"{int(100*_triage_out/_triage_in)}% pass"
                       if _triage_in else f"-{_triage_in - _triage_out} off-profile"
                       if score_input and score_pass else "")
        _arrow(cols[3], _triage_pct)
        _big_number(cols[4], "🎯", "Triaged", score_pass,
                    sub="stage-1 pass" if score_pass else
                        ("not scored yet" if scan_f and not scored_f else ""))
        # Triaged → scored: show coverage rate
        _sc_pct = (f"{int(100*(score_count or 0)/(score_pass or 1))}% LLM-scored"
                   if score_pass else "")
        _arrow(cols[5], _sc_pct or (f"-{(score_pass or 0) - (score_count or 0)} err"
                        if score_pass is not None and score_count is not None and score_pass != score_count else ""))

        # Scored column: explain WHY it's blank if it is
        _scored_sub = ""
        if score_count:
            _scored_sub = f"apply_now:{apply_n} tailor:{tailor_n}"
        elif scored_f and not score_count:
            _scored_sub = "dry-run only (rule-triage, no LLM)"
        elif not scored_f and scan_f:
            _scored_sub = "scorer not run yet"
        _big_number(cols[6], "🤖", "Scored", score_count, sub=_scored_sub)

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

    st.markdown("---")

    # ---------- Main tabs ----------
    # Three tabs: Run (chain + Score-a-URL expander), Inspect (triage
    # funnel + scored drill-down), History. The old per-stage tabs
    # (1·Scrape / 2·Score / 4·Promote) were UI wrappers around CLIs that
    # the Run-chain button already invokes -- collapsed so the user sees
    # one page instead of juggling seven.
    tabs = st.tabs(["🎯 Run", "👁 Inspect", "📜 History", "🕒 Recent Runs"])

    # ================== TAB: Run ==================
    with tabs[0]:
        # --- Quick actions: the 3 things the user actually does ---
        # Buttons FIRST, config SECOND. Most visits to this page are
        # "launch something" or "check what's running". The detailed
        # configuration (scrape strategy, concurrency, etc.) is in an
        # expander below for power-user tuning.
        key_ok_here = api_key.is_key_valid()
        _gmail_ok = gmail_ui.is_connected()
        _can_run = not any_work_active

        # Show a clear blocker banner BEFORE the buttons so user knows why
        # things are disabled, with a direct fix action.
        if not key_ok_here:
            st.error(
                "**🔑 API key missing or invalid** — scoring, tailoring, and "
                "full-refresh all require a working Anthropic key. "
                "Open the **sidebar → Manage Anthropic API key** expander, "
                "paste your `sk-ant-...` key, and hit Save & validate. "
                "Scraping works without a key.",
                icon="🔑",
            )

        st.markdown("#### Quick launch")
        qa1, qa2, qa3, qa4 = st.columns(4)
        with qa1:
            if st.button("🛰 Scrape only", width='stretch',
                         type="primary" if not key_ok_here else "secondary",
                         disabled=not _can_run,
                         help="Core 77 targets, no API key needed. ~15-30 min. "
                              "Writes scan_<date>.json."):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--scrape-mode", "core", "--skip-score", "--skip-promote",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Core scrape"}
                st.toast("🛰 Core scrape launched!", icon="🚀")
                st.rerun()
        with qa2:
            _score_label = "🤖 Score latest scan" if scan_f else "🤖 Score (no scan)"
            if st.button(_score_label, width='stretch',
                         type="primary" if (key_ok_here and scan_f) else "secondary",
                         disabled=(not _can_run or not key_ok_here or not scan_f),
                         help=f"Run the LLM scorer on `{scan_f.name if scan_f else '?'}`. "
                              f"~5-15 min, costs ~$0.10-0.30. Requires API key."):
                rec = scan_runner.start_run("pipeline", [
                    sys.executable, str(ROOT / "automation" / "run_pipeline.py"),
                    "--skip-scrape", "--skip-promote",
                    "--score-concurrency", "6",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Score latest scan"}
                st.toast("🤖 Scorer launched!", icon="🚀")
                st.rerun()
        with qa3:
            if st.button("📬 Gmail alerts", width='stretch',
                         disabled=(not _gmail_ok or not _can_run),
                         help="Pull LinkedIn/Indeed alert emails (14d). ~10s, free."):
                rec = scan_runner.start_run("gmail_fetch", [
                    sys.executable,
                    str(ROOT / "automation" / "gmail_fetch.py"), "--days", "14",
                ])
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Gmail fetch"}
                st.toast("📬 Gmail fetch launched!", icon="🚀")
                st.rerun()
            if not _gmail_ok:
                st.caption("🔌 Connect Gmail in sidebar")
        with qa4:
            if st.button("🌅 Full refresh", width='stretch',
                         disabled=(not key_ok_here or not _can_run),
                         help="Scrape + score new roles + morning brief. "
                              "~25 min, ~$0.03. Requires API key."):
                nightly_cmd_list = [sys.executable, str(ROOT / "automation" / "nightly_refresh.py")]
                rec = scan_runner.start_run("nightly_refresh", nightly_cmd_list)
                st.session_state["_last_launch"] = {"run_id": rec.run_id, "label": "Full refresh"}
                st.toast("🌅 Full refresh launched!", icon="🚀")
                st.rerun()

        # Stop button — shown whenever any job is active (all launch buttons are
        # disabled then, so this is the only way the user can unblock).
        if any_work_active and active_runs:
            _stop_run = active_runs[0]
            st.warning(
                f"⏳ **{_stop_run.get('label', 'job')}** is running "
                f"({human_elapsed(_stop_run.get('started_at'))}) — "
                "launch buttons are disabled until it finishes.",
                icon="⚠️",
            )
            if st.button("⏹ Stop running job", type="primary", key="ql_stop_btn"):
                scan_runner.stop_run(_stop_run["run_id"])
                st.warning("⏹ Stop signal sent — job will exit after the current step.")
                st.rerun()

        # --- Live progress panel (fragment or fallback) ---
        # _pipeline_live_panel() is defined before this page block and is
        # decorated with @st.fragment(run_every=3) when Streamlit ≥1.33.
        # With fragments: only this widget refreshes — zero full-page flash.
        # Without fragments: page-wide autorefresh handles the 5s polling.
        _pipeline_live_panel()

        # Gmail trash cleanup panel — only renders when there's an
        # un-trashed scan_gmail_*.json. Same widget as the Dashboard,
        # surfaced here too so users running the Gmail fetch from the
        # Pipeline page see the prompt without bouncing back to home.
        render_gmail_trash_panel()

        # --- Recent runs: what actually happened ---
        st.markdown("---")
        st.markdown("#### Recent runs")
        _recent_runs = scan_runner.list_runs(limit=5)
        if _recent_runs:
            _rr_rows = []
            for _rr in _recent_runs:
                _rr_icon = {"running": "🟡", "finished": "✅",
                            "failed": "❌", "stopped": "⏹"}.get(
                            _rr.get("state", ""), "❓")
                _rr_rows.append({
                    "": _rr_icon,
                    "run": _rr.get("label", "?"),
                    "state": _rr.get("state", "?"),
                    "started": fmt_dt(_rr.get("started_at")),
                    "duration": human_elapsed(_rr.get("started_at"), _rr.get("finished_at")),
                })
            st.dataframe(pd.DataFrame(_rr_rows), hide_index=True, width='stretch',
                         height=min(220, 40 + 36 * len(_rr_rows)))
        else:
            st.caption("No runs recorded. Launch something above.")

        # --- Advanced config (collapsed by default) ---
        st.markdown("---")
        with st.expander("⚙️ Advanced pipeline configuration", expanded=False):
            st.caption("Fine-tune scrape strategy, scorer settings, and promote options.")
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

            needs_llm = not skip_score or not skip_promote
            can_run_adv = not pipeline_running and (key_ok_here or not needs_llm)
            if needs_llm and not key_ok_here:
                st.warning(
                    "This run will call the Anthropic API. Set a valid key in the sidebar, "
                    "or tick Skip score + Skip promote for scrape-only.",
                    icon="🔑",
                )
            if st.button("▶️ Launch custom pipeline", type="primary",
                         width='stretch', disabled=not can_run_adv,
                         key="adv_launch_pipe"):
                rec = scan_runner.start_run("pipeline", cmd)
                st.success(f"Pipeline launched (`{rec.run_id}`, pid {rec.pid})")
                st.rerun()

        # ---------- Score a single URL (expander inside Run tab) ----------
        # Kept from the old tabs[1]. Paste any URL → fresh LLM fit score.
        st.markdown("---")
        with st.expander("🔗 Score a single URL (ad-hoc, no scan needed)",
                          expanded=False):
            st.caption(
                "Paste any job URL (jobs.citi.com, OSFI careers, company "
                "career site, even a LinkedIn you found outside the scan) "
                "and get a fresh LLM fit score against your Master "
                "Repository. Takes ~5s and costs ~$0.001."
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

    # ================== TAB: Inspect ==================
    with tabs[1]:
        st.subheader("Inspect the scoring funnel")
        st.caption("What was scraped, what got dropped at rule-triage, "
                   "what Claude actually scored. Three sub-tabs below.")

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
                by_co_df = pd.DataFrame(by_co)
                if "scraped" in by_co_df.columns:
                    by_co_df = by_co_df.sort_values("scraped", ascending=False)
                st.dataframe(by_co_df, hide_index=True, width='stretch', height=500)

    # ================== TAB: History ==================
    with tabs[2]:
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

    # ================== TAB: Recent Runs ==================
    # Polished "what just happened" view: last 20 pipelines with state
    # badge, wall time, per-stage line, total cost, and a JSON expander
    # per run. Complements the dataframe-style History tab above with
    # something more glanceable. Robust to old/half-written status JSONs
    # — every field uses .get() with sensible defaults.
    with tabs[3]:
        st.subheader("🕒 Recent Pipeline Runs")
        _runs = list_pipelines(20)
        if not _runs:
            st.info("No pipeline runs yet. Hit **Run pipeline** to start one.")
        else:
            _badge = {"finished": "✅ finished", "failed": "❌ failed",
                      "crashed": "💥 crashed", "running": "🔄 running",
                      "stale": "⚪ stale", "stopped": "⏹ stopped"}
            _n = len(_runs)
            _ok = sum(1 for r in _runs if r.get("state") == "finished")
            _bad = sum(1 for r in _runs
                       if r.get("state") in ("failed", "crashed", "stale"))
            _costs = [r.get("total_cost") or r.get("cost_usd") or 0.0
                      for r in _runs]
            _costs = [c for c in _costs if isinstance(c, (int, float)) and c > 0]
            _avg_cost = (sum(_costs) / len(_costs)) if _costs else 0.0

            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("Runs", _n)
            kc2.metric("Successful", _ok)
            kc3.metric("Failed/crashed", _bad)
            kc4.metric("Avg cost", f"${_avg_cost:.2f}" if _avg_cost else "—")
            st.markdown("---")

            for _r in _runs:
                _pid = _r.get("pipeline_id") or _r.get("id") or "?"
                _state = _r.get("state") or "?"
                _stages = _r.get("stages") or {}
                _started = _r.get("started_at")
                _finished = _r.get("finished_at")
                _wall = human_elapsed(_started, _finished)
                _parts = []
                for _name in ("scrape", "score", "promote", "tailor"):
                    _s = _stages.get(_name) or {}
                    _ss = _s.get("state", "—")
                    if _ss == "skipped":
                        _parts.append(f"{_name}: skipped")
                    elif _s.get("elapsed_sec") is not None:
                        _parts.append(f"{_name}: {int(_s['elapsed_sec'])}s")
                    elif _ss != "—":
                        _parts.append(f"{_name}: {_ss}")
                _stage_line = " · ".join(_parts) if _parts else "no stages recorded"
                _cost = _r.get("total_cost") or _r.get("cost_usd") or 0.0
                _cost_str = f" · ${_cost:.2f}" if isinstance(_cost, (int, float)) and _cost > 0 else ""

                with st.container(border=True):
                    rc1, rc2, rc3 = st.columns([3, 4, 2])
                    rc1.markdown(
                        f"**{fmt_dt(_started)}**  \n"
                        f"{_badge.get(_state, _state)} · `{_pid}`"
                    )
                    rc2.caption(f"⏱ {_wall}{_cost_str}")
                    rc2.caption(_stage_line)
                    with rc3:
                        with st.expander("View details"):
                            _scrape_f = (_stages.get("scrape") or {}).get("scan_file")
                            _score_f = (_stages.get("score") or {}).get("scored_file")
                            _prom_f = (_stages.get("promote") or {}).get("promote_report")
                            for _label, _val in (("scan", _scrape_f),
                                                 ("scored", _score_f),
                                                 ("promote_report", _prom_f)):
                                if _val:
                                    st.caption(f"📁 {_label}: `{_val}`")
                            st.json(_r, expanded=False)


# ============================================================================
# 📋 JOBS KANBAN
# ============================================================================
elif page == "📋 Jobs Kanban":
    st.title("📋 Jobs Tracker")

    # ── Kanban summary strip ──────────────────────────────────────────────────
    _kan_statuses = {}
    _STATUS_ORDER = [
        ("Found","🔍"), ("Watch","👀"), ("Tailoring","✍️"), ("Applied","📤"),
        ("Recruiter_Screen","📞"), ("Phone_Screen","📱"), ("Take_Home","💻"),
        ("Onsite","🏢"), ("Offer","🎉"), ("Rejected","❌"), ("Withdrawn","⚪"),
    ]
    for _jj in jobs:
        _ss = _jj.get("status", "?")
        _kan_statuses[_ss] = _kan_statuses.get(_ss, 0) + 1
    _active_stages = [s for s, _ in _STATUS_ORDER if s in _kan_statuses]
    if _active_stages:
        _ks_cols = st.columns(min(len(_active_stages), 8))
        for _kci, (_ks, _ke) in enumerate([(s, e) for s, e in _STATUS_ORDER if s in _kan_statuses]):
            _kci_mod = _kci % 8
            _ks_cols[_kci_mod].metric(f"{_ke} {_ks.replace('_', ' ')}", _kan_statuses[_ks])
    st.caption("Your promoted-to-tracker roles — update status, add notes, launch tailor.")
    st.markdown("---")

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

    # Provenance badge: rows promoted from a Gmail-alert scan get a 📬
    # marker so it's visible at a glance which leads came from inbox
    # alerts vs. scraped postings. auto_promote.py preserves the original
    # gmail_* source as a "<source>+fit_scorer" composite.
    if "source" in view.columns:
        view = view.assign(
            src=view["source"].apply(
                lambda s: "📬" if isinstance(s, str) and s.startswith("gmail_") else ""
            )
        )

    cols = [c for c in ["id", "draft", "freshness", "src", "company", "title", "gta_area",
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
                # ── Header with tier badge ──────────────────────────────────
                _tier_colors = {1: "#10b981", 2: "#3b82f6", 3: "#f59e0b", 4: "#6b7280"}
                _job_tier = int(job.get("tier") or 4)
                _tier_color = _tier_colors.get(_job_tier, "#6b7280")
                _fit_num = int(job.get("fit_score_numeric") or 0)
                _score_color = "#10b981" if _fit_num >= 8 else "#f59e0b" if _fit_num >= 6 else "#ef4444" if _fit_num > 0 else "#6b7280"
                st.markdown(
                    f"<div style='margin-bottom:6px'>"
                    f"<span style='font-size:1.1em;font-weight:700'>{job['company']} — {job['title']}</span>"
                    f"<span style='margin-left:8px;padding:2px 8px;border-radius:10px;"
                    f"background:{_tier_color}22;color:{_tier_color};"
                    f"font-size:0.78em;font-weight:700'>T{_job_tier}</span>"
                    f"<span style='margin-left:4px;padding:2px 8px;border-radius:10px;"
                    f"background:{_score_color}22;color:{_score_color};"
                    f"font-size:0.78em;font-weight:700'>{_fit_num}/10</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                variants = job.get("resume_variants") or ([job["primary_variant"]]
                    if job.get("primary_variant") else [])
                variant_str = " · ".join(variants) if variants else "—"
                st.caption(
                    f"{job.get('sector')} · {job.get('status','?')} · "
                    f"fit {job.get('fit_score')} · 📄 {variant_str}"
                )
                _jurl = job.get('url', '')
                if _jurl:
                    st.link_button("🔗 Open posting", _jurl)
                _fit_notes = job.get("fit_notes", "")
                if _fit_notes:
                    with st.expander("📊 Fit notes", expanded=False):
                        st.write(_fit_notes)
                _nxt = job.get("next_action") or ""
                if _nxt:
                    st.info(f"**Next action:** {_nxt}", icon="🎯")
                # ── Outreach / activity timeline ───────────────────────────
                _olog = job.get("outreach_log") or []
                _fsched = job.get("followup_schedule") or {}
                _date_app = parse_date(job.get("date_applied"))
                _date_found = parse_date(job.get("date_found"))
                _timeline_events = []
                if _date_found:
                    _timeline_events.append((_date_found, "🔍", "Found"))
                if _date_app:
                    _timeline_events.append((_date_app, "📤", "Applied"))
                for _oe in _olog:
                    _ed = parse_date(_oe.get("date"))
                    if _ed:
                        _ekind = _oe.get("kind") or _oe.get("channel") or "message"
                        _timeline_events.append((_ed, "📨", f"Outreach: {_ekind}"))
                _next_due = parse_date(_fsched.get("next_due"))
                if _next_due:
                    _overdue = _next_due < date.today()
                    _fu_icon = "🔴" if _overdue else "🔔"
                    _timeline_events.append((_next_due, _fu_icon,
                        f"Follow-up {'OVERDUE' if _overdue else 'due'}"))
                if _timeline_events:
                    _timeline_events.sort(key=lambda x: x[0])
                    with st.expander("🕐 Activity timeline", expanded=bool(_olog or _date_app)):
                        for _td, _ti, _tl in _timeline_events:
                            _is_future = _td > date.today()
                            _style = "opacity:0.55;" if _is_future else ""
                            st.markdown(
                                f"<div style='display:flex;gap:8px;padding:4px 0;{_style}'>"
                                f"<span style='font-size:1em'>{_ti}</span>"
                                f"<span style='font-size:0.82em;opacity:0.7;min-width:80px'>"
                                f"{_td.strftime('%b %d')}</span>"
                                f"<span style='font-size:0.88em'>{_tl}</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

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
            # ── Quick-log row: mark any recruiter as contacted today ─────────
            with st.expander("⚡ Quick-log: mark contacted today", expanded=False):
                _quick_ids = [r["id"] for r in recs
                               if r.get("status") in ("Not_Contacted", "Outreach_Sent", "Active")]
                if _quick_ids:
                    _qlog_pick = st.selectbox("Recruiter", _quick_ids, key="crm_qlog_pick")
                    _qlog_note = st.text_input("Note (optional)", key="crm_qlog_note",
                                               placeholder="LinkedIn DM / email / call …")
                    if st.button("✅ Log as contacted today", key="crm_qlog_btn", type="primary"):
                        for _rx in crm.get("recruiters", []):
                            if _rx["id"] == _qlog_pick:
                                _rx["last_touchpoint"] = date.today().isoformat()
                                if _rx.get("status") == "Not_Contacted":
                                    _rx["status"] = "Outreach_Sent"
                                break
                        crm.setdefault("outreach_log", []).append({
                            "date": date.today().isoformat(),
                            "contact_id": _qlog_pick,
                            "note": _qlog_note,
                            "channel": "manual",
                        })
                        save_crm(crm)
                        st.success(f"Logged contact with {_qlog_pick} today.")
                        st.rerun()
                else:
                    st.caption("All recruiters already contacted. 🎉")
            sel = st.selectbox("Pick firm id to inspect/edit", rdf["id"].tolist())
            r = next((x for x in recs if x["id"] == sel), None)
            if r:
                # Status pill
                _crm_s_colors = {
                    "Not_Contacted": "#6b7280", "Outreach_Sent": "#3b82f6",
                    "Active": "#10b981", "Paused": "#f59e0b", "Closed": "#ef4444",
                }
                _crm_sc = _crm_s_colors.get(r.get("status",""), "#6b7280")
                _crm_pri_colors = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#6b7280"}
                _crm_pc = _crm_pri_colors.get(r.get("priority",""), "#6b7280")
                st.markdown(
                    f"<div style='margin:6px 0'>"
                    f"<span style='font-size:1.1em;font-weight:700'>{r['firm']}</span>"
                    f"<span style='margin-left:8px;padding:2px 10px;border-radius:10px;"
                    f"background:{_crm_sc}22;color:{_crm_sc};font-size:0.8em;font-weight:600'>"
                    f"{r.get('status','?')}</span>"
                    f"<span style='margin-left:4px;padding:2px 10px;border-radius:10px;"
                    f"background:{_crm_pc}22;color:{_crm_pc};font-size:0.8em;font-weight:600'>"
                    f"{r.get('priority','?')}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.caption(f"{r.get('firm_type')} · {r.get('location')} · Last touch: {r.get('last_touchpoint','never')}")
                if r.get("notes"):
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

    t_crit, t_repo, t_linkedin, t_engagement, t_campaign = st.tabs([
        "🎯 Targeting Criteria",
        "📚 Master Repository",
        "📅 LinkedIn Calendar",
        "📋 Engagement Log",
        "🧠 Campaign Memory",
    ])

    # ── Tab 1: Targeting Criteria ────────────────────────────────────────────
    with t_crit:
        st.markdown("### 🎯 Role Targeting Criteria")
        st.caption("Live rules governing which roles to pursue, how to angle the application, and where to direct outreach energy.")

        # ── Key identity tags — the 6 phrases that open doors ────────────────
        _tags = [
            ("ALM / IRRBB", "#3b82f6"),
            ("Model Risk & Governance", "#6366f1"),
            ("Balance Sheet Analytics", "#0891b2"),
            ("Stochastic Scenario Engine", "#0284c7"),
            ("Institutional Platform Delivery", "#7c3aed"),
            ("Director / VP level", "#059669"),
        ]
        _tag_html = "".join(
            f"<span style='display:inline-block;padding:4px 12px;margin:3px 4px;"
            f"border-radius:14px;background:{c}20;border:1px solid {c}55;"
            f"color:{c};font-size:0.82em;font-weight:600'>{t}</span>"
            for t, c in _tags
        )
        st.markdown(
            f"<div style='margin:4px 0 12px 0'>{_tag_html}</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        crit_col1, crit_col2 = st.columns([1, 1], gap="large")

        with crit_col1:
            st.markdown("#### 🔵 PRIMARY Lane — ALM / IRRBB / Model Governance")
            st.markdown(
                "**Best-fit titles:**  \n"
                "Director — ALM & Balance Sheet Risk  \n"
                "Director — IRRBB Modelling  \n"
                "Senior Manager / Director — Model Risk & Validation  \n"
                "Head of ALM Analytics  \n"
                "Director — Treasury Risk  \n"
                "VP — Balance Sheet Risk"
            )
            st.markdown(
                "**Evidence stack:**  \n"
                "• Sign-off authority on multi-asset institutional portfolios (Moody's)  \n"
                "• Cash flow projection engine design & delivery (Moody's)  \n"
                "• IRRBB-analogous shock analytics & curve calibration (Moody's)  \n"
                "• LDI and stochastic scenario generators (Ortec)  \n"
                "• Model governance framework operation (Moody's)"
            )
            st.info(
                "**Target employers:** Scotiabank · RBC · BMO · CIBC · TD · National Bank · Equitable Bank  \n"
                "CPP · OTPP · OMERS · HOOPP · PSP · OPTrust · CAAT · IMCO  \n"
                "Manulife · Sun Life · Canada Life · Intact · iA · RGA"
            )

            st.markdown("#### 🟡 SECONDARY Lane — Vendor-Platform / Client Solutions")
            st.markdown(
                "**Best-fit titles:**  \n"
                "Director — Aladdin Client Engagement  \n"
                "Senior Analytics Specialist  \n"
                "Director — Risk Solutions  \n"
                "Product Manager (Risk/ALM platforms)  \n"
                "Director — Client Advisory"
            )
            st.markdown(
                "**Evidence stack:**  \n"
                "• Institutional platform delivery at Moody's (direct parallel to Aladdin, S&P, MSCI)  \n"
                "• Calypso → PFaroe migration leadership  \n"
                "• Client-translation across investment teams and dev  \n"
                "• Agentic-AI workflow design (Claude Code, Cursor)"
            )
            st.info(
                "**Target employers:** BlackRock (Aladdin) · Bloomberg · MSCI · S&P Global  \n"
                "FactSet · Morningstar DBRS · SS&C Algorithmics · Numerix · Prometeia"
            )

        with crit_col2:
            st.markdown("#### 💰 Compensation Targets")
            comp_data = [
                {"Band": "Director / VP — Big 6 Banks", "Base (CAD)": "$195–260K", "Total Comp": "$300–420K"},
                {"Band": "Director — Maple 8 Pension", "Base (CAD)": "$200–310K", "Total Comp": "$320–500K"},
                {"Band": "Director — US/Global AM", "Base (CAD)": "$195–310K", "Total Comp": "$330–550K"},
                {"Band": "Director — Vendor (Bloomberg, MSCI)", "Base (CAD)": "$175–250K", "Total Comp": "$260–400K"},
                {"Band": "Sr. Manager — Insurer / Mid-bank", "Base (CAD)": "$165–230K", "Total Comp": "$220–310K"},
                {"Band": "Sr. Manager — Big 4 Risk Advisory", "Base (CAD)": "$170–230K", "Total Comp": "$220–300K"},
            ]
            st.dataframe(pd.DataFrame(comp_data), hide_index=True, width="stretch")
            st.caption("Floor: $160K base for Sr. Manager. Negotiate off **total comp**, not base alone.")

            st.markdown("#### 🏛️ Active OSFI Regulatory Hooks")
            osfi_hooks = [
                ("E-23 Model Risk Management", "Effective 2027-05-01", "🔴 High"),
                ("B-12 IRRBB Revision", "Q1 2026 consultations", "🔴 High"),
                ("LAR 2026 Liquidity Adequacy", "2026 deadline", "🟡 Medium"),
                ("IFRS 17 (insurers)", "Ongoing", "🟡 Medium"),
                ("IFRS 9 ECL (banks)", "Ongoing", "🟡 Medium"),
            ]
            for hook, timeline, urgency in osfi_hooks:
                st.markdown(f"{urgency} **{hook}** — {timeline}")

            st.markdown("#### 📐 Application Rules")
            st.markdown(
                "✅ **Warm intros over cold** for Director+ roles — ~70% referral-driven in Toronto finance  \n"
                "✅ Open every Big 6 / pension cover letter with a **concrete capability tied to the team**, not generic regulatory framing  \n"
                "✅ Open every vendor cover letter with the **platform practitioner hook** (know your buyers)  \n"
                "✅ Confirm work authorization wording **before first application**  \n"
                "🚫 Do not self-describe as '8+ years' or '10+ years' — **~7 years** is correct  \n"
                "🚫 Do not actively search retired angles (PM, Portfolio Manager, Project Mgr) — ad-hoc only"
            )

            st.markdown("#### 📋 Weekly KPI Targets")
            kpi_col1, kpi_col2, kpi_col3 = st.columns(3)
            try:
                _tracker_kpi = json.loads((ROOT / "data" / "job_tracker_data.json").read_text(encoding="utf-8"))
                _kpis = _tracker_kpi.get("meta", {}).get("weekly_kpi_targets", {})
                kpi_col1.metric("Applications / wk", _kpis.get("tailored_applications", 8))
                kpi_col2.metric("Outreach / wk", _kpis.get("outreach_messages", 10))
                kpi_col3.metric("Coffees / wk", _kpis.get("coffee_chats", 3))
            except Exception:
                kpi_col1.metric("Applications / wk", 8)
                kpi_col2.metric("Outreach / wk", 10)
                kpi_col3.metric("Coffees / wk", 3)

    # ── Tab 2: Master Repository ─────────────────────────────────────────────
    with t_repo:
        _repo_path = ROOT / "docs" / "Saber_Ayatollahi_Master_Repository.md"
        if not _repo_path.exists():
            st.warning("Master repository not found at `docs/Saber_Ayatollahi_Master_Repository.md`.")
        else:
            _repo_text = _repo_path.read_text(encoding="utf-8")

            # Quick-nav section links
            _sections = [
                ("1. Identity & Contact", "## 1. IDENTITY"),
                ("2. Education", "## 2. EDUCATION"),
                ("3. Experience", "## 3. PROFESSIONAL"),
                ("4. Skills", "## 4. SKILLS"),
                ("5. Bullet Library", "## 5. TAGGED"),
                ("6. STAR Stories", "## 6. STAR"),
                ("7. Positioning", "## 7. TARGET"),
                ("8. Summary Bank", "## 8. SUMMARY"),
                ("9. Logistics", "## 9. LOGISTICS"),
                ("10. Resume Variants", "## 10. RESUME"),
                ("11. Strategy", "## 11. JOB-SEARCH"),
            ]

            st.caption(f"Source: `{_repo_path.relative_to(ROOT)}` · {len(_repo_text.split(chr(10)))} lines · Last modified: {datetime.fromtimestamp(_repo_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}")

            # Section filter
            _sec_names = ["(full document)"] + [s[0] for s in _sections]
            _picked_sec = st.selectbox("Jump to section", _sec_names, key="repo_section_jump")

            if _picked_sec == "(full document)":
                _display_text = _repo_text
            else:
                # Find the matching section header in the text
                _sec_marker = next((s[1] for s in _sections if s[0] == _picked_sec), None)
                if _sec_marker:
                    _sec_idx = _repo_text.find(_sec_marker)
                    # Find next top-level section
                    _next_sec_idx = len(_repo_text)
                    for _, _m in _sections:
                        _ni = _repo_text.find(_m, _sec_idx + 10)
                        if _ni > _sec_idx and _ni < _next_sec_idx:
                            _next_sec_idx = _ni
                    _display_text = _repo_text[_sec_idx:_next_sec_idx]
                else:
                    _display_text = _repo_text

            # Search filter — with ±2 lines of context
            _repo_search = st.text_input("🔍 Search in repository", key="repo_search",
                                          placeholder="e.g. IRRBB, cash flow, sign-off")
            if _repo_search:
                _lines = _display_text.split("\n")
                _q_lo = _repo_search.lower()
                _hit_indices = [i for i, l in enumerate(_lines) if _q_lo in l.lower()]
                if _hit_indices:
                    # Collapse overlapping context windows into contiguous blocks
                    _ctx = 2
                    _blocks = []
                    _cur_start = _cur_end = None
                    for _hi in _hit_indices:
                        _ws = max(0, _hi - _ctx)
                        _we = min(len(_lines) - 1, _hi + _ctx)
                        if _cur_start is None:
                            _cur_start, _cur_end = _ws, _we
                        elif _ws <= _cur_end + 1:
                            _cur_end = max(_cur_end, _we)
                        else:
                            _blocks.append((_cur_start, _cur_end, _hit_indices))
                            _cur_start, _cur_end = _ws, _we
                    if _cur_start is not None:
                        _blocks.append((_cur_start, _cur_end, _hit_indices))
                    st.success(f"Found **{len(_hit_indices)}** match(es) across {len(_blocks)} block(s):")
                    _shown = 0
                    for _bs, _be, _ in _blocks[:8]:
                        _block_lines = []
                        for _li in range(_bs, _be + 1):
                            _ll = _lines[_li]
                            if _q_lo in _ll.lower():
                                _block_lines.append(f"▶ {_ll}")
                            else:
                                _block_lines.append(f"  {_ll}")
                            _shown += 1
                        st.code("\n".join(_block_lines), language="markdown")
                    if len(_blocks) > 8:
                        st.caption(f"… +{len(_blocks)-8} more context blocks")
                else:
                    st.warning(f"No matches for '{_repo_search}' in {'this section' if _picked_sec != '(full document)' else 'the repository'}")

            with st.expander("📄 Repository Content", expanded=(_picked_sec != "(full document)")):
                st.markdown(_display_text)

    # ── Tab 3: LinkedIn Calendar ─────────────────────────────────────────────
    with t_linkedin:
        p = ROOT / "docs" / "linkedin_content_engine.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no linkedin_content_engine.md)_")

    # ── Tab 4: Engagement Log ────────────────────────────────────────────────
    with t_engagement:
        p = ROOT / "docs" / "linkedin_engagement_log.md"
        st.markdown(p.read_text(encoding="utf-8") if p.exists() else "_(no linkedin_engagement_log.md)_")

    # ── Tab 5: Campaign Memory ───────────────────────────────────────────────
    with t_campaign:
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

    # Quick-jump notice for month-end
    _admin_data_file = ROOT / "data" / "job_tracker_data.json"
    _admin_archive_dir = ROOT / "data" / "archives"
    _admin_tracker_jobs = 0
    try:
        _admin_tracker_jobs = len(json.loads(_admin_data_file.read_text(encoding="utf-8")).get("jobs", []))
    except Exception:
        pass
    _admin_archives = list(_admin_archive_dir.glob("job_tracker_*.json")) if _admin_archive_dir.exists() else []

    _admin_a1, _admin_a2 = st.columns([3, 1])
    with _admin_a1:
        st.info(
            f"**Month-end reset:** {_admin_tracker_jobs} jobs in live tracker · "
            f"{len(_admin_archives)} archive(s) on disk. "
            "Use **🗄️ Month-End Archive & Reset** below to archive and start fresh.",
            icon="🗄️",
        )
    with _admin_a2:
        if st.button("🗄️ Jump to Reset", width="stretch", key="admin_jump_reset"):
            st.markdown('<a href="#month-end-archive-reset" style="display:none"></a>',
                        unsafe_allow_html=True)
            st.toast("Scroll down to 🗄️ Month-End Archive & Reset section.", icon="📢")

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

    # ---------- Weekly Maintenance ----------
    st.subheader("📅 Weekly Maintenance")
    st.caption(
        "Run these once a week to keep the search fresh. "
        "The nightly refresh does the URL rotation automatically, but you can "
        "trigger it manually here too."
    )

    _url_hist_path = OUT_DIR / "url_history.json"
    _url_archives  = sorted(OUT_DIR.glob("url_history_*.json"), reverse=True)

    # --- Metrics row ---
    wm_c1, wm_c2, wm_c3, wm_c4 = st.columns(4)

    if _url_hist_path.exists():
        _uh_age_s   = datetime.now().timestamp() - _url_hist_path.stat().st_mtime
        _uh_age_d   = _uh_age_s / 86400
        _uh_size_kb = _url_hist_path.stat().st_size / 1024
        try:
            _uh_count = len(json.loads(_url_hist_path.read_text(encoding="utf-8")))
        except Exception:
            _uh_count = "?"
        _uh_age_label = f"{_uh_age_d:.1f}d"
        _uh_delta     = ("🟢 fresh" if _uh_age_d < 3
                         else "🟡 aging" if _uh_age_d < 7
                         else "🔴 stale — rotate!")
        wm_c1.metric("URL history age", _uh_age_label, _uh_delta)
        wm_c2.metric("Seen URLs", f"{_uh_count:,}" if isinstance(_uh_count, int) else _uh_count)
        wm_c3.metric("History size", f"{_uh_size_kb:.0f} KB")
        wm_c4.metric("Archives on disk", len(_url_archives))
    else:
        wm_c1.metric("URL history age", "—")
        wm_c2.metric("Seen URLs", "—")
        wm_c3.metric("History size", "—")
        wm_c4.metric("Archives on disk", len(_url_archives))
        st.info("No url_history.json yet — it will be created on the first scrape.")

    st.markdown("")  # breathing room

    wm_btn_col, wm_info_col = st.columns([1, 3])

    with wm_btn_col:
        _rotate_disabled = bool(any_work_active) or not _url_hist_path.exists()
        if st.button("🔄 Rotate URL history now",
                     width='stretch',
                     disabled=_rotate_disabled,
                     help=("Rotates url_history.json immediately — same logic as "
                           "the auto-rotation in nightly refresh (archives the old "
                           "file, fresh db for next scrape).")):
            # Perform the rotation inline (same logic as nightly_refresh.py)
            try:
                _uh_age_s2  = datetime.now().timestamp() - _url_hist_path.stat().st_mtime
                _stamp      = datetime.now().strftime("%Y%m%d_%H%M%S")
                _archive    = _url_hist_path.with_name(f"url_history_{_stamp}.json")
                _url_hist_path.rename(_archive)
                st.success(
                    f"✅ Rotated! `url_history.json` → `{_archive.name}` "
                    f"({_uh_age_s2/86400:.1f}d old). "
                    "Next nightly refresh starts with a clean dedup database."
                )
                st.rerun()
            except Exception as _re:
                st.error(f"Rotation failed: {_re}")

    with wm_info_col:
        if _url_hist_path.exists():
            if _uh_age_d >= 7:
                st.warning(
                    "⚠️ URL history is **stale** (≥7 days). "
                    "Old job links are being filtered out of every scrape. "
                    "Rotate now — or run nightly refresh (it auto-rotates)."
                )
            elif _uh_age_d >= 3:
                st.info(
                    "🟡 URL history is aging. Nightly refresh will rotate it "
                    "automatically when it hits 7 days."
                )
            else:
                st.success("🟢 URL history is fresh — no action needed.")
        if _rotate_disabled and any_work_active:
            st.caption("⏳ Button available when no jobs are running.")

    # --- Old run logs cleanup ---
    st.markdown("")
    _runs_dir  = OUT_DIR / "runs"
    _old_logs  = []
    if _runs_dir.exists():
        _cutoff = datetime.now().timestamp() - 7 * 86400
        _old_logs = [p for p in _runs_dir.glob("*.log")
                     if p.stat().st_mtime < _cutoff]
    _total_log_kb = sum(p.stat().st_size for p in _old_logs) / 1024 if _old_logs else 0

    with st.expander(
        f"🧹 Old run logs — {len(_old_logs)} logs older than 7d "
        f"({_total_log_kb:.0f} KB)",
        expanded=False,
    ):
        if not _old_logs:
            st.success("No old run logs to clean up.")
        else:
            st.caption(
                f"These {len(_old_logs)} log files are >7 days old and safe to delete. "
                "JSON status files are kept so run history remains intact."
            )
            _log_rows = [{
                "file": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "age_days": round((datetime.now().timestamp() - p.stat().st_mtime) / 86400, 1),
            } for p in sorted(_old_logs, key=lambda x: x.stat().st_mtime)]
            st.dataframe(pd.DataFrame(_log_rows), hide_index=True, use_container_width=True)

            if st.button(
                f"🗑 Delete {len(_old_logs)} old log files ({_total_log_kb:.0f} KB)",
                type="secondary",
                key="wm_delete_old_logs",
            ):
                _errs = []
                for _lp in _old_logs:
                    try:
                        _lp.unlink()
                    except Exception as _le:
                        _errs.append(f"{_lp.name}: {_le}")
                if _errs:
                    st.error("Some files could not be deleted:\n" + "\n".join(_errs))
                else:
                    st.success(f"✅ Deleted {len(_old_logs)} old log files.")
                st.rerun()


    # ---------- Month-End Archive & Reset ----------
    st.subheader("🗄️ Month-End Archive & Reset")
    st.caption(
        "At the end of each search month, archive your full tracker to a dated snapshot "
        "and start fresh. All active jobs, outreach history, and follow-up schedules are "
        "preserved in the archive — the live tracker resets to zero new leads."
    )

    _data_file = ROOT / "data" / "job_tracker_data.json"
    _archive_dir = ROOT / "data" / "archives"
    _url_hist = ROOT / "automation" / "url_history.json"
    _now = datetime.now()
    _archive_month = _now.strftime("%Y%m")
    _archive_name = f"job_tracker_{_archive_month}.json"
    _archive_path = _archive_dir / _archive_name

    # Load current tracker for preview
    try:
        _tracker_raw = json.loads(_data_file.read_text(encoding="utf-8")) if _data_file.exists() else {}
        _all_jobs = _tracker_raw.get("jobs", [])
        _meta = _tracker_raw.get("meta", {})
        _applied_jobs  = [j for j in _all_jobs if j.get("status") in ("Applied","Recruiter_Screen","Phone_Screen","Take_Home","Onsite","Offer")]
        _active_jobs   = [j for j in _all_jobs if j.get("status") in ("Found","JD_Verified","Tailoring","Watch")]
        _closed_jobs   = [j for j in _all_jobs if j.get("status") in ("Rejected","Ghosted","Withdrawn","Expired")]
        _tracker_ok = True
    except Exception as _te:
        _tracker_ok = False
        _all_jobs = []; _applied_jobs = []; _active_jobs = []; _closed_jobs = []
        _meta = {}

    # Status banner
    if _archive_path.exists():
        st.info(f"📋 Archive **{_archive_name}** already exists in `data/archives/`. Running again will overwrite it.")

    # Preview columns
    me_col1, me_col2, me_col3, me_col4 = st.columns(4)
    me_col1.metric("Total jobs in tracker", len(_all_jobs))
    me_col2.metric("In pipeline (Applied+)", len(_applied_jobs), help="Applied, Recruiter Screen, Phone Screen, Take Home, Onsite, Offer")
    me_col3.metric("Active leads", len(_active_jobs), help="Found, JD Verified, Tailoring, Watch")
    me_col4.metric("Closed", len(_closed_jobs), help="Rejected, Ghosted, Withdrawn, Expired")

    st.markdown(
        "▶️ **What will happen:**  \n"
        "1️⃣ Archive `data/job_tracker_data.json` → `data/archives/` (dated snapshot)  \n"
        "2️⃣ Reset the live tracker to **0 jobs** (meta / status enum / tier definitions preserved)  \n"
        "3️⃣ Update `campaign_start` to today and clear `changelog`"
    )

    _reset_url_hist = st.checkbox(
        "Also archive `url_history.json` (lets the scraper revisit all URLs next month)",
        value=True,
        key="me_reset_url_hist",
    )

    _me_confirm = st.text_input(
        "Type **NEW MONTH** to confirm",
        value="",
        key="me_confirm_phrase",
        placeholder="NEW MONTH",
    )

    _me_ready = _me_confirm.strip() == "NEW MONTH" and _tracker_ok

    if st.button(
        "🗄️ Archive & Reset for New Month",
        type="primary",
        width="stretch",
        disabled=not _me_ready,
        key="me_archive_go",
        help="Type NEW MONTH above to enable" if not _me_ready else None,
    ):
        try:
            # 1. Create archive dir
            _archive_dir.mkdir(parents=True, exist_ok=True)

            # 2. Write archive snapshot
            _archive_path.write_text(
                _data_file.read_text(encoding="utf-8"), encoding="utf-8"
            )

            # 3. Build fresh tracker (preserve meta fields, wipe jobs/changelog)
            _fresh_meta = dict(_meta)
            _fresh_meta["last_reset"] = _now.strftime("%Y-%m-%d")
            _fresh_meta["campaign_start"] = _now.strftime("%Y-%m-%d")
            _fresh_meta["scan_count"] = 0
            _fresh_meta["total_roles"] = 0
            _fresh_meta["changelog"] = [
                {
                    "date": _now.strftime("%Y-%m-%d"),
                    "event": f"Month-end reset. Archived {len(_all_jobs)} jobs to {_archive_name}.",
                }
            ]
            _fresh_tracker = {
                "meta": _fresh_meta,
                "jobs": [],
            }
            # Route through save_tracker so we get the .bak.<timestamp>.json
            # safety copy in addition to the dated archive above. If the
            # write crashes mid-JSON, the .bak file is untouched.
            save_tracker(_fresh_tracker)

            # 4. Optionally archive url_history. Same belt-and-braces:
            # write a .bak alongside the dated archive before the reset
            # write, so a crash mid-write doesn't leave the file empty.
            if _reset_url_hist and _url_hist.exists():
                # Read once; reuse for both archive and bak so we don't risk
                # the source file changing between reads.
                _uh_src = _url_hist.read_text(encoding="utf-8")
                _uh_dest = _url_hist.parent / f"url_history_{_archive_month}.json"
                _uh_dest.write_text(_uh_src, encoding="utf-8")
                _uh_bak = _url_hist.with_suffix(
                    f".bak.{_now.strftime('%Y%m%d-%H%M%S')}.json"
                )
                _uh_bak.write_text(_uh_src, encoding="utf-8")
                # Atomic reset: tempfile + os.replace so a crash between
                # truncate and re-populate can't leave url_history empty.
                import os as _os, tempfile as _tf
                _fresh = json.dumps(
                    {"urls": [], "archived_on": _now.strftime("%Y-%m-%d")},
                    indent=2,
                )
                _fd, _tmp = _tf.mkstemp(prefix=_url_hist.name + ".",
                                          suffix=".tmp",
                                          dir=str(_url_hist.parent))
                try:
                    with _os.fdopen(_fd, "w", encoding="utf-8") as _f:
                        _f.write(_fresh)
                    _os.replace(_tmp, _url_hist)
                except Exception:
                    try: _os.unlink(_tmp)
                    except OSError: pass
                    raise
                _url_msg = "  \n✅ URL history archived to `" + _uh_dest.name + "` and reset."
            else:
                _url_msg = ""

            _success_msg = (
                "✅ **Month-end reset complete!**  \n"
                + f"🗄️ {len(_all_jobs)} jobs archived → `data/archives/{_archive_name}`  \n"
                + f"🔄 Live tracker reset to 0 jobs." + _url_msg
            )
            st.success(_success_msg)
            st.cache_data.clear()
            st.rerun()

        except Exception as _me_err:
            st.error(f"❌ Reset failed: {_me_err}")

    if not _tracker_ok:
        st.warning("Could not read tracker file — check `data/job_tracker_data.json`.")

    # Show existing archives
    if _archive_dir.exists():
        _existing_archives = sorted(_archive_dir.glob("job_tracker_*.json"), reverse=True)
        if _existing_archives:
            with st.expander(f"📚 Past archives ({len(_existing_archives)} found)", expanded=False):
                for _af in _existing_archives:
                    try:
                        _af_data = json.loads(_af.read_text(encoding="utf-8"))
                        _af_jobs = len(_af_data.get("jobs", []))
                        _af_size = _af.stat().st_size // 1024
                        _af_mtime = datetime.fromtimestamp(_af.stat().st_mtime).strftime("%Y-%m-%d")
                        st.caption(f"📄 `{_af.name}` — {_af_jobs} jobs, {_af_size} KB, archived {_af_mtime}")
                    except Exception:
                        st.caption(f"📄 `{_af.name}`")

    st.markdown("---")

    # ---------- Reset & cleanup ----------
    # Four scopes, each a two-click (plan -> confirm -> execute) flow so
    # the user always sees WHAT will be deleted before it happens. The
    # plan/execute split lives in automation/reset_ops.py.
    st.subheader("🗑 Reset & cleanup")
    st.caption(
        "Delete specific runs, clear caches, or reset the whole app. "
        "Every destructive action shows a preview first; `Full reset` "
        "requires a typed confirmation phrase. Backups are made of "
        "tracker/CRM/ledger before any reset so you can roll back."
    )

    try:
        import reset_ops  # noqa: E402  (already on sys.path via automation/)
    except Exception as _rx:
        st.error(f"reset_ops module unavailable: {_rx}")
        reset_ops = None  # type: ignore

    if reset_ops is not None:
        # Inventory bar — what's on disk right now
        _inv = reset_ops.inventory_outputs()
        iv1, iv2, iv3, iv4, iv5 = st.columns(5)
        iv1.metric("Scans", _inv["scan_count"])
        iv2.metric("Scored", _inv["scored_count"])
        iv3.metric("Pipeline runs", _inv["pipeline_runs"])
        iv4.metric("Tailor docs", _inv["tailor_docs"])
        iv5.metric("outputs/ size",
                    f"{_inv['outputs_bytes'] / (1024*1024):.1f} MB")
        st.caption(
            f"Caches: JD {_inv['jd_cache_bytes']//1024} KB · "
            f"Fit {_inv['fit_cache_bytes']//1024} KB · "
            f"background runs logged: {_inv['background_runs']}"
        )

        reset_tabs = st.tabs([
            "🎯 Delete one scan",
            "🧹 Clear all scans",
            "💾 Clear caches",
            "💣 Full reset",
        ])

        # -------- Tab 1: Delete one scan ---------------------------------
        with reset_tabs[0]:
            scans = reset_ops.list_scans()
            if not scans:
                st.info("No scans on disk.")
            else:
                labels = [
                    f"{s['stem']} · {s['rows']:,} rows · "
                    f"{s['size_kb']:,} KB · {s['mtime']}"
                    for s in scans
                ]
                idx = st.selectbox(
                    "Scan to delete", range(len(scans)),
                    format_func=lambda i: labels[i],
                    key="reset_scan_pick",
                )
                chosen = scans[idx]
                plan = reset_ops.plan_delete_scan(chosen["stem"])
                if plan.files_to_delete:
                    st.markdown("**Will delete:**")
                    for p in plan.files_to_delete:
                        st.code(str(p.name), language="text")
                    st.caption(f"Total: {plan.summary()}")
                    rc1, rc2 = st.columns([1, 3])
                    with rc1:
                        if st.button("🗑 Delete this scan",
                                      type="primary",
                                      width='stretch',
                                      key="reset_scan_go"):
                            result = reset_ops.execute(plan)
                            if result.errors:
                                st.error(
                                    f"Deleted {result.deleted_files} file(s); "
                                    f"{len(result.errors)} error(s): "
                                    + "; ".join(result.errors[:3])
                                )
                            else:
                                st.success(
                                    f"Deleted {result.deleted_files} file(s) "
                                    f"({result.deleted_bytes/1024:.0f} KB)."
                                )
                            st.cache_data.clear()
                            st.rerun()
                    with rc2:
                        st.caption(
                            "One-click delete. No typed confirmation for "
                            "single-scan deletes — small blast radius."
                        )

        # -------- Tab 2: Clear all scans ---------------------------------
        with reset_tabs[1]:
            plan = reset_ops.plan_clear_scans()
            if not plan.files_to_delete:
                st.info("No scans to clear.")
            else:
                st.markdown(
                    f"**Will delete {len(plan.files_to_delete)} file(s)** "
                    f"(~{plan.total_bytes/(1024*1024):.1f} MB):"
                )
                preview_n = min(10, len(plan.files_to_delete))
                for p in plan.files_to_delete[:preview_n]:
                    st.code(p.name, language="text")
                if len(plan.files_to_delete) > preview_n:
                    st.caption(
                        f"… +{len(plan.files_to_delete) - preview_n} more")
                st.caption(
                    f"**Preserved:** {', '.join(plan.preserved)}. "
                    "The scan_checkpoint.json is also preserved so an "
                    "in-progress paused scrape can still resume."
                )
                if st.checkbox("I understand this removes all scan history",
                                 key="reset_scans_ack"):
                    if st.button("🧹 Clear all scans now",
                                  type="primary",
                                  width='stretch',
                                  key="reset_scans_go"):
                        result = reset_ops.execute(plan)
                        if result.errors:
                            st.error(
                                f"Deleted {result.deleted_files} file(s); "
                                f"{len(result.errors)} error(s): "
                                + "; ".join(result.errors[:3])
                            )
                        else:
                            st.success(
                                f"Deleted {result.deleted_files} file(s) "
                                f"({result.deleted_bytes/(1024*1024):.1f} MB)."
                            )
                        st.cache_data.clear()
                        st.rerun()

        # -------- Tab 3: Clear caches ------------------------------------
        with reset_tabs[2]:
            plan = reset_ops.plan_clear_caches()
            st.markdown(
                f"**Will empty** `jd_cache/` and `fit_cache/` "
                f"({len(plan.files_to_delete)} file(s), "
                f"~{plan.total_bytes/1024:.0f} KB)."
            )
            st.caption(
                "Forces scrapes to re-fetch JDs and the scorer to re-call "
                "the LLM on every role. Useful when scoring logic changed "
                "and you want clean re-runs. Does NOT delete scans, "
                "scored files, tracker, CRM, or the lifetime ledger."
            )
            if plan.files_to_delete:
                if st.button("💾 Clear caches",
                              type="primary",
                              width='stretch',
                              key="reset_cache_go"):
                    result = reset_ops.execute(plan)
                    if result.errors:
                        st.error(
                            f"Deleted {result.deleted_files} file(s); "
                            f"{len(result.errors)} error(s): "
                            + "; ".join(result.errors[:3])
                        )
                    else:
                        st.success(
                            f"Deleted {result.deleted_files} cache file(s) "
                            f"({result.deleted_bytes/1024:.0f} KB)."
                        )
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.info("Caches already empty.")

        # -------- Tab 4: Full reset --------------------------------------
        with reset_tabs[3]:
            plan = reset_ops.plan_full_reset()
            st.warning(
                "**Full reset** wipes `automation/outputs/`, clears the "
                "tracker, clears the recruiter CRM, and resets the "
                "lifetime cost ledger to zero. Tracker, CRM, and ledger "
                "are backed up first.",
                icon="⚠️",
            )
            rf1, rf2 = st.columns([1, 1])
            with rf1:
                st.markdown("**Will delete:**")
                st.caption(
                    f"{len(plan.files_to_delete)} top-level file(s), "
                    f"{len(plan.dirs_to_empty)} subdir(s) emptied, "
                    f"{len(plan.json_to_reset)} JSON reset, "
                    f"ledger zeroed. "
                    f"~{plan.total_bytes/(1024*1024):.1f} MB freed."
                )
            with rf2:
                st.markdown("**Preserved:**")
                for pr in plan.preserved:
                    st.caption(f"· {pr}")
            required_phrase = "RESET EVERYTHING"
            typed = st.text_input(
                f'Type `{required_phrase}` to confirm',
                value="",
                key="reset_full_confirm",
                placeholder=required_phrase,
            )
            if st.button("💣 Full reset (cannot be undone except from backups)",
                          type="primary",
                          width='stretch',
                          disabled=(typed.strip() != required_phrase),
                          key="reset_full_go"):
                result = reset_ops.execute(
                    plan,
                    confirm_phrase=typed,
                    required_phrase=required_phrase,
                )
                if result.errors:
                    st.error(
                        f"Partial reset: {result.deleted_files} file(s) "
                        f"deleted, {len(result.errors)} error(s): "
                        + "; ".join(result.errors[:5])
                    )
                else:
                    st.success(
                        f"✅ Full reset complete. "
                        f"{result.deleted_files} file(s) removed "
                        f"({result.deleted_bytes/(1024*1024):.1f} MB). "
                        f"Tracker + CRM + ledger: reset. "
                        f"Backups: {len(result.backups)}."
                    )
                    for bak in result.backups:
                        st.caption(f"🗄 backup: `{bak.name}`")
                st.cache_data.clear()
                st.rerun()

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
    if st.button("🌅 Run nightly refresh now (background)",
                 width='content',
                 disabled=bool(any_work_active),
                 help="Disabled while another job is running." if any_work_active else None):
        _nr_cmd = [sys.executable, str(ROOT / "automation" / "nightly_refresh.py")]
        _nr_rec = scan_runner.start_run("nightly_refresh", _nr_cmd)
        st.session_state["_last_launch"] = {"run_id": _nr_rec.run_id, "label": "Nightly refresh"}
        st.toast("🌅 Nightly refresh launched!", icon="🚀")
        st.rerun()
    if any_work_active:
        st.caption("⏳ A job is already running — button re-enables when it finishes.")

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

# ═══════════════════════════════════════════════════════════════════════════
# 📊 ANALYTICS PAGE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📊 Analytics":
    import altair as alt

    st.title("📊 Analytics")
    st.caption("Search pipeline at a glance — funnel, fit distribution, sector coverage, and scrape trends.")

    # ── Load data ──────────────────────────────────────────────────────────
    _an_tracker = load_tracker()
    _an_jobs    = _an_tracker.get("jobs", [])

    # Scan files for trend. Match scan_YYYYMMDD.json only — the loose
    # scan_*.json glob also pulled in scan_YYYYMMDD_scored.json sidecars,
    # which are missing top-level scrape stats and crashed Analytics with
    # KeyError('total_new_candidates').
    _an_scan_files = sorted(
        p for p in OUT_DIR.glob("scan_*.json")
        if p.stem.replace("scan_", "").isdigit() and len(p.stem) == 13
    )
    _an_scans = []
    for _sf in _an_scan_files:
        try:
            _sd = json.loads(_sf.read_text(encoding="utf-8"))
            _an_scans.append(_sd)
        except Exception:
            pass

    # ── TOP KPI ROW ────────────────────────────────────────────────────────
    _an_scraped  = (_an_scans[-1].get("total_new_candidates", 0) if _an_scans else 0)
    _an_tracked  = len(_an_jobs)
    _an_high_fit = sum(1 for j in _an_jobs if (j.get("fit_score_numeric") or 0) >= 4)
    _an_applied  = sum(1 for j in _an_jobs if j.get("date_applied"))
    _an_response = sum(1 for j in _an_jobs
                       if j.get("rejection_date") or j.get("status") in ("Offer", "Interview"))

    _ak1, _ak2, _ak3, _ak4, _ak5 = st.columns(5)
    _ak1.metric("Latest scrape",  f"{_an_scraped:,}",  help="New candidates from most recent scrape (post-dedup)")
    _ak2.metric("Tracked jobs",   str(_an_tracked),    help="Total jobs in your tracker")
    _ak3.metric("High-fit (4–5)", str(_an_high_fit),   help="fit_score_numeric ≥ 4")
    _ak4.metric("Applied",        str(_an_applied),    help="date_applied is set")
    _ak5.metric("Responses",      str(_an_response),   help="Rejection logged or Interview/Offer status")

    st.markdown("---")

    # ── ROW 1: Funnel + Score Distribution ────────────────────────────────
    _an_col_l, _an_col_r = st.columns(2)

    with _an_col_l:
        st.markdown("#### 🔽 Application funnel")
        _an_funnel_df = pd.DataFrame({
            "Stage": ["Scraped", "Tracked", "High-fit", "Applied", "Response"],
            "Count": [_an_scraped, _an_tracked, _an_high_fit, _an_applied, _an_response],
        })
        _an_funnel_chart = (
            alt.Chart(_an_funnel_df)
            .mark_bar(color="#6366f1", cornerRadiusEnd=4)
            .encode(
                x=alt.X("Count:Q", title="Jobs"),
                y=alt.Y("Stage:N",
                        sort=["Scraped", "Tracked", "High-fit", "Applied", "Response"],
                        title=None),
                tooltip=["Stage:N", "Count:Q"],
            )
            .properties(height=220)
        )
        st.altair_chart(_an_funnel_chart, use_container_width=True)
        if _an_scraped:
            st.caption(
                f"Scraped → Tracked conversion: "
                f"**{_an_tracked / _an_scraped * 100:.1f}%**"
            )

    with _an_col_r:
        st.markdown("#### ⭐ Fit score distribution")
        _an_score_counts: dict = {}
        for _j in _an_jobs:
            _s = _j.get("fit_score_numeric")
            if _s is not None:
                _an_score_counts[int(_s)] = _an_score_counts.get(int(_s), 0) + 1
        if _an_score_counts:
            _an_score_df = pd.DataFrame([
                {"Score": f"{int(k)} ({'⭐' * int(k)})", "Count": v, "_k": int(k)}
                for k, v in _an_score_counts.items()
            ]).sort_values("_k")
            _an_score_chart = (
                alt.Chart(_an_score_df)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Score:N", sort=alt.SortField("_k"), title="Fit Score"),
                    y=alt.Y("Count:Q", title="Jobs"),
                    color=alt.Color(
                        "_k:Q",
                        scale=alt.Scale(domain=[3, 4, 5],
                                        range=["#f59e0b", "#10b981", "#6366f1"]),
                        legend=None,
                    ),
                    tooltip=["Score:N", "Count:Q"],
                )
                .properties(height=220)
            )
            st.altair_chart(_an_score_chart, use_container_width=True)
            st.caption("  ·  ".join(
                f"**{lbl}**: {_an_score_counts.get(k, 0)}"
                for lbl, k in [("High (5)", 5), ("Strong (4)", 4), ("Medium (3)", 3)]
                if _an_score_counts.get(k)
            ))
        else:
            st.info("No scored jobs yet — run the scoring stage in Pipeline.")

    st.markdown("---")

    # ── ROW 2: Sector breakdown + Urgency donut ───────────────────────────
    _an_col2_l, _an_col2_r = st.columns([3, 2])

    with _an_col2_l:
        st.markdown("#### 🏢 Sector breakdown")
        _an_sector_counts: dict = {}
        for _j in _an_jobs:
            _sec = (_j.get("sector") or "Unknown")
            _an_sector_counts[_sec] = _an_sector_counts.get(_sec, 0) + 1
        _an_sector_df = pd.DataFrame([
            {"Sector": k, "Jobs": v}
            for k, v in _an_sector_counts.items()
        ])
        if "Jobs" in _an_sector_df.columns:
            _an_sector_df = _an_sector_df.sort_values("Jobs", ascending=False)
        _an_sector_chart = (
            alt.Chart(_an_sector_df)
            .mark_bar(color="#0ea5e9", cornerRadiusEnd=4)
            .encode(
                x=alt.X("Jobs:Q"),
                y=alt.Y("Sector:N", sort="-x", title=None),
                tooltip=["Sector:N", "Jobs:Q"],
            )
            .properties(height=max(220, len(_an_sector_df) * 26))
        )
        st.altair_chart(_an_sector_chart, use_container_width=True)

    with _an_col2_r:
        st.markdown("#### 🚦 Urgency breakdown")
        _an_urg_order  = ["High", "Medium", "Low", "Unknown"]
        _an_urg_colors = {"High": "#ef4444", "Medium": "#f59e0b",
                          "Low": "#10b981", "Unknown": "#94a3b8"}
        _an_urg_counts: dict = {}
        for _j in _an_jobs:
            _u = _j.get("urgency") or "Unknown"
            _an_urg_counts[_u] = _an_urg_counts.get(_u, 0) + 1
        _an_urg_df = pd.DataFrame([
            {"Urgency": k, "Jobs": _an_urg_counts.get(k, 0),
             "Color": _an_urg_colors.get(k, "#94a3b8")}
            for k in _an_urg_order if _an_urg_counts.get(k, 0) > 0
        ])
        if not _an_urg_df.empty:
            _an_urg_chart = (
                alt.Chart(_an_urg_df)
                .mark_arc(innerRadius=50)
                .encode(
                    theta=alt.Theta("Jobs:Q"),
                    color=alt.Color(
                        "Urgency:N",
                        scale=alt.Scale(
                            domain=list(_an_urg_df["Urgency"]),
                            range=list(_an_urg_df["Color"]),
                        ),
                    ),
                    tooltip=["Urgency:N", "Jobs:Q"],
                )
                .properties(height=220)
            )
            st.altair_chart(_an_urg_chart, use_container_width=True)
        for _u in _an_urg_order:
            _cnt = _an_urg_counts.get(_u, 0)
            if _cnt:
                _ic = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(_u, "⚪")
                st.caption(f"{_ic} **{_u}**: {_cnt}")

    st.markdown("---")

    # ── ROW 3: Scrape trend ───────────────────────────────────────────────
    st.markdown("#### 📈 Scrape volume trend")
    if len(_an_scans) >= 2:
        _an_trend_rows = []
        for _sd in _an_scans:
            _raw = str(_sd.get("scan_date", ""))
            try:
                _lbl = datetime.strptime(_raw, "%Y%m%d").strftime("%b %d")
            except Exception:
                _lbl = _raw
            _dd = _sd.get("dedup_stats", {})
            _an_trend_rows.append({
                "Date":              _lbl,
                "Input (raw)":       _dd.get("input", 0),
                "Dropped (URL dup)": _dd.get("dropped_url", 0),
                "Dropped (near-dup)":_dd.get("dropped_near", 0),
                "Scraped (kept)":    _sd.get("total_new_candidates", 0),
            })
        _an_trend_long = pd.DataFrame(_an_trend_rows).melt(
            id_vars=["Date"],
            value_vars=["Input (raw)", "Dropped (URL dup)", "Dropped (near-dup)", "Scraped (kept)"],
            var_name="Metric",
            value_name="Count",
        )
        _an_trend_chart = (
            alt.Chart(_an_trend_long)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                x=alt.X("Date:N", title="Scan date"),
                y=alt.Y("Count:Q", title="Jobs"),
                color=alt.Color(
                    "Metric:N",
                    scale=alt.Scale(
                        domain=["Input (raw)", "Dropped (URL dup)",
                                "Dropped (near-dup)", "Scraped (kept)"],
                        range=["#94a3b8", "#f59e0b", "#ef4444", "#6366f1"],
                    ),
                ),
                tooltip=["Date:N", "Metric:N", "Count:Q"],
            )
            .properties(height=260)
        )
        st.altair_chart(_an_trend_chart, use_container_width=True)
        _an_last  = _an_scans[-1]
        _an_in    = (_an_last.get("dedup_stats", {}).get("input") or 1)
        _an_out   = (_an_last.get("total_new_candidates") or 0)
        st.caption(
            f"Latest dedup efficiency: **{_an_out / _an_in * 100:.0f}%** kept "
            f"({_an_out:,} of {_an_in:,} raw candidates). "
            f"{len(_an_scans)} scan{'s' if len(_an_scans) != 1 else ''} on record."
        )
    else:
        st.info("Need ≥ 2 scans to show a trend. Run the nightly pipeline to accumulate data.")
        if _an_scans:
            _an_one = _an_scans[0]
            _sc1, _sc2, _sc3 = st.columns(3)
            _sc1.metric("Input (raw)", _an_one.get("dedup_stats", {}).get("input", 0))
            _sc2.metric("After dedup", _an_one.get("total_new_candidates", 0))
            _sc3.metric("Companies",   _an_one.get("companies_scanned", 0))

    st.markdown("---")

    # ── ROW 4: Sector scan coverage (latest scrape) ───────────────────────
    st.markdown("#### 🗺️ Sector scan coverage (latest scrape)")
    if _an_scans:
        _an_by_sector = _an_scans[-1].get("by_sector", {})
        if _an_by_sector:
            _an_cov_df = pd.DataFrame([
                {"Sector": k, "Open roles": v}
                for k, v in sorted(_an_by_sector.items(), key=lambda x: -x[1])
            ])
            _an_cov_chart = (
                alt.Chart(_an_cov_df)
                .mark_bar(color="#818cf8", cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Open roles:Q"),
                    y=alt.Y("Sector:N", sort="-x", title=None),
                    tooltip=["Sector:N", "Open roles:Q"],
                )
                .properties(height=max(220, len(_an_cov_df) * 24))
            )
            st.altair_chart(_an_cov_chart, use_container_width=True)
            _an_total_open = sum(_an_by_sector.values())
            st.caption(
                f"**{_an_total_open:,}** total open roles across "
                f"**{len(_an_by_sector)}** sectors "
                f"(scan {_an_scans[-1].get('scan_date', 'unknown')})."
            )
    else:
        st.info("No scan files found. Run the nightly pipeline to generate scan data.")


# ===========================================================================
# REVIEW QUEUE PAGE
# One-at-a-time card workflow for triaging "Found" jobs.
# ===========================================================================
elif page == "📬 Review Queue":
    st.title("📬 Review Queue")
    st.caption(
        "Work through new matches one card at a time. "
        "Each card shows fit, keywords, and the suggested next action. "
        "Promote to Watch, Shortlist, or Expire your choice."
    )

    # Pull jobs needing review (Found, highest fit first)
    _rq_all   = load_tracker()
    _rq_jobs  = _rq_all.get("jobs", [])
    _rq_queue = sorted(
        [j for j in _rq_jobs if j.get("status") == "Found"],
        key=lambda j: (
            -(j.get("fit_score_numeric") or 0),
            -({"High": 3, "Medium": 2, "Low": 1}.get(j.get("urgency", ""), 0)),
        ),
    )
    _rq_total = len(_rq_queue)

    if _rq_total == 0:
        st.success("All caught up no Found jobs left to review!", icon="✅")
        st.info(
            "New jobs appear here after the nightly pipeline runs. "
            "Check the Pipeline page to run a fresh scrape."
        )
        st.stop()

    # Session state: current card index + session tally
    if "_rq_idx" not in st.session_state:
        st.session_state["_rq_idx"] = 0
    if "_rq_session_acted" not in st.session_state:
        st.session_state["_rq_session_acted"] = 0

    _rq_idx = min(int(st.session_state["_rq_idx"]), _rq_total - 1)

    # Progress bar
    _rq_pct = _rq_idx / _rq_total if _rq_total else 1.0
    _rq_h1, _rq_h2 = st.columns([5, 1])
    _rq_h1.progress(
        _rq_pct,
        text=f"Card {_rq_idx + 1} of {_rq_total} · {_rq_total - _rq_idx} remaining",
    )
    _rq_h2.metric("Actioned today", st.session_state["_rq_session_acted"])
    st.markdown("")

    # Current card
    _rq_job       = _rq_queue[_rq_idx]
    _rq_score_num = _rq_job.get("fit_score_numeric") or 0
    _rq_score_txt = _rq_job.get("fit_score") or "n/a"
    _rq_urgency   = _rq_job.get("urgency") or "n/a"
    _rq_tier      = _rq_job.get("tier")
    _rq_level     = _rq_job.get("level") or "n/a"
    _rq_sector    = _rq_job.get("sector") or "n/a"
    _rq_comp      = _rq_job.get("expected_comp_band_cad") or ""
    _rq_kw        = _rq_job.get("keywords") or []
    _rq_fit_notes = _rq_job.get("fit_notes") or ""
    _rq_next_act  = _rq_job.get("next_action") or ""
    _rq_osfi      = _rq_job.get("osfi_hook") or ""
    _rq_url       = _rq_job.get("url") or _rq_job.get("portal_url") or ""
    _rq_job_id    = _rq_job.get("id", "")

    _rq_score_color = {"5": "#6366f1", "4": "#10b981", "3": "#f59e0b"}.get(
        str(int(_rq_score_num)), "#94a3b8"
    )
    _rq_urg_color = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#10b981"}.get(
        _rq_urgency, "#94a3b8"
    )

    with st.container(border=True):
        # Title row
        _rq_t1, _rq_t2 = st.columns([5, 1])
        with _rq_t1:
            st.markdown(
                f"### {_rq_job.get('company', 'Unknown')} "
                f"— {_rq_job.get('title', 'Unknown role')}"
            )
        with _rq_t2:
            st.markdown(
                f"<div style='text-align:center;padding:10px 6px;"
                f"background:{_rq_score_color}22;border:2px solid {_rq_score_color};"
                f"border-radius:10px;'>"
                f"<div style='font-size:22px;font-weight:700;color:{_rq_score_color}'>"
                f"{'&#11088;' * int(_rq_score_num)}</div>"
                f"<div style='font-size:11px;color:{_rq_score_color};font-weight:600'>"
                f"Fit {int(_rq_score_num)}/5 · {_rq_score_txt}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Tag row
        _rq_tags = []
        if _rq_tier:
            _rq_tags.append(f"\U0001f3c5 Tier {_rq_tier}")
        _rq_tags.append(f"\U0001f4c2 {_rq_sector}")
        _rq_tags.append(f"\U0001f464 {_rq_level}")
        _rq_tags.append(
            f"<span style='color:{_rq_urg_color};font-weight:600'>"
            f"⚡ {_rq_urgency} urgency</span>"
        )
        if _rq_comp:
            _rq_tags.append(f"\U0001f4b0 {_rq_comp}")
        st.markdown("  ·  ".join(_rq_tags), unsafe_allow_html=True)
        st.markdown("")

        # Body columns
        _rq_b1, _rq_b2 = st.columns([3, 2])
        with _rq_b1:
            if _rq_fit_notes:
                st.markdown("**\U0001f4dd Fit notes**")
                _preview = _rq_fit_notes[:500]
                st.markdown(_preview + (" ..." if len(_rq_fit_notes) > 500 else ""))
                if len(_rq_fit_notes) > 500:
                    with st.expander("Read full fit notes"):
                        st.markdown(_rq_fit_notes)
            if _rq_osfi:
                st.markdown(f"\U0001f3db **OSFI hook:** {_rq_osfi}")

        with _rq_b2:
            if _rq_kw:
                st.markdown("**\U0001f3f7 Keywords**")
                _kw_html = " ".join(
                    f"<span style='display:inline-block;margin:2px;padding:2px 8px;"
                    f"background:#6366f122;border:1px solid #6366f144;"
                    f"border-radius:12px;font-size:12px'>{kw}</span>"
                    for kw in _rq_kw[:12]
                )
                st.markdown(_kw_html, unsafe_allow_html=True)
                if len(_rq_kw) > 12:
                    st.caption(f"... +{len(_rq_kw) - 12} more")
            if _rq_next_act:
                st.markdown("")
                st.markdown("**\U0001f3af Suggested next action**")
                _trunc = _rq_next_act[:280] + (" ..." if len(_rq_next_act) > 280 else "")
                st.info(_trunc, icon="\U0001f4a1")

        st.markdown("")
        st.markdown("---")

        # Tailored docs badge on Review Queue card
        _rq_docs = _find_tailor_docs(_rq_job)
        if _rq_docs:
            with st.expander(f"📄 Tailored docs ({len(_rq_docs)}) — preview"):
                for _rdoc in _rq_docs:
                    st.caption(f"**{_rdoc.name}**")
                    _rt = _rdoc.read_text(encoding="utf-8", errors="replace")
                    _rt_suffix = " *(truncated)*" if len(_rt) > 2000 else ""
                    st.markdown(_rt[:2000] + _rt_suffix)
                    st.markdown("---")

        # Action buttons
        _rq_a1, _rq_a2, _rq_a3, _rq_a4, _rq_a5 = st.columns([2, 2, 2, 2, 1])

        def _rq_apply_action(new_status, new_urgency=None):
            _td = json.loads(TRACKER.read_text(encoding="utf-8"))
            for _j2 in _td.get("jobs", []):
                if _j2.get("id") == _rq_job_id:
                    if new_status:
                        _j2["status"] = new_status
                    if new_urgency:
                        _j2["urgency"] = new_urgency
                    break
            save_tracker(_td)
            st.session_state["_rq_idx"] = _rq_idx + 1
            st.session_state["_rq_session_acted"] = (
                st.session_state.get("_rq_session_acted", 0) + 1
            )

        if _rq_a1.button(
            "\U0001f4cc Watch", use_container_width=True,
            help="Move to Watch - monitor without committing to apply"
        ):
            _rq_apply_action("Watch")
            st.rerun()

        if _rq_a2.button(
            "✅ Apply", type="primary", use_container_width=True,
            help="Record application — sets date_applied and seeds follow-up schedule"
        ):
            st.session_state["_rq_apply_open"] = _rq_job_id
            st.rerun()

        if _rq_a3.button(
            "❌ Expire", use_container_width=True,
            help="Mark as Expired - not pursuing"
        ):
            _rq_apply_action("Expired")
            st.rerun()

        if _rq_url:
            if _rq_url:
                _rq_a4.link_button("🔗 Open JD", _rq_url, use_container_width=True)

        if _rq_a5.button("⏭", use_container_width=True, help="Skip - come back later"):
            st.session_state["_rq_idx"] = _rq_idx + 1
            st.rerun()

    # Inline Apply form — shown when user clicks Apply on a card
    if st.session_state.get("_rq_apply_open") == _rq_job_id:
        with st.container(border=True):
            st.markdown(f"#### ✅ Confirm application — {_rq_job.get('company')} · {_rq_job.get('title')}")
            with st.form(key=f"rq_apply_form_{_rq_job_id}"):
                _ap_col1, _ap_col2 = st.columns(2)
                _ap_date = _ap_col1.date_input(
                    "Date applied", value=date.today(), help="When did you submit the application?"
                )
                _ap_channel = _ap_col2.selectbox(
                    "Applied via", ["Company portal", "LinkedIn", "Email", "Referral", "Recruiter", "Other"]
                )
                _ap_notes = st.text_area(
                    "Notes (optional)", placeholder="E.g. referral from Jane, used tailored resume v2, ...",
                    height=80
                )
                _ap_tailor = st.checkbox(
                    "🤖 Launch jd_tailor in background (tailors resume + cover letter)",
                    value=False,
                    help="Requires API key. Runs jd_tailor.py for this job ID."
                )
                _ap_c1, _ap_c2 = st.columns(2)
                _ap_submit = _ap_c1.form_submit_button("✅ Confirm application", type="primary", use_container_width=True)
                _ap_cancel = _ap_c2.form_submit_button("Cancel", use_container_width=True)

            if _ap_submit:
                _td = json.loads(TRACKER.read_text(encoding="utf-8"))
                for _j2 in _td.get("jobs", []):
                    if _j2.get("id") == _rq_job_id:
                        _j2["status"] = "Applied"
                        seed_followup(_j2, _ap_date)
                        _log_entry = {
                            "date": _ap_date.isoformat(),
                            "type": "applied",
                            "channel": _ap_channel,
                            "notes": _ap_notes or "",
                        }
                        if not isinstance(_j2.get("outreach_log"), list):
                            _j2["outreach_log"] = []
                        _j2["outreach_log"].append(_log_entry)
                        break
                save_tracker(_td)
                if _ap_tailor and _rq_job_id and api_key.is_key_valid():
                    _tailor_cmd = [sys.executable, str(ROOT / "automation" / "jd_tailor.py"), "--job-id", _rq_job_id]
                    scan_runner.start_run(f"tailor_{_rq_job_id}", _tailor_cmd)
                    st.toast(f"🤖 jd_tailor launched for {_rq_job_id}", icon="🚀")
                del st.session_state["_rq_apply_open"]
                st.session_state["_rq_idx"] = _rq_idx + 1
                st.session_state["_rq_session_acted"] = st.session_state.get("_rq_session_acted", 0) + 1
                st.toast(f"✅ Application recorded for {_rq_job.get('company')}!", icon="📨")
                st.rerun()

            if _ap_cancel:
                del st.session_state["_rq_apply_open"]
                st.rerun()

        # Navigation strip
    st.markdown("")
    _rq_n1, _rq_n2, _rq_n3 = st.columns([1, 3, 1])
    if _rq_n1.button("◄ Prev", disabled=(_rq_idx == 0)):
        st.session_state["_rq_idx"] = max(0, _rq_idx - 1)
        st.rerun()
    _rq_n2.caption(
        f"**{_rq_job.get('company')}** · {_rq_job.get('title')} · "
        f"ID `{_rq_job_id}` · found {_rq_job.get('date_found', 'n/a')}"
    )
    if _rq_n3.button("Next ►", disabled=(_rq_idx >= _rq_total - 1)):
        st.session_state["_rq_idx"] = min(_rq_total - 1, _rq_idx + 1)
        st.rerun()

    with st.expander("⚙️ Queue options"):
        st.caption(
            f"Queue contains **{_rq_total}** Found jobs sorted by fit score then urgency."
        )
        if st.button("\U0001f504 Restart from card 1"):
            st.session_state["_rq_idx"] = 0
            st.session_state["_rq_session_acted"] = 0
            st.rerun()
        st.caption(
            "Actioning a card (Watch / Shortlist / Expire) saves immediately to the tracker. "
            "Skip leaves the job unchanged for next session."
        )

# ===========================================================================
# FOLLOW-UPS PAGE
# Triage applied jobs by follow-up due date — overdue, today, this week.
# ===========================================================================
elif page == "🔔 Follow-ups":
    st.title("🔔 Follow-ups")
    st.caption(
        "Track every application after you hit submit. "
        "Log each outreach touch so the cadence advances automatically. "
        "Overdue items are sorted most-overdue first."
    )

    _fu_all   = load_tracker()
    _fu_jobs  = _fu_all.get("jobs", [])
    _fu_bkts  = followup_buckets(_fu_jobs)

    _fu_overdue      = _fu_bkts["overdue"]        # [(days_overdue, job), ...]
    _fu_due_today    = _fu_bkts["due_today"]       # [job, ...]
    _fu_this_week    = _fu_bkts["due_this_week"]   # [(days_until, job), ...]
    _fu_upcoming     = _fu_bkts["upcoming"]         # [(days_until, job), ...]
    _fu_no_sched     = _fu_bkts["no_schedule"]     # [job, ...]

    _fu_total_due = len(_fu_overdue) + len(_fu_due_today)

    # KPI row
    _fk1, _fk2, _fk3, _fk4 = st.columns(4)
    _fk1.metric("Overdue",     len(_fu_overdue),   delta="past due" if _fu_overdue else None, delta_color="inverse")
    _fk2.metric("Due today",   len(_fu_due_today))
    _fk3.metric("This week",   len(_fu_this_week))
    _fk4.metric("No schedule", len(_fu_no_sched),  help="Applied but follow-up date not set")

    if _fu_total_due == 0 and not _fu_no_sched:
        st.success("🎉 All follow-ups are current — nothing overdue or due today!", icon="✅")

    st.markdown("---")

    def _fu_render_card(job, days_label, border_color):
        """Render a single follow-up card with log-outreach action."""
        _fj_job_obj = job  # keep full dict for AI helpers
        _fj_id      = job.get("id", "")
        _fj_co      = job.get("company", "?")
        _fj_title   = job.get("title", "?")
        _fj_applied = job.get("date_applied", "?")
        _fj_sched   = job.get("followup_schedule") or {}
        _fj_next    = _fj_sched.get("next_due", "?")
        _fj_log     = job.get("outreach_log") or []
        _fj_url     = job.get("url") or job.get("portal_url") or ""
        _fj_contact = (job.get("contact") or {})
        _fj_rec     = _fj_contact.get("recruiter_name") or ""

        with st.container(border=True):
            _fc1, _fc2 = st.columns([5, 1])
            with _fc1:
                st.markdown(
                    f"<span style='border-left:4px solid {border_color};"
                    f"padding-left:8px'>"
                    f"**{_fj_co}** — {_fj_title}</span>",
                    unsafe_allow_html=True
                )
                _fu_meta = f"Applied {_fj_applied}"
                if _fj_rec:
                    _fu_meta += f" · Recruiter: {_fj_rec}"
                st.caption(_fu_meta)
            with _fc2:
                st.markdown(
                    f"<div style='text-align:center;padding:6px;"
                    f"background:{border_color}22;border:1px solid {border_color};"
                    f"border-radius:8px;font-size:11px;color:{border_color};"
                    f"font-weight:700'>{days_label}</div>",
                    unsafe_allow_html=True
                )

            # Outreach history (compact)
            if _fj_log:
                with st.expander(f"📋 {len(_fj_log)} outreach touch{'es' if len(_fj_log)!=1 else ''} logged", expanded=False):
                    for _entry in reversed(_fj_log[-5:]):
                        _etype = _entry.get("type", "touch")
                        _edate = _entry.get("date", "?")
                        _enote = _entry.get("notes", "")
                        st.caption(f"**{_edate}** · {_etype}" + (f" — {_enote[:120]}" if _enote else ""))

            # Action row
            _fa1, _fa2, _fa3, _fa4 = st.columns([3, 3, 3, 2])

            # AI email drafter
            with _fa1.expander("✉️ Draft email"):
                _draft_touch = len(_fj_log) + 1
                _draft_key   = f"draft_{_fj_id}_{_draft_touch}"
                _draft_type  = st.selectbox(
                    "Tone", ["Standard follow-up", "Warm / brief nudge", "Value-add angle"],
                    key=f"dt_{_fj_id}"
                )
                if st.button("✨ Generate draft", key=f"gen_{_fj_id}",
                             disabled=not api_key.is_key_valid(),
                             help="Uses Claude Haiku (~$0.001)"):
                    with st.spinner("Drafting…"):
                        _prompt = _email_draft_prompt(_fj_job_obj, _draft_touch)
                        _generated = _ai_draft(_draft_key + _draft_type, _prompt)
                    st.session_state[_draft_key] = _generated
                _draft_text = st.session_state.get(_draft_key, "")
                if _draft_text:
                    _editable = st.text_area(
                        "Edit before sending", _draft_text,
                        height=220, key=f"dedit_{_fj_id}"
                    )
                    if st.button("💾 Save to outreach log", key=f"dsave_{_fj_id}"):
                        _td_d = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _jd2 in _td_d.get("jobs", []):
                            if _jd2.get("id") == _fj_id:
                                if not isinstance(_jd2.get("outreach_log"), list):
                                    _jd2["outreach_log"] = []
                                _jd2["outreach_log"].append({
                                    "date": date.today().isoformat(),
                                    "type": "email_draft",
                                    "notes": _editable[:500],
                                })
                                advance_followup(_jd2)
                                break
                        save_tracker(_td_d)
                        del st.session_state[_draft_key]
                        st.toast("💾 Draft saved and follow-up advanced!", icon="✅")
                        st.rerun()
                elif not api_key.is_key_valid():
                    st.caption("Set API key in the sidebar to enable AI drafts.")

            # Log outreach expander
            with _fa2.expander("✅ Log outreach"):
                with st.form(key=f"fu_log_{_fj_id}_{_fj_next}"):
                    _log_date  = st.date_input("Date", value=date.today(), key=f"fu_d_{_fj_id}")
                    _log_type  = st.selectbox("Type", ["email", "linkedin_message", "phone", "referral_nudge", "other"], key=f"fu_t_{_fj_id}")
                    _log_notes = st.text_input("Notes", placeholder="Brief message sent, follow-up in X days...", key=f"fu_n_{_fj_id}")
                    if st.form_submit_button("Save", type="primary"):
                        _td2 = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _j3 in _td2.get("jobs", []):
                            if _j3.get("id") == _fj_id:
                                if not isinstance(_j3.get("outreach_log"), list):
                                    _j3["outreach_log"] = []
                                _j3["outreach_log"].append({
                                    "date":  _log_date.isoformat(),
                                    "type":  _log_type,
                                    "notes": _log_notes,
                                })
                                advance_followup(_j3, _log_date)
                                break
                        save_tracker(_td2)
                        st.toast(f"✅ Outreach logged for {_fj_co}!", icon="📨")
                        st.rerun()

            # Got response
            with _fa3.expander("📨 Response"):
                with st.form(key=f"fu_resp_{_fj_id}"):
                    _resp_type = st.selectbox(
                        "Outcome",
                        ["Interview scheduled", "Rejected", "Offer received", "Ghosted / withdrawn"],
                        key=f"fu_r_{_fj_id}"
                    )
                    _resp_note = st.text_input("Notes", key=f"fu_rn_{_fj_id}")
                    if st.form_submit_button("Save", type="primary"):
                        _status_map = {
                            "Interview scheduled": "Interview",
                            "Rejected":            "Rejected",
                            "Offer received":      "Offer",
                            "Ghosted / withdrawn": "Withdrawn",
                        }
                        _td3 = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _j4 in _td3.get("jobs", []):
                            if _j4.get("id") == _fj_id:
                                _j4["status"] = _status_map.get(_resp_type, "Watch")
                                if not isinstance(_j4.get("outreach_log"), list):
                                    _j4["outreach_log"] = []
                                _j4["outreach_log"].append({
                                    "date":  date.today().isoformat(),
                                    "type":  "response",
                                    "notes": f"{_resp_type}" + (f" — {_resp_note}" if _resp_note else ""),
                                })
                                _j4.setdefault("followup_schedule", {})["next_due"] = None
                                break
                        save_tracker(_td3)
                        st.toast(f"📨 Response recorded: {_resp_type}", icon="✅")
                        st.rerun()

            if _fj_url:
                with _fa4:
                    st.link_button("🔗 Open JD", _fj_url, use_container_width=True)

            # Tailored docs — show if jd_tailor has run for this job
            _fj_docs = _find_tailor_docs(job)
            if _fj_docs:
                with st.expander(f"📄 Tailored docs ({len(_fj_docs)})"):
                    for _doc in _fj_docs:
                        st.markdown(f"**{_doc.name}**")
                        _doc_text = _doc.read_text(encoding="utf-8", errors="replace")
                        _trunc_suffix = "\n\n*(truncated)*" if len(_doc_text) > 1500 else ""
                        st.markdown(_doc_text[:1500] + _trunc_suffix)
                        st.markdown("---")

            # Interview prep — available for any applied job, surfaced prominently for Interview status
            _fj_status = job.get("status", "")
            _prep_label = "🎯 Interview prep" if _fj_status == "Interview" else "📋 Prep notes"
            _prep_key   = f"prep_{_fj_id}"
            with st.expander(_prep_label, expanded=(_fj_status == "Interview")):
                if st.button("✨ Generate prep brief", key=f"prepbtn_{_fj_id}",
                             disabled=not api_key.is_key_valid(),
                             help="Uses Claude Haiku. Covers technical Qs, behavioural Qs, selling points."):
                    with st.spinner("Building prep brief…"):
                        _prep_prompt   = _interview_prep_prompt(job)
                        _prep_result   = _ai_draft(_prep_key, _prep_prompt)
                    st.session_state[_prep_key] = _prep_result
                _prep_text = st.session_state.get(_prep_key, "")
                if _prep_text:
                    st.markdown(_prep_text)
                    if st.button("💾 Save to job notes", key=f"prepsave_{_fj_id}"):
                        _td_p = json.loads(TRACKER.read_text(encoding="utf-8"))
                        for _jp in _td_p.get("jobs", []):
                            if _jp.get("id") == _fj_id:
                                _existing = (_jp.get("notes") or "")
                                _prep_header = f"### Interview Prep ({date.today().isoformat()})\n\n"
                                _jp["notes"] = _prep_header + _prep_text + "\n\n---\n\n" + _existing
                                break
                        save_tracker(_td_p)
                        st.toast("💾 Prep notes saved to job!", icon="✅")
                        st.rerun()
                elif not api_key.is_key_valid():
                    st.caption("Set API key in sidebar to generate prep notes.")

    # ── OVERDUE ───────────────────────────────────────────────────────────
    if _fu_overdue:
        st.markdown(f"### 🔴 Overdue ({len(_fu_overdue)})")
        for _days_over, _job in _fu_overdue:
            _fu_render_card(_job, f"{_days_over}d overdue", "#ef4444")

    # ── DUE TODAY ─────────────────────────────────────────────────────────
    if _fu_due_today:
        st.markdown(f"### 🟡 Due today ({len(_fu_due_today)})")
        for _job in _fu_due_today:
            _fu_render_card(_job, "Due today", "#f59e0b")

    # ── NO SCHEDULE ───────────────────────────────────────────────────────
    if _fu_no_sched:
        st.markdown(f"### ⚠️ No schedule ({len(_fu_no_sched)})")
        st.caption("These jobs are Applied but have no next follow-up date — seed one now.")
        for _job in _fu_no_sched:
            _fu_render_card(_job, "Needs schedule", "#94a3b8")

    # ── DUE THIS WEEK ─────────────────────────────────────────────────────
    if _fu_this_week:
        with st.expander(f"🟢 Due this week ({len(_fu_this_week)})", expanded=False):
            for _days_left, _job in _fu_this_week:
                _fu_render_card(_job, f"In {_days_left}d", "#10b981")

    # ── UPCOMING ─────────────────────────────────────────────────────────
    if _fu_upcoming:
        with st.expander(f"📅 Upcoming ({len(_fu_upcoming)})", expanded=False):
            for _days_left, _job in _fu_upcoming:
                _fu_render_card(_job, f"In {_days_left}d", "#6366f1")

    if not any([_fu_overdue, _fu_due_today, _fu_no_sched, _fu_this_week, _fu_upcoming]):
        st.info(
            "No applied jobs in the follow-up loop yet. "
            "Use the 📬 Review Queue to triage Found jobs and click ✅ Apply "
            "to start tracking applications."
        )
