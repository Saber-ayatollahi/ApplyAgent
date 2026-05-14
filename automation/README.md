# Automation agents

Five Claude-powered Python agents that run the Saber Ayatollahi job-search pipeline. Each agent is standalone and runs against the canonical artifacts in the project root.

| Script | Purpose | Run cadence |
|---|---|---|
| `jd_scraper.py` | Hit 155 target careers pages (20+ validated Workday APIs + Greenhouse + LinkedIn guest search) → pull new postings → dedupe against tracker | Weekly (Fridays) |
| `fit_scorer.py` | Rule-triage + LLM fit-score (1-10, verdict, skill gaps, resume variants) each surviving candidate. Fetches JDs, caches to disk | After each scan |
| `auto_promote.py` | Promote scored roles ≥ threshold to tracker (backup-safe); auto-expire entries whose URLs disappeared | After each fit_scorer run |
| `jd_tailor.py` | Single-role: JD + Master Repo + cover templates → tailored resume + cover letter + interview brief | On-demand, before any application |
| `weekly_report.py` | Read tracker + CRM → weekly KPI deltas, stale apps, followups due, LinkedIn posting plan | Friday 18:00 |

---

## Setup (one-time)

### 1. Python version
Python **3.9 or newer** (tested with 3.10 / 3.11 / 3.12). Check with:
```bash
python --version
```

### 2. Install dependencies

```bash
pip install anthropic requests beautifulsoup4 python-dateutil
```

### 3. Set your Anthropic API key

**Windows PowerShell** (recommended for this project):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```
Make it persistent:
```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

**Windows Command Prompt:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-...
```

**macOS / Linux bash:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at https://console.anthropic.com.

### 4. Optional — override the model

The tailor agent defaults to Claude Opus 4.7 (`claude-opus-4-7`) with Claude Sonnet 4.6 (`claude-sonnet-4-6`) fallback. To override:

```powershell
$env:JD_TAILOR_MODEL = "claude-opus-4-7"
$env:JD_TAILOR_FALLBACK = "claude-sonnet-4-6"
```

---

## Smoke tests (run after setup)

From the project root:

```bash
# 1. Weekly report — reads tracker, produces a report. No API calls, no network.
python automation/weekly_report.py

# 2. JD scraper — Workday API only for one company (quick, one-shot)
python automation/jd_scraper.py --company "BMO"

# 3. Fit scorer — rule stage only (no LLM call, no API key needed)
python automation/fit_scorer.py --scan scan_v4.json --dry-run

# 4. Auto-promote — dry run shows what would be added/expired
python automation/auto_promote.py

# 5. JD tailor — uses a tracker entry with its URL
python automation/jd_tailor.py --job-id bmo-001 --dry-run
```

Successful output lands in `automation/outputs/`.

## The end-to-end pipeline (weekly cadence)

```bash
# Friday 08:00 — start scan
python automation/jd_scraper.py --expansion           # ~25 min, 155 companies
python automation/fit_scorer.py --scan scan_YYYYMMDD.json --concurrency 6   # ~15 min LLM scoring
python automation/auto_promote.py --min-score 7       # dry run: preview
python automation/auto_promote.py --commit --min-score 7 --expire-stale   # commit
python automation/weekly_report.py                    # Friday report

# Monday 07:00 — UI for monitoring
streamlit run ui/app.py
```

---

## Known limitations (be honest with yourself)

- **LinkedIn scraping is unreliable.** LinkedIn detects and throttles unauthenticated scrapes. The guest-search endpoint works ~30% of the time; the rest return 429 / HTML that contains no job cards. Workday API is the primary reliable source for Workday-hosted tenants. If the scraper returns zero results, run it again later or check manually.
- **Workday location filters vary by tenant.** The scraper uses `searchText="Toronto"` instead of a country GUID — catches roles where "Toronto" appears in the title or description. Some Canada-only roles without "Toronto" in the title may be missed; trade-off for reliability.
- **JD fetching from arbitrary URLs** works for static HTML careers pages. It fails on JS-rendered SPAs (e.g. SmartRecruiters, some Greenhouse). In that case: paste the JD text into a file and use `--jd-file path/to/jd.txt`.
- **Tailor output is a markdown draft.** You still need to paste into your Word resume template (manual step) and human-edit the cover letter before sending. The agent writes; you ship.

---

## Why these three agents

These are the compound-interest investments of the campaign:
- `jd_tailor.py` — each run saves ~90 min of manual tailoring; used 8+ times/week ≈ **12 hrs/week saved**.
- `jd_scraper.py` — catches roles you'd otherwise miss for a week; **~5 hrs/week saved**.
- `weekly_report.py` — replaces the manual "where am I in my funnel" scan; **~2 hrs/week saved**, also enforces consistency.

**Total: ~19 hrs/week returned** — more than enough to absorb interviews, prep, and outreach when the pipeline heats up in Weeks 5-8.

---

## A note on dogfooding

Building these agents is also a **portfolio artifact for interviews** — especially at BlackRock Aladdin, Bloomberg, MSCI, S&P Global, SS&C Algorithmics, or any Claude-Code-curious bank. If someone asks "what have you built recently with agentic AI?" — demo this system. It exactly matches the positioning on the Moody's experience bullet points.
