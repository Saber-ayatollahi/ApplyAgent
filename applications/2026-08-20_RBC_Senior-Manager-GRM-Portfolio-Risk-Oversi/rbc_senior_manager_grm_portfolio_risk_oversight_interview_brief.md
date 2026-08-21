## Likely technical questions (with model answers)

**1. "Walk me through how you would build a loss-stressing model for a commercial portfolio."**
Start from the framework I have actually built: the multi-asset cash-flow projection engine at Moody's, where base, stress, and reverse-stress scenarios run off a common scenario spine with behavioural assumptions (prepayment, drawdown timing) layered on top. For a credit book the same architecture applies - segment the portfolio by risk driver, map macro scenarios to segment-level loss drivers, and validate that the stressed output is economically defensible, not just mathematically produced. I would be explicit that calibrating PD/LGD on a BFS book is the piece I would learn on the job.

**2. "How do you decide where risk is actually concentrated in a portfolio?"**
Decomposition rather than headline numbers. At Ortec I ran contribution-to-risk and risk-attribution analysis on VaR and CVaR-optimized portfolios, then explored near-optimal portfolios around the efficient frontier to test whether a concentration finding was robust or an artifact of the optimizer. The output that changes a committee's mind is 'these three segments drive 60% of tail risk', not a single aggregate number.

**3. "Tell me about a time your analysis contradicted what a stakeholder wanted to hear."**
(STAR 2) A client-delivery run produced sensitivities that passed every internal check but did not square with economic intuition under a specific rate shock. I held the release under deadline pressure, decomposed sensitivities by asset class, isolated a curve-calibration edge case at the short end, and escalated to the product owners and the client's Head of Risk with a remediation plan. Release slipped 48 hours; the client avoided acting on wrong numbers and I became their direct escalation contact.

**4. "How strong is your Python/SQL, concretely?"**
Daily, production-facing. Python (pandas, NumPy, SciPy) for the projection engine and for re-engineering spreadsheet workflows into pipelines with logging, validation, and version control; SQL/PostgreSQL for the data layer. I also run agentic development workflows (Claude Code, Cursor) for first-pass code review and validation scaffolding - roughly 30-40% cycle-time reduction on comparable modules, with human sign-off retained on anything governance-critical. Visualization is Plotly/matplotlib; I have not used Tableau, and would pick it up quickly.

**5. "How do you make a technical result land with senior leadership?"**
(STAR 4) The Ortec LDI study: the committee's real question was whether their fixed-income duration positioning was appropriate against an extending liability. I ran funding-ratio distributions under base and stressed regimes, decomposed the duration gap's contribution to funding-ratio volatility, and presented one recommendation with the trade-off quantified. They adopted the duration extension. The discipline is: lead with the decision, show two or three numbers that support it, keep the methodology in the appendix.

## Questions Saber should ask

1. What does the Portfolio Management Committee currently *not* get that it should - is the gap in data, in forecasting capability, or in how the narrative is framed?
2. Where does this role's loss-forecasting work sit relative to the bank's IFRS 9 / stress-testing model development and validation teams - am I a consumer of those models, a challenger of them, or building alongside?
3. What does 'Best of Class' look like 12 months in, and which one reporting process would you most want rebuilt first?

## The competency gap to prepare for

**Commercial credit risk fundamentals for the BFS book.** No PD/LGD/EAD estimation, ECL modelling, credit migration, or covenant/watchlist experience in the record. Before the HM round: refresh commercial credit loss mechanics (PD x LGD x EAD, through-the-cycle vs point-in-time, IFRS 9 stage transfer logic), and be able to name BFS portfolio segments and their cyclicality. Own it in the first ten minutes rather than being caught: 'multi-asset market and balance-sheet risk is my portfolio; the credit book itself is the learning curve, and here is the machinery I bring to it.'