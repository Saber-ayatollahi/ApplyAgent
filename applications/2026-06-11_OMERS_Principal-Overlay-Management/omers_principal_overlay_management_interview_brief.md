## Likely Technical Questions

**1. Walk us through how you would build an Equity Risk Premia signal and combine it with macro judgment in an overlay framework.**
> At Ortec I built stochastic ESGs that linked macro regimes (growth, inflation, real rates) to equity returns, correlations, and drawdown behavior - the same scaffolding ERP modeling relies on. I'd start with a multi-factor decomposition (real yield, term premium, credit, earnings yield gap), test signal stability across regimes, then size positions against VaR/CVaR-budgeted risk limits with the qualitative overlay reserved for regime-shift inflection points the systematic model is slow to catch.

**2. How do you size a tail risk hedge using options without bleeding too much carry?**
> I'd frame it as a drawdown-budget problem, not a premium-budget problem: what max plan-level drawdown is acceptable, what's the convexity profile of put spreads vs. outright puts vs. VIX structures across the stress regimes that matter (2008-, 2020-, 2022-style). At Moody's I run base/stress/reverse-stress engines for exactly this kind of payoff design - I'd anchor the hedge sizing to scenario P&L, not implied vol levels alone.

**3. How do you link macroeconomic regimes to equity correlations and drawdowns?**
> The most useful framing in my Ortec work was conditional correlation: stocks/bonds flip sign under inflation regimes, EM correlations spike in USD-strength regimes, factor correlations collapse in liquidity events. I built scenario generators that captured those state-dependent shifts and decomposed risk contribution by factor - that's the layer that tells you whether your equity overlay is genuinely diversifying or just adding beta in a different costume.

**4. You hold sign-off authority - what's an output you've held back, and why?**
> A client run produced portfolio sensitivities that passed internal checks but didn't square with the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, found a short-end curve-calibration edge case, escalated to the PO and the client's Head of Risk, and the defect was remediated upstream. The lesson I carry: mathematically defensible isn't the same as economically defensible.

**5. How would you complement a systematic Overlay framework with qualitative judgment without undermining the discipline?**
> Judgment earns its keep at regime inflections and at the tails - where the systematic model's training data is thinnest. I'd want the framework to make the judgment overlay explicit, sized, and reviewable (an attribution line, not a hidden tilt), with a clear governance trail. That's how Ortec ran its TAA work for committees, and how Moody's runs model-vs-override governance today.

## Sharp Questions to Ask

1. How is the boundary drawn between the Overlay Management book and the underlying public-equity teams' active risk - particularly when an ERP signal and an active manager's positioning disagree?
2. As OMERS transitions toward a total-portfolio approach, where do you see Overlay Management's risk budget evolving over the next 2-3 years - and what's the constraint that's hardest to move?
3. What does success look like in year one for this seat, separately on the passive-equity benchmark delivery side and on the TAA/tail-risk side?

## Competency Gap to Prepare For

**Direct buy-side overlay portfolio-management seat-time.** Saber's portfolio construction, derivatives, and TAA work has been delivered as advisor (Ortec) and as sign-off authority on institutional outputs (Moody's), not as a sitting PM running an overlay book. Prepare to frame the transition: the analytical, governance, and implementation muscles are built; the step is owning the trade, not the analysis. Lean on the UPP merger work and the Ortec committee-facing TAA studies as the closest proxies.