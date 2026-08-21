## Five likely questions (and model answers)

**1. "This is a business analytics role across sales, marketing, and operations — your background is investment and risk analytics. Why you?"**
The transferable core is the same: define the metric, guarantee the data behind it, and get an executive to act on it. At Moody's I own analytical output that clients' Heads of Risk challenge directly, and I sit on the model governance committee that sets documentation and performance-assessment standards. The domain vocabulary changes; the discipline of defensible numbers, clean pipelines, and committee-ready narratives does not.

**2. "Walk me through a time you rebuilt a manual reporting process."** (STAR 6)
A Moody's valuation workflow was spreadsheet-driven with no logging or versioning — unacceptable under governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line by line, then cut over with a rollback plan. The audit closed satisfactorily and the pipeline became the template for adjacent workflows.

**3. "Tell me about presenting a difficult finding to executives."** (STAR 2)
A client delivery passed every internal check but the portfolio sensitivities contradicted the client's economic intuition under a specific shock. I held the release, decomposed sensitivities by asset class, found a curve-calibration edge case, and walked the product owners and the client's Head of Risk through the remediation. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**4. "How do you improve data quality and accessibility working with engineering teams?"** (STAR 3)
During the Calypso-to-PFaroe migration, client requirements were getting lost between the investment desk and the development team. I scoped requirements into structured Product Owner requests, walked the PO through the business decision logic, and translated dev constraints back into business language. The client onboarded on schedule and the configuration pattern was reused across the whole migration cohort.

**5. "How would you scale a small analytics team's output?"** (STAR 7)
Validation workload was growing faster than headcount, so I built agentic review workflows in Claude Code and Cursor — automated first-pass review, validation scaffolding, and documentation drafts, with a human still signing off on anything governance-critical. Cycle time on comparable modules dropped 30-40%. That is the leverage model I would bring to an analyst team: automate the first draft, protect the judgment layer.

## Three questions to ask

1. Which business decisions are currently being made without the analytics you want this team to produce — advisor engagement, retention, or sales effectiveness? Where is the pain sharpest today?
2. How is the analytics function positioned relative to data engineering — do we own the pipelines and the semantic layer, or consume them? That determines how fast a KPI framework can actually ship.
3. What does the current team look like in size and seniority, and what is the first 12-month mandate the executive team would call a success?

## The one competency gap to prepare for

**Direct people-leadership of a business-analytics team plus commercial BI tooling (Power BI/Tableau, sales/marketing/advisor analytics).** Saber has mentored juniors, led delivery on a three-person study team, and led design of an enterprise engine — but has not managed a standing analyst team, and his visualization stack is Python (Plotly/matplotlib) and Excel, not enterprise BI suites. Own it plainly: "I have led delivery, not a standing team — here is how I'd staff and run one, and here is why picking up Power BI or Tableau is a weeks-not-months problem for someone who has built the pipelines feeding them." Do not bluff a tool name.