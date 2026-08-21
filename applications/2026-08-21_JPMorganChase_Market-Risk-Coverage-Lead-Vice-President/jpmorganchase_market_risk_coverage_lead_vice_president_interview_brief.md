## Five likely technical questions

**1. "How would you monitor market risk daily across thousands of customized, model-delivered portfolios?"**
Start from the aggregation layer: at Moody's I review the logic that converts security-level exposures into portfolio-level metrics, so the first control is consistency of sensitivities across the aggregation chain. On top of that, threshold and dispersion checks against the model portfolio (tracking-error, duration and sector drift, factor exposure outliers), then exception triage by materiality rather than count. Anything that fails economic defensibility - not just tolerance - gets held and escalated.

**2. "VaR vs. CVaR - which do you use and why?"**
At Ortec I ran both asset-only and asset-liability (surplus) portfolio optimization on VaR and CVaR using the GLASS platform. VaR is the communication metric; CVaR is the decision metric, because tail shape drives allocation once you're optimizing a surplus rather than a return distribution. I also stress-tested robustness by exploring near-optimal portfolios around the frontier, since a single CVaR-optimal point is fragile to assumption error.

**3. "Tell me about a time you challenged a model output."** *(STAR Story 2)*
A client delivery run produced portfolio sensitivities that passed every internal check but didn't square with the client's economic intuition under one rate shock. I held the release under deadline pressure, decomposed sensitivities by asset class, and found a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was fixed upstream and captured in validation tests. I became that Head of Risk's direct escalation contact.

**4. "How do you set risk parameters for a new product with no history?"** *(Stories 1 and 4)*
Scenario-first, not history-first. I built stochastic economic scenario generators at Ortec and designed the base/stress/reverse-stress cash-flow engine at Moody's - both cases where you specify the economics and behavioral assumptions explicitly rather than fitting a short return series. For a new sleeve I'd define the exposure taxonomy, set provisional limits from analogue mandates, run reverse-stress to find the breaking assumption, and re-baseline once live data accumulates.

**5. "What's your anomaly-detection approach - and is it machine learning?"**
Be precise here. What I've built is rules-plus-statistical diagnostics embedded in Python pipelines, plus agentic-AI workflows (Claude Code, Cursor) that automate validation scaffolding and flag anomalies in code and output - roughly 30-40% cycle-time reduction on comparable modules. That's LLM-assisted tooling and statistical screening, not production supervised ML. I'd be candid about that and about interest in extending toward statistical outlier models.

## Three questions to ask

1. For Tax Management Solutions and model delivery at scale, is the coverage lead's primary risk lens tracking-error and implementation drift against the model, or absolute portfolio risk - and where does the current infrastructure fall short of that?
2. The posting spans market, stress, liquidity, and counterparty metrics plus a Real Estate Alternatives build-out. Which of those is the first 90 days actually spent on?
3. How does escalation work in practice between Asset Management Risk and the investment teams - what's the last decision this seat successfully changed?

## The one competency gap to prepare

**Alternatives risk, specifically Real Estate, plus counterparty risk metrics.** Nothing in the record covers private real estate valuation cycles, appraisal lag, NAV smoothing, or leverage/covenant risk in property funds; nor counterparty exposure measurement (PFE/xVA). Prepare a crisp answer: name the transfer - illiquid, cash-flow-driven, long-horizon mandates with model-based valuation and liquidity-gap analytics, which is exactly the pension/ALM work - then ask how the team currently handles appraisal-lag and NAV-staleness in its risk metrics. Do not bluff a real-estate track record or counterparty methodology depth.