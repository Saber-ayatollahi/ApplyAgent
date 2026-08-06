## Likely Technical Questions

**1. Walk us through how you'd build a systematic macro signal from raw data to live portfolio.**
Draw on Story 1 (cash-flow engine) and Ortec scenario-generator work: ingest data into a versioned Python pipeline with validation; calibrate the macro driver (rates/inflation/FX) using stochastic scenario generation; backtest the signal with risk decomposition to confirm where return is coming from; shadow-run in production before cutover, as in Story 6 (spreadsheet-to-Python under governance).

**2. How do you do portfolio optimization on VaR/CVaR — and what breaks?**
At Ortec I ran asset-only and surplus (asset-liability) optimization on VaR and CVaR via GLASS. The honest answer is that CVaR optimization is tail-sample-driven, so you have to test robustness around the efficient frontier — explore near-optimal portfolios — because the 'optimal' point is fragile to scenario weighting and parameter assumptions. I also pair it with contribution-to-risk to make sure the allocation is intuitive, not just numerically optimal.

**3. Tell us about your factor investing / asset pricing foundation.**
CFA-level coverage of MPT, CAPM, and multi-factor models, applied at Ortec through risk decomposition and contribution-to-risk on multi-asset portfolios — I'd attribute risk and return to systematic factors, then test whether the SAA was actually delivering the factor exposures the client thought it was. Happy to go deeper on a specific factor framework you use.

**4. How do you maintain high coding standards in a research-driven team?**
Story 6 + Story 7: I treat research code and production code as a continuum — version control, testing, logging, and review from day one, with agentic AI tooling (Claude Code, Cursor) accelerating first-pass review and documentation while a human still signs off on anything governance-critical. I've mentored junior colleagues on this pattern at Moody's.

**5. Tell us about a time you had to push back on a result.**
Story 2: an output that passed every internal mathematical check but didn't square with economic intuition under a specific scenario. I held the release, decomposed sensitivities by asset class, found a curve-calibration edge case, escalated to the product owner and the client's Head of Risk, and we remediated upstream. Built more trust than a clean release would have.

## Questions Saber Should Ask

1. How does IEA partition ownership across data engineering, research, and PM-facing analytics — and where would this role sit on that spectrum on day 60 vs day 360?
2. Which systematic macro strategies are currently in production vs in research, and what's the typical idea-to-production cadence?
3. How is the team using AI tooling today inside the research and engineering loop, and where do you see the highest-leverage next step?

## Competency Gap to Prepare For

**Live systematic strategy ownership at a buy-side asset owner.** Saber's portfolio analytics, optimization, and signal-pipeline work has been delivered to institutional clients (vendor/advisory seat), not as a sit-on-the-desk PM/quant running live CMF-style systematic macro books. Prepare to acknowledge this honestly and pivot to the strong transfer: the GLASS optimization work at Ortec is the same mathematical machinery; the Moody's production analytics work is the same engineering discipline. The leap is the seat, not the skill — and Saber is choosing to make it deliberately.