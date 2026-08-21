## 5 likely questions + model answers

**1. "Walk me through an analytics product you built end-to-end and the decisions it changed."**
STAR 1: at Moody's the liquidity/cash-flow view was spreadsheet-driven and unauditable. I architected a multi-asset cash-flow projection engine with configurable time buckets (T+1 to multi-year), embedded behavioural assumptions, and base/stress/reverse-stress scenarios. It shipped into production and gave institutional clients forward-looking funding and allocation visibility they previously had to assemble by hand.

**2. "How do you guarantee the integrity of the numbers executives see?"**
Two layers. Process: I sit on Moody's model governance committee - methodology review, documentation and benchmarking standards, model-performance assessment - and I hold delegated sign-off on outputs before release. Engineering: I migrated spreadsheet workflows to Python/SQL pipelines with logging, validation, and version control (STAR 6 - parallel-built, shadow-run for two cycles, reconciled, cut over with a rollback plan; the governance audit closed clean).

**3. "Tell me about a time you had to hold a number back under deadline pressure."**
STAR 2: a client run passed every internal check but the sensitivities didn't square with economic intuition under one rate shock. I held the release, decomposed by asset class, found a curve-calibration edge case, escalated to product owners and the client's Head of Risk with a remediation plan. 48-hour delay; the client avoided acting on wrong numbers; I became their direct escalation contact.

**4. "How do you work with technology and data teams who don't speak your language?"**
STAR 3: during the Calypso-to-PFaroe migration a client's requirements were getting lost between their investment desk and our development org. I scoped their decision logic into structured Product Owner requests, walked the PO through the investment rationale, and translated dev constraints back into business language. Client onboarded on schedule and the configuration pattern was reused across the migration cohort.

**5. "You're not from a wealth-management BI function. Why you?"**
My clients are the buy side - asset managers, pension funds, consultants - so I already know the questions this business asks and the audiences that consume the answers. I've presented to pension investment committees (STAR 4), built the analytics, and owned the governance around it. The tooling layer (Power BI/Tableau) is the thinnest part of the gap and the fastest to close; the judgement layer is the part that takes seven years.

## 3 questions to ask

1. Where does this team sit on the maturity curve today - is the first year about building trusted foundational reporting for sales/ops, or about layering predictive insight on top of data that's already clean?
2. What does the current analytics team look like - size, split between reporting and analysis, and which functions (sales, marketing, ops) have embedded analysts versus centralized support?
3. Which executive decision in the last 12 months would have been made differently if this function had already existed at full strength?

## The one competency gap to prepare for

**People leadership of a standing analytics team, plus commercial-domain analytics (advisor engagement, sales effectiveness, client retention, CRM/marketing data).** My leadership evidence is senior review, mentorship, and escalation ownership inside a 12-person team - not a headcount-managed org - and my analytics domain is investment/risk, not sales funnels. Prepared answer: I've owned the quality bar and the escalation path for a team's output, hired-adjacent through requirements and standards, and the analytical method (define the metric, instrument the data, test it against a decision) transfers directly; ask for the first 90 days to sit with sales and ops leaders before proposing a KPI framework.