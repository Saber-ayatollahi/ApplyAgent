# Interview Brief — State Street, Global Treasury Audit VP

## 5 likely technical questions + model answers

**1. "Walk me through how you would assess the appropriateness of a bank's non-maturity deposit behavioral assumptions."**
Start from the evidence chain: what data window supports the decay/beta assumption, how it was segmented (retail vs. institutional, rate-sensitive vs. operational), and whether the behavior held through the 2022-23 rate cycle. In my Moody's work I embed and validate behavioral cash flow assumptions and prepayment logic inside projection models, so my instinct is to test the assumption's sensitivity: if a plausible alternative beta materially moves EVE or NII, the assumption needs stronger documentation and a governance-approved override log.

**2. "What would make you disagree with a Treasury EVE result that passed every internal check?"**
(STAR Story 2.) I once held a client release where portfolio sensitivities passed all internal checks but did not square with economic intuition under a specific rate shock. I decomposed the sensitivities by asset class, found a curve-calibration edge case in short-end inversion handling, escalated to the product owner and the client's Head of Risk, and delayed release 48 hours. Mathematically defensible is not the same as economically defensible — that distinction is the core of credible challenge.

**3. "How do you audit scenario design — who decides the shocks are severe enough?"**
I look for three things: coverage (parallel and non-parallel shocks, steepeners/flatteners, and a reverse-stress case that identifies what breaks the plan), traceability of calibration to observed history plus forward-looking judgment, and governance evidence that the scenario set was challenged, not just approved. My cash-flow engine at Moody's was built to run base, stress, and reverse-stress precisely so severity was a parameter under review, not a hard-coded assumption.

**4. "Where does model risk live in an IRRBB framework, and how would you test the controls?"**
Inputs (curve construction, spread calibration, position completeness), assumptions (behavioral, prepayment, pricing), and use (reporting and limit escalation). I sit on Moody's model governance committee covering methodology review, documentation and benchmarking standards, and model-performance assessment — so I test whether independent review actually challenged the model, whether findings were tracked to closure, and whether the model's use matches the scope it was approved for.

**5. "How do you translate this material for ALCO or the Board?"**
(Stories 4 and the Ortec committee work.) At Ortec I presented ALM and LDI study conclusions on-site to pension investment committees, and at Moody's I prepare analytical summaries on interest-rate exposure and balance-sheet sensitivities for senior stakeholders. The format that works: the number, the driver, the assumption it is most sensitive to, and the decision it should inform — never the model mechanics unless asked.

## 3 questions Saber should ask
1. How does this team split its coverage between IRRBB measurement/model use and the Treasury governance and reporting chain — and where has the MD seen the most repeat findings?
2. How much of the role is regulatory engagement (exam support, MRA/issue remediation validation) versus planned audit execution, and who owns the regulator relationship?
3. What does the Managing Director need this VP to be the firm's go-to person on within the first 12 months — deposit modelling, investment portfolio, or hedge accounting/hedging effectiveness?

## The one competency gap to prepare for
**Internal audit methodology and issue writing.** Saber has never worked in a third-line function: no IIA standards, audit work-programs, risk-and-control matrices, sampling/testing evidence standards, issue rating, or MRA remediation validation. Prepare a crisp answer: "My review authority has been second-line and vendor-side model governance — independent of the builders, with formal sign-off, documented findings, and escalation of unsupported outputs. The audit methodology layer (work programs, RCM design, issue rating, testing evidence) is learnable and is where I would lean on the team in month one; the Treasury technical challenge is what I bring on day one." Also be ready to name the framework: three lines of defense, design vs. operating effectiveness, and control-vs-process distinction.