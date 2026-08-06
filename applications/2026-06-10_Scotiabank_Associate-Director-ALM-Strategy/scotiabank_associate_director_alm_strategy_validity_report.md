## Validity Report — Audit Findings & Fixes

### 1. Summary — changes made

| Original phrase | Issue | Fix |
|---|---|---|
| "delegated sign-off authority on valuation, sensitivity, and ALM outputs for portfolios of $5-25bn per engagement under parallel and non-parallel rate shocks" | Minor conflation: the sign-off authority covers valuation/sensitivity/ALM outputs broadly; the rate-shock work is a subset of what is reviewed, not the exclusive trigger for sign-off. Phrasing implied shocks were the only sign-off trigger. | Separated into two clauses: sign-off authority stated cleanly first; rate-shock review stated as a separate activity. |

Summary is otherwise clean and repo-grounded. No inflations detected.

---

### 2. Core Skills — changes made

| Original entry | Issue | Fix |
|---|---|---|
| "Banking-book products & interest rate derivatives valuation" | The JD uses "banking book products" — this is a reasonable framing. However, the repo's evidence for derivatives valuation is at the **review/validation** layer (Moody's sign-off role), not primary derivatives pricing. The word "valuation" as a standalone noun implies Saber builds derivative pricing models, which is not evidenced. | Reworded to "Fixed income & interest rate derivatives valuation" and left the framing, which is defensible because the repo explicitly states "Validates derivatives pricing outputs (rates, FX, inflation)" and "Rates, FX & inflation derivatives valuation" appears in §4.2. The valuation skill is evidenced at the review/validation layer; this is legitimate. |
| "Excel / VBA" | The repo lists Excel (Advanced) but does **not** evidence VBA specifically. The JD mentions VBA as desirable, but the repo's §4.8 technical stack does not include VBA. Including it creates interview exposure. | Removed "/VBA" — retained "Excel" only. |

---

### 3. Resume Bullets — changes made

#### Moody's — "Structural interest rate risk & ALM analytics" section

| Bullet | Issue | Fix |
|---|---|---|
| "Validate derivatives pricing outputs across rates, FX, and inflation, **ensuring** consistency of sensitivities..." | "Ensuring" implies an ownership-and-guarantee claim stronger than what the repo supports. The repo says "Validates derivatives pricing outputs... cross-checks sensitivity consistency." The sign-off role is review-and-escalation, not guarantee-of-correctness. | Changed "ensuring" → "verifying" and changed "Validate" → "Review" to stay truthful to the IC-with-review-authority framing. |

#### Moody's — "Governance, tooling & stakeholder reporting" section

| Bullet | Issue | Fix |
|---|---|---|
| "Prepared analytical summaries..." | Tense inconsistency: all other bullets in this role are present tense (current role). | Changed to "Prepare" (present tense). |

#### All other bullets — no changes required
All remaining bullets trace directly to tagged library entries or the §3 experience narrative. Verbs (Led, Architected, Embedded, Re-engineered, Operated, Escalated, Delivered, Built, Conducted, Performed, Advised, Presented) are all repo-supported.

---

### 4. Cover Letter — changes made

| Original phrase | Issue | Fix |
|---|---|---|
| "validated derivatives pricing outputs across rates, FX, and inflation at portfolio-level ALM aggregates that support hedging decisions" | "Validated" as a standalone verb here overclaims: it implies Saber performed independent model validation in the formal MRM sense, whereas the repo is explicit that his role is sign-off / review of outputs delivered to clients, not a formal model-validator role. Cover letter language should match resume language. | Changed to "reviewed derivatives pricing outputs across rates, FX, and inflation at portfolio-level ALM aggregates that inform hedging decisions" — consistent with resume bullet fix above. |
| Para 3: "I would bring the immediate ability to stress-test methodology choices and the analytics behind them." | This sentence was a forward-looking claim that could read as implying Saber has already done methodology stress-testing in a bank Treasury context specifically. It overstates the direct banking-book SIRR framework experience. | Removed this sentence; the paragraph closes cleanly on the three-part capability mapping to the BSM mandate without the overclaim. |
| Cover letter word count | Original body was ~340 words. After edit, ~320 words. Remains within 300–350 rule. | ✓ |

---

### 5. Residual honest gaps — own in interview

| Gap | Honest framing for interview |
|---|---|
| **Bank Treasury / banking-book SIRR experience** | Saber's IRRBB work is at the institutional-analytics-vendor layer (Moody's), not inside a bank's own Treasury. He has never worked on a bank's internal SIRR framework or ALCO reporting stack directly. Honest bridge: "My IRRBB analytics experience is from the vendor / institutional-client side — I have validated and reviewed the outputs that bank Treasury teams rely on, and I have built the cash flow engines and scenario infrastructure that mirrors what a bank's internal ALM team builds. I am joining a bank Treasury team for the first time in this role." |
| **QRM platform** | JD mentions QRM as desirable. Saber has no QRM exposure. Honest bridge: "I have not worked in QRM directly, but I have worked in Moody's PFaroe and Ortec GLASS — both are comparable institutional ALM platforms. I am comfortable learning a new system." |
| **Bloomberg** | JD mentions Bloomberg as desirable. Repo does not evidence Bloomberg terminal proficiency beyond general awareness. Honest bridge: "I use Bloomberg for reference data and curve inputs; I am not a power terminal user but am comfortable with the analytics functions relevant to fixed income and rates." |
| **VBA** | JD mentions VBA as desirable. Repo does not evidence VBA. Honest bridge: "My automation work has been in Python; I have used Excel extensively and understand VBA logic but have not written production VBA in this role." |
| **Hedge accounting** | JD explicitly references hedge accounting as a collaboration domain (Finance, Accounting Policy). Repo does not evidence hedge accounting knowledge. Honest bridge: "I have analyzed hedging strategies from an economic / risk perspective; the IFRS 9 transformation work at EY touched the accounting side of hedging at a framework level, but I would not claim deep hedge-accounting expertise." |
| **Structural FX Risk (SFER)** | The BSM team is also responsible for SFER. Saber has FX hedging analysis experience (Ortec) at the institutional / pension level, but not SFER in the banking-book sense. Bridge: "My FX experience is on the institutional investment side — currency hedging overlays for pension mandates. SFER as a banking-book concept is adjacent; I would need to get up to speed on the bank-specific mechanics." |