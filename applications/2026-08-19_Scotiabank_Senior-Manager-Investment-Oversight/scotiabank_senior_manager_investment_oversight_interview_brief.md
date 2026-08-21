## Likely technical questions (with model answers)

**1. "How would you assess whether a portfolio advisor is delivering in line with its mandate?"**
Start from the mandate's stated objective, risk budget, and benchmark, then decompose realised risk and return: contribution-to-risk by asset class and factor, tracking-error drift, and whether exposures sit inside the stated ranges. At Ortec I did exactly this decomposition work (contribution-to-risk, risk budgeting, near-optimal frontier robustness) to test whether allocation recommendations held up. The oversight question is the same one asked of a mandate rather than a proposal: does the observed exposure profile still match what was approved?

**2. "Walk me through a time you challenged a number that looked fine."** (STAR Story 2)
A client delivery run produced portfolio-level sensitivities that passed every internal check but did not square with the client's economic intuition under a specific rate shock. I held the release, re-ran sensitivities decomposed by asset class, found a curve-calibration edge case in short-end inversion handling, and escalated to the product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**3. "You're Assistant Director — what does sign-off actually mean?"** (STAR Story 9)
Moody's runs a formal governance framework where sign-off authority is delegated by role, not title. My role is IC-with-independent-review authority: the sign-off attests to the defensibility of specific analytical outputs — curve construction, spread calibration, cross-asset interactions, sensitivity consistency — not to a portfolio's investment strategy. I also sit on the model governance committee covering methodology review, documentation standards, and model-performance assessment.

**4. "How do you present quantitative analysis to a committee that isn't quantitative?"** (STAR Story 4)
Lead with the decision, not the method. For a Canadian pension client questioning duration positioning, I built a calibrated scenario generator, ran funding-ratio distributions under base and stressed regimes, and decomposed the duration gap's contribution to funding-ratio volatility — but the committee slide was one chart of outcome dispersion and one explicit SAA recommendation. The committee adopted the duration extension and the client returned for further studies.

**5. "How do you handle competing priorities across many products with tight reporting deadlines?"** (STAR Story 6 / Story 1)
I industrialise the repeatable part so judgement time goes to the exceptions. At Moody's I migrated a spreadsheet-driven valuation workflow into a Python pipeline with logging and versioning — parallel-built, shadow-run for two cycles, reconciled, then cut over with a rollback plan. That closed a governance audit and became the template for adjacent workflows; it is also how I would approach a recurring quarterly performance-analysis cycle.

## Questions Saber should ask

1. Where does the oversight function's authority actually bite today — is it advisory input into portfolio-advisor hiring and termination decisions, or a formal veto/escalation path to the Investment Committee and IRC?
2. How much of the quarterly performance and compliance-to-mandate analysis is currently manual versus system-generated, and is there appetite to rebuild that pipeline?
3. How does oversight of the international asset management companies differ in data quality, reporting cadence, and peer-comparison sources from the Canadian 1832 book?

## The competency gap to prepare for

**Retail mutual fund oversight mechanics — and Power BI.** Saber has no experience with fund-specific oversight (NI 81-102 constraints, IRC processes, prospectus-mandate compliance monitoring, sub-advisor contract/fee negotiation) and no professional Power BI use. Prepared answer: name it plainly, then bridge — the oversight *logic* (independent review, escalation on defensibility, committee reporting, peer benchmarking, sub-advisor performance monitoring) is what he has done for institutional mandates; the fund-regulatory wrapper is learnable in weeks, and reporting tooling is a skin over analytics he already builds in Python and Excel. Do not claim Power BI, CIPM, FRM, or mutual fund industry experience.