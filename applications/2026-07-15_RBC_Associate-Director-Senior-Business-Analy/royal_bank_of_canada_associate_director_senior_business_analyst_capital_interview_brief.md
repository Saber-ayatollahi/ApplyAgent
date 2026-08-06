## Likely Technical / Domain Questions

**1. Walk me through how you'd take an ambiguous 'measure client profitability' ask and turn it into data specifications.**
Start from stakeholder intent, decompose into the components (revenue by business line, resource/capital consumption, reference-data joins), then write functional specs and data models with explicit validation rules. Reference Story 3 (bridging investment team and dev org): I scoped requirements into structured Product Owner requests, translated dev pushback back into business language, and reused the pattern across the cohort.

**2. Give an example of establishing data-quality and validation standards.**
Use Story 6 (spreadsheet-to-Python governance upgrade): parallel-built the pipeline, ran it in shadow mode for two cycles, reconciled outputs, then cut over with a rollback plan - closing a governance audit and creating a reusable template. Frame validation protocols and auditability as first-class deliverables, not afterthoughts.

**3. How do you handle an output that looks technically correct but is business-wrong?**
Story 2: a client run passed every internal check but failed economic intuition under a rate shock. I held the release, decomposed sensitivities by asset class, traced it to a curve-calibration edge case, escalated to Product and the client's Head of Risk, and got it fixed upstream with a new validation test. Sign-off is about defensibility, not deadline convenience.

**4. Describe your hands-on SQL and data-modeling work.**
Be concrete: PostgreSQL day-to-day, re-engineered spreadsheet workflows into Python/SQL pipelines with embedded logging and validation, and reviewed aggregation logic from security-level to portfolio-level metrics and return calculations. Honest ceiling: intermediate-to-advanced SQL - lead with data-modeling judgment, not exotic tuning.

**5. How do you drive Agile delivery while keeping strategic alignment?**
At Moody's I scope requirements into PO requests, participate in scrum, define acceptance criteria, and manage stakeholder sign-off across the product lifecycle from design through production monitoring. Balance short-term delivery with long-term interest by making validation and documentation standards part of definition-of-done.

## Sharp Questions Saber Should Ask

1. How are the Client Revenue Analytics, Client Resource Consumption, and Client Wallet platforms currently stitched together - is this a greenfield build or a rationalization of existing reference-data silos?
2. Where does this role's authority end and the Risk/Finance capital-measurement teams' begin when definitions of 'client value' conflict?
3. What does the target-state cloud data architecture (AWS/Azure) look like, and how mature is the migration today?

## The One Competency Gap to Prepare For

**Direct Capital Markets front-office product depth (credit exposures, new issuances, xVA/CCR, trade lifecycle) and named tooling (Tableau, cloud platforms).** The JD wants ~10 years and CM-specific product knowledge; Saber has ~7 years in ALM/risk analytics, not front-office CIB/Global Markets. Own it honestly: emphasize transferable strength in reference data, risk metrics, return calculations, validation, and requirements translation; position Tableau/cloud as adjacent (Python/SQL/PostgreSQL, agentic-AI, platform migrations) that he can ramp quickly. Do NOT claim Tableau, xVA/CCR, or trade-lifecycle experience - frame them as fast-ramp areas.