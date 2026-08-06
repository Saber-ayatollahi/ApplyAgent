## Top 5 Likely Technical Questions

**1. Walk us through how you independently validate a derivatives pricing model.**
Frame the four-layer review I run at Moody's: (1) inputs & data — market data quality, curve construction inputs; (2) assumptions & methodology — calibration approach, model choice defensibility; (3) implementation — replicate developer results on a benchmark portfolio, cross-check sensitivities at portfolio-level aggregates; (4) limitations & conditions for use — stress points, edge cases (e.g., short-end curve inversion handling that I escalated in a real client engagement), documentation. Sign-off only after each layer passes.

**2. Tell me about a time you provided effective challenge on a model output.**
Use Story 2 (Master Repo §6): client-delivery run produced sensitivities that passed internal checks but didn't square with the client's economic intuition under a specific rate shock. Held the release, decomposed sensitivities by asset class, identified a curve-calibration edge case (short-end inversion), escalated to product owners and the client's Head of Risk, delayed release 48 hours. Defect was remediated upstream and captured in validation tests. Became the Head of Risk's direct escalation contact afterward.

**3. How do you assess model risk and quantify conditions for use?**
Model risk = probability of materially wrong output × magnitude of business decision impact. Quantify via: benchmark replication error bands, stress sensitivity to assumption perturbation, scope-of-use boundaries (which products, which market regimes), and residual qualitative risk. Document conditions for use explicitly — e.g., "valid for vanilla rates and FX up to 10y tenor; do not apply to exotic structures or to environments where the short end inverts beyond X bps without re-calibration."

**4. How would you approach validating a new model type the team has never seen before?**
Start with literature and benchmark implementations to understand the methodology's known failure modes. Build an independent replication (Python) of the core calculation on a small benchmark set. Stress the model on edge cases — extreme inputs, non-standard market regimes, reverse-stress scenarios. Compare against simpler challenger models for plausibility. Document residual risk and recommend conditions for use plus an ongoing monitoring plan. Engage the developer collaboratively but maintain independence.

**5. How do you represent the validation program in a regulatory examination?**
The examiner wants three things: that the inventory is complete and tiered by risk, that documentation is defensible, and that escalation actually happens. Walk them through: model inventory and attestation records, sample validation reports showing methodology challenge and benchmark replication, escalation log with real examples of conditions imposed or release held, and the governance framework consistent with OSFI E-23 / SR 11-7. Confidence comes from being able to show the process worked on a real escalation.

## 3 Sharp Questions Saber Should Ask

1. **What does the current capital-markets model inventory look like by product line — which asset classes or model types are the biggest validation backlog or risk concentration today?**
2. **How is the validation team positioned relative to the model-development desks and the front office — what does "effective challenge" look like in practice when the model owner pushes back?**
3. **What is the team's current adoption of automation and AI-assisted tooling in validation workflows (replication, documentation, monitoring), and how open is the group to expanding it?**

## The 1 Competency Gap to Prepare For

**Trading-book capital machinery: FRTB (SA & IMA), CCR/PFE/xVA, and VaR backtesting on a live trading book.** Saber has not directly validated these on a sell-side desk. Preparation: review FRTB SA risk-class structure (DRC, RRAO, sensitivities-based method), the PFE/EE/EPE framework, and standard VaR backtesting (Kupiec, traffic-light). When asked, answer honestly: "I have applied-knowledge familiarity with FRTB and CCR frameworks from validating analogous rate and derivatives outputs, but I have not validated on a live sell-side trading book — I would ramp on the desk specifics quickly given the underlying quant foundation." Don't bluff specifics.