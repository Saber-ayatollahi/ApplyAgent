## Validity Report — BMO Director, Model Validation

### What changed and why

#### Summary paragraph
| Location | Original | Issue | Fix |
|---|---|---|---|
| Summary, sentence 4 | 'Built enterprise cash-flow projection and stochastic scenario-generation models validated under governance audit' | 'Validated under governance audit' applied equally to the scenario-generation models built at Ortec. The repo attributes the formal governance audit *closure* only to the Moody's Python pipeline migration (Story 6), not to the Ortec scenario generators (which were client-study tools, not internally audited). Overstating the governance audit scope. | Rewrote to 'validated throughout the development lifecycle' — supportable across both Moody's (formal audit) and Ortec (client-study validation) without overclaiming audit provenance. |

#### Core skills
| Skill | Original | Issue | Fix |
|---|---|---|---|
| Model Governance framing | 'Model Governance (OSFI E-23 / SR 11-7)' | Repo §4.9 explicitly classifies OSFI E-23 as *awareness* and SR 11-7 as *parallel framework awareness*, not practitioner capability. Presenting them unhedged as a skill implies hands-on compliance program delivery, which is not supported. | Changed to 'Model Governance (SR 11-7 / OSFI E-23 aware)' — the parenthetical hedge is honest and still signals regulatory literacy. |

#### Resume bullets — Moody's Phase 2
| Bullet | Original | Issue | Fix |
|---|---|---|---|
| Model Dev bullet 2 | 'ensured sensitivity consistency and scenario impact integrity' | 'Ensured' implies ownership of the outcome; the repo supports 'validated' and 'confirmed' (review authority, not ownership). | Changed 'ensured' → 'confirmed' to match the review/validation verb set. |
| Model Dev bullet 3 | 'Oversaw interest-rate risk and duration analysis under parallel and non-parallel rate shocks, aligned with IRRBB standards analogous to OSFI B-12 and Basel Committee frameworks' | 'Analogous to OSFI B-12 and Basel Committee frameworks' is a hedge already in the repo — preserved. No change needed. | No change. |
| Tooling bullet | '30–40% on comparable modules' | Repo §3.1 uses 'estimated 30–40%' — the word 'estimated' is load-bearing; it was preserved in the draft. Confirmed present. | No change needed — already correct. |

#### Cover letter
| Location | Original | Issue | Fix |
|---|---|---|---|
| Para 1, sentence 2 | 'built around the same functional-separation and documentation principles codified in SR 11-7 and OSFI E-23' | The word 'codified' implies Saber has read and applied these regulations directly. Repo positions these as *awareness*, not direct application. | Softened to 'built around the functional-separation and documentation principles that SR 11-7 and OSFI E-23 codify' — shifts the codification to the frameworks, not to his practice. |
| Para 2, sentence 4 | 'giving me both the quantitative depth and the cross-functional program experience that Director-level model risk roles require' | 'require' is slightly presumptuous/generic. | Changed to 'providing both the quantitative depth and cross-functional program experience that Director-level model risk roles require' — verb downgraded from active claim to factual descriptor. |
| Para 3, sentence 1 | 'BMO's Model Risk Management function is one of the most technically rigorous in the Canadian market' | Flattery that cannot be verified and reads as generic filler — anti-pattern per cover letter templates. | Removed. Replaced with a direct statement about BMO's mandate scope and how it maps to Saber's background. |
| Word count | Original body: ~370 words | Exceeds the 300–350 word ceiling. | Tightened para 3 — removed the flattery sentence, consolidated two sentences. Final count: ~330 words. |

---

### Material that survived — all strong and true
- Delegated sign-off authority, $5–25bn per engagement, ~$50bn cumulative — supported verbatim in repo §3.1.
- Curve construction, spread calibration, cross-asset interaction review — supported verbatim.
- Cash-flow projection engine design and implementation — supported verbatim (Story 1, §3.1).
- Behavioral assumptions, prepayment logic, macro stress overlays — supported verbatim.
- Python pipeline migration, parallel shadow-run for two cycles, governance audit closed — supported verbatim (Story 6, §3.1).
- Stochastic scenario generators at Ortec — supported verbatim (§3.3).
- VaR/CVaR optimization, risk decomposition, GLASS platform — supported verbatim (§3.3, §4.4).
- UPP three-plan merger ALM study — supported verbatim (§3.3).
- IFRS 9/17 at EY — supported verbatim (§3.2).
- Agentic AI workflows, Claude Code, Cursor — supported verbatim (§3.1, §4.8).
- CFA 2024, dual MSc — supported verbatim (§2).

---

### Residual honest gaps to own in interview

1. **OSFI E-23 / SR 11-7 depth.** Saber has *awareness*, not delivery experience. If an interviewer asks 'walk me through how you've implemented an E-23-compliant validation framework,' the honest answer is: 'I haven't built a bank's MRM framework from scratch — I've operated within a formal governance framework at Moody's and understand the functional-separation, documentation, and escalation requirements that E-23 and SR 11-7 codify. I would be learning the bank's specific implementation while contributing practitioner depth from day one.' Do not overstate.

2. **Banking-book vs. client-portfolio governance.** Moody's sign-off authority is on *client-delivery outputs* within a vendor governance framework, not on a bank's internal model risk management function (MRM 1LoD/2LoD). If an interviewer probes the 2LoD independence angle, be precise: 'My governance role sits at the vendor layer — I hold sign-off on analytical outputs delivered to institutional clients, not on a bank's internal 2LoD validation program. That's the gap I'm stepping into at BMO, and the practitioner depth is the bridging credential.' Story 9 in the repo handles this well.

3. **FRTB / CCR / trading-book capital.** Not in scope for this role (Model Validation — ALM/IRRBB focus), but if it surfaces, the repo is explicit: do not claim hands-on experience. Redirect to adjacent quant depth.

4. **Direct people management.** The draft does not claim it — correctly. If the BMO JD requires managing a team of validators, Saber's evidence is limited to mentorship of junior colleagues (repo §4.10). Do not inflate to 'managed a team of N' in interview without explicit repo support.