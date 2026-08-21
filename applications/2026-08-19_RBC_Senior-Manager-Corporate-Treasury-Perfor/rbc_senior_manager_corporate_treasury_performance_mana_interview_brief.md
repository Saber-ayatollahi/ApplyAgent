# Interview Brief — RBC, Senior Manager, Corporate Treasury Performance Management, ALM

## 5 most likely technical questions

**1. "Walk me through how Personal & Commercial balance sheet flows create interest rate exposure, and what Treasury does about it."**
Frame it as repricing mismatch: assets and liabilities reprice on different schedules, and non-maturity deposits and prepayable mortgages behave differently from their contractual terms. At Moody's I oversee duration and repricing analysis under parallel and non-parallel shocks and embed behavioural cash-flow and prepayment assumptions into projection scenarios — the same mechanics, run on institutional client balance sheets. Treasury closes the resulting gap with swaps and funding-mix choices; my day job includes validating the rates, FX, and inflation derivative sensitivities that show whether the hedge is doing what it is supposed to.

**2. "How do you explain a month-over-month move in ALM / net interest income results to a VP?"**
Decompose before you narrate: volume, rate, mix, hedge contribution, and basis, then isolate the one or two drivers that actually moved the number. My standing deliverable at Moody's is exactly this — analytical summaries for senior stakeholders and clients' Heads of Risk translating scenario impacts and balance sheet sensitivities into committee-ready narratives. The discipline I would import is never presenting a variance I cannot attribute to a mechanism.

**3. "Tell me about a time a model output looked defensible but was wrong." (STAR Story 2)**
A client-delivery run produced portfolio sensitivities that passed all internal checks but did not square with the client's economic intuition under a specific rate shock. I held the release under deadline pressure, re-ran sensitivities decomposed by asset class, and found a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was remediated upstream and captured in validation tests, and I became that Head of Risk's direct escalation contact.

**4. "Describe a forecasting or projection system you built." (STAR Story 1)**
Moody's needed forward-looking multi-scenario visibility that the prior spreadsheet approach could not audit. I designed and implemented a multi-asset cash-flow projection engine covering base, stress, and reverse-stress, with configurable time-bucketed gap analytics from T+1 to multi-year, behavioural assumptions and prepayment logic embedded, and macro stress overlays layered on top. It shipped into production and replaced manual workflow time with an auditable pipeline.

**5. "Where would you find time savings in a month-end reporting cycle?" (STAR Stories 6 & 7)**
I have done this twice: parallel-built a Python pipeline against a spreadsheet-driven valuation workflow, ran it in shadow mode for two cycles, reconciled, then cut over with a rollback plan — which closed a governance audit and became the template for adjacent workflows. Separately, agentic AI workflows (Claude Code, Cursor) cut development and review cycle time an estimated 30-40% on comparable modules, with human sign-off retained on anything governance-critical.

## 3 questions Saber should ask

1. "Where does the boundary sit today between this team's ALM results reporting and what Corporate Treasury's own analytics produce — am I explaining their numbers, or independently rebuilding them for the plan and five-year outlook?"
2. "How much of the FTP Centre of Excellence interaction is consuming FTP rates versus challenging the methodology when transfer-priced margin and reported ALM results diverge?"
3. "What does the current month-end cycle actually cost in elapsed days, and which step would you most want automated in the first year?"

## The one competency gap to prepare for

**Management Funds Transfer Pricing, and bank-specific reporting stack (EPM / FOM).** I have no hands-on FTP implementation and have not run a bank's matched-maturity FTP curve. Prepared answer: be direct — "I have not owned an FTP process; I have owned the curve construction, spread calibration, and behavioural cash-flow assumptions that sit underneath one, and I have reviewed how transfer-priced components aggregate into portfolio-level ALM metrics. I would expect to be fluent within a quarter working with the CoE." Do the reading on matched-maturity FTP, liquidity premium components, and how FTP shifts IRR from the business lines to Treasury before the first round. Same posture on EPM/Hyperion and FOM: no experience with the specific tools, strong Excel modelling plus Python/SQL, and a track record of learning enterprise platforms fast (Calypso → PFaroe migration).