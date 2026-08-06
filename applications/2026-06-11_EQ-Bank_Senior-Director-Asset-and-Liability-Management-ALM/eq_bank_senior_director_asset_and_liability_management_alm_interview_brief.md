## Likely Technical Questions

**1. Walk me through how you would set up an EVE and NII sensitivity framework for EQ Bank's balance sheet under OSFI B-12.**
Start with curve construction and behavioural assumptions (non-maturity deposits, prepayment), then layer parallel and non-parallel shocks (level, slope, twist) per IRRBB standard scenarios. At Moody's I oversee exactly this: curve calibration review, shock generation, and reconciliation of EVE and NII outputs at portfolio-level ALM aggregates. Key sign-off questions are economic defensibility under the short-end shocks and consistency of cross-asset sensitivities.

**2. How do you embed behavioural cash-flow assumptions into a cash-flow projection engine, and how do you stress them?**
Draws on STAR Story 1 (cash-flow engine). I architected time-bucketed liquidity-gap analytics from T+1 through multi-year with behavioural overlays on prepayments, deposit decay, and revolver utilisation. Stressing them means flexing behavioural parameters alongside macro paths and running reverse-stress to identify the assumption combinations that break funding ratios first.

**3. Tell me about a time you held a model output back rather than signing off.**
STAR Story 2 verbatim: client run passed internal checks but didn't square with economic intuition under a short-end inversion. Held the release, decomposed sensitivities by asset class, identified a curve-calibration edge case, escalated to product owners and the client's Head of Risk with a remediation plan. Release delayed 48h; defect captured in validation tests; became their direct escalation contact.

**4. How would you think about hedging EQ Bank's interest rate exposure given hedge-accounting implications?**
Frame around target exposure first (what duration gap is the bank willing to run), then instrument selection - swaps for level, swaptions where convexity matters, bond forwards for treasury portfolio. Hedge accounting introduces designation and effectiveness-testing constraints that often dictate instrument choice as much as economics. Honest framing: I have validated derivatives outputs and analysed hedging strategies at Ortec; the hedge-accounting nuance is something I'd want to deepen quickly with Finance partners.

**5. What's your view on integrating ALM modelling with the ICAAP capital-evaluation process?**
ALM scenario outputs feed Pillar 2 capital quantification - rate shocks, liquidity stress, and reverse-stress translate into capital impact under ICAAP. The discipline is consistency: same macro paths, same behavioural assumptions, same governance trail across EWST/MST/ICAAP. The cash-flow engine I built at Moody's was designed exactly to be that single source of truth feeding downstream capital and liquidity processes.

## Questions Saber Should Ask

1. "How is the ALM function currently positioned between first-line Treasury and second-line Treasury Risk & Capital Oversight - and where does this role sit in that interface today versus where you want it to sit in 12 months?"
2. "What's the current state of the ALM modelling stack - in-house, vendor (QRM/Moody's/Empyrean), or hybrid - and what's the appetite for re-platforming or modernising the cash-flow projection layer?"
3. "With OSFI's revised B-12 consultations and LAR 2026 in flight, what are the one or two regulatory changes that will most reshape EQ Bank's ALM operating model over the next 18 months?"

## Competency Gap to Prepare

**15-years-of-progressive-ALM-experience requirement and direct people-leadership of a quant team.** Saber has ~7 years and is IC-with-sign-off, not yet a formal team lead. Prepare to address head-on: (a) the breadth of the Moody's mandate compresses bank-side learning curves because the institutional client base is largely Canadian Schedule I and Maple-8 - same problems, more reps; (b) frame the team-leadership story around the cash-flow-engine build (cross-functional ownership, product-owner alignment, mentoring junior modellers) and Story 3 (bridging client investment teams and dev); (c) be explicit that this would be a stretch into people-management at Senior Director level and that the path is credible because of demonstrated technical authority. Also brush up on EQ Bank's mortgage-heavy asset mix, deposit base mechanics, and the Concentra acquisition implications for the balance sheet.