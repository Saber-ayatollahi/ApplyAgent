## 5 likely technical / role questions

**1. "Walk me through how you onboarded a client onto a new analytics platform end-to-end."**
Use STAR Story 3 (Calypso → PFaroe migration). A pension client's ALM and portfolio configuration requirements were getting lost between their investment desk and the Moody's dev team. I scoped requirements into structured Product Owner requests, walked the PO through the investment team's decision logic, and translated dev constraints back into investment language. Client onboarded on schedule and the configuration pattern was reused across the rest of the migration cohort.

**2. "You're the RM. A client's PM team says the risk numbers look wrong. What do you do?"**
Use STAR Story 2. I've lived this: an output passed every internal check but contradicted the client's economic intuition under a specific rate shock. I held the release rather than sign off under deadline pressure, decomposed sensitivities by asset class, found a curve-calibration edge case at the short end, escalated to product owners and the client's Head of Risk, and walked them through remediation. 48-hour delay, client avoided acting on wrong numbers, and I became their standing escalation contact.

**3. "Explain portfolio optimization and risk decomposition as you've actually used them."**
At Ortec on the GLASS platform I ran both asset-only and asset-liability (surplus) optimization on VaR and CVaR, then decomposed contribution-to-risk to see which exposures were actually driving funding-ratio volatility. I also explored near-optimal portfolios around the frontier — the point being that a single 'optimal' allocation is fragile, and showing a committee the near-optimal neighbourhood is what makes the recommendation adoptable.

**4. "How do you get a client to adopt more of the platform?"**
Ground it in the same mechanic I used at Moody's: adoption follows an unsolved investment problem, not a feature list. In the LDI study (Story 4) the client's real question was whether their fixed-income duration positioning survived a liability-duration extension; answering it required scenario-generator functionality they weren't using. Solve the problem, and the capability sells itself — then feed the gap back to Product.

**5. "How technical are you day to day?"**
Python is my primary tool — pandas/NumPy/SciPy — and I re-engineered spreadsheet-driven valuation workflows into production pipelines with logging and version control (Story 6: parallel-built, shadow-run two cycles, reconciled, cut over with rollback). SQL at intermediate level, PostgreSQL day-to-day. I also build agentic development workflows in Claude Code and Cursor that cut comparable module cycle time ~30–40%.

## 3 questions Saber should ask

1. "Which client segments does this book cover — and how much of the seat is deepening existing adoption versus rescuing at-risk relationships? The playbooks are very different."
2. "How does the feedback loop from Front Office RMs into Product Management actually work today — what does a 'win' look like when a client's request gets built?"
3. "For front-office users specifically, where do you see the biggest gap between what Aladdin can do and what clients currently use it for?"

## The one competency gap to prepare for

**Private markets / eFront.** The JD asks for industry knowledge across both private and public markets; the evidenced record is public-market and multi-asset institutional (pension, insurance, asset-manager portfolios), plus liability modelling — not private-markets fund accounting, capital calls, or eFront. Own it directly: "My depth is public multi-asset and liability-side; on private markets I've worked around illiquid allocations in SAA studies but I haven't run an eFront implementation. I'd expect to close that in the first quarter." Do not bluff — an eFront-fluent interviewer will find the floor in two questions. Same discipline on **performance attribution** (my attribution work is risk attribution / contribution-to-risk, not return attribution) and **Linux/JavaScript** (not part of my stack).