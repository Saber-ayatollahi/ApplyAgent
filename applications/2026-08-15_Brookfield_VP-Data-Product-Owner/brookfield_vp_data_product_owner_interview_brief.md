## 5 likely technical/role questions

**1. "How would you prioritize a backlog of data product requests from competing business groups?"**
My Moody's model is: score by decision impact (what investment or risk decision changes if this exists), feasibility against the current data foundation, and reuse across clients. At Moody's I scoped client requirements into Product Owner requests and the configuration pattern from the first pension-fund migration was reused across the whole migration cohort — reuse is the multiplier I look for first. Where trade-offs are genuinely close, I escalate a short list of decisions rather than adjudicating alone (EY IFRS 17 approach: isolate the three decisions that need executive sign-off).

**2. "How do you embed governance and quality into product delivery without slowing it down?"**
Governance has to be a gate in the pipeline, not a review at the end. I re-built a spreadsheet-driven valuation workflow into a Python pipeline with logging, versioning, and validation baked in, ran it in shadow mode for two cycles, reconciled outputs, then cut over with a rollback plan — the governance audit closed and the pipeline became the template for adjacent workflows. I also sit on Moody's model governance committee, so I write to the documentation and benchmarking standard rather than retrofitting to it.

**3. "Tell me about driving adoption of a product users didn't want to move to."**
Calypso-to-PFaroe migration: adoption stalled because a client's investment desk and our dev team were talking past each other. I scoped the desk's decision logic into structured Product Owner requests, walked the PO through why the logic mattered, and translated dev constraints back into investment language. The client onboarded on schedule and all assigned accounts migrated, with outputs validated post-deployment so users trusted the new numbers.

**4. "How do you measure whether a data product delivered value?"**
Three layers I've used in practice: usage (are the outputs actually feeding the downstream decision — at Moody's, security-to-portfolio aggregations feeding ALM and capital processes), cycle time (agentic AI workflows cut comparable development cycles an estimated 30-40%), and defect/escalation rate (I'm the escalation point for client-critical analytical issues, so escalation volume is a direct quality signal). I'd add a stakeholder feedback loop per release, which is the piece I'd want to formalize at Brookfield.

**5. "Give me an example of holding the line on quality under delivery pressure."**
A client run produced portfolio sensitivities that passed every internal check but didn't square with the client's economic intuition under a specific rate shock. I held the release, decomposed sensitivities by asset class, found a curve-calibration edge case in short-end inversion handling, escalated to the product owners and the client's Head of Risk, and walked them through remediation. Release slipped 48 hours; the client avoided acting on wrong numbers; the defect was fixed upstream and captured in validation tests.

## 3 questions Saber should ask

1. "Which data products would you consider the first proof points for this role — is the near-term mandate consolidating existing assets across business groups, or standing up net-new capabilities for private-markets reporting and analytics?"
2. "Where does decision rights sit today between Technology Services, data engineering, architecture, and the business groups? What has been the friction point that created this new position?"
3. "How is success measured in the first 12 months — adoption metrics, delivery throughput, or governance/standardization maturity? And how are AI use cases currently being sourced and prioritized against them?"

## The one competency gap to prepare for

**Formal data-platform and data-governance-framework fluency.** Saber has never owned a modern data stack (Snowflake/Databricks/dbt, cloud data lakes, catalog/lineage tooling) or run a formal data governance framework (DAMA/DCAM, stewardship councils, data domain ownership), and has never carried a Product Owner title with a Scrum backlog. Prepare an honest bridge: "I've governed the analytics layer that sits on top of the platform — model governance committee, documentation and benchmarking standards, sign-off gates, validation and auditability controls in production Python pipelines — and I've been the requirements-to-Product-Owner translator for institutional clients. I'd expect to lean on the architecture and engineering leads for platform build decisions in the first 90 days while I own the demand side, the prioritization framework, and adoption." Rehearse a crisp answer on agile mechanics (epics, story slicing, definition of done) so the mechanics don't become the objection.