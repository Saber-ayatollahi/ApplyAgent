## Likely Technical Questions

**1. Walk us through a model validation where your finding changed the outcome.**
A client-delivery run produced portfolio-level sensitivities that passed internal checks but didn't square with the client's economic intuition under a specific rate shock. I held the release, decomposed the sensitivities by asset class, and identified a curve-calibration edge case in short-end inversion handling. Escalated to product owners and the client's Head of Risk; release was delayed 48 hours, the defect was remediated upstream, and the case became a validation test.

**2. How would you validate an actuarial liability model — what do you look at first?**
Funding policy dynamics, demographic and economic assumption stack, and the linkage to the investment-side cash flows. At Ortec I led the ALM and liability model for a three-plan university pension merger — validated that the Funding Policy mechanics (contribution rules, smoothing, asset value definitions) flowed correctly through to funding-ratio distributions, then stressed duration, currency, inflation, and leverage overlays. Conceptual soundness first; then implementation; then back-testing against base-period actuals.

**3. How do you approach validating an AI/ML model differently from a traditional pricing model?**
The conceptual-soundness question shifts from 'is the closed-form right' to 'is the training data representative, is the feature set economically defensible, and is the model stable out-of-sample.' I add explainability review, drift monitoring, and adversarial / edge-case testing. I've used Claude Code and Cursor extensively in our own development workflow, which gives me a practitioner view of where LLM-assisted code can be trusted and where human sign-off is non-negotiable.

**4. You don't have direct buy-side pension validation experience — why is HOOPP the right next step?**
My Moody's client book is Canadian and US pension funds, asset managers, and consultants — I've been validating models on their behalf for four years. At Ortec I was on the pension-advisory side, building scenario generators and running LDI for these same plans. The seat I'm applying for is the institutional model-validation discipline I already do, but as an owner inside one plan rather than across a vendor's book.

**5. How would you build a peer-review network with quants who don't report to you?**
Three levers: clear scope and templates so it isn't open-ended work; making peer review intellectually valuable — exposing reviewers to models outside their day-job — and a knowledge-sharing forum where findings are reused. I've operated this way at Moody's, where escalation and review depend on relationships, not authority. The Head of Risk at one of our largest clients now contacts me directly because I held a release rather than push it through under deadline pressure.

## Sharp Questions to Ask

1. How is the model inventory currently structured by risk tier, and where are the validation backlogs concentrated — pricing, investment, actuarial, or AI/ML?
2. What is the working split between this seat's own validation execution and oversight of validations run by quants embedded in Investments, Finance, and Actuarial? How rigid is that ratio in year one?
3. Where has external validation been most useful so far, and where has it under-delivered? That shapes how I'd manage the external provider panel.

## The One Gap to Prepare For

**Direct counterparty credit risk / xVA and FRTB-style market-risk capital exposure.** HOOPP's book is buy-side so this is less central than at a bank, but if a private-credit or derivatives-collateral model comes up, lead with the derivatives valuation and sensitivity review work at Moody's plus the stochastic-scenario depth from Ortec, and be honest that desk-level CCR/xVA is adjacent rather than direct. Frame as 'applied knowledge, learn-fast on the desk-specific machinery.'