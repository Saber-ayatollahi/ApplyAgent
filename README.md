# Saber Ayatollahi — Toronto Finance Job Search System

> **Campaign:** 2026-05-03 → 2026-07-12 (10 weeks).
> **Target:** Director / VP roles in Toronto — primary ALM / IRRBB / Model Governance; secondary Vendor-Platform / Client Solutions.
> **Architecture:** 5 Python agents + Streamlit dashboard + persistent Claude memory.

---

## 30-second quick start

**Windows (PowerShell):**
```powershell
cd C:\Users\ayatollS\Downloads\deep-research-report
.\bootstrap.ps1 -SetApiKey          # one-shot install + key + verify
streamlit run ui\app.py              # open dashboard at http://localhost:8501
```

**macOS / Linux:**
```bash
cd /path/to/deep-research-report
SET_API_KEY=1 bash bootstrap.sh
streamlit run ui/app.py
```

What bootstrap does: installs dependencies, optionally saves your `ANTHROPIC_API_KEY`, scaffolds output directories, runs `verify.py` (49 checks).

---

## The weekly pipeline (Fridays)

```bash
# 1. Scrape 155 target companies (~25-40 min, 1,000-1,600 raw candidates)
python automation/jd_scraper.py --expansion

# 2. LLM-score survivors (~15 min with concurrency=6, ~$3-5)
python automation/fit_scorer.py --scan scan_YYYYMMDD.json --concurrency 6

# 3. Preview auto-promote (dry run)
python automation/auto_promote.py --min-score 7

# 4. Commit promotions + expire stale URLs
python automation/auto_promote.py --commit --min-score 7 --expire-stale

# 5. Weekly KPI report
python automation/weekly_report.py
```

Everything is cached — re-runs on the same scan cost $0.

---

## Start of day — the 60-second ritual

**Option A — terminal + editor:**
1. Open `this_week.md` to re-anchor on today's priorities.
2. Check `job_tracker_data.json → kanban_targets_week1` for the week's apply list.
3. Open `operating_cadence.md` for today's slot in the daily ritual.

**Option B — dashboard:**
```bash
streamlit run ui/app.py
```

Seven pages:

| Page | Purpose |
|---|---|
| 🏠 Dashboard | Weekly KPIs, pipeline funnel, apply-this-week queue, latest fit-scored summary |
| 📋 Jobs Kanban | Filterable tracker table; edit status, mark applied, save notes |
| 🔍 Scored Scan | Filter LLM-scored candidates by score / verdict / sector |
| 🤝 Recruiter CRM | Recruiters, alumni warm-intro queues, outreach templates |
| 📅 Weekly Plan | `this_week.md` + `operating_cadence.md` + latest weekly report |
| 📝 Content & Memory | LinkedIn calendar, engagement log, Master Repo, Claude memory |
| ⚙️ Admin | One-click run of all 5 agents |

Every UI edit writes back with a `.bak.<timestamp>.json` safety copy.

---

## File map

| File | Purpose | When to open |
|---|---|---|
| **`README.md`** *(this)* | Entry point, daily ritual, file index | Every morning |
| **`CHANGELOG.md`** | v1 → v4 history, architecture, validated ATS endpoints | Reference |
| **`verify.py`** | Post-install sanity check (49 tests) | After bootstrap; before shipping |
| **`bootstrap.ps1` / `bootstrap.sh`** | One-shot setup | Once per install |
| **`requirements.txt`** | Consolidated Python deps | Once per install |
| **`operating_cadence.md`** | 10-week calendar, daily ritual, KPI targets, follow-up cadence | Every Monday; ref daily |
| **`job_tracker_data.json`** | Live pipeline — 96 roles, 14-status funnel, contacts, outreach log | Every application / interview / Friday |
| **`Saber_Ayatollahi_Master_Repository.md`** | Single source of truth for resumes + cover letters. Tagged bullet library (§5). STAR stories (§6). Two positioning angles (§7) | Before every resume tailoring |
| **`Target_Companies_2026.md`** | 155-firm curated shortlist | When considering a new target |
| **`cover_letter_templates.md`** | 3 templates (ALM-bank / Vendor-platform / Consulting) | Every cover letter |
| **`interview_prep.md`** | IRRBB/ALM/model-risk/LDI technical Q&A, STAR mapping, per-company prep, interview-day protocol | 1 hour before every interview |
| **`recruiter_crm.json`** | Toronto finance recruiters + warm-intro queues + outreach templates | Weekly — parallel with applications |
| **`references_and_salary.md`** | Reference archetypes, CAD comp bands per tier, negotiation scripts | Week 1 (reference priming); final-round week |
| **`linkedin_content_engine.md`** | 12-week post calendar; profile setup; engagement strategy | Every Sunday evening |
| **`this_week.md`** | Active working queue — today's checklist. Replace every Monday | Every morning |
| **`inbox.md`** | Morning-scan raw-leads landing pad. Triage Friday | Every morning |
| **`linkedin_engagement_log.md`** | Per-post engagement metrics. Review monthly | After each Monday post |
| **`campaign_retrospective.md`** | End-of-campaign debrief template | Week 10 |
| **`deep-research-report.md`** | Archival research layer (tokens stripped). Superseded by Target_Companies_2026.md | Reference only |
| **`automation/README.md`** | Automation index + setup + smoke tests + pipeline commands | Before running any agent |
| **`automation/jd_scraper.py`** | Scrape 155 companies (20+ validated Workday + Greenhouse + LinkedIn) | Friday |
| **`automation/fit_scorer.py`** | Fetch JD + LLM-score (1-10, verdict, gaps, resume variants) with caches | After each scan |
| **`automation/auto_promote.py`** | Promote scored roles to tracker; auto-expire stale URLs; backup-safe | After each fit_scorer |
| **`automation/jd_tailor.py`** | JD → tailored resume + cover letter + interview brief | Before every application |
| **`automation/weekly_report.py`** | KPI deltas, stale apps, followups due, interview pipeline, next-week targets | Friday 18:00 |
| **`automation/expansion_companies.py`** | 89-company expansion list (mid-banks, insurers, fintechs, regulators, fund admins) | Read-only reference |
| **`ui/app.py`** | Streamlit dashboard — 7 pages | When monitoring |

---

## The discipline

**Two positioning narratives only.** Primary = ALM/IRRBB/Model Governance. Secondary = Vendor-platform. Everything else retired from outbound — see Master Repo §7.

**Weekly KPIs:**
- 8 tailored applications
- 10 outreach messages (recruiters + warm intros + hiring managers)
- 3 coffee chats
- 1 LinkedIn post
- 2 recruiter conversations

**Every application requires:**
1. JD verified as live.
2. Tracker entry updated (`date_jd_verified`, `urgency`).
3. Resume tailored via `jd_tailor.py`.
4. Cover letter tailored from `cover_letter_templates.md`.
5. Warm intro attempted (via `recruiter_crm.json`) BEFORE submitting if possible.
6. `date_applied` and `followup_schedule.next_due` set post-submit.

**Every interview requires:**
1. Skim `interview_prep.md` for technical block + 2-3 STAR stories.
2. Per-company §3 prep.
3. Re-read latest earnings call transcript (banks, public AMs).
4. Thank-you email within 4 hours.
5. Tracker note within 24 hours.

---

## Week-of-2026-05-04 apply queue (from tracker)

Top 10 Tier-1 matches surfaced by scan v2/v3/v4:

1. `rbc-irrbb-001` — **RBC Director, IRRBB & FTP Model Risk Management** 🔥 near-verbatim match
2. `cibc-quant-001` — CIBC Director, Quantitative Risk Modelling
3. `hoopp-mv-001` — HOOPP Senior Director, Model Validation
4. `bmo-001` — BMO Director, Model Validation (existing)
5. `bmo-mv-002` — BMO Director, Model Validation (2nd team)
6. `scot-treasplat-001` — Scotia AD, Treasury Strategic Platforms (vendor-platform meets ALM)
7. `br-aladdin-bd-001` — BlackRock Aladdin Business Development Director
8. `citi-ntmr-001` — Citi Non-Trading Market Risk VP (IRRBB in Citi-speak)
9. `ivari-alm-001` — ivari AVP, Asset Liability Management
10. `manu-mrm-001` — Manulife Manager/Director, Model Risk Management

See `this_week.md` for full checklist.

---

## Persistent memory

Claude's memory for this project lives in `~/.claude/projects/.../memory/` with six files:

- `user_profile.md` — Saber's career profile
- `feedback_positioning.md` — the 2-angle positioning decision
- `project_campaign.md` — campaign, targets, file map, weekly pipeline
- `feedback_scan_engineering.md` — 10 scraper rules (LinkedIn `OR` is literal, Workday subdomains vary, pagination, etc.)
- `reference_validated_ats.md` — 20+ empirically validated Workday + Greenhouse endpoints
- `feedback_agent_architecture.md` — 5-agent separation of concerns

Future Claude Code sessions in this directory auto-load these.

---

## Limits (known and accepted)

- Tailor outputs markdown — you paste into your own `.docx` template manually.
- LinkedIn guest search throttles after ~60-80 companies; a full 155-company scan takes 25-50 min.
- Fit scorer requires `ANTHROPIC_API_KEY` (paid Claude tier). Dry-run mode works without it.
- Interview practice is not automated. Use `interview_prep.md`; do mocks with a peer.
- Recruiter conversations are human — the CRM tracks state, you make calls.

---

## Ship-readiness

Run `python verify.py` to confirm. Current status:

```
49 pass · 1 warn (API key) · 0 fail
```

See `CHANGELOG.md` for full architecture and validated ATS endpoint list.

---

*Last updated: 2026-05-04 · v1.0 ship release*
