## Likely technical questions

**1. Walk me through how you validate a derivatives pricing model.**
Use Story 2: I review conceptual soundness first (methodology, assumptions), then re-run sensitivities decomposed by asset class, and stress the model at edge cases. On one client run the outputs passed all internal checks but conflicted with economic intuition under a rate shock - I traced it to a short-end curve-calibration edge case (inversion handling), escalated to the Head of Risk, and had it remediated upstream with a validation test added.

**2. How do you think about SR 11-7 conceptual soundness vs. implementation testing?**
Conceptual soundness asks whether the model's theory and assumptions fit its intended use; implementation testing asks whether the code faithfully reproduces that theory. In my governance-committee work I separate the two: assumption/methodology review and benchmarking on one side, output reconciliation and validation scaffolding on the other. Documentation must evidence both plus limitations and ongoing monitoring.

**3. You're an Assistant Director - how do you have sign-off authority?**
Use Story 9: Moody's delegates sign-off by role, not title, under a formal governance framework. The role is IC-with-independent-review authority; sign-off attests to the defensibility of specific analytical outputs, not to an entire portfolio's investment strategy. That distinction keeps the framing honest.

**4. How would you improve a monitoring methodology for pricing/margining models?**
Use Stories 6 & 7: I shadow-ran a Python pipeline against a spreadsheet workflow for two cycles, reconciled outputs, then cut over with a rollback plan - closing a governance audit. I also built agentic-AI review workflows (Claude Code, Cursor) that cut comparable-module cycle time ~30-40%, with humans still signing off on governance-critical review.

**5. Describe your Python for quantitative validation work.**
pandas/NumPy/SciPy for analytics; re-engineered manual spreadsheet workflows into auditable pipelines with logging and validation; version control and CI/CD in a professional context. Be honest that R and MATLAB are intermediate/historical, and that C++/C# are not part of my production stack.

## Questions Saber should ask

1. How is the MRM function positioned relative to RISQ and the independent validation team - is R&D remediating recommendations, or also issuing them?
2. What is the current tooling stack for pricing/margining model monitoring, and where do you most want it modernized?
3. How deep does the AMER SIMM oversight work go for this role - reconciliation and monitoring, or methodology contribution?

## The one competency gap to prepare for

**C++/C# and SIMM/margining specifics.** The JD lists C++/C# and margining-model + SIMM oversight; the repo evidences Python (strong), R/MATLAB (intermediate), derivatives-pricing validation, and risk metrics - but not production C++/C# or hands-on SIMM. Own it directly: position Python + quantitative validation transferability, note C++/C# as reading/learning-level (not shipped production), and frame SIMM as an ISDA-standardized sensitivities-based margin framework you can ramp on quickly given your existing rates/FX/inflation sensitivity-validation depth. Do not claim either as prior hands-on experience.