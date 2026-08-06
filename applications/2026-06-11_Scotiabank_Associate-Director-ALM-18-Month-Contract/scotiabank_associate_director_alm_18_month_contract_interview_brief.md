## Top 5 Likely Technical Questions

**1. Walk us through how you'd explain a week-over-week change in EVE to the Treasurer.**
Decompose the move into: (i) curve shift (parallel vs. non-parallel, by KRD bucket), (ii) balance-sheet volume and mix changes, (iii) behavioral assumption updates (prepayment, NMD beta/decay), and (iv) hedge re-positioning. At Moody's I built the analytical scaffolding that produces exactly this attribution at portfolio-level ALM aggregates, and prepared the executive commentary that translates it for non-quant audiences.

**2. How do you handle non-maturity deposit modelling for IRRBB?**
NMDs are the single largest modelling judgment in IRRBB — core/non-core split, beta to policy rates, and decay/repricing profile drive EVE and NII directionally. My approach: anchor assumptions to behavioral data, stress them under the OSFI B-12 standardized shocks, and run sensitivity around the beta/decay parameters. I've embedded analogous behavioral logic (prepayment, cash-flow timing) in the projection engine at Moody's and would expect a formal challenger-model review under the Bank's governance framework.

**3. EVE vs. NII — when do they tell you different stories, and which do you trust?**
EVE captures the present-value impact across the full term structure (long-dated, economic-value lens); NII captures the next 12–24 months of earnings (short-dated, P&L lens). They diverge when there's significant duration mismatch beyond the NII horizon — e.g., a long-duration fixed asset funded by short NMDs can show benign NII but adverse EVE under a steepener. Neither is 'right' — you need both, plus KRD decomposition to localize the exposure.

**4. The team is transitioning to QRM. How would you approach validation of the new ALM model outputs?**
This maps directly onto Story 6 from my track record — the Calypso→PFaroe migration. Parallel-run the new and legacy models for at least two reporting cycles, reconcile EVE/NII/KRD output by product hierarchy and shock scenario, isolate variance drivers (curve construction, behavioral assumption translation, aggregation logic), document tolerances, and only cut over with a rollback plan. Treat the transition as a model-governance event, not an IT migration.

**5. How do you ensure RDARR compliance when sourcing ALM data from enterprise data lakes?**
RDARR (BCBS 239) demands accuracy, completeness, timeliness, and traceability. Practically: lineage documentation from source system to ALM aggregate, reconciliation controls at each transformation step, exception logging on data quality breaks, and version-controlled SQL/Python pipelines (which is what I migrated the Moody's workflows toward). The audit trail has to be reproducible end-to-end — that's how I built the Python pipelines that replaced spreadsheet workflows at Moody's.

## 3 Sharp Questions for Saber to Ask

1. *On the QRM transition — where is the program today (design, build, parallel-run), and what's the gating risk you most want this seat to de-risk over the 18 months?*
2. *How is SIRR governance split between this team, the Treasurer's office, and Risk — specifically, who owns the assumption-setting on NMDs and prepayment, and where does this role sit in that flow?*
3. *What does success look like at month 6 vs. month 18 for this contract — and is there a realistic path to permanent conversion if the QRM build runs longer than expected?*

## 1 Competency Gap to Prepare For

**Direct hands-on production of OSFI B-12 regulatory submissions for a Schedule I bank.** Saber's IRRBB work is on the vendor/institutional-client side — analogous methodology, but not a Big-6 Treasury submission. Prepare to frame this honestly: *'I've produced the EVE/NII/KRD outputs and the executive commentary on the same methodology; what I haven't owned is the OSFI submission packet itself — and the 5–10 years of banking experience in the JD is the runway for me to close that within the first 60 days.'* Lean on the Moody's sign-off discipline and the QRM-transition relevance as the offsets.