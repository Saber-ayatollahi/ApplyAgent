## Likely technical questions (with model answers)

**1. "Walk me through how you would build the annual capital plan analytics for a private real estate book."**
Anchor on the cash flow projection engine (STAR Story 1): start from committed and projected cash flows by asset, bucket them T+1 through multi-year, layer base/stress/reverse-stress overlays, then reconcile projected uses against the approved allocation envelope and pipeline. Be explicit that the engine work was multi-asset institutional, not real estate deal-level — the mechanics (draw/distribution timing, refinancing dates, behavioural assumptions) transfer directly.

**2. "How do you stress-test a leveraged portfolio and assess covenant risk?"**
Describe the parallel and non-parallel rate-shock analytics I oversee at Moody's, plus the Ortec scenario-generator work: build a stochastic macro scenario set, propagate to valuations, debt service, and funding metrics, then measure headroom in each scenario and identify the breach-driving variables. Note honestly that I have run leverage-overlay strategy analysis (three-plan university pension merger) rather than lender covenant testing, and that the analytical structure is the same — thresholds, sensitivities, breach probability.

**3. "How do you decide whether a capital allocation recommendation is robust?"**
Use the Ortec GLASS optimization work: asset-only and surplus optimization on VaR and CVaR, then risk decomposition and contribution-to-risk budgeting, then explicitly explore near-optimal portfolios around the efficient frontier. If the recommendation collapses under small parameter changes, it is not a recommendation — it is a point estimate.

**4. "Tell me about a time your analysis contradicted what a senior stakeholder wanted to hear."**
STAR Story 2: a client delivery run passed every internal check but the sensitivities did not square with economic intuition under one rate shock. I held the release, decomposed by asset class, found a short-end curve-calibration edge case, escalated to the product owner and the client's Head of Risk, and walked through remediation. 48-hour delay; the client avoided acting on wrong numbers; I became their direct escalation contact.

**5. "How do you turn a complex quantitative result into something an investment committee can act on?"**
STAR Story 4: for a Canadian pension client I ran funding-ratio distributions under base and stressed regimes, decomposed the duration gap's contribution to funding-ratio volatility, and presented three explicit allocation options with the trade-off stated in the committee's own terms. Committee adopted the duration extension. Rule of thumb: lead with the decision, then the number, then the method.

## Questions Saber should ask

1. How is the capital plan reconciled against the pipeline mid-year when deal timing slips — is Portfolio Monitoring the arbiter of reallocation, or the analyst supporting the CIO office's call?
2. What does the current leverage reporting stack look like end-to-end (data sourcing, covenant tracking, scenario runs), and where is the biggest manual bottleneck today?
3. Which benchmark set does the Real Estate Group hold itself to, and how much of this role is defending or evolving that benchmark choice versus reporting against it?

## The one competency gap to prepare for

**Direct global real estate / private markets domain knowledge.** No repo evidence of real estate underwriting, valuation of direct property, or private-market capital call mechanics. Prepare a credible 90-second answer: name the transferable spine (portfolio-level analytics, capital allocation frameworks, leverage and liquidity scenario work, IC-facing synthesis), then show homework — be able to speak to core/core-plus/opportunistic risk buckets, cap rate and NOI drivers, LTV/DSCR/ICR covenants, and NCREIF/MSCI real estate index benchmarking. Do not bluff deal experience; frame as the monitoring layer above the deal. Secondary gaps to have short honest answers for: Power BI/Tableau (Python/Plotly and advanced Excel instead) and French (conversational, actively improving).