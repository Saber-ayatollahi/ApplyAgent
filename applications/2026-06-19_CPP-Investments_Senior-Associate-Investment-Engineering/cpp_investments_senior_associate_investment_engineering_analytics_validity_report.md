## Validity & Audit Report

### 1. CHANGES MADE

#### Summary
- **Flag:** Original opening claimed 'designs production Python data pipelines, signals, and models.' The word 'signals' is a JD-import: the repo has no evidence Saber has built investment signals. Removed 'signals' from the summary claim.
- **Fix:** Reworded to 'designs and delivers production Python analytics pipelines and multi-asset models' — grounded in the repo's evidence of the cash-flow projection engine and Python pipeline re-engineering.
- **Flag:** The original summary did not contain the exact posting title verbatim (Rule 8). The title 'Senior Associate, Investment Engineering & Analytics' was present but not as the literal first phrase.
- **Fix:** Confirmed the corrected summary opens with 'Senior Associate, Investment Engineering & Analytics candidate' — exact title verbatim, no inflation.
- **Flag:** 'modern portfolio theory' appeared in the original summary and core_skills as a claimed skill. The repo lists MPT-adjacent evidence (VaR/CVaR optimization, efficient frontier, portfolio optimization) but does not explicitly tag MPT as a named skill. MPT as a label is fine when tied to the Ortec evidence, but the summary phrasing 'fluent in ... modern portfolio theory' overstates it as a practiced methodology rather than an applied framework.
- **Fix:** Removed 'modern portfolio theory' from the summary. The Ortec bullets carry the evidence; the label does not need to appear in the summary claim.

#### Core Skills
- **Flag:** 'Factor investing · asset pricing · MPT' was listed as a single core skill. 'Factor investing' as a standalone discipline (systematic factor strategies, factor-model construction, alpha-factor development) is a JD-import: the repo supports factor-*style attribution* at Ortec but not factor strategy construction or asset pricing model development.
- **Fix:** Replaced with 'Factor-style risk attribution & decomposition' — the honest repo-grounded version. Removed 'asset pricing' and 'MPT' from core skills (no repo bullet uses either as a named method).
- **Flag:** 'Systematic & macro strategy analytics' was listed separately from 'Factor investing.' Keeping 'Systematic macro strategy analytics' is defensible (Ortec stochastic scenario generators, GLASS optimization) but the word 'strategy' implies strategy construction, not analytics support. The repo supports the analytics side.
- **Fix:** Retained as 'Systematic macro strategy analytics' — the JD asks for support of systematic macro strategies, which the Ortec scenario-generator and GLASS optimization work genuinely supports. Acceptable.
- **No change needed:** Python, SQL, PostgreSQL, Git, CI/CD, VaR/CVaR, stochastic/Monte Carlo, Claude Code/Cursor are all repo-evidenced.

#### Moody's — Section Heading 'Research Collaboration & AI-Augmented Development'
- **Flag:** The heading uses 'Research Collaboration' which implies ongoing quant-research co-authorship. The repo describes partnering with product owners and client investment teams to translate requirements — not co-authoring research papers or co-developing alpha signals.
- **Fix:** Renamed to 'AI-Augmented Development & Research Partnership' to soften the implication while retaining the JD-relevant framing.
- **Flag:** The original bullet 'Partner with researchers, product owners, and client investment teams to translate research ideas into production analytics' — 'researchers' is a JD-import. The repo says 'product owners' and 'client investment teams,' not internal quant researchers.
- **Fix:** Reworded to 'Partner with product owners and client investment teams to translate analytical requirements into production-grade Python' — removes the unsupported 'researchers' claim.

#### Moody's — 'signal calculations post-deployment' (Client Service Specialist bullet)
- **Flag:** Original read: 'validated model outputs and signal calculations post-deployment.' 'Signal calculations' is a JD-import; the repo says only 'validated model outputs post-deployment.'
- **Fix:** Removed 'and signal calculations' — now reads 'validated model outputs post-deployment.'

#### Cover Letter
- **Flag 1:** Original opened with 'I am writing to be considered for...' — an explicitly prohibited opening per the cover-letter rules. Also the first paragraph led with a regulatory-calendar-style framing ('The path from raw data to signal to strategy') rather than a concrete capability claim.
- **Fix:** Replaced with a direct capability-claim opener tied to Moody's sign-off authority and the cash-flow engine — the strongest verifiable credential for this role.
- **Flag 2:** 'signal to production strategy is the work I do every day' — 'signal' is unsupported by the repo. Removed.
- **Flag 3:** The original cover letter was 4 paragraphs and approximately 380 words — over the 300–350 word ceiling.
- **Fix:** Consolidated to 3 paragraphs, ~320 words. Word count confirmed within range.
- **Flag 4:** 'mentoring junior colleagues alongside it' in paragraph 3 was phrased as a current practice. The repo supports this at Moody's ('mentorship of junior colleagues' in §4.10) so the claim is defensible, but it was moved into the resume rather than the cover letter to avoid over-relying on it as a cover-letter proof point.
- **Fix:** Removed from cover letter; already present in the resume bullet.

### 2. RESIDUAL HONEST GAPS TO OWN IN INTERVIEW

- **'Factor investing' as a discipline:** IEA sits within 'Capital Markets and *Factor* Investing.' Saber has factor-*style attribution* (Ortec risk decomposition) and optimization (VaR/CVaR GLASS), but has not built factor models, run factor-exposure analyses in the Barra/Axioma sense, or constructed systematic factor strategies. Honest framing in interview: 'My work has been on the analytics and optimization side of factor-style mandates — risk decomposition, attribution, and scenario analysis — rather than factor model construction. I am familiar with the framework and eager to deepen on the signal side.'
- **'Signals':** The JD repeatedly references 'investment signals.' The repo has zero evidence of signal construction or signal research. Do not claim this. In interview: 'I have supported the analytics infrastructure that consumes signals downstream — validation, aggregation, scenario overlay — but signal generation itself is a gap I would be building into at CPP.'
- **'Systematic macro strategies' as a live portfolio management context:** Saber's macro scenario work was for pension ALM studies (Ortec), not live systematic macro portfolio management (risk premia, trend, carry, etc.). The GLASS optimization was for SAA/TAA, not daily systematic strategy management. Own this distinction if pressed: 'The macro scenario work I did at Ortec was in an ALM study context — calibrating ESGs for long-horizon SAA — rather than running a live systematic macro book. The engineering skills transfer directly; the live-trading operational layer is new territory.'
- **CPP-specific platform familiarity:** No repo evidence of CPP's internal systems, Aladdin at the CMF level, or the specific data infrastructure IEA maintains. Not a gap to volunteer; just be honest if asked about specific systems.
- **'Asset pricing' as a named methodology:** JD asks for 'familiarity with factor investing, asset pricing, and modern portfolio theory.' Saber has applied MPT (optimization, efficient frontier) and asset pricing outputs (derivatives valuation, spread calibration) but has not formally studied or applied asset-pricing models (CAPM, Fama-French, APT) in a research context. Honest framing: 'I have worked with asset-pricing outputs — derivatives valuation, spread calibration — and optimization frameworks built on MPT, but formal factor model research using CAPM or Fama-French is adjacent rather than hands-on.'