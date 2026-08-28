## Five likely technical / scenario questions

**1. "You haven't run a VOC program. Why should we believe you can build the Client Insights Factory?"**
The factory is three problems: integrating heterogeneous sources into one trusted view, building predictive capability on top, and making executives act on it. I've done all three with different inputs — I review the aggregation logic that turns security-level data into a single portfolio-level view, I built a multi-scenario projection engine from scratch, and I hold delegated sign-off on what gets released. The domain (survey, complaint, frontline signal) is learnable in a quarter; the engineering-plus-governance muscle is not.

**2. "Walk me through building an analytics engine from nothing."** (STAR Story 1)
At Moody's, forward-looking liquidity visibility was spreadsheet-based and unauditable while clients were asking for reverse-stress and behavioural coverage. I architected configurable time-bucketed analytics (T+1 to multi-year), embedded behavioural and prepayment assumptions, layered macro stress overlays, and rebuilt upstream workflows into Python pipelines with logging. Shipped to production and became the delivery standard.

**3. "How do you make a predictive model trustworthy enough that a business will act on it?"** (STAR Story 2)
A client run passed every internal check but the sensitivities didn't square with economic intuition under one rate shock. I held the release, decomposed by asset class, found a curve-calibration edge case, escalated to the product owner and the client's Head of Risk, and got it into the validation test suite. 48-hour delay; the client avoided acting on wrong numbers. Trust comes from being the person who stops the release, not the person who ships on time.

**4. "Where does AI actually help, versus where is it theatre?"** (STAR Story 7)
Validation workload was outgrowing headcount, so I built agentic workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, anomaly detection, and documentation drafts — roughly 30-40% cycle-time reduction on comparable modules. The rule I kept: humans sign off on anything governance-critical. AI compresses the drafting and detection layers; it doesn't own the decision.

**5. "How do you link analytics to a financial number leadership will defend?"** (STAR Story 4)
At Ortec I decomposed the contribution of duration gap to funding-ratio volatility, ran outcome distributions under base and stressed regimes, and gave the investment committee an explicit trade-off with a recommended action — which they adopted. Same method for CX economics: decompose the outcome variable, attribute the drivers, quantify the delta from a candidate action, then stress the assumption you're least sure of.

## Three questions Saber should ask

1. What exists today — is there a VOC platform and taxonomy to inherit, or is the first year a greenfield build, and how much of the data engineering sits in my team versus Data/AI?
2. When a CX economics model says a top irritant is worth less than the business assumed, who arbitrates, and has that call actually been made yet?
3. What does the team look like on day one — headcount, mix of analysts versus engineers, and which capabilities are you expecting me to hire rather than inherit?

## The one competency gap to prepare for

**People leadership at VP scale and marketing-domain fluency.** The repo evidences mentorship, a three-person project team, and heavy cross-functional influence — not a large direct-report organization or a marketing/CX P&L. Prepare a crisp answer: how you'd structure the function's first 90 days, what you'd hire first, and how you've led through influence across Finance, IT, actuarial, product, and client teams. Do not overclaim direct management scope; lead with build-and-influence evidence and a concrete org plan.