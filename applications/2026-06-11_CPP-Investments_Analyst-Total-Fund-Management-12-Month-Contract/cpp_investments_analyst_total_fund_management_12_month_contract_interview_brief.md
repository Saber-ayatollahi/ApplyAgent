## Likely technical questions (with model answers)

**1. Walk us through a typical day on your desk at Moody's — what does your validation and reconciliation workflow look like?**
Daily run produces valuation, sensitivity, and ALM outputs for client portfolios. I review curve construction, spread calibration, and cross-asset sensitivities, then cross-check portfolio-level aggregates against prior-day records and expected scenario behavior. Discrepancies get decomposed by asset class; if root-caused upstream (curve handling, calibration edge case), I escalate to product owners with a remediation plan before release.

**2. Describe the trade lifecycle and where front-office, middle office, and operations interact.**
Front-office captures the trade and economic intent; middle office books, enriches, and confirms; operations handles settlement, collateral, and cash. Breaks usually surface at confirmation, settlement, or PnL reconciliation. I'd be honest that my hands-on lifecycle exposure is on the analytics-validation side at Moody's and the requirements-scoping side during the PFaroe migration — I've worked adjacent to ops teams but haven't owned a settlement queue. I learn fast and would close that gap quickly on the desk.

**3. A PnL number disagrees with the trader's expectation. How do you investigate?**
First, reconcile inputs: positions, prices, FX rates, curves as of close. Then decompose PnL into market move, carry, new-trade, and unexplained. Match the unexplained against known model or data changes. If still unresolved, isolate by asset class and run a clean re-pricing against an alternate source. Document the chain, escalate with a hypothesis, and confirm with middle office before close.

**4. Tell us about a time you identified an output that was mathematically defensible but economically wrong.**
STAR-2: client run passed all internal checks but didn't square with the client's intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, identified a curve-calibration edge case at the short end, escalated to product and the client's Head of Risk, and walked through remediation. 48-hour delay, client avoided acting on wrong numbers, defect captured in validation tests, and I became the Head of Risk's direct escalation contact.

**5. How would you use Python to investigate a recurring booking break?**
Pull the trade and booking records into pandas, join on trade ID and version, diff the economic fields (notional, rate, dates, counterparty, currency). Group by counterparty, product, and booking source to find concentration. If recurring, write a daily check that flags the pattern at T+1 instead of waiting for the weekly reconciliation. I do this style of work today migrating spreadsheet workflows into auditable pipelines.

## Questions to ask

- How is the Analyst role split across Beta, Collateral & Liquidity, and Trading day-to-day, and where do you most need coverage in the first 90 days?
- Which Technology & Operations workstreams are highest-priority right now — and where has the bar for front-office self-service been moving?
- What does a strong outcome at month 12 look like, and is there a typical path from the contract into a permanent seat on TFM or an adjacent desk?

## The one competency gap to prepare for

**Direct front-office trading-assistant / middle-office break-resolution experience.** I have validated analytics and resolved analytical discrepancies, scoped requirements between front-office and tech, and worked adjacent to ops — but I haven't sat on a trading-assistant seat with order tickets, allocation breaks, or collateral-call workflows. Prepare to be honest about this, demonstrate the transferable muscles (control mindset, escalation discipline, Python on messy data, cross-team coordination), and show specific curiosity about CPP's trade-lifecycle technology and TCA process.