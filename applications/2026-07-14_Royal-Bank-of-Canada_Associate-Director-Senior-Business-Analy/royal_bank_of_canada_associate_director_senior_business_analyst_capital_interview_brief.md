## Likely Technical Questions

**1. Walk me through how you would design the data model for a Client Revenue Analytics platform spanning CIB and Global Markets.**
> I'd start from the grain of the fact — one row per client per product per period — and work backwards to conformed dimensions (client, product, desk, currency, book). At Moody's I did the analogous exercise designing security- to portfolio-level aggregation for the cash-flow engine: defining keys, reference-data joins, and validation protocols before any downstream analytic. I'd insist on a reference-data governance layer (client hierarchy, product taxonomy) as its own workstream, because that's where wrong numbers actually come from.

**2. Give me an example of translating ambiguous business requirements into technical specifications.**
> STAR Story 3 (Master Repo): During Calypso→PFaroe migration a pension client's ALM requirements were being lost between their investment desk and Moody's dev team. I scoped their decision logic into structured Product Owner tickets, walked PO through the investment rationale, and translated dev pushback back into investment language. Client onboarded on schedule and the pattern was reused across the migration cohort.

**3. How do you handle a stakeholder pushing back on an analytical output they don't like?**
> STAR Story 2: I once held a client release for 48 hours because portfolio sensitivities passed internal checks but didn't square with the client's economic intuition under a specific shock. Decomposing by asset class surfaced a short-end curve-calibration edge case. Held the release, escalated to POs and the client's Head of Risk with a remediation plan. Built trust — became their direct escalation contact.

**4. How advanced is your SQL, honestly, and where's your ceiling?**
> Advanced hands-on for data modeling, complex joins, window functions, CTEs, and validation queries against relational stores — that's my daily bread at Moody's, on PostgreSQL. Ceiling: I've not tuned petabyte-scale warehouses; my scale is enterprise institutional books, not exchange-tick volumes. Python + SQL is where I'm strongest; I'd pair with a data engineer on deep warehouse-optimization work.

**5. Tell me about running Agile delivery across business and technical teams.**
> At Moody's I participate in sprint planning, backlog grooming, and acceptance with Product Owners and engineering — I write the acceptance criteria my sign-off attests to. STAR 6 (spreadsheet→Python migration) is a governance-driven Agile delivery: parallel-built, shadow-ran two cycles, reconciled, then cut over with rollback plan. Milestone hit, audit closed clean.

## Questions Saber Should Ask

1. How is 'client value' currently measured across CIB vs Global Markets, and where are the biggest reconciliation gaps between the two views today?
2. What's the state of reference-data governance for client hierarchy and product taxonomy — is there a golden source, or is this initiative building one?
3. Who owns the trade-off decisions when a business stakeholder wants a metric that the underlying data can't yet defend? How is that escalation path structured?

## Competency Gap to Prepare For

**Direct sell-side / trading-desk Capital Markets experience.** Saber's Capital Markets exposure is buy-side and institutional-investor-facing (pensions, asset managers, insurers) via Moody's and Ortec — not a CIB or Global Markets desk. Prep by refreshing on: credit exposures and new-issuance economics, trade lifecycle at a high level, return-on-risk-capital metrics (RoRWA, RAROC), and reference-data pain points in front-office workflows. Frame the gap honestly if probed: 'My Capital Markets fluency is on the analytics and risk side — I've built the systems that measure this, not sat on the desk. I close the desk-context gap fast in the first 60 days by embedding with the sales/banking coverage teams.'