## Likely Technical Questions

**1. Walk me through how you would set up a bank's liquidity stress testing framework.**
Reference the multi-asset cash-flow projection engine built at Moody's: base, stress, and reverse-stress scenarios layered over time-bucketed liquidity gaps from T+1 to multi-year. Key design choices were behavioral cash-flow assumptions, prepayment logic, and macro stress overlays calibrated to align with regulatory liquidity expectations. The engine replaced a manual spreadsheet workflow with auditable Python pipelines so each assumption could be challenged independently.

**2. How do you exercise effective challenge as a second-line function without being adversarial with Treasury?**
Draw on Story 2 (escalating an economically-indefensible output) and Story 3 (bridging client investment teams and development). The discipline is to hold the analytical line while staying inside the same conversation - decompose the disputed number by driver, surface the specific calibration or assumption at issue, and route it through the formal escalation path rather than email arguments. Done well, it earns you the Head-of-Risk seat at the table.

**3. What's your view on intraday liquidity risk and how would you monitor it?**
Honest framing: my hands-on intraday work is lighter than my structural-liquidity work, but the underlying mechanics - cash-flow timing, payment-system flows, settlement buffers, and concentration of intraday peaks - are the same building blocks as the cash-flow engine, just at higher frequency. The metric set (LCR daily monitoring, intraday peak usage, throughput by counterparty/currency) is well-defined; the harder problem is data quality and reconciliation across payment systems.

**4. How do behavioral assumptions in deposit modelling affect liquidity reporting, and how would you challenge them?**
Non-maturity deposit assumptions are usually the single largest driver of structural liquidity outcomes. Challenge framework: (1) is the segmentation granular enough (retail vs commercial vs operational)? (2) is the rate-sensitivity / beta calibrated to a stressed regime, not just the recent benign one? (3) does the assumption survive a reverse-stress test that asks what deposit behavior would have to look like to breach the limit? At Moody's I embedded prepayment and behavioral logic into the projection engine and validated it against client-specific calibrations.

**5. Tell me about a time you found an error in a model output that everyone else was about to sign off on.**
Use Story 2 verbatim: client-delivery run produced sensitivities that passed all internal checks but didn't square with the client's intuition under a specific rate shock. Held the release under deadline pressure, decomposed sensitivities by asset class, identified a short-end curve-calibration edge case, escalated to product owners and the client's Head of Risk. 48-hour delay, defect remediated upstream, became the client's direct escalation contact.

## Questions Saber Should Ask

1. How is the second-line liquidity team currently structured between policy/framework, measurement/reporting, and stress testing - and where does the Senior Director see the biggest gap to close in the first 12 months?
2. What does the working relationship with Treasury look like in practice on contentious assumptions (e.g. NMD behavior, intraday buffer sizing), and where has effective challenge most recently changed an outcome?
3. With OSFI's LAR 2026 updates and continued attention on recovery & resolution, which of the five oversight pillars (liquidity, intraday, R&R, contingency funding, subsidiary oversight) is currently the highest regulatory-priority item for CIBC?

## The One Competency Gap to Prepare For

**Direct bank second-line liquidity experience and recovery & resolution planning.** Saber's liquidity and balance-sheet depth is real but delivered from a vendor/consulting seat, not from inside a Big-6 Treasury or second-line risk team. He has not personally drafted a Recovery Plan or a Resolution submission, and intraday liquidity is structurally familiar but not hands-on at bank-payment-system scale. Prep: review OSFI's Recovery & Resolution guidance and the LAR 2026 consultation document; be ready to acknowledge the seat-change honestly and pivot to transferable evidence (cash-flow engine, stress framework, sign-off discipline, cross-functional delivery at EY and Ortec). Do not bluff on R&R specifics.