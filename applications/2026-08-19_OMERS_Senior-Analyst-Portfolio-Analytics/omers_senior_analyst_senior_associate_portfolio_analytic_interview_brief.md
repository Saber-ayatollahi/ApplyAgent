## 5 likely technical questions

**1. "Walk us through how you'd build a CVaR-optimized overlay allocation."**
At Ortec I ran asset-only and asset-liability (surplus) optimization on VaR and CVaR through the GLASS platform: calibrate a stochastic economic scenario generator to the client's assumptions, simulate joint asset/liability paths, then optimize on the tail statistic rather than variance so the solution is driven by the loss distribution's left tail. I always paired the optimal point with near-optimal frontier analysis and risk decomposition (contribution-to-risk), because a CVaR optimum is unstable to input estimates — the robustness check is the part that survives committee scrutiny.

**2. "How do you guarantee data quality in an analytics pipeline?"** (STAR Story 6)
A Moody's valuation workflow was spreadsheet-driven with no logging or versioning and would not survive a governance audit. I parallel-built the Python pipeline, ran it in shadow mode for two production cycles, reconciled outputs line by line, and cut over with a rollback plan. Embedded logging, validation checks, and documented escalation paths were the deliverable — not an afterthought — and the pattern became the template for adjacent workflows.

**3. "Tell us about a time your model output looked right but wasn't."** (STAR Story 2)
A client run produced portfolio sensitivities that passed every internal check but conflicted with the client's economic intuition under one rate-shock scenario. I held the release under deadline pressure, decomposed sensitivities by asset class, and isolated a curve-calibration edge case in short-end inversion handling. Release slipped 48 hours, the defect was fixed upstream and captured in validation tests, and I became the client Head of Risk's direct escalation contact.

**4. "What derivatives work have you actually done?"**
At Moody's I validate derivatives pricing outputs across rates, FX, and inflation and check that sensitivities aggregate consistently to the portfolio level — review-and-challenge of pricing, not desk-side model development. At Ortec I built the hedging analysis behind interest-rate, inflation, and currency overlays for international clients, including the currency and leverage overlay strategies in a three-plan pension merger. Be explicit about the review-vs-build boundary; it reads as credible, and the aggregation and sensitivity-consistency work is the directly transferable piece for overlay analytics.

**5. "How do you translate a PM's ask into a built product?"** (STAR Story 3)
During the Calypso→PFaroe migration a pension client's configuration requirements kept getting lost between their investment desk and our development team. I scoped the requirements into structured Product Owner requests, walked the PO through the investment team's decision logic, and translated engineering pushback back into investment language. The client onboarded on schedule and the configuration pattern was reused across the rest of the migration cohort.

## 3 questions Saber should ask

1. Overlay Management is newly established — for the first twelve months, is Portfolio Analytics' priority building the rebalancing/exposure data foundation, or delivering signal-level analytics for TAA and tail-risk hedging?
2. Where does the ownership line sit between Portfolio Analytics and the Data & Technology team — do you productionize your own pipelines, or hand off to engineering after prototype?
3. The posting mentions ML and AI for alpha generation. What has actually made it into production so far, and what has been tried and shelved?

## The one competency gap to prepare for

**The named tech stack: Redis, Parquet, and Azure DevOps CI/CD.** Saber has advanced Python (pandas/NumPy/SciPy), intermediate SQL on PostgreSQL, Git, and CI/CD in a professional context — but not Redis or Parquet, and his CI/CD is not Azure DevOps specifically. Answer honestly and pivot to the transferable frame: "I've shipped production pipelines under version control and CI/CD with shadow-mode reconciliation; caching layers and columnar storage formats are tooling choices I'd pick up in weeks, not a modelling gap." Do not bluff query-optimization or indexing depth beyond day-to-day PostgreSQL use. Same discipline for ML: the AI evidence is agentic developer tooling (Claude Code, Cursor), not trained ML alpha models.