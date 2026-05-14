# Saber's Job Search — Streamlit UI

Multi-page dashboard for monitoring the job search. Reads the canonical JSON/MD files at the project root.

## Setup

```bash
pip install -r ui/requirements.txt
```

## Run

From the project root:

```bash
streamlit run ui/app.py
```

Opens at http://localhost:8501.

## Pages

| Page | Purpose |
|---|---|
| 🏠 Dashboard | Weekly KPIs, pipeline funnel, apply-this-week queue, latest fit-scored scan summary |
| 📋 Jobs Kanban | Sortable/filterable tracker table. Edit status, mark applied, save notes |
| 🔍 Scored Scan | Browse LLM-scored candidates from fit_scorer output. Filter by score / verdict / sector |
| 🤝 Recruiter CRM | Recruiters, alumni warm-intro queues, message templates |
| 📅 Weekly Plan | `this_week.md` + `operating_cadence.md` + latest weekly report |
| 📝 Content & Memory | LinkedIn calendar + engagement log + Master Repo + Claude memory |
| ⚙️ Admin | One-click buttons to run the scraper, fit scorer, auto-promoter, weekly report, JD tailor |

## Writeback safety

Every edit creates a `.bak.<timestamp>.json` next to the canonical file. Revert by copying the backup over the main file.

## Limits

- Long-running agents (scraper = 20-40 min) will block the Streamlit UI while running. For long jobs, run from the terminal in a separate window and the UI will pick up the output files when done.
- ANTHROPIC_API_KEY must be set in the shell that launches Streamlit for the Admin-page AI agents to work.
