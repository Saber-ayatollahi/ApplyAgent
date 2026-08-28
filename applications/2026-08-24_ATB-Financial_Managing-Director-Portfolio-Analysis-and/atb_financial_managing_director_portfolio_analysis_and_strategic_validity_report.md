## JD core themes (mirror check)
1. Top-of-house (TOH) market risk view spanning BOTH trading and banking books.
2. Risk infrastructure build-out — data structure/governance, connectivity to pricing and risk engines (Murex, DEEP/BigQuery).
3. Stress testing and scenario design across trading and banking books.
4. Governance and stakeholder coordination (Treasury, Front Office, MROC, ALCO) plus team recruiting/mentoring/management.
5. Process calibration — TOH risk-appetite limits, review-and-challenge for enterprise models including VaR backtesting.

## Changes made and why

**Summary**
- Kept the exact posting title verbatim per rule 8 ('Managing Director, Portfolio Analysis and Strategic Initiatives') — this was already present and unchanged.
- Softened 'holds delegated sign-off... balance sheet risk outputs' framing is unchanged (repo-supported), but added 'portfolio-level risk aggregation review and senior-stakeholder risk commentary' in place of vaguer wording, to mirror the JD's TOH-reporting language using terms the repo actually supports (aggregation review, senior-stakeholder summaries) rather than claiming literal 'top-of-house' bank-wide ownership, which Saber has not held.

**Core skills**
- Renamed 'Enterprise Market Risk Analytics' to 'Institutional Portfolio & Market Risk Analytics.' The original label borrowed the JD's own team name (Enterprise Market Risk / EMR) into a prime slot, implying enterprise-bank-wide market-risk ownership that is not evidenced — the repo supports institutional, multi-asset, client-portfolio-level risk work, not a bank's own enterprise book.
- Renamed 'Derivatives Valuation & Sensitivity Review' to 'Derivatives Pricing Validation & Sensitivity Review.' The repo evidences that Saber *validates* derivatives pricing outputs (rates, FX, inflation) and cross-checks sensitivities — he does not price/value derivatives himself. 'Valuation' overstated the verb.
- Confirmed 'Python, SQL & Risk Data Pipelines' is repo-grounded (§4.8: Python advanced, SQL intermediate/PostgreSQL) — kept as-is.
- Confirmed no Murex, Tableau, or DEEP/BigQuery terms appear anywhere in core_skills or bullets — correctly excluded since ungrounded; these only appear, appropriately hedged as 'would come in learning,' in the cover letter.

**Bullets**
- Removed 'enforcing consistency of risk aggregation across asset classes' from the aggregation-logic bullet — this clause was not present in the master repo bullet ('Reviews aggregation logic converting security-level exposures into portfolio-level risk metrics feeding downstream ALM and capital processes') and read as an unearned strengthening of the aggregation claim. Reverted to the repo-supported phrasing.
- Removed 'removing manual handling from the production reporting path' from the Python-pipeline bullet. This was a JD-keyword import — it echoes the JD's Strategic Initiatives language about 'significantly reduce manual data adjustments in daily liquidity and balance sheet reporting,' a specific ATB deliverable Saber has not performed. Reverted to the repo-verbatim bullet.
- Confirmed the IRRBB/Basel language keeps the repo's own hedge ('aligned with IRRBB standards analogous to Basel / OSFI B-12') rather than a bare claim of Basel-IRRBB ownership — compliant with rule 4.
- All other bullets checked line-by-line against §5 tagged library and §3 experience — no unsupported verbs, tools, or duties found; 'Led,' 'Architected,' 'Built,' and 'Serve on' all trace to repo language.

**Cover letter**
- Softened the opening claim from an implied 'I have already built the exact ATB pillar once' framing to 'sits close to work I already do' — the original overstated parity between a vendor-side client-analytics engine build and a newly established bank-wide TOH function spanning trading and banking books, governance stakeholders (Treasury/Front Office/MROC/ALCO), and a to-be-recruited team.
- Reworded the Calypso reference. The original ('the pricing- and risk-engine work I have done across PFaroe, Calypso migration, and Ortec GLASS') implied Saber built pricing/risk-engine functionality on Calypso; per the repo he migrated clients *off* Calypso onto PFaroe and validated outputs post-deployment — he did not build on Calypso itself. Reworded to 'the platform and modelling work I have done across PFaroe delivery, the Calypso-to-PFaroe migration, and Ortec's GLASS optimization engine,' which is accurate to the migration/liaison role actually performed.
- Kept the explicit, honest hedge that trading-book depth is not present and that Murex/DEEP/BigQuery would be learned on the job — this is the correct treatment of the repo's flagged retired/opportunistic gap (§7.5) and should not be removed or oversold in either direction.
- Verified word count: approximately 332 words across three body paragraphs plus salutation/close — within the 300-350 word requirement.

## Residual honest gaps to own in interview
- **Trading-book market risk**: no evidence anywhere in the repo (VaR backtesting, FRTB, CCR-xVA, trading-desk P&L). The JD explicitly requires TOH coverage across 'trading AND banking books.' This is the single biggest honest gap for this specific mandate — be ready to pivot immediately to banking-book/ALM depth and offer to partner with existing trading-desk market-risk SMEs rather than claim hands-on trading-book experience.
- **Team recruiting/management**: the JD explicitly requires 'Recruit, mentor, and manage the team.' The repo only supports informal 'mentorship of junior colleagues' (§4.10) within an IC-plus-senior-review role, not formal people management, hiring, or team-building at scale. Do not claim team leadership on the resume; in interview, pivot to the PO-liaison, Head-of-Risk escalation-contact, and cross-functional coordination stories (STAR stories 3 and 9) as adjacent evidence of leading-without-authority.
- **VaR backtesting specifically**: Ortec experience is VaR/CVaR portfolio *optimization* and risk decomposition via GLASS, not backtesting of an enterprise VaR model. Do not claim backtesting experience directly; frame as adjacent quantitative familiarity with VaR/CVaR mechanics.
- **Murex, Tableau, DEEP/BigQuery**: none evidenced. Correctly absent from resume; cover letter hedges as 'would come in learning' — hold this line in interview rather than claiming familiarity.