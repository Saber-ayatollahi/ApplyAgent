## Adversarial Audit Report — OPTrust Principal/Trader, TPM

### JD Core Themes (the 5 things OPTrust is actually hiring for)
1. **Active trading execution** — fixed income (Canada/US), global FX, cash and derivative products; alpha generation; sell-side relationships.
2. **Liability hedging program management** — ongoing oversight, not just analytical support.
3. **Total Portfolio construction** — top-down risk lens, internal + external strategy allocation.
4. **AI-enabled and Python/SQL/VBA tooling** — build and implement, not just use.
5. **Cross-functional desk collaboration** — risk, middle office, compliance, legal.

---

### Flags Raised & Fixes Applied

**FLAG 1 — Summary: exact posting title missing (Rule 8)**
Original opened with 'Principal/Trader, Total Portfolio Management candidate' — the posting title is 'Principal/Trader, Total Portfolio Management' (no 'candidate' needed but the full title was close). Corrected to include the verbatim posting title in the first sentence unambiguously: 'Candidate for Principal/Trader, Total Portfolio Management...'

**FLAG 2 — Summary: 'Executes rates, credit, and currency positioning through cash and derivative products' (Rule 1 — JD-imported duty)**
This sentence claimed active trading execution. The repo contains zero evidence of live trade execution. Saber reviews, validates, and analyzes derivatives outputs — he does not execute trades. The sentence was deleted entirely. The corrected summary stays within 'derivatives validation,' 'liability hedging analysis,' and 'portfolio analytics.'

**FLAG 3 — Summary: 'builds Python/SQL/VBA tooling for pricing, trading, portfolio management' (Rule 1 + Rule 7)**
'Pricing' and 'trading' tooling are JD imports; repo supports Python pipelines for analytics and validation workflows. 'VBA' appears in the JD but has no specific evidence in the repo beyond Excel/Python. The repo lists Excel (Advanced) and Python (Advanced) — VBA is not listed. Corrected to: 'Builds Python and SQL analytics pipelines; has deployed AI-enabled workflows to accelerate modelling and validation cycles.' VBA removed from summary; addressed in core_skills with explicit '(working knowledge)' hedge — actually on reflection VBA is not evidenced at all in the repo, so it has been removed from core_skills entirely (see Flag 5).

**FLAG 4 — Core Skill: 'Fixed Income & FX Portfolio Management' (Rule 1 + Rule 6 — JD import)**
The repo supports analytics, validation, and advisory work on fixed income and FX — not active portfolio management. Renamed to 'Fixed Income & FX Derivatives Analytics' which is what the repo evidences.

**FLAG 5 — Core Skill: 'Rates, Credit & Currency Strategy' and 'VBA' (Rule 1 + Rule 7)**
'Strategy' implies discretionary positioning authority not evidenced in repo. 'Credit' as a distinct trading/strategy domain is not evidenced (repo has spread calibration and IFRS 9, not credit portfolio management). Renamed to 'Rates, Inflation & Currency Risk' which is repo-grounded. VBA: not listed anywhere in §4.8 of the Master Repo; it appears only in the JD. Removed from core_skills entirely. If asked in interview, the honest answer is familiarity through Excel/spreadsheet work but no production VBA development.

**FLAG 6 — Core Skill: 'AI-Enabled Trading & Analytics Tooling' (Rule 1 + Rule 7)**
'Trading' in this skill label is a JD import — the repo's AI workflows are for code generation, validation scaffolding, and anomaly detection, not trading systems. Corrected to 'AI-Enabled Analytics Tooling (Claude Code, Cursor IDE).'

**FLAG 7 — Section Heading: 'Cross-Asset Portfolio & Derivatives Analytics' (Rule 6 — relevance)**
Heading was generic and did not echo the JD's primary accountability theme. Renamed to 'Cross-Asset Derivatives & Rate-Risk Analytics' which maps to the JD's 'rates, credit, and currency positioning' and 'derivatives and cash products' language while staying within repo evidence.

**FLAG 8 — Moody's bullet: 'to inform hedging and portfolio-construction decisions' (Rule 2 — inflated verb)**
Original said Saber's analysis directly informs hedging 'decisions.' The repo says he prepares analytical summaries and reviews outputs — decision authority sits with clients. Corrected to: 'informing hedging and portfolio-construction review for institutional fixed-income mandates.' The change from 'decisions' to 'review' is small but material for interview integrity.

**FLAG 9 — Moody's bullet: 'Validate derivatives pricing outputs... reconcile sensitivities' (Rule 2 — verb level)**
Original used 'Validate' and 'reconcile' — both are repo-supported verbs for Saber's Modelling Services role. These were retained. However, the original framing 'for institutional fixed-income and cross-asset mandates' implied he was the PM; corrected to 'for pension and insurance mandates' (more accurate client description per repo §3.1).

**FLAG 10 — Ortec bullet: 'credit' risk in scenario generators (Rule 1 + Rule 7)**
Original Ortec bullet: 'assessing rate, credit, inflation, and currency risk.' The repo §3.3 says 'interest rate risk and funding volatility' and '§5 bullet: rate, inflation, and currency risk.' Credit as a distinct factor in Ortec's scenario generators is not evidenced — the repo does not mention credit scenario generation at Ortec. Removed 'credit' from that bullet. Now reads: 'assessing rate, inflation, and currency risk.'

**FLAG 11 — Cover letter: 'generating alpha through macro, rates, credit, and currency positioning' implied framing**
The original cover letter did not use this exact phrase but the framing 'On the fixed-income and FX side, I validate derivatives outputs... and oversee duration and rate-shock analysis' was close to the boundary. Retained because 'validate' and 'oversee' are repo-accurate verbs. However, the original also said 'to inform hedging and funding decisions' — corrected to 'the analytical foundation underneath liability-hedging decisions' to clarify Saber is the analytics layer, not the decision-maker.

**FLAG 12 — Cover letter word count**
Original body: ~310 words (acceptable). Corrected body: ~320 words. Within the 300–350 rule.

**FLAG 13 — Cover letter: 'My programming stack (Python, SQL, VBA) is the one your JD calls for' (Rule 5 + Rule 7)**
VBA is not repo-evidenced (see Flag 5). Removed the explicit VBA claim from the cover letter. Replaced with: 'My Python and SQL pipelines are in daily production use, and I have deployed agentic-AI workflows...'

**FLAG 14 — RELEVANCE audit of prime slots**
The original summary contained 'delegated sign-off authority' in the opening — this is retained as it is a concrete capability claim (repo-grounded) and relevant to the JD's senior-level expectation. 'IRRBB,' 'OSFI B-12,' 'Basel' do NOT appear in any prime slot in the corrected version — these are appropriate for bank/insurer ALM JDs, not pension investment desks. The JD never mentions them; they were not in prime slots in the original either, so no change needed on this specific point.

---

### Residual Honest Gaps — Own These in Interview

1. **Live trade execution**: Saber has zero live-market trade execution experience. The JD requires active trading in fixed income, FX, and derivatives with sell-side relationships. This is the largest gap. Interview framing: 'My work sits on the analytical and validation layer immediately behind execution decisions — I understand the instruments, the risk mechanics, and the portfolio-construction logic; I have not held a live execution seat. I am applying because the analytical depth of the role is the closer match to my background than a pure execution-trader role, and I am prepared to build the execution-desk fluency quickly.'

2. **VBA**: ~~Not evidenced in the repo.~~ **RESOLVED 2026-07-08:** Saber confirmed working VBA knowledge (maintenance/refactor level, not greenfield); Master Repo §4.8 updated. The resume's 'VBA (working knowledge)' line now traces to the repo and stands. If asked: 'I work primarily in Python; I maintain and refactor VBA in a professional Excel context, but I would not present it as a build-from-scratch strength.'

3. **Sell-side relationships**: No evidence of active sell-side broker/dealer relationship management. Adjacent evidence: client-facing work at Moody's and Ortec, investment-committee presentations. Do not claim; acknowledge if probed.

4. **Bloomberg terminal**: JD lists it as 'an asset.' The repo does not mention Bloomberg as a tool Saber has used. Do not claim hands-on Bloomberg proficiency. If asked: 'I have not used Bloomberg as a primary tool in my current role; I have worked with comparable multi-asset analytics platforms (PFaroe, GLASS) and can get up to speed quickly.'

5. **Credit strategy / credit portfolio positioning**: 'Credit' is a named alpha-generation theme in the JD. Saber's credit exposure is limited to IFRS 9 transformation (EY) and spread calibration review (Moody's). This is a meaningful gap on the strategy/positioning side. Do not claim.

6. **'Alpha generation'**: The JD explicitly asks candidates to 'generate alpha through macro, rates, credit, and currency positioning.' Saber's background is analytical/advisory — he has never held a P&L-accountable alpha-generation mandate. Do not use 'alpha' as a claimed competency. The resume and cover letter deliberately omit it.

### What Is Strong and TRUE — Retained
- Delegated sign-off on $5–25bn portfolios (Moody's, repo-grounded)
- Cash-flow projection engine design and implementation (Moody's, repo-grounded)
- VaR/CVaR asset-liability optimization via GLASS (Ortec, repo-grounded)
- Risk decomposition and near-optimal frontier analysis (Ortec, repo-grounded)
- Stochastic scenario generation for rate, inflation, currency (Ortec, repo-grounded)
- LDI and liability-hedging analytics (both employers, repo-grounded)
- Python pipelines in production (Moody's, repo-grounded)
- Agentic-AI tooling with measurable cycle-time reduction (Moody's, repo-grounded)
- CFA + dual MSc (evidenced)
- Investment-committee presentation experience (Ortec, repo-grounded)