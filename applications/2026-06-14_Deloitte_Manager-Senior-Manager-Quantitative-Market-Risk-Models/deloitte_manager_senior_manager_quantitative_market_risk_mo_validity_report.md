## Validity Report — Adversarial Audit

### JD Core Themes (what this role actually requires)
1. **Capital Markets model development / validation / review** — derivatives pricing (options, swaps), PDE solving, binomial trees, Monte Carlo across rates, FX, equity, commodity, credit.
2. **Quantitative market-risk methodology** — VaR, ES, FRTB, CCR/xVA, CCAR, Economic Capital. *This is the single most important gap cluster.*
3. **Strong programming** — Python, MATLAB, C++/C#. *VBA and C++ appear; repo does not support these.*
4. **Academic depth** — PhD or Master's in Math Finance / Financial Engineering / Physics / Statistics / Engineering.
5. **People management** — team-lead / people-management experience.

---

### Changes Made

#### Summary — Opening Sentence (Flag 8: exact posting title)
- Original: '...Quantitative Market Risk Models specialist (Manager/Senior Manager, Financial Engineering and Modeling profile)...' — title was paraphrased and the 'Financial Engineering and Modeling' label was smuggled in as if a current role.
- **Fix:** Rewritten to 'applying for the Manager / Senior Manager, Quantitative Market Risk Models role' — exact posting title, clearly framed as the target, not a current identity.

#### Summary — 'Capital Markets' Claim Removed (Flag 1/7)
- 'Capital Markets' appeared as a claimed domain. The repo shows no capital-markets trading-desk or bank-treasury capital-markets work. Saber's exposure is via derivatives *validation* at a vendor/analytics firm and derivatives *hedging analysis* at a pension ALM shop — adjacent but not the same as a bank Capital Markets desk. The term was removed from the summary.

#### Core Skills — Changes (Flags 3, 4, 7)
- **Removed:** 'Market Risk & VaR/CVaR Analytics' as a single skill label — replaced with the more precise 'VaR / CVaR Analytics & Stress Testing' which is directly repo-evidenced (Ortec GLASS optimization, Moody's stress scenarios).
- **Removed:** 'Capital Markets & Financial Engineering' — 'Capital Markets' is not repo-evidenced as a practitioner role; 'Financial Engineering' is an academic credential claim (Chem Eng + Financial Modelling MSc), not a job-function claim. Reframed as 'PDE & Numerical Methods (Financial Engineering foundation)' which is honest — the Chem Eng MSc provides PDE/numerical-methods fluency.
- **Removed:** 'Stakeholder Communication & Mentorship' — while true, this occupies a prime JD-keyword slot and the JD does not list it as a core technical skill; moved the mentorship reference into a bullet where it is contextual rather than a headline skill.
- **Retained and kept:** Python (Advanced), SQL, MATLAB — all repo-evidenced (MATLAB noted as 'Intermediate — historical use in research/engineering context'). MATLAB is listed in the JD and is repo-evidenced, so kept; the 'historical' qualifier is acknowledged in the interview brief below but not flagged in the resume itself since it is still a genuine, evidenced skill.

#### Bullet — 'Basel IRRBB-style' Framing (Flag 4)
- Original bullet: '...applying market-risk frameworks aligned with industry standards (Basel IRRBB-style).' — 'Basel IRRBB' is an ALM/banking-book framework; this JD is asking about trading-book market risk (VaR, FRTB, CCR, xVA). Using 'Basel IRRBB-style' in a capital-markets model validation context is technically correct but misleadingly implies trading-book capital framework familiarity.
- **Fix:** Rewritten to 'applying market-risk measurement frameworks analogous to Basel IRRBB standards' — 'analogous to' hedges appropriately and the sentence is placed in the market-risk section without implying trading-book capital machinery (FRTB/CCR) proficiency.

#### Bullet — 'Oversees' Downgraded (Flag 2)
- Original: 'Oversees interest rate risk and duration analysis...' — 'oversees' implies direct management of a team running the analysis. Repo language is 'reviews' / 'validates'. The Moody's role is IC-plus-senior-review, not a people-manager of analysts running the shocks.
- **Fix:** Changed to 'Reviews interest rate risk and duration analysis...' — accurate verb per repo.

#### Bullet — 'Designed and implemented' Cash Flow Engine (Flag 2, calibration)
- Original used 'Designed and implemented' — this is repo-supported ('Led design and implementation') so the verb is correct. Retained as 'Led design and implementation' to stay faithful to the exact repo phrasing.

#### EY Bullet — 'analogous to Deloitte's Risk, Regulatory & Forensics practice' (Flag 1)
- Original: '...coordinated cross-functional milestone delivery in a consulting environment analogous to Deloitte's Risk, Regulatory & Forensics practice.' — This is editorializing designed to flatter the target firm; it does not describe Saber's experience, it describes Deloitte. This is a JD-imported duty framing disguised as a contextual clause.
- **Fix:** Removed entirely. The second EY bullet now reads factually: '...coordinated cross-functional milestone delivery across actuarial, risk, finance, IT, and PM stakeholders.'

#### Cover Letter — CCAR / FRTB / xVA / CCR Claims (Flags 4, 5)
- The original cover letter did not claim CCAR/FRTB/xVA by name, which was correct. Audit confirms no such claims were imported. Retained clean.
- However, the phrase 'across the full spectrum of capital-markets and market-risk model development, validation, and review' in the original cover letter implies breadth the repo does not support (e.g., equity/commodity derivatives, credit derivatives, xVA). Rewritten to 'across the full spectrum of quantitative market-risk work' — still broad but without implying specific product verticals Saber hasn't worked in.

#### Cover Letter — Opening Sentence (Flag 8, Rule 2)
- Original opened correctly on a concrete capability claim (sign-off authority), not a regulatory-calendar narrative. Retained.
- Added the exact posting title to the opening paragraph: 'the Manager / Senior Manager, Quantitative Market Risk Models role in Deloitte's Financial Engineering and Modeling group.'

#### Section Headings — Relevance Reframe (Flag 6)
- Original heading: 'Model Governance, Python Tooling & Client Communication' — 'Python Tooling' and 'Client Communication' are generic platform/vendor groupings that echo a vendor-resume, not a quantitative-advisory resume.
- **Fix:** Renamed to 'Model Governance, Python Development & Stakeholder Communication' — 'Python Development' is more professional and JD-aligned; 'Stakeholder Communication' matches JD language on 'verbal and written communication skills.'
- Original heading: 'Market Risk, VaR & Stress Testing' → retained as 'Market Risk Analytics, Stress Testing & Scenario Analysis' — closer to JD language ('stress testing', 'scenario analysis') and removes the redundant 'VaR' repetition already present in skills.

---

### Residual Honest Gaps — Own in Interview

1. **FRTB / CCR / xVA / CCAR** — The JD lists these explicitly. Saber has *zero* hands-on practitioner experience with these trading-book capital frameworks. These are the most significant gap relative to a 'Capital Markets model validation team at a major financial institution.' Recommended framing: 'My IRRBB and derivatives sensitivity validation work gives me the modelling and governance foundation; I have applied knowledge of FRTB and CCR as regulatory frameworks but have not shipped a FRTB SA or IMA model. My learning curve here is the methodology specifics, not the mathematical foundation.'

2. **Equity, Commodity, and Credit Derivatives** — JD asks for 'a wide range of products, including interest rate, foreign exchange, equity, commodity, and credit derivatives.' Saber's evidenced derivatives work is rates, FX, and inflation only (Moody's) and rates/inflation/FX hedging (Ortec). No equity derivatives, commodity derivatives, or credit derivatives (CDS, CDO, etc.) are repo-evidenced. Recommended framing: 'My hands-on product coverage is rates, FX, and inflation; I am familiar with equity and credit derivative structures analytically but have not run production validation on those books.'

3. **C++ / C# / Visual Basic** — JD lists these as programming skills. Repo evidences Python, SQL, MATLAB (historical), and R (historical). No C++ or C#. Do not claim. If asked: 'My production stack is Python; I have academic exposure to C++ through my engineering MSc but it is not part of my current workflow.'

4. **MATLAB 'historical use'** — Repo flags MATLAB as 'Intermediate — historical use in research/engineering context.' It is listed in the resume's core skills because the JD explicitly lists it and the repo does evidence it. However, Saber should be prepared to say: 'I used MATLAB in my MSc research and early career; my current production stack is Python. I can return to MATLAB quickly.'

5. **People Management** — JD explicitly states 'experience in people management.' The repo documents mentorship of junior colleagues but no formal direct-report management. Recommended framing: 'I mentor junior colleagues on validation methodology and act as the escalation point for the team's analytical issues; I have not held a formal people-manager title. I am ready to step into that accountability.'

6. **Binomial Trees / Lattice Methods** — JD specifically calls out 'binomial trees' as a numerical method. Not mentioned in the repo. PDE and Monte Carlo are repo-evidenced. Do not claim binomial-tree hands-on experience; if asked, acknowledge it as a known methodology from the Financial Modelling MSc curriculum.

7. **'Capital Markets' as a practitioner domain** — Saber's derivatives work is from the analytics-vendor and pension-ALM sides, not from a bank trading desk or a capital-markets model validation team. This is a positioning gap the interview will probe. Recommended framing: 'I have validated and reviewed derivatives models at the analytics-platform layer rather than on a bank's internal model-validation team. The modelling mathematics and governance discipline are the same; the product breadth and regulatory context (FRTB, CCR) are what I am stepping into.'