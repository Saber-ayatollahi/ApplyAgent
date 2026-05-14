# ApplyAgent — Improvement Plan
*Created: 2026-05-04 | Status: In progress*

---

## Current State

The pipeline is a 3-stage sequential batch processor:

```
Scrape (jd_scraper.py)
  → Score (fit_scorer.py)
    → Promote (auto_promote.py)
      → [MANUAL: review, tailor, apply, follow up, track responses]
```

Everything after "Promote" is manual. The goal of this plan is to progressively automate the manual layer so that the system surfaces decisions for approval rather than waiting to be told what to do.

---

## Bugs Fixed (2026-05-04)

- [x] UI crash on Scored Scan page when verdicts don't contain `apply_now` / `tailor_and_apply`
- [x] Fit scorer now aborts early on fatal API errors (billing / auth) instead of grinding through all jobs
- [x] UI shows error/warning banner when scorer run failed
- [x] JD text truncated 12,000 → 3,000 chars per call (cost reduction ~70%)
- [x] Max output tokens reduced 800 → 400 (further cost reduction)
- [x] Default model changed to `claude-haiku-4-5-20251001` for scoring
- [x] `start.ps1` launcher created — opens browser automatically

---

## Phase 1 — Data & Infrastructure (Do First)

### 1.1 Gmail Integration *(5th data source)*

**Why:** LinkedIn, Indeed, and other job boards email alerts with pre-extracted job title, company, and URL. Parsing these emails is cleaner and faster than scraping career pages. Also enables tracking recruiter replies and interview invites automatically.

**What to build:** `automation/gmail_scraper.py`
- OAuth 2.0 authentication via Google Cloud Console (one-time setup)
- Search Gmail for job alert emails from: `jobalerts@linkedin.com`, `alert@indeed.com`, `noreply@glassdoor.com`, job alert subjects
- Parse job title, company, URL out of each email
- Output in same format as `jd_scraper.py` so it feeds directly into fit scorer
- Store `token.json` locally — subsequent runs are silent (no browser popup)

**Setup required (one-time, ~10 min):**
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project → Enable Gmail API
3. Create OAuth 2.0 credentials → Download `credentials.json`
4. Place `credentials.json` in `automation/credentials/`
5. First run opens browser to authorize → `token.json` saved

**UI change:** Add Gmail as a source option in the Scrape tab alongside Workday / LinkedIn / Greenhouse / Lever.

**Status:** ⬜ Not started — need code from `C:\Users\PC\Desktop\Job hunt 2026`

---

### 1.2 Nightly Scorer + 72-Hour Urgency Alerts ✅ SHIPPED 2026-05-04

**Why:** Applications submitted within 72 hours of posting have significantly higher callback rates. The current weekly scrape means a Monday posting might not hit the tracker until Friday — well past the sweet spot.

**What to build:**
- Scheduled task running `run_pipeline.py --skip-scrape` every morning at 6am
- New urgency flag in scorer output: `hours_since_posted` field
- UI highlights jobs posted <72 hours in a distinct colour on Kanban and Dashboard
- Morning briefing section on Dashboard: "🔴 X urgent jobs posted in last 24h"

**Scheduling options:**

*Option A — Windows Task Scheduler (laptop must be on):*
```powershell
schtasks /create /tn "ApplyAgent Morning Score" `
  /tr "python C:\Users\PC\Documents\GitHub\ApplyAgent\automation\run_pipeline.py --skip-scrape" `
  /sc daily /st 06:00
```

*Option B — GitHub Actions (runs in cloud, laptop can be off):*
- Add `.github/workflows/nightly_score.yml`
- Store `ANTHROPIC_API_KEY` as GitHub secret
- Commits results back to repo
- Pull changes when you open the app

**Status:** ✅ Shipped 2026-05-04. Sharper than the plan:
- `automation/scan_delta.py` diffs today's scan vs. yesterday's (not just re-scoring stale data)
- `automation/morning_brief.py` scores only the delta (~20-50 roles/day) → $0.01-0.05/day
- Dashboard "🌅 Today's fresh matches" widget shows top 5 ranked, with Open JD + Add-to-tracker quick actions
- Pipeline page has a "🌅 Nightly refresh" one-click button
- `automation/nightly_refresh.ps1` + `install_schedule.ps1` install as Windows scheduled task at 6:30 AM daily

---

## Phase 2 — Agentic Layer (Build After Phase 1)

### 2.1 Gmail → Tracker Status Sync

**Why:** Right now all status updates (recruiter reply, interview invite, rejection) are manual. You have to remember to update the tracker. With Gmail access the agent can do this automatically.

**What to build:** `automation/gmail_status_agent.py`

| Email signal | Action |
|---|---|
| Recruiter replies to an application | Move status → `Recruiter_Screen` |
| Interview invite detected | Move status → `Phone_Screen`, trigger interview prep |
| Rejection email detected | Move status → `Rejected`, log reason |
| No reply after 21 days | Flag as stale, queue follow-up draft |

**Detection approach:** Keyword + sender pattern matching first (cheap, no API call). LLM classification only for ambiguous emails.

**Status:** ⬜ Blocked on Gmail integration (1.1)

---

### 2.2 Auto-Tailor on Tier 1 Promote ✅ SHIPPED 2026-05-04

**Why:** `jd_tailor.py` only runs when you explicitly trigger it. But `auto_promote.py` already knows which jobs just got added as Tier 1. The documents should be ready before you even look at the job.

**What to build:**
- Hook in `auto_promote.py`: after writing each new Tier 1 job to tracker, queue a tailor run
- Output lands in `automation/outputs/` with status "ready for review"
- UI shows a "📄 Draft ready" badge on Tier 1 jobs in the Kanban view

**Cost note:** `jd_tailor.py` uses Opus/Sonnet — only runs on Tier 1 jobs (typically 5-15% of promoted roles) so cost stays manageable.

**Status:** ✅ Shipped 2026-05-04. `auto_promote.py --auto-tailor` spawns one tailor subprocess per new Tier-1 role after commit; outputs land in `automation/outputs/` as `*_prompt.md`. Kanban shows a "📄 ready" column when a draft exists. UI exposes this as a checkbox on the Promote tab.

---

### 2.3 Follow-Up Cadence Agent ✅ SHIPPED 2026-05-04 (in-UI variant)

**Why:** Your tracker already has `followup_schedule.next_due` on every applied job. Nothing acts on it. The "10 outreach messages/week" KPI is aspirational rather than automatic.

**What to build:** `automation/followup_agent.py`
- Runs every morning (same scheduled task as 1.2)
- Reads tracker for all jobs with `followup_schedule.next_due` <= today
- For each: selects appropriate template from `recruiter_crm.json`, personalizes it
- Outputs a "Follow-up queue" for review in the UI — one-click approve/skip per message
- On approve: marks follow-up as sent, sets next due date

**UI change:** New "📬 Follow-ups" tab showing today's queue with approve/edit/skip per message.

**Status:** ✅ Shipped in-UI variant 2026-05-04. Dashboard widget shows overdue / due-today / due-this-week / no-schedule buckets with one-click log-and-advance or skip-and-push-+7d. Cadence defaults to [3, 10, 21] days after `date_applied`. Outreach-log appended on each follow-up.

A scheduled pre-draft variant (generates all follow-up messages overnight, shows a review queue each morning) could be added if needed, but the in-UI queue already makes the 10-outreach KPI trackable.

---

### 2.4 Warm Intro Mapper 🟡 PARTIAL

**Why:** Your Master Repository notes that 70% of Director-level hiring in Toronto finance is referral-driven. Every high-scoring job should be cross-referenced against your CRM and alumni contacts before you apply cold.

**What to build:**
- On every new Tier 1 promotion, check `recruiter_crm.json` + `alumni_warm_intros` for company match
- If match found: surface it prominently in the UI ("⚡ You have a contact at this company")
- Auto-draft the warm intro outreach using the templates in your CRM
- Track whether intro was sent and response received

**Status:** 🟡 Partial. The outreach digest on the CRM page groups contacts by staleness and drafts template-substituted nudges — this covers the "drive 10 outreaches/week KPI" side.

Still missing: the *per-Tier-1-job* cross-reference. When a new role lands at Company X, the UI should show "⚡ 2 CRM contacts at X — send warm intro before applying cold." Next iteration.

---

### 2.5 Interview Intelligence Auto-Trigger

**Why:** When a job moves to `Phone_Screen` or `Onsite`, you currently prep manually. An agent can do most of the prep work automatically the moment the status changes.

**What to build:** `automation/interview_prep_agent.py`
- Triggered when tracker status changes to `Recruiter_Screen`, `Phone_Screen`, or `Onsite`
- Fetches recent company news (last 30 days)
- Maps JD requirements against STAR story bank (Section 6 of Master Repo)
- Recommends top 3 stories per likely question category
- Drafts a role-specific prep document in `automation/outputs/interview_prep_<job_id>.md`
- UI surfaces "🎯 Interview prep ready" notification

**Status:** ⬜ Not started

---

## Phase 3 — Intelligence Upgrades

### 3.1 Competitive Intelligence Monitor

**Why:** Hiring at Director level often happens before jobs are posted. Corporate signals (earnings commentary, restructuring news, platform migrations, senior departures) often leak upcoming hiring activity weeks in advance.

**What to monitor:**
- Target company press releases (earnings, restructuring, new initiatives)
- LinkedIn posts from hiring managers at target companies
- Senior departures at target companies (backfill signal)

**Output:** Weekly briefing added to the Dashboard — "🔔 3 companies showing hiring signals this week"

**Status:** ⬜ Not started — assess after Phase 2 is complete

---

### 3.2 Scoring Intelligence Feedback Loop

**Why:** The scorer currently has no memory. It doesn't know that you applied to 10 model validation roles and got 0 responses, or that 3 of your 4 interviews came from vendor-platform roles. Over time it should adjust.

**What to build:**
- After 60+ applications, analyze: which sectors / titles / fit scores led to responses
- Feed outcome data back as context into the scorer system prompt
- Adjust tier assignments based on your actual response rate, not just profile fit

**Status:** ⬜ Future — needs 60+ applications of data first

---

## Architecture Vision

```
                    ┌─────────────────────────────┐
                    │      MORNING AGENT (6am)      │
                    │  • Score new jobs             │
                    │  • Flag 72hr urgent           │
                    │  • Sync Gmail status          │
                    │  • Queue follow-ups           │
                    │  • Trigger auto-tailor        │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     STREAMLIT DASHBOARD       │
                    │  • Review & approve queue     │
                    │  • Urgency alerts             │
                    │  • Follow-up approvals        │
                    │  • Interview prep             │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
   ┌──────────▼──────┐  ┌─────────▼──────┐  ┌─────────▼──────┐
   │  job_tracker    │  │  recruiter_crm  │  │  outputs/      │
   │  _data.json     │  │  .json          │  │  (tailored     │
   │                 │  │                 │  │   docs, prep)  │
   └─────────────────┘  └─────────────────┘  └────────────────┘
```

**The shift:** From "control panel where you run scripts" → "review queue where the agent has done the work and you make judgment calls."

---

## Cost Estimates (per week)

| Task | Model | Est. calls/week | Est. cost |
|---|---|---|---|
| Nightly scoring (new jobs only) | Haiku | ~50-100 | ~$0.02-0.05 |
| Auto-tailor (Tier 1 only) | Sonnet | ~5-10 | ~$0.10-0.30 |
| Follow-up drafts | Haiku | ~10 | ~$0.01 |
| Gmail status classification | Haiku | ~20 | ~$0.01 |
| Interview prep | Sonnet | ~1-2 | ~$0.05-0.10 |
| **Total** | | | **~$0.20-0.50/week** |

---

## Priority Order

| # | Item | Impact | Effort | Status |
|---|---|---|---|---|
| 1 | Gmail integration (via IMAP app-password) | 🔴 High | Medium | ⬜ Next up |
| 2 | Nightly scorer + urgency alerts | 🔴 High | Low | ✅ Shipped 2026-05-04 |
| 3 | Gmail → tracker status sync | 🔴 High | Low | ⬜ Blocked on Gmail |
| 4 | Auto-tailor on Tier 1 promote | 🟡 Medium | Low | ✅ Shipped 2026-05-04 |
| 5 | Follow-up cadence agent | 🟡 Medium | Medium | ✅ In-UI variant shipped |
| 6 | Warm intro mapper (per-job) | 🟡 Medium | Medium | 🟡 Partial — CRM digest done |
| 7 | Interview prep auto-trigger | 🟡 Medium | Medium | ⬜ Defer to Week 3-4 |
| 8 | Competitive intelligence | 🟢 Low | High | ⬜ Future |
| 9 | Scoring feedback loop | 🟢 Low | High | ⬜ Future (needs data) |

---

## Immediate Next Steps

1. **Retrieve Gmail code** from `C:\Users\PC\Desktop\Job hunt 2026` → port into ApplyAgent
2. **Set up Windows Task Scheduler** for nightly scoring (Option A, no cloud needed)
3. **Add urgency flag** to scorer output and Dashboard UI
4. **Wire auto-tailor** hook into `auto_promote.py`

---

*Last updated: 2026-05-04*
