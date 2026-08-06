## Likely Technical Questions

**1. Walk me through how you would evaluate an external investment manager for a pension mandate.**
At Ortec, manager and strategy evaluation sat inside the ALM/SAA process: we assessed how a strategy's return distribution, duration profile, and liquidity behavior interacted with the plan's liabilities, not just its standalone Sharpe. I'd cover quantitative due diligence (performance attribution vs. benchmark and peers, factor exposures, drawdown behavior, fit with the surplus-VaR/CVaR budget), qualitative (team, process, ownership, capacity, ESG integration), and operational (fees, vehicle, liquidity terms, alignment).

**2. How do you think about LDI hedge ratios for a Canadian DB plan?**
It is a joint decision over return-seeking budget, funded-status volatility tolerance, and the shape of the liability. At Ortec I ran this for pension clients: decompose liability duration and key-rate duration, choose a hedge ratio that targets a tolerable funded-ratio volatility under the scenario generator, then layer leverage (repo, bond futures) so the hedge does not crowd out return-seeking. The UPP study explicitly tested leverage overlay strategies inside the Funding Policy.

**3. VaR vs CVaR for portfolio construction - when do you use which?**
VaR is intuitive and easier to communicate to committees, but it is silent on the tail and not subadditive. CVaR (expected shortfall) is the better optimization objective for pension surplus work because the bad tail is precisely what threatens funded status and contribution stability. At Ortec I ran both asset-only and surplus optimizations on VaR and CVaR via GLASS, and used near-optimal frontier analysis to check that recommendations weren't knife-edge.

**4. How would you structure FX and derivative overlays for a global equity sleeve?**
Start from the liability: Canadian DB liabilities are CAD, so unhedged foreign currency is an uncompensated risk relative to the plan's funded-status objective. I would size the equity FX hedge ratio based on correlation-with-liabilities and historical contribution to surplus volatility, then implement via rolling forwards with explicit collateral/liquidity budgeting. At Ortec I performed currency-hedging analysis for international clients and modeled the cash-flow and liquidity impact of overlay programs.

**5. Tell me about a time you escalated a model output you didn't trust.**
(STAR Story 2.) At Moody's a portfolio-sensitivity run passed internal checks but didn't square with the client's economic intuition under a specific rate-shock. I held the release, decomposed by asset class, found a short-end curve-calibration edge case, and escalated to the product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; defect was fixed upstream; the Head of Risk later used me as a direct escalation contact.

## Questions Saber Should Ask

1. How is the team currently split between DB funded-status work and DC participant-options work, and where is this seat expected to spend the most time in year one?
2. What is the current state of the liability-hedging and derivative-overlay program - in-house implementation, external manager, or hybrid - and what is the next planned evolution?
3. How does RBC's Pension Investments team interact with RBC GAM's broader manager-research and ESG functions - do you leverage that platform or run independent diligence?

## Competency Gap to Prepare For

**Direct private-markets manager due diligence experience (PE, private credit, infrastructure, real estate).** The JD explicitly names public AND private markets. Saber's manager-evaluation depth sits on the public-market and multi-asset overlay side, with private exposures handled at the ALM/allocation layer rather than at fund-by-fund underwriting. Be ready to: (a) describe the private-markets framework analytically (J-curve, vintage diversification, cash-flow pacing, NAV smoothing, valuation lag, fee/carry waterfalls), (b) point to the cash-flow projection engine work at Moody's as directly relevant infrastructure for private-asset pacing models, and (c) frame the gap as a fast ramp rather than a blocker.