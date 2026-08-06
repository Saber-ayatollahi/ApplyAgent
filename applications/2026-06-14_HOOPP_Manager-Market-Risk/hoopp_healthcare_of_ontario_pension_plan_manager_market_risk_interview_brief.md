## Likely Technical Questions

**1. "Walk us through how you would set up risk attribution for a multi-asset Capital Markets book."**
Start from the security-level exposures and aggregate up: decompose total risk into factor contributions (rates, credit spread, equity beta, FX, inflation) using a covariance-based decomposition, then link changes period-over-period to trading activity vs. market moves vs. parameter updates. At Ortec I ran contribution-to-risk and near-optimal frontier work on the GLASS platform; at Moody's I review aggregation logic from security level to portfolio-level metrics — same discipline, different tooling.

**2. "How do you design a stress test that is actually decision-useful, not just a regulatory exercise?"**
Three principles: (i) anchor scenarios to a real economic narrative the PM can argue with, not just a historical replay; (ii) decompose the impact by factor and asset class so the source of pain is identifiable; (iii) pair every stress with a reverse-stress to find what break would matter. At Moody's I embedded base, stress, and reverse-stress scenarios with behavioral overlays into the cash flow engine so the output landed on the investment-decision table, not just the compliance file.

**3. "VaR vs CVaR — when do you prefer one over the other for a pension book?"**
VaR is the cleaner communication tool and ties to capital/limit frameworks; CVaR captures tail severity, which matters more for a long-horizon pension fund whose worst-case drawdowns drive funded-status volatility. At Ortec I ran portfolio optimization on both — asset-only and asset-liability/surplus — and used CVaR for the tail-sensitive mandates and the leverage-overlay testing. For HOOPP's funded-status orientation I'd lean CVaR for tail work, VaR for daily limit monitoring.

**4. "Tell us about a time you held a release because the numbers didn't pass the smell test."** (STAR Story 2)
A client run produced sensitivities that passed internal checks but didn't square with the client's economic intuition under a specific rate shock. I held the release, decomposed by asset class, isolated a curve-calibration edge case at the short end, escalated to product owners and the client's Head of Risk, and walked through remediation. Delayed delivery 48 hours; client avoided trading on wrong numbers; I became their direct escalation contact.

**5. "How do you use AI tools without losing the right to sign off?"** (STAR Story 7)
AI accelerates the first pass — code generation, validation scaffolding, documentation drafts, anomaly detection — but human review owns governance-critical sign-off. At Moody's I built agentic workflows in Claude Code and Cursor that cut cycle time ~30-40% on comparable modules. The discipline is that every AI-generated output is treated as a draft requiring independent review of the math and the data, not as a finished answer.

## Sharp Questions to Ask

1. **"How does the Market Risk team's independent voice get heard at the asset-allocation table — what does the escalation path look like when your view diverges from the PM's?"**
2. **"Where is the team on the AI-tooling curve — are you piloting agentic workflows for risk analytics, and where do you see the human-in-the-loop boundary settling?"**
3. **"Capital Markets at HOOPP spans public equity, fixed income, derivatives, and multi-asset — would this seat cover the breadth or have a 'selective focus' from day one, and how does that shape the first six months?"**

## The One Competency Gap to Prepare For

**Buy-side trading-desk vernacular and sell-side product machinery (live trade lifecycle, prime-broker margining, intraday VaR backtesting, dealer-side derivatives ops).** Saber's risk work has been institutional/ALM-side rather than embedded next to a trading desk. Frame honestly: the analytical machinery (VaR/CVaR, sensitivities, attribution, stress testing, derivatives sensitivities) transfers cleanly; the day-to-day desk cadence is the learning curve. Lean into Ortec GLASS optimization and Moody's derivatives validation as the proof of the analytical depth; signal eagerness to absorb the desk-cadence piece quickly.