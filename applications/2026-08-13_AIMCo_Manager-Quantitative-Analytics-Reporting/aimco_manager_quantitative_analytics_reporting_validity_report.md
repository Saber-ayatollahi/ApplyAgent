## JD Core Themes
1. Validate/interpret investment risk analytics and ensure accuracy of reported results.
2. Investigate and explain changes in risk metrics, portfolio exposures, and performance drivers.
3. Build/maintain risk reports, dashboards, databases, and analytical tools; data quality and governance.
4. Enhance risk-systems, reporting infrastructure, and automation via modern tools/programming.
5. Collaborate with internal teams and external vendors to resolve system/data/modeling/reporting issues.

## Fixes Applied

1. **'Data Quality Controls' core_skill (Rule 3/7 — JD-noun import).** The repo's tagged bullet library uses 'auditability controls', not 'data quality controls'. The draft silently swapped in the JD's exact phrase ('data quality' appears verbatim in the JD). Renamed the skill to 'Independent Model Review & Documentation Standards' and reverted the matching resume bullet ('...embedded logging, validation, and auditability controls') to the repo's true wording. 'Data quality' as a distinct discipline (profiling, remediation, lineage) is not evidenced anywhere in the repo and must not be claimed as a named capability.

2. **Client Service Specialist migration bullet (Rule 1/7 — JD duty imported as experience).** The draft added '...and resolving configuration, data, and reporting issues' onto the Calypso-to-PFaroe migration bullet. This clause is not in the repo's tagged bullet ('Successfully migrated all assigned client accounts from a legacy Calypso environment to a modern PFaroe PM platform, validating model outputs post-deployment') and closely mirrors the JD's own line ('resolve system, data, modeling, and reporting issues'). Reverted to the repo's exact bullet — no fabricated added scope.

3. **PFaroe DB label mismatch (minor accuracy).** Draft labelled it '(risk analytics)'; corrected to '(risk & ALM analytics)', the exact parenthetical the repo itself uses in Section 3.1, so the label is both accurate and consistent across the resume.

4. **MSc parenthetical.** Summary said 'MSc (Financial Modelling, Engineering)', dropping 'Chemical'. Restored to 'Financial Modelling, Chemical Engineering' to match Section 2/Education exactly — no need to hide the engineering degree; the repo explicitly treats it as a quant-credibility asset, and the JD lists 'another relevant quantitative discipline' as acceptable.

5. **Cover letter — 'from both sides of that table' (Rule 5 — unsupported buy-side claim).** The original draft implied Saber has sat on the asset-owner side collaborating with external vendors (exactly what AIMCo's JD line 'collaborate with internal teams and external vendors to resolve system, data, modeling, and reporting issues' describes). In truth, Saber has only ever been on the vendor/consulting side (Moody's, Ortec, EY) — never inside a pension fund or asset-owner seat. Rewrote to 'both the vendor-delivery side... and direct pension-fund advisory work at Ortec Finance' — truthful and still relevant, without claiming the buy-side seat itself.

6. **Cover letter — 'data quality controls' phrase.** Same fix as #1, changed to 'embedded logging and validation' in the final paragraph, dropping the unearned 'data quality' label.

7. **Cover letter paragraph count (Rule: 3 paragraphs, 300-350 words).** Draft had four paragraphs (intro / mandate+story / AIMCo hook / closing-logistics). Merged the closing-logistics sentence into paragraph 3 to produce exactly three paragraphs. Recounted at ~324 words — within the 300-350 band.

8. **Exact title check (Rule 8).** Summary's first sentence already contains 'Manager, Quantitative Analytics & Reporting' verbatim — retained.

## Relevance / Mirror Check
Section headings ('Risk Analytics Validation & Insight', 'Portfolio Exposure, Stress & Scenario Analytics', 'Risk Reporting, Automation & Governance') already echo the JD's own accountability language (validate/interpret, portfolio exposures/stress/scenario, reporting/automation/governance) rather than generic ALM/IRRBB/banking-platform groupings — no IRRBB, OSFI B-12/E-23, or Basel language leaked into prime slots (summary, headings, core_skills). This was already correctly de-emphasized in the draft; no further reframing needed there.

## Nothing Added That Wasn't Already There
No Databricks, Power BI, Aladdin, or 'risk limits/breach monitoring' language was fabricated — these are JD preferred-qualification/duty items with zero repo support, and the draft correctly avoided claiming them. Left untouched.

## Residual Honest Gaps to Own in Interview
- **No direct buy-side/asset-owner employment.** Every pension-fund and asset-manager relationship in Saber's record (Moody's, Ortec) has been as vendor/consultant, not as an internal team member at the asset owner. Frame this honestly: 'I've been the outside rigor applied to these portfolios, not the internal team — the validation discipline is identical, the org-chart seat is different.'
- **No named platform overlap (Databricks/Power BI/Aladdin).** If asked, be direct: hands-on with Python/SQL and PFaroe's own analytics stack, not these specific tools — but the underlying workflow (ingest, validate, report, automate) transfers.
- **No explicit 'risk limits and breach monitoring' experience** as described in the JD's second bullet; closest analog is escalation of economically-indefensible model outputs, which is adjacent but not identical — do not claim limit-monitoring/breach-resolution process ownership directly.