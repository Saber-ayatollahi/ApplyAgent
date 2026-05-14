# Changelog

## v1.0 — 2026-05-04 — Ship-ready release

This is the packaged release. Everything compiles, every agent has been smoke-tested, end-to-end pipeline is documented.

### System architecture

5-agent pipeline + 7-page Streamlit UI:

```
jd_scraper.py  →  scan_YYYYMMDD.json          (raw: title + URL + sector)
    ↓
fit_scorer.py  →  scan_YYYYMMDD_scored.json    (LLM-scored: fit 1-10 + verdict + gaps + resume variants)
    ↓
auto_promote.py →  job_tracker_data.json      (roles ≥ threshold promoted; stale expired)
    ↓
jd_tailor.py   →  outputs/<co>_<role>_<date>.md  (tailored resume + cover letter + interview brief)
    ↓
weekly_report.py →  weekly_report_YYYYMMDD.md  (KPIs, stale, followups)
```

### Versions of the scan

- **v1** (initial): 66 companies, 7 LinkedIn keywords, no pagination, strict company-name prefix match. 407 candidates.
- **v2** (expanded): 66 companies, 18 LinkedIn keywords, pagination, fuzzy brand match, negative filter. 804 candidates.
- **v3** (expansion): +89 more companies (Fairstone, ivari, IMCO, Canada Life, Canada Guaranty, MCAP, mid-banks, insurers, fintechs, regulators, fund admins, etc.). +304 deduped. Merged total 1,063.
- **v4** (ATS validation): 20+ validated Workday tenants + Greenhouse (CIBC board `search` not `CIBC-External`, CPP on `wd10`, Brookfield on `wd5`, CAAT = `caatpension`, etc.). Workday API contributes 494 / LinkedIn 1,093 = **1,588 total candidates**.
- **v4 scored** (fit scorer): rule-triage drops 1,088 junk titles; 500 survivors score via Sonnet-4.6 with JD fetch + cache. Produces fit 1-10 + verdict + skill-gaps + applicable resume variants per role.

### Tracker

- Schema v2: 14 status states (Watch / Found / JD_Verified / Tailoring / Applied / Recruiter_Screen / Phone_Screen / Take_Home / Onsite / Offer / Rejected / Ghosted / Withdrawn / Expired)
- 96 roles tracked post-Tier-1 merge from v2/v3 scan
- Per-role: tier, fit_score, fit_score_numeric, fit_verdict, resume_variants, primary_variant, urgency, expected_comp_band_cad, fit_notes, keywords, contact{}, outreach_log, followup_schedule, resume_file, cover_letter_file
- kanban_targets_week1.apply_this_week = top-10 priority queue

### What's in the package

**Docs (14 markdown + 3 JSON):**
- `README.md` + `CHANGELOG.md`
- `Saber_Ayatollahi_Master_Repository.md` — tagged bullet library + STAR stories + positioning (primary ALM/IRRBB, secondary Vendor-Platform, 5 retired angles)
- `Target_Companies_2026.md` — curated 155-firm shortlist
- `cover_letter_templates.md` — 3 templates (ALM-bank / Vendor-platform / Consulting)
- `interview_prep.md` — IRRBB/ALM/model-risk/LDI Q&A + 10 STAR stories + per-company prep
- `operating_cadence.md` — 10-week calendar with weekly KPIs
- `references_and_salary.md` — reference archetypes + CAD comp bands + negotiation scripts
- `linkedin_content_engine.md` — 12-week post calendar
- `this_week.md`, `inbox.md`, `linkedin_engagement_log.md`, `campaign_retrospective.md` — workflow files
- `deep-research-report.md` — archival
- `job_tracker_data.json`, `recruiter_crm.json`

**Automation (5 agents + infrastructure):**
- `automation/jd_scraper.py` — 155-company scraper; Workday + Greenhouse + LinkedIn; validated endpoints
- `automation/fit_scorer.py` — rule-triage + LLM scoring; JD + fit caches
- `automation/auto_promote.py` — promotes scored roles; expires stale; backup-safe
- `automation/jd_tailor.py` — single-role tailor; dry-run mode; preflight
- `automation/weekly_report.py` — Friday KPI generator
- `automation/expansion_companies.py` — 89-company expansion list
- `automation/README.md` — setup + smoke tests + pipeline commands
- `automation/outputs/` — ephemeral outputs; survives clone via `.gitkeep`

**UI (Streamlit):**
- `ui/app.py` — 7-page dashboard
- `ui/requirements.txt`, `ui/README.md`

**Bootstrap + verify:**
- `requirements.txt` — consolidated Python deps
- `bootstrap.ps1` — Windows PowerShell one-shot setup
- `bootstrap.sh` — macOS/Linux one-shot setup
- `verify.py` — post-install sanity check
- `.gitignore` — ignores ephemeral outputs + caches + backups

**Persistent memory (at `~/.claude/projects/.../memory/`):**
- 6 memory files: user profile, positioning, campaign, scan engineering, agent architecture, validated ATS
- `MEMORY.md` index

### Validated ATS endpoints (v4)

- Workday (20+): TD, BMO, CIBC (`search`), HOOPP (wd10), OMERS, OTPP, CPP (`cppib/wd10/cppinvestments`), OPTrust, CAAT (`caatpension/wd10/Careers`), CDPQ, Brookfield (`wd5`), AGF, BlackRock (wd1), Vanguard (wd5), Invesco (wd1), Wellington (wd5), Morgan Stanley, Deutsche Bank, State Street (wd1), Northern Trust (wd1), S&P Global (wd5), SS&C (wd1), Manulife, Sun Life, iA, RGA (wd1)
- Greenhouse: Canada Infrastructure Bank

### Known limits

- LinkedIn guest search throttles after ~60-80 companies. Full 155-company scan takes ~30-50 min.
- Workday `locationCountry` GUIDs vary per tenant — we use `searchText="Toronto"` + Python location filter instead.
- Tailor output is markdown; paste into your own `.docx` template (last-mile is intentionally manual).
- Fit scorer requires `ANTHROPIC_API_KEY` (paid tier). Dry-run mode works without it.
- Weekly KPI targets are editable in `job_tracker_data.json → meta.weekly_kpi_targets`.
