# CLAUDE.md — ApplyAgent

Saber Ayatollahi's Toronto finance job-search system. 5 Python agents (scrape → fit-score → auto-promote → tailor → weekly report) + canonical resume renderer + Streamlit dashboard (`ui/app.py`, 7 pages).

## Non-negotiable rules

1. **Resume honesty.** Every resume/cover-letter claim must trace to `docs/Saber_Ayatollahi_Master_Repository.md`. Never import JD duties as experience. No inflation.
2. **Canonical resume pipeline.** Author `resume_content.json` per `docs/resume_agent_instructions.md`, render with `automation/resume_render.py`. Never ship a generic or hand-built resume.
3. **Comp discipline.** Never reveal current comp (Moody's: $130K base / $150K total). Anchor forward on market.
4. **Warm intro before cold app** wherever possible (`recruiter_crm.json`).
5. **Tracker hygiene.** Every application: JD verified live, tracker entry updated, `date_applied` + `followup_schedule.next_due` set. Tracker writes create `.bak.<timestamp>.json` copies.
6. **Stay employed until a signed offer.**

## Strategy (Master Plan, consolidated 2026-06-21)

Barbell — see `Job_Search_Master_Plan.md`:
- **Spearhead A:** Solutions Engineering / vendor-platform (BlackRock Aladdin, MSCI, S&P, Bloomberg, FactSet…)
- **Spearhead B:** Maple-8 pension / asset-owner buy-side (CPP, OTPP, OMERS, HOOPP, IMCO…)
- **Floor:** Bank ALM/IRRBB / Model Validation (Big-6, EQB)
- **Side-track:** US-remote fintech risk (no visa; EOR/contractor). **Skip:** IB, trading-desk quant capital (FRTB/CCR/CCAR).

Comp target: Director band ~$300–500K TC CAD (repo §9 anchors). Geography: Canada on-site > US-remote-from-Canada > US relocate (TN as Economist/Statistician).

## Hot leads (as of 2026-07-08)

- **HOOPP Sr Manager, Risk Analytics & Modelling (JR102444)** — recruiter screen DONE; HM round = Python coding + exotics/model-dev + trader-facing framing. Quoted $160–180K + 20%; negotiate up at offer stage only. Prep: `docs/HOOPP_JR102444_prep.md`, `docs/HOOPP_story_draft.md`.
- **BlackRock VP Solutions Engineering (Toronto)** — interviewed May 15 with HM Mohsen Namazi; awaiting reply; keep-in-touch drafted. Competing-interest lever for HOOPP.

Live state of record: `data/job_tracker_data.json` (this section is a snapshot — trust the tracker and Claude memory over this file if they disagree).

## Key files

| File | Purpose |
|---|---|
| `Job_Search_Master_Plan.md` | Strategy of record (supersedes US-remote-only plan) |
| `docs/Saber_Ayatollahi_Master_Repository.md` | Single source of truth for all resume/CL claims |
| `data/job_tracker_data.json` | Live pipeline (14-status funnel) |
| `automation/README.md` | Agent index, setup, pipeline commands |
| `docs/resume_agent_instructions.md` | How to author `resume_content.json` |
| `SolutionsEngineering_Targets.md` / `Tier1_BuySide_Targets.md` | Spearhead target lists |

## Dev conventions

- Run `python verify.py` before shipping (`--fast` in pre-commit hook via `scripts/install-hooks.sh`).
- Pipeline runs are cached — re-runs on the same scan cost $0. Fit scorer needs `ANTHROPIC_API_KEY`.
- Windows is the primary runtime (PowerShell scripts); bash equivalents exist.
- Persistent session context lives in Claude's memory system (auto-loaded); this file is the in-repo mirror for coding sessions. Update both when campaign state changes materially.
