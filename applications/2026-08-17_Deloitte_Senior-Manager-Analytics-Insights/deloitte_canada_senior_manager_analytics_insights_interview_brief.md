## 5 likely technical/practitioner questions

**1. "Walk me through an end-to-end analytics build you led — problem to production."**
Use STAR Story 1 (cash flow projection engine): the prior workflow was spreadsheet-based and non-auditable while clients were asking for reverse-stress and behavioural cash-flow coverage. I architected configurable time-bucketed gap analytics (T+1 to multi-year), embedded behavioural and prepayment logic, and re-engineered the upstream workflow into Python pipelines with auditable logging. Result: a production engine that delivered forward-looking visibility clients had been requesting and materially cut manual effort.

**2. "How do you quality-assure a complex analytical deliverable you didn't build yourself?"**
Use STAR Story 2: outputs passed every internal check but did not square with the client's economic intuition under a specific shock. I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case, escalated to product owners and the client's Head of Risk, and delivered the remediation plan. 48-hour delay; client avoided acting on wrong numbers; the defect became a permanent validation test. Point: mathematically clean is not the same as economically defensible.

**3. "Where have you used optimization, simulation, or statistical modelling to change a client decision?"**
Use STAR Story 4 (Ortec LDI study): calibrated a stochastic scenario generator to client assumptions, ran funding-ratio distributions under base and stressed regimes, decomposed duration-gap contribution to funding-ratio volatility, and presented explicit allocation recommendations. The committee adopted the duration extension and the client returned for further studies. Reinforce with VaR/CVaR asset-liability optimization and near-optimal frontier robustness testing on Ortec GLASS.

**4. "How do you see AI actually being delivered inside an engagement, and where does it break?"**
Use STAR Story 7: validation workload grew faster than headcount, so I built agentic review workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, and documentation drafts — with a human retaining sign-off on governance-critical review. Cycle time on comparable modules dropped ~30-40%. Where it breaks is adoption and control: without validation, monitoring, and explainability owners, teams stop trusting the output. That is where my model-governance-committee experience applies directly.

**5. "Tell me about aligning stakeholders who disagree on a technical answer."**
Use STAR Story 5 (EY IFRS 17): finance, actuarial, and IT were out of sync on data sourcing and CSM mechanics. I built shared requirements documentation, walked each function through the others' constraints, isolated the three decisions needing executive sign-off, and escalated cleanly. The milestone was hit and the documentation was reused on later engagements. Pair with Story 3 (client investment team ↔ dev organization during the Calypso→PFaroe migration).

## 3 questions Saber should ask

1. "How is the Analytic Insights P&L structured for a Senior Manager — what share of the year is sold work versus practice-building, and what does an origination target look like in year one?"
2. "Where is the practice on AI-enabled delivery today — are you shipping client-facing AI solutions, or mostly using AI to accelerate internal delivery? Who owns validation and monitoring standards for those solutions?"
3. "Which client sectors are driving the growth in this team? My client book has been financial services — pensions, insurers, asset managers, bank treasuries — and I'd like to understand how much of the pipeline sits there versus consumer, marketing, or PE-sponsored portfolio work."

## The one competency gap to prepare for

**Formal people-management and engagement economics.** The JD asks for 5+ years leading teams, plus planning, budgeting, staffing, and risk management of multi-workstream engagements. Saber's leadership evidence is real but different in shape: senior review and delegated sign-off authority over other people's work, escalation ownership with clients' Heads of Risk, mentoring junior colleagues, leading the design and delivery of the cash flow engine, leading client onboarding cohorts, and leading a three-person modelling team on the university pension merger. Prepare a crisp two-sentence version: "I have led workstreams, owned quality for work I didn't personally build, and been the escalation point clients call — what I have not carried is a formal P&L or a standing direct-report line, and that is the piece I would expect to build in the first year." Do not improvise numbers on utilization, margin, or headcount managed.