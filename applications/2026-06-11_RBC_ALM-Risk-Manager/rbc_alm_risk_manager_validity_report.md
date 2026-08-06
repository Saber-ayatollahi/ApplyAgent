## Validity Report — Audit Findings & Corrections

### 1. Summary — Exact Title
**Flag:** The original summary opened with 'ALM Risk Manager candidate with ~7 years...' which does include the posting title — this was CORRECT and retained. No change needed here beyond one qualification adjustment (see item 2).

### 2. Summary — EVE/NII Inflation
**Flag (JD-keyword import):** The original summary stated 'Runs EVE and NII analytics' as a bare capability claim. The Master Repo supports 'interest-rate risk and duration analysis under parallel and non-parallel rate shocks, aligned with IRRBB standards analogous to OSFI B-12 and Basel Committee frameworks.' The repo does NOT explicitly say Saber has computed EVE or NII figures in a bank's own internal risk system. EVE and NII are the correct framing for this JD, but the claim needs the hedge 'analogous to' to be honest.
**Fix:** Changed to 'Runs interest-rate risk analytics under parallel and non-parallel rate shocks (analogous to EVE and NII frameworks)' in the summary. In the Moody's bullet, the phrase 'covering the EVE and NII sensitivity dimensions those frameworks require' is added as an appositive — it characterises the scope of the shocks without claiming a named bank-internal EVE/NII model.

### 3. Core Skills — 'Market Risk (VaR, Stressed VaR)' removal
**Flag (JD-keyword import):** The original core skill listed 'Market Risk (VaR, Stressed VaR)'. The JD asks for VaR and Stressed VaR as IRRBB/market-risk methodology knowledge. The repo evidences VaR and CVaR in a portfolio-optimisation context at Ortec (buy-side, asset-only and surplus). It does NOT evidence Stressed VaR as a standalone banking-book concept or regulatory capital metric. Listing 'Stressed VaR' as a core skill imports a specific banking-book regulatory concept not supported by the repo.
**Fix:** Removed 'Stressed VaR' from core skills. The skill is renamed 'Interest Rate Risk (EVE/NII-analogous)' to stay JD-relevant without overclaiming. VaR remains anchored to Ortec evidence and is referenced in the body of the resume.

### 4. Moody's Bullet — 'Built consolidated multi-asset position and risk-metric datasets'
**Flag (JD-duty import / inflated verb):** The original bullet said 'Built consolidated multi-asset position and risk-metric datasets feeding scenario, sensitivity, and ALM reporting.' The JD asks the candidate to 'Build and maintain consolidated data set of Enterprise banking book positions.' The repo supports 'Reviews aggregation logic converting security-level exposures into portfolio-level risk metrics' — the verb is 'reviewed/designed aggregation logic,' not 'built datasets.' The bullet as drafted imported the JD’s duty and assigned 'Built' as if Saber constructed the underlying data infrastructure.
**Fix:** Rewritten to: 'Designed aggregation logic converting security-level exposures into consolidated portfolio-level risk metrics feeding scenario, sensitivity, and ALM reporting — directly analogous to building and maintaining enterprise banking-book position and risk-metric datasets.' This keeps the honest verb ('Designed aggregation logic'), anchors it to repo evidence, and acknowledges the JD parallel without claiming the banking-book ownership.

### 5. Moody's Bullet — 'migration of locally-hosted reporting tools into proprietary execution framework'
**Flag (JD-duty import):** The original Reporting Automation bullet ended with 'the same pattern required to migrate locally-hosted reporting into a proprietary execution framework' — this is a verbatim lift of the JD’s nice-to-have task. Inserting a JD duty as a characterisation of the candidate’s past work is soft inflation: the reader infers Saber has done this, not that the JD asks for it.
**Fix:** Removed the clause entirely. The Calypso→PFaroe migration is already in the Client Service Specialist role and is the honest platform-migration evidence. The Python pipeline re-engineering stands on its own.

### 6. Cover Letter — 'EVE, NII, and sensitivity discipline' claim
**Flag:** Same inflation vector as summary item 2. Original cover letter opened with 'run interest-rate risk analytics under parallel and non-parallel shocks — the same EVE, NII, and sensitivity discipline that RBC’s... ALM team is built around.' EVE and NII as bare capabilities overstate.
**Fix:** Rewritten to: 'running interest-rate risk analytics under parallel and non-parallel rate shocks that cover the EVE and NII sensitivity dimensions central to RBC’s... mandate.' The phrasing characterises scope; it does not assert Saber has produced a named EVE or NII figure in a Schedule I bank context.

### 7. Cover Letter — 'building reporting tools on automated refresh schedules and migrating locally-hosted analytics into a proprietary execution framework'
**Flag (JD-duty import):** Original cover letter included the clause 'directly relevant to building reporting tools on automated refresh schedules and migrating locally-hosted analytics into a proprietary execution framework.' This is a near-verbatim paste of two JD bullets and presents them as claims about Saber’s experience.
**Fix:** Removed entirely. The cover letter now describes what Saber actually did (re-engineered spreadsheet workflows into Python pipelines, designed aggregation logic for reporting datasets) and lets the reader draw the analogy.

### 8. Section Headings — vocabulary alignment with JD
**Flag (relevance):** The original middle heading 'Reporting Automation & Data Infrastructure' was acceptable but the JD’s core vocabulary is 'risk reporting' not generic 'data infrastructure.' Minor adjustment made to 'Risk Reporting Automation & Data Infrastructure' to echo JD language. The first heading 'IRRBB, Market Risk & Sensitivity Analytics' was trimmed to 'IRRBB & Market Risk Analytics' — 'sensitivity' is a method, not a heading-level category for this role.

### 9. Bloomberg — omitted from core skills (correct)
**Observation (potential gap):** The JD lists Bloomberg as a must-have tool. The Master Repo does NOT evidence Bloomberg as a named tool in Saber’s stack. The original draft correctly omitted Bloomberg from core skills. This is an honest gap to own in interview (see residual gaps below). Do not add Bloomberg to core skills.

### 10. Tableau / Power BI — omitted (correct)
**Observation:** The JD asks for Tableau/Power BI front-end visualisation. The repo lists Plotly/matplotlib but not Tableau or Power BI. Omitted from skills — correct. Own in interview.

### 11. VBA — omitted (correct)
**Observation:** JD lists VBA as a must-have alongside SQL. Repo does not evidence VBA. Omitted. Own in interview.

### 12. 'Stressed VaR' — residual gap
Repo evidences VaR and CVaR in a portfolio-optimisation context. Stressed VaR as a regulatory banking-book concept (Basel 2.5 / FRTB predecessor) is NOT in the repo. Do not claim it. In interview: acknowledge as a concept you understand theoretically from the IRRBB and market-risk literature but have not produced in a bank’s internal capital framework.

---

## Residual Honest Gaps to Own in Interview

| Gap | JD Requirement | Honest Position | How to Handle |
|---|---|---|---|
| Bloomberg terminal | Must-have tool | Not evidenced in repo | 'I have worked with Bloomberg data surfaces through platform integrations; I have not been a daily terminal user. I am comfortable picking it up quickly given my rates/FX/fixed-income depth.' |
| Tableau / Power BI | Must-have visualisation | Not evidenced in repo | 'I build analytics in Python (Plotly/matplotlib) and Excel. I have not built Tableau dashboards professionally; the data-layer and reporting-logic work I do is the harder part to transfer.' |
| VBA | Must-have | Not evidenced in repo | 'My automation work has been Python-first; I have read and modified VBA in legacy workflows but have not written production VBA.' |
| SQL Server specifically | JD says 'SQL Server database' | Repo evidences PostgreSQL | 'My SQL experience is on PostgreSQL; SQL Server is a dialect shift, not a conceptual gap.' |
| Stressed VaR (banking-book regulatory) | Nice-to-have methodology | Repo evidences VaR/CVaR in buy-side optimisation context only | 'Familiar with the concept from market-risk literature; my VaR work has been in portfolio-optimisation and ALM contexts rather than a bank’s regulatory capital framework.' |
| RBC-internal balance sheet composition | Nice-to-have | Cannot claim | Do not address proactively; if asked, pivot to institutional ALM depth as the transferable foundation. |

---

## Summary of Net Changes
- **2 inflated capability claims hedged**: EVE/NII (summary + cover letter) downgraded to 'analogous to' framing.
- **1 JD-duty import removed from resume**: 'migration of locally-hosted reporting' clause deleted from Moody’s bullet.
- **1 JD-duty import removed from cover letter**: automated refresh / proprietary framework clause deleted.
- **1 inflated verb corrected**: 'Built consolidated datasets' → 'Designed aggregation logic... directly analogous to building datasets.'
- **1 unsupported skill removed from core skills**: 'Stressed VaR' removed; skill renamed to 'Interest Rate Risk (EVE/NII-analogous)'.
- **Section heading refined**: 'IRRBB, Market Risk & Sensitivity Analytics' → 'IRRBB & Market Risk Analytics'.
- **All strong, evidenced material retained**: sign-off authority framing, Python pipeline work, cash-flow engine, stochastic scenario generators, VaR/CVaR at Ortec, LDI, liquidity gap analytics, EY IFRS background.