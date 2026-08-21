## Five likely technical questions

**1. "Walk me through how you would validate a quantitative model used in the investment process."**
Start with the governance frame: at Moody's I review assumptions, data inputs, curve construction, spread calibration, and cross-asset interactions before production release, and I sit on the model governance committee that sets benchmarking and documentation standards. Then the practitioner layer: mathematical defensibility is necessary but not sufficient — I test whether the output is economically defensible under specific scenarios, which is where most real defects surface. Close with the spreadsheet-to-Python migration: parallel build, two shadow cycles, output reconciliation, cut-over with rollback.

**2. "Describe a portfolio optimization you built end to end."**
At Ortec I ran both asset-only and asset-liability (surplus) optimization on VaR and CVaR using the GLASS platform. The value was rarely the point estimate — I decomposed contribution-to-risk and explored near-optimal portfolios around the efficient frontier to test whether an allocation recommendation was robust or an artifact of the calibration. That robustness testing is what made recommendations defensible in front of an investment committee.

**3. "How do you build and calibrate a stochastic scenario generator, and how do you know it's right?"**
Use the LDI story (STAR 4): calibrated an ESG to the client's assumptions, produced funding-ratio distributions under base and stressed regimes, and decomposed duration-gap contribution to funding-ratio volatility. Validation is threefold — distributional plausibility versus history, sensitivity of conclusions to calibration choices, and whether the economic story behind an extreme path is one a practitioner would accept.

**4. "Tell me about a time a model gave you an answer you didn't trust."**
STAR 2 verbatim: a client run passed every internal check but the portfolio sensitivities didn't square with the client's economic intuition under one rate shock. I held the release under deadline pressure, decomposed sensitivities by asset class, isolated a curve-calibration edge case in short-end inversion handling, escalated to the product owner and the client's Head of Risk, and put the defect into the validation test suite. Release slipped 48 hours; the client avoided acting on wrong numbers.

**5. "Where would you take automation in a quantitative research team?"**
STAR 7: validation workload was growing faster than headcount, so I built agentic review workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, and documentation drafts — roughly 30-40% cycle-time reduction on comparable modules, with humans still signing off on anything governance-critical. Pair that with the Python pipeline rebuild: the automation win is auditability and repeatability, not just speed.

## Three questions Saber should ask

1. Which decisions in the investment process are currently made on judgment that this team is expected to make quantitative first — and who owns the model once it goes live?
2. How is the boundary drawn between this team's model development and the bank's independent model validation function, especially for models that touch client portfolios?
3. What does the current toolchain look like end to end — where does data land, where does research happen, and how much of the reporting layer is still spreadsheet-based?

## The one competency gap to prepare for

**Security-level quantitative investment research (bond/credit/equity factor and signal work) and Bloomberg fluency.** Saber's quantitative work sits at portfolio and balance-sheet level — optimization, risk decomposition, scenario generation, derivatives sensitivity validation — not single-name alpha research or factor-model construction, and the Master Repo evidences no Bloomberg use. Prepared answer: "My research has been at the total-portfolio and asset-class level rather than security selection — VaR/CVaR optimization, contribution-to-risk decomposition, and scenario generation. I've worked adjacent to security-level analytics through aggregation review and derivatives sensitivity validation, and I'd expect the Bloomberg terminal surface to be a short ramp on top of an existing data workflow. What I bring on day one is the model development and validation discipline plus the Python and SQL to build it." Do not overclaim; also be ready for a people-leadership probe — evidence is mentorship and cross-functional coordination, not a direct-report team.