# Interview Brief — CI Financial · Director, Business Analytics and Insights

## 5 likely technical/functional questions

**1. "Walk me through an analytics product you built end-to-end."**
Use STAR Story 1: the enterprise multi-asset cash flow projection engine at Moody's. Prior state was manual, spreadsheet-driven, and not auditable; I designed configurable time-bucketed analytics (T+1 to multi-year), embedded behavioural assumptions and stress overlays, and re-engineered the upstream workflow into Python pipelines with logging. Result: a production capability clients were explicitly asking for, with materially less manual effort.

**2. "How have you actually used AI — not talked about it?"**
STAR Story 7. Validation workload was growing faster than headcount, so I built agentic review workflows in Claude Code and Cursor: automated first-pass code review, validation scaffolding, and documentation drafts, with a human retaining sign-off on anything governance-critical. Cycle time on comparable modules dropped an estimated 30-40%. The key design principle is that AI drafts, humans approve — that framing is what makes it adoptable in a regulated firm.

**3. "How do you migrate a critical reporting process without breaking it?"**
STAR Story 6. Parallel-build the Python pipeline, run it in shadow mode for two full cycles, reconcile output line by line against the incumbent, then cut over with a documented rollback plan. That closed a governance audit and became the template for adjacent workflows. Same playbook applies to a BI/dashboard migration.

**4. "Tell me about pushing back on a stakeholder who didn't like the answer."**
STAR Story 2. Sensitivities passed every internal check but didn't square with the client's economic intuition under one rate shock. I held the release under deadline pressure, decomposed by asset class, found a curve-calibration edge case, escalated to product owners and the client's Head of Risk, and walked them through remediation. 48-hour delay; client avoided acting on wrong numbers; I became their direct escalation contact.

**5. "How do you ensure data quality and controls in a self-serve analytics environment?"**
Ground it in the model governance committee work: methodology review, documentation and benchmarking standards, independent review before production release, and escalation of anything not economically defensible. Translate to the CI context — controls at the pipeline layer (logging, validation, reconciliation), plus a clear definition owner for every published metric so the same KPI never means two things in two dashboards.

## 3 questions Saber should ask

1. "What does the current insight-to-decision cycle look like for a business partner — how much of the team's time is spent producing recurring reporting versus net-new analysis, and what would 'good' look like in twelve months?"
2. "Where does this team sit relative to data engineering, data governance, and IT — do we own the semantic/metric layer, or consume it? That determines how fast AI use cases can actually ship."
3. "Of the AI use cases already on the backlog, which one has an executive sponsor and a measurable outcome attached? I'd like to know what the first win is expected to be."

## The one competency gap to prepare for

**Formal people management of an analytics team.** Saber has senior-review authority, mentorship, and escalation ownership within a 12-person modelling services team — but has not carried direct reports with hiring, performance-review, and headcount responsibility. Prepare a crisp, non-defensive answer: name the gap, then evidence the adjacent muscles (setting the review standard others work to, mentoring juniors, coordinating actuarial/finance/IT/PM teams at EY, owning client-facing escalations), and state plainly the intent to step into first-line people leadership. Do not overclaim 'led a team' — CI will reference-check scope.

Secondary probe risk: the BI/cloud tool stack (Tableau, Power BI, Salesforce, AWS/Azure, React/Streamlit). Answer honestly — deep Python/SQL/Plotly/Excel, plus Git and CI/CD, with visualization-tool syntax being a short ramp on top of the analytics judgement that takes years.