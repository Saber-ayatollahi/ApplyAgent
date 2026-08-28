## 5 likely technical questions

**1. "Walk us through how you would assess the portfolio impact of a model or asset-mix change before it goes live."**
Decompose the change by asset class and risk factor first, then quantify: contribution-to-risk and VaR/CVaR shift, duration and currency exposure change, and cash implications for funding the trades. At Ortec I ran exactly this on GLASS — asset-only and surplus optimization plus near-optimal frontier analysis to test whether a recommendation was robust or a corner solution. At Moody's the same discipline is formalized: nothing releases to a client without independent review of calibration, cross-asset interactions, and sensitivity consistency.

**2. "Tell me about a time you caught an error before it reached the client."** (STAR Story 2)
A client run produced portfolio sensitivities that passed every internal check but did not square with the client's economic intuition under one rate shock. I held the release, re-ran sensitivities decomposed by asset class, and found a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours; the client avoided acting on wrong numbers, the defect was remediated upstream and captured in validation tests, and I became that Head of Risk's direct escalation contact.

**3. "You haven't used Charles River or Broadridge. How quickly can you get productive on our platform stack?"**
Own it directly: I have not run Charles River or Broadridge. What I have done is migrate an entire client book from Calypso onto PFaroe PM and PFaroe DB — configuring, validating, and then supporting users on a portfolio management and risk platform, including translating investment-team requirements into Product Owner requests. Platform-specific screens are learnable in weeks; the ability to tell when a system's output is wrong is what took seven years.

**4. "How do you build controls into a high-volume, error-intolerant process?"** (STAR Story 6)
A Moody's valuation workflow was spreadsheet-driven with no logging or versioning — unacceptable under model-governance audit. I parallel-built a Python pipeline, ran it in shadow mode for two cycles, reconciled outputs line by line, and cut over with a rollback plan. The audit closed and the pipeline became the template for adjacent workflows. Controls that are designed in and shadow-tested beat controls bolted on after an incident.

**5. "How would you keep Wealth Managers informed when markets move against the models?"**
Two layers. First, an evidence layer: scenario and stress analysis showing what the move does to positioning and to client outcomes — the same work I package for senior stakeholders today as investment-committee-ready narratives. Second, a discipline layer: a consistent cadence and a single rationale so the field hears one story. At Ortec I delivered this live to pension investment committees, including recommendations they did not initially want to hear.

## 3 questions Saber should ask

1. How is the boundary drawn today between this team's execution mandate and the manufacturing/research teams that set the models — where does judgment live, and where does the team follow the model?
2. What does the current technology roadmap look like for the investment book of record and performance layer, and which platform gaps cost the team the most time this year?
3. What is the shape of the team — how many direct reports, what is the seniority mix, and what does the hiring manager most want changed about how it operates in the first twelve months?

## The one competency gap to prepare for

**Formal people leadership at scale (JD asks for 5+ years managing teams of professionals) and direct discretionary investment management authority.** Saber's leadership evidence is real but different: escalation authority delegated by governance framework, leading a three-person modelling team through the UPP merger, mentoring junior colleagues, and coordinating actuarial/finance/IT/risk workstreams at EY. Prepare a crisp two-minute answer that (a) does not pretend, (b) shows concrete instances of setting direction, holding a standard, and developing someone, and (c) names the specific support he would want in the first year (coaching, an experienced deputy, HR partnership on performance management). Interviewers forgive an honest step-up; they do not forgive an inflated one.