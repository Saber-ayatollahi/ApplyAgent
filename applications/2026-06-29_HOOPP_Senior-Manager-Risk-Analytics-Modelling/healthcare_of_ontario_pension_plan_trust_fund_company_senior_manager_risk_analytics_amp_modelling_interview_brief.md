## Likely technical questions

**1. Walk us through how you would model a vanilla interest-rate swap and a payer swaption inside a risk system, and what you'd review before signing the output off.**
For the swap: dual-curve framework — OIS discounting, projection curve from the relevant IBOR/RFR fixings, par/zero/forward bootstrap, and DV01 attributed to key-rate buckets. For the swaption: Black or shifted-SABR depending on the rate regime, vol surface calibrated to ATM and the relevant skew, and Bachelier for negative-rate environments. Before sign-off I check curve construction, spread calibration, cross-asset consistency of sensitivities, and that scenario shocks (parallel and non-parallel) move the position in the economically defensible direction — that's the discipline I run today at Moody's.

**2. How do you validate a new instrument or model going into the risk system?**
Document the intended use and methodology, benchmark against an independent implementation or analytical limit case, test sensitivities against known-direction shocks, reconcile against a vendor or market quote where one exists, and stress the model at the boundaries (deep ITM/OTM, extreme curves, near-expiry). Then assess ongoing performance through back-testing of P&L vs. risk explain and exception reporting. That's the SR 11-7 / OSFI E-23 shape of validation I operate within today.

**3. You found a portfolio sensitivity that passed every internal check but didn't square with the trader's intuition. What did you do?**
This is real — short-end inversion edge case in curve calibration. I held the release, decomposed sensitivities by asset class, identified the calibration issue, escalated to the product owner and the client's Head of Risk, and walked through remediation. Release slipped 48 hours; client avoided acting on wrong numbers; the defect was captured as a validation test. The principle: mathematical defensibility isn't the same as economic defensibility, and the sign-off attests to both.

**4. How would you measure and monitor market risk on a portfolio that includes derivatives, hedge funds, and pension liabilities together?**
Decompose by risk factor, not by product: rates (KRD across the curve), credit spread, FX, equity, inflation, and liquidity. Hedge funds get factor-mapped or proxied where look-through is limited. Liabilities enter as a long-duration short position in the rate factors plus inflation sensitivity. Aggregate via Monte Carlo with a calibrated scenario generator — that's what I did at Ortec on GLASS for pension clients: VaR/CVaR on the surplus, contribution-to-risk by factor, and stress on the joint asset–liability position rather than just the asset book.

**5. Where do you actually use AI agents and LLMs in your modelling work today?**
Agentic workflows in Claude Code and Cursor IDE for first-pass code generation, validation scaffolding (test cases against analytical limits), anomaly detection on output diffs across runs, and drafting model documentation. Human signs off on anything governance-critical — the LLM accelerates the mechanical work, not the judgment. Net ~30–40% reduction in cycle time on comparable modules. Adoption is being explored more broadly on the team.

## Questions Saber should ask

1. How is the line drawn between the Risk Analytics & Modelling team and the trading desks on instrument coverage — does the team own the production model, or is it independent challenge of a model the desk owns?
2. What does the current toolchain look like for derivatives and hedge-fund modelling — is there a single vendor risk system or a mix, and where is the team investing next?
3. How is the team currently using (or planning to use) LLMs and AI agents in the modelling workflow — is there appetite for what I've been building, or is the governance posture more conservative?

## The one competency gap to prepare for

**Hedge-fund risk modelling specifically.** The repo has multi-asset and derivatives depth and pension-liability depth, but hedge-fund-specific factor proxying / returns-based style analysis / illiquidity adjustment is adjacent rather than direct experience. Be ready to talk about how I'd approach it (factor regression, peer-group proxies, NAV-lag adjustment, treating illiquidity as a separate risk axis) and to be honest that I haven't owned a hedge-fund book end-to-end. Frame it as a fast-ramp area, not a claimed strength.