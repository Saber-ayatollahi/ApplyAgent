# Interview Brief - RBC, Associate Director, Enterprise Model Risk Management

## 5 most likely technical questions

**1. "Walk me through a validation where you disagreed with the model owner."**
Use STAR Story 2: a client-delivery run produced portfolio sensitivities that passed every internal check but conflicted with the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, isolated a curve-calibration edge case (short-end inversion handling), and escalated to product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the defect was fixed upstream and encoded in standing validation tests, and I became that Head of Risk's direct escalation contact.

**2. "You're an Assistant Director - how do you have sign-off authority?"**
Use STAR Story 9. Moody's runs a formal governance framework where sign-off is delegated by role, not title: the Assistant Director seat is an IC-with-independent-review-authority role. The sign-off attests to the defensibility of specific analytical outputs - curve construction, spread calibration, sensitivities, scenario behaviour - not to a client's investment strategy. Portfolios range $5-25bn per engagement, cumulatively ~$50bn+ across the book.

**3. "How would you validate a retail credit scorecard you've never seen before?"**
Be honest that my hands-on inventory is valuation, market, and balance-sheet models, then show the generalisable framework: conceptual soundness (is the target variable and segmentation fit for intended use), data lineage and input review, replication of the estimated model, discriminatory power and calibration testing on out-of-time samples, a simpler challenger/benchmark as a reference point, sensitivity to assumption changes, and documentation adequacy against policy. Anchor with the aggregation-logic review and economic-defensibility test I already run.

**4. "Show me your Python and data work."**
STAR Story 6 plus Story 1: I migrated a spreadsheet-driven valuation workflow into a Python pipeline (pandas/NumPy/SciPy, PostgreSQL, Git version control), shadow-ran it for two cycles, reconciled outputs, and cut over with a rollback plan - which closed a governance audit and became the template for adjacent workflows. Separately I architected a multi-asset cash-flow projection engine with time-bucketed liquidity gap analytics from T+1 to multi-year.

**5. "How do you write a validation report senior stakeholders will actually act on?"**
Lead with the conclusion and the use-decision (approve / approve-with-conditions / reject), then findings ranked by materiality with each finding tied to evidence and a specific remediation owner. I do this today in analytical summaries for Heads of Risk and did it at Ortec presenting ALM and stress-testing findings to pension investment committees (Story 4) - the discipline is making the quantitative result and the limitation equally legible.

## 3 sharp questions to ask

1. How is the Canadian Banking model inventory split across validators - by model family (PD/LGD/EAD, scorecards, ML challengers) or by business line - and where would this seat sit?
2. As AI/ML models enter the inventory ahead of OSFI E-23's effective date, how is EMRM adapting its validation standards - explainability, drift monitoring, and challenger construction - versus the traditional logistic-regression toolkit?
3. What does the escalation path look like when validation and development can't converge, and how often does a model actually get a conditional or rejected outcome here?

## The one competency gap to prepare for

**Retail credit risk modelling + supervised ML (logistic regression, XGBoost, deep learning).** The Master Repo evidences no PD/LGD/scorecard work and no production ML modelling. Do not claim either. Prepare by (a) being able to talk fluently about scorecard mechanics, PD calibration, Gini/KS, PSI and out-of-time performance testing as *theory you know*, (b) framing the gap as product knowledge rather than method knowledge, backed by the CFA plus dual MSc quantitative base and daily Python, and (c) having one credible learning plan sentence ready ("first 90 days: shadow two scorecard validations and rebuild a challenger in Python"). Expect a direct probe - answer it in one sentence and pivot back to the governance and escalation evidence, which is the strongest part of the profile.