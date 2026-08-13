## Five most likely technical questions

**1. "Walk me through how you would model prepayment or redemption behaviour on a retail mortgage/GIC book."**
Be honest about the layer of the problem I have owned: in the Moody's cash-flow projection engine I embedded behavioural cash-flow assumptions, prepayment logic, and macro stress overlays, and validated that the resulting cash-flow profiles and sensitivities were economically defensible under base, stress, and reverse-stress scenarios. My depth is in the projection, calibration-review, and stress-overlay layer rather than in estimating a Cox/GLM hazard on retail account data — I would frame the modelling choice (hazard vs. logistic vs. panel) as a question of how much of the effect is rate-driven versus seasoning/burnout and how the parameter review cycle will re-estimate it.

**2. "How do you build and govern a cash-flow modelling book end to end?"** (STAR Story 1)
The prior approach at Moody's was spreadsheet-driven and not auditable. I architected configurable time-bucketed liquidity gap analytics (T+1 to multi-year), layered behavioural assumptions and macro stress overlays, and re-built the upstream workflow into Python pipelines with logging and reconciliation. The engine shipped to production and became the delivery standard — the governance point is that scenario definitions, assumptions, and version history all had to be reproducible before sign-off.

**3. "How do you explain a large unexplained move in a risk or valuation number to a CFO group?"** (STAR Story 2)
A client run produced portfolio sensitivities that passed every internal check but did not square with the client's economic intuition under one rate shock. I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case in short-end inversion handling, and escalated to product and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers, and the defect became a permanent validation test.

**4. "What is your hands-on experience with interest rate derivatives valuation and rate shocks?"**
I validate derivatives pricing outputs across rates, FX, and inflation and cross-check sensitivity consistency at portfolio-level ALM aggregates, including yield curve construction and spread calibration review. I run duration and key-rate analysis under parallel and non-parallel shocks on an IRRBB-aligned basis. Framing to keep honest: I review and validate pricing and sensitivity output rather than build the swaption pricers themselves — my hedging depth is from Ortec, where I ran interest-rate, inflation, and currency hedging analysis for institutional clients.

**5. "What is your Python/SQL stack, and how do you get models from prototype into a supported analytics library?"** (STAR Stories 6 and 7)
Python (pandas, NumPy, SciPy) daily, PostgreSQL for data, Git and CI/CD in a professional context, plus R and MATLAB historically. On migration I parallel-build, run shadow mode for two cycles, reconcile line by line, then cut over with a rollback plan — that pattern closed a model-governance audit and became the template for adjacent workflows. I also use agentic AI workflows (Claude Code, Cursor) for first-pass review, validation scaffolding, and documentation drafts, with a human still signing off on governance-critical review; cycle time on comparable modules dropped an estimated 30–40%.

## Three questions Saber should ask

1. How is the boundary drawn today between Treasury Analytics owning the behavioural parameters and the model validation/vetting group challenging them — and where does this role sit when the two disagree?
2. Which parts of the cash-flow modelling book P&L are currently the hardest to decompose, and is the priority for this role improving the attribution or improving the underlying behavioural models?
3. How much of the analytics library is production Python versus legacy spreadsheet or vendor code, and is modernizing that stack part of this mandate or a separate technology program?

## The one competency gap to prepare for

**Advanced GLM / Cox regression / survival analysis on retail banking product data (mortgages, commitments, GICs), and funds transfer pricing.** The repo evidences behavioural cash-flow and prepayment assumption design, stochastic scenario generation, and Monte Carlo — but not fitted survival/GLM models on customer-level data, and not FTP. Prepare a crisp, non-defensive answer: state the statistical foundation (dual MSc, CFA, stochastic and Monte Carlo modelling), describe survival analysis correctly at concept level (hazard rate, censoring, time-varying rate covariates, why Cox suits prepayment), and be explicit that the estimation-on-retail-data piece is the part to learn in the first quarter. Before the interview, review one prepayment-model paper and one FTP primer so the vocabulary is fluent.