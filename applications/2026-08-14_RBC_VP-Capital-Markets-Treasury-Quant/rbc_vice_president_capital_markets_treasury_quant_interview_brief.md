## Likely technical questions

**1. "Walk me through how you'd review a curve build and spread calibration for a funding book."**
My sign-off review at Moody's decomposes the build: instrument selection and bootstrapping consistency at the short end, interpolation behaviour across the belly, and whether the calibrated spread reproduces observed prices within tolerance across the curve, not just at the pillars. I check sensitivities for sign/magnitude plausibility at portfolio aggregates before release — Story 2 (short-end inversion edge case) is the concrete example: the run passed all internal checks but broke economic intuition under one rate shock, so I held the release, decomposed sensitivities by asset class, and escalated to the product owner and the client's Head of Risk.

**2. "Describe a model you designed and implemented end to end."**
The enterprise multi-asset cash-flow projection engine (STAR Story 1). Prior state was spreadsheet-based and non-auditable; I architected configurable time-bucketed liquidity gap analytics from T+1 to multi-year, embedded behavioural cash-flow and prepayment logic, layered macro stress and reverse-stress overlays, and rebuilt the upstream workflow into Python pipelines with logging. Shipped into production and gave clients forward-looking liquidity visibility they had been asking for.

**3. "How do you document and monitor a model so it stays fit for purpose?"**
I work inside a formal governance framework and sit on the model governance committee — methodology review, documentation and benchmarking standards, and ongoing performance assessment. Story 6 is the migration case: I parallel-built the Python pipeline, ran it in shadow mode for two cycles, reconciled outputs, and cut over with a rollback plan, which closed the governance audit and became the template for adjacent workflows.

**4. "How do you explain model mechanics to a trader or product controller who doesn't want the math?"**
I translate to the decision: what moved, why, and what the range of outcomes is. At Ortec I presented ALM study findings to pension investment committees (Story 4 — decomposed duration-gap contribution to funding-ratio volatility and made an explicit SAA recommendation the committee adopted). At Moody's I prepare interest-rate exposure and scenario summaries for Heads of Risk. Lead with the number that changes the decision, keep the derivation in the appendix.

**5. "Where does AI actually help in quant model development, and where does it not?"**
Story 7: I built agentic review workflows in Claude Code and Cursor for first-pass code review, validation scaffolding, and documentation drafts — roughly 30-40% cycle-time reduction on comparable modules. Where it does not help: governance-critical sign-off. A human still owns economic defensibility, because the failure mode I care about is output that is mathematically clean and economically wrong.

## Questions Saber should ask

1. Where does the team's model perimeter sit today — is the rate and spread product library owned in-house, or are you calibrating and extending vendor pricing engines, and how much of the roadmap is new build versus enhancement?
2. How does the handoff to Model Risk Management work in practice — what does a validation submission from this team look like, and what typically comes back as a finding?
3. Who are the highest-volume internal consumers of these models — Treasury traders, product control, or the IRRBB/balance-sheet-management side — and which of those relationships most needs strengthening?

## The one competency gap to prepare for

**Building rate and spread product pricing models from scratch in a compiled language, on a sell-side trading-desk footing.** My evidence is independent review, validation, and sign-off of pricing and sensitivity outputs (rates, FX, inflation) plus end-to-end development of cash-flow, liquidity, and scenario-generation models in Python — not authoring a C++/C# pricing library or sitting behind a Capital Markets trading desk. Own it plainly: I know these models from the challenge side, which is exactly what catches calibration and behavioural-assumption defects; my production build history is Python, and C++/C# would be a ramp I'd take on deliberately. Do not claim C++, C#, or GitHub Copilot experience.