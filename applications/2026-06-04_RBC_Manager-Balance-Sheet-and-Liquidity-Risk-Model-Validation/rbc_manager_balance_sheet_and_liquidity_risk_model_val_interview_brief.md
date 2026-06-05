## Likely Technical Questions

**1. Walk me through how you would validate a banking-book IRRBB model — what would you look at first?**
I'd start with the curve construction and the behavioral assumptions, because those drive 80% of the EVE and NII sensitivity. At Moody's I review yield curve calibration, spread treatment, and short-end handling for edge cases like inverted curves. Then I'd benchmark the model's parallel and non-parallel shock outputs against a simpler replication and look for non-monotonic behavior that signals a calibration or aggregation defect.

**2. How do you assess the reasonableness of behavioral assumptions in a liquidity or deposit model?**
I'd separate the empirical question (does the historical data support the assumed runoff or prepayment rate?) from the stress question (does the assumption still hold under the scenarios the model is meant to capture?). At Moody's I embed behavioral cash flow assumptions and prepayment logic into the cash flow engine, so I think about assumption fragility — what's the smallest plausible regime change that breaks the assumption?

**3. Tell me about a time you challenged a model output.**
(STAR Story 2.) A client-delivery run produced sensitivities that passed all internal checks but didn't square with the client's economic intuition under a rate-shock scenario. I held the release, decomposed the sensitivities by asset class, and identified a curve-calibration edge case in short-end inversion handling. Escalated to the product owner and the client's Head of Risk. Release was delayed 48 hours; defect was remediated and captured in validation tests.

**4. You're at a vendor today, not a bank. How does that translate to second-line validation at RBC?**
The governance posture is the same: I'm the independent reviewer between model developers and the stakeholders who consume the output. The Moody's framework operates with the same mechanics as a bank's MRM function — independent review, documentation to validation standards, escalation of indefensible outputs. The transfer is the bank's specific product set (mortgages, deposits, mortgage commitments) and FTP — adjacent, learnable, and where my Ortec banking-product modelling helps.

**5. How would you approach a model where you don't yet know the methodology well (e.g., FTP)?**
(STAR Story 8 framing — rapid learning.) I'd start with the methodology document, then independently replicate the simplest case end-to-end in Python — that surfaces the gaps in my understanding faster than reading. Then I'd benchmark against an industry reference (e.g., matched-maturity FTP) and stress the edges. My chem-eng background trained me to learn unfamiliar quantitative systems quickly.

## Questions to Ask

1. How is the BSLR validation team's workload split across IRRBB, liquidity, and FTP models — and where is the team most stretched right now?
2. What's the current state of the model-performance-monitoring framework on the banking-book IRRBB models? Is monitoring centralized or model-by-model?
3. How does the team interact with the QRM platform — is RBC running QRM as the production engine, and how much of validation is benchmark-modelling against it versus independent replication?

## Competency Gap to Prepare

**Direct hands-on with Big-Six retail banking products (mortgage prepayment models, deposit beta/decay, mortgage commitment pipeline risk) and QRM software.** Saber has modelled actuarial liabilities, multi-asset institutional portfolios, and pension cash flows — the *modelling muscle* transfers cleanly, but he has not personally built or validated a Canadian mortgage prepayment model or a deposit attrition model in production, and has not used QRM. Prep: read a recent OSFI B-12 IRRBB consultation summary; review the public BIS IRRBB SA framework on mortgage prepayment treatment; read one industry whitepaper on QRM's IRRBB module. Frame in interview as 'I haven't worked in QRM specifically, but the methodology decisions it forces — behavioral profiles, prepayment models, FTP curve choice — are exactly what I review every week at Moody's, just in a different platform.'