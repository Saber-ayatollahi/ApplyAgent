#!/usr/bin/env python3
"""
weekly_report.py — Generate the Friday weekly campaign report.

Reads:
    job_tracker_data.json
    recruiter_crm.json
    automation/outputs/scan_YYYYMMDD.json (latest)

Writes:
    automation/outputs/weekly_report_YYYYMMDD.md

Content:
- KPI deltas (apps submitted, outreach sent, interviews, coffees)
- Stale applications (> 21 days, no response → propose close)
- Followups due this week
- Interview pipeline
- Recruiter activity
- Fresh candidates from latest scraper run
- Next week's recommended 8 apply targets
- Next week's LinkedIn post topic
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "job_tracker_data.json"
CRM = ROOT / "data" / "recruiter_crm.json"
OUT_DIR = ROOT / "automation" / "outputs"


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-of", help="YYYY-MM-DD — Monday of the week to report on (defaults to most recent Monday)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    if args.week_of:
        week_start = datetime.fromisoformat(args.week_of).date()
    else:
        # most recent Monday
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    tracker = json.loads(TRACKER.read_text(encoding="utf-8"))
    crm = json.loads(CRM.read_text(encoding="utf-8"))
    jobs = tracker.get("jobs", [])

    # --- KPIs ---
    applied_this_week = [
        j for j in jobs
        if parse_date(j.get("date_applied")) and week_start <= parse_date(j["date_applied"]) <= week_end
    ]
    applied_campaign = [j for j in jobs if parse_date(j.get("date_applied"))]

    outreach_this_week = []
    for j in jobs:
        for log in j.get("outreach_log", []):
            d = parse_date(log.get("date"))
            if d and week_start <= d <= week_end:
                outreach_this_week.append((j["id"], log))

    for r in crm.get("recruiters", []) + crm.get("alumni_warm_intros", []):
        d = parse_date(r.get("last_touchpoint"))
        if d and week_start <= d <= week_end:
            outreach_this_week.append((r.get("id"), {"date": r["last_touchpoint"], "channel": "recruiter_crm"}))

    # --- Stale applications ---
    stale_threshold = today - timedelta(days=21)
    stale = [
        j for j in jobs
        if parse_date(j.get("date_applied"))
        and parse_date(j["date_applied"]) < stale_threshold
        and j.get("status") in ("Applied", "Recruiter_Screen", "Phone_Screen")
    ]

    # --- Followups due ---
    followups_due = []
    for j in jobs:
        nxt = parse_date((j.get("followup_schedule") or {}).get("next_due"))
        if nxt and nxt <= today + timedelta(days=7):
            followups_due.append((j, nxt))

    # --- Interview pipeline ---
    in_process = [j for j in jobs if j.get("status") in ("Recruiter_Screen", "Phone_Screen", "Take_Home", "Onsite", "Offer")]

    # --- Pipeline by status ---
    status_counts = {}
    for j in jobs:
        s = j.get("status", "Unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    # --- Latest scan ---
    scans = sorted(OUT_DIR.glob("scan_*.json"))
    latest_scan = None
    latest_scan_path = None
    if scans:
        latest_scan_path = scans[-1]
        latest_scan = json.loads(latest_scan_path.read_text(encoding="utf-8"))

    # --- Build report ---
    targets = tracker["meta"]["weekly_kpi_targets"]
    lines = [
        f"# Weekly Campaign Report — Week of {week_start.isoformat()} → {week_end.isoformat()}",
        f"_Generated {today.isoformat()}_",
        "",
        "## 1. KPI deltas",
        "",
        f"| KPI | Target | Actual | Delta |",
        f"|---|---|---|---|",
        f"| Tailored applications | {targets['tailored_applications']} | {len(applied_this_week)} | {len(applied_this_week) - targets['tailored_applications']:+d} |",
        f"| Outreach messages | {targets['outreach_messages']} | {len(outreach_this_week)} | {len(outreach_this_week) - targets['outreach_messages']:+d} |",
        f"| Coffee chats | {targets['coffee_chats']} | ? (manual log) | — |",
        f"| LinkedIn posts | {targets['linkedin_posts']} | ? (manual log) | — |",
        f"| Recruiter conversations | {targets['recruiter_conversations']} | {len([o for o in outreach_this_week if o[1].get('channel') == 'recruiter_crm'])} | — |",
        "",
        f"**Campaign-to-date: {len(applied_campaign)} total applications submitted.**",
        "",
        "## 2. Pipeline by status",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for s in tracker["meta"]["status_enum"]:
        lines.append(f"| {s} | {status_counts.get(s, 0)} |")

    lines += [
        "",
        "## 3. Interview pipeline (active)",
        "",
    ]
    if in_process:
        lines.append("| ID | Company | Role | Status | Last touch |")
        lines.append("|---|---|---|---|---|")
        for j in in_process:
            lines.append(f"| {j['id']} | {j['company']} | {j['title']} | {j['status']} | {j.get('date_last_followup', '—')} |")
    else:
        lines.append("_No active interviews. Push harder on outreach + applications._")

    lines += [
        "",
        "## 4. Stale applications (> 21 days, no response)",
        "",
    ]
    if stale:
        lines.append("| ID | Company | Role | Applied | Action |")
        lines.append("|---|---|---|---|---|")
        for j in stale:
            lines.append(f"| {j['id']} | {j['company']} | {j['title']} | {j.get('date_applied')} | Close → Ghosted, or final followup |")
    else:
        lines.append("_None._")

    lines += [
        "",
        "## 5. Followups due this week",
        "",
    ]
    if followups_due:
        lines.append("| ID | Company | Role | Next due | Status |")
        lines.append("|---|---|---|---|---|")
        for j, d in followups_due:
            lines.append(f"| {j['id']} | {j['company']} | {j['title']} | {d} | {j.get('status')} |")
    else:
        lines.append("_None. Next review: end of next week._")

    lines += [
        "",
        "## 6. Fresh candidates from latest scan",
        "",
    ]
    if latest_scan:
        lines.append(f"_Latest scan: {latest_scan_path.name}, {len(latest_scan.get('results', []))} new candidates._")
        lines.append("")
        lines.append("| Company | Title | Source | Link |")
        lines.append("|---|---|---|---|")
        for r in latest_scan.get("results", [])[:20]:
            lines.append(f"| {r.get('company')} | {r.get('title')} | {r.get('source')} | [open]({r.get('link')}) |")
    else:
        lines.append("_No scan results found. Run `python jd_scraper.py`._")

    # --- Next week recommended apply targets ---
    lines += [
        "",
        "## 7. Next-week recommended apply targets",
        "",
        "Derived from: Tier 1/2 entries with status=Watch or Found, urgency=High, and no date_applied.",
        "",
    ]
    candidates = [
        j for j in jobs
        if j.get("tier") in (1, 2)
        and j.get("urgency") == "High"
        and not j.get("date_applied")
        and j.get("status") in ("Found", "Watch")
    ]
    candidates.sort(key=lambda j: (j.get("tier", 99), -j.get("fit_score_numeric", 0)))
    for j in candidates[:8]:
        lines.append(f"- `{j['id']}` **{j['company']}** — {j['title']} (Tier {j['tier']}, fit {j['fit_score']})")

    lines += [
        "",
        "## 8. LinkedIn post topic (reminder)",
        "",
        "_See `linkedin_content_engine.md` for the schedule._",
        "",
        "---",
        "",
        f"_Report generated by weekly_report.py at {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}_",
    ]

    stamp = today.strftime("%Y%m%d")
    out_path = OUT_DIR / f"weekly_report_{stamp}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[weekly_report] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
