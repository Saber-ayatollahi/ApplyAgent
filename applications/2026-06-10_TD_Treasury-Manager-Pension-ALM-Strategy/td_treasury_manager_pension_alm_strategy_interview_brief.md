## Likely Technical Questions

**1. Walk us through how you'd structure a funded-status stress test for a Canadian DB plan.**
At Ortec I built these end-to-end: stochastic ESG calibrated to the plan's economic assumptions, run funded-ratio distributions under base and stressed regimes, then decompose funded-status volatility into rate, equity, credit, inflation, and FX contributions. The deliverable is a committee narrative tying each driver to an SAA or hedging lever - not just a distribution chart.

**2. How would you approach onboarding a new investment manager and the associated transition?**
Treat it as a project with three workstreams: legal/IMA and operational setup, transition management (in-kind vs cash, market-impact analysis, interim hedging), and post-transition validation against benchmark and risk targets. I ran the analogous discipline migrating clients from Calypso to PFaroe at Moody's - scoping requirements, managing timelines and dependencies, and validating outputs post-go-live.

**3. Talk us through LDI design for a plan whose liability duration is extending.**
From my UPP work: quantify the duration gap and its contribution to funded-status volatility, model extension via physical long bonds vs. derivative overlays (cost, collateral, liquidity drag), stress under non-parallel shocks and curve twists, and present trade-offs against SAA return objectives. Committee usually wants the decision framed as marginal funded-ratio volatility reduction per unit of cost.

**4. How do you ensure data integrity when implementing a new portfolio analytics platform?**
Define data requirements up-front against the analytics use cases (performance, risk, ALM), build reconciliation between source-of-truth feeds and the platform, shadow-run against the legacy environment for at least two cycles, and document exceptions with owners. I did this on every PFaroe migration and on the spreadsheet-to-Python rebuild for governance audit.

**5. How do you communicate complex risk results to a pension governance committee?**
Lead with the decision, not the math: one-sentence answer, one chart showing funded-status impact, then drivers and recommendation. I presented to investment committees at Ortec and to client Heads of Risk at Moody's - the discipline is translating sensitivities into 'what changes about how we run the plan.'

## Questions to Ask

1. How is the Pension Investment team structured across Treasury, and where does this role's project portfolio sit relative to the new analytics-platform implementation you mention in the JD?
2. What does the current funded-status risk framework look like, and where is the team prioritizing enhancements - stress methodology, LDI design, or reporting?
3. How does the team interact with the external actuary and investment managers on funding valuations vs. accounting basis, and where do friction points typically arise?

## Competency Gap to Prepare For

**Bank-internal Treasury governance processes (SOX vendor audit, third-party risk management, business continuity).** Saber has model governance, control documentation, and IFRS 17 governance experience from Moody's and EY, but not TD-internal SOX/TPRM processes specifically. Frame as: 'I've operated within formal governance frameworks - delegated sign-off, documentation to validation standards, and SOX-relevant control documentation at EY - and would expect a short ramp on TD's specific Treasury process taxonomy.'