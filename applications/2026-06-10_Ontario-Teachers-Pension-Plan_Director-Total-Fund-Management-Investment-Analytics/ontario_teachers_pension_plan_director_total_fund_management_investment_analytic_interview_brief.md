## Likely Technical Questions

**1. Walk us through how you would design analytics to support Total Fund portfolio construction and liquidity management.**
Lean on the cash-flow projection engine story (STAR #1): T+1 to multi-year time-bucketed liquidity gap analytics, base/stress/reverse-stress scenarios, behavioral cash-flow and prepayment logic, macro overlays. Frame it as the same problem at Total Fund scale - aggregate security-level exposures into multi-asset views of funding, leverage, and cross-asset risk - and emphasize the auditable Python pipeline that replaced spreadsheets.

**2. How have you used AI/ML in investment analytics, and where would you NOT use it?**
Describe the agentic workflows (STAR #7): Claude Code and Cursor for first-pass code review, validation scaffolding, anomaly detection, documentation - 30-40% cycle-time reduction. Honest boundary: humans still sign off on governance-critical outputs; predictive models need explainability and validation before they touch portfolio decisions. Tie to model governance.

**3. Tell us about model governance in a quant analytics context.**
Use STAR #2 (the escalation story) and STAR #6 (spreadsheet-to-Python governance upgrade). Independent review and challenge, assumption validation, economic defensibility, escalation when math is right but economics are wrong, parallel-run/shadow-mode cutovers, documentation to SR 11-7 / OSFI E-23-style standards. Explainability and monitoring extend the same discipline to AI/ML.

**4. How would you stand up and lead a cross-functional squad?**
Use the PFaroe migration story (STAR #3) and current squad work: scope client/business requirements into prioritized PO work, bridge investment intent and engineering constraints, run validation post-deployment, reuse patterns across the cohort. For Director scope: roadmap, capacity, vendor management, talent development, delivery cadence.

**5. Talk about an LDI / funded-status analytics problem you owned end-to-end.**
UPP merger and the duration-shift study (STAR #4): stochastic ESG calibrated to client assumptions, funding-ratio distributions, duration-gap decomposition, leverage overlay evaluation, investment-committee presentation that shifted SAA. This is the most direct OTPP-relevant story in the bank.

## Questions Saber Should Ask

1. How is the Investment Analytics function currently organized between TFM, Investment Risk, and Investment Strategy - where are the seams today, and where does this role most need to redraw them?
2. What is the current state of the AI/ML platform inside TFM - greenfield, or are there production models I would inherit and govern from day one?
3. How does the SMD, Investment Technology & Applied Intelligence measure value realization for this team - is it delivery velocity, model performance, decisions enabled, or something else?

## The One Competency Gap to Prepare For

**Scale of people leadership.** The JD asks for 15+ years with 5+ in senior leadership; Saber is at ~7.3 years and leads through squad and review authority rather than direct managerial headcount. Prepare a crisp answer that (a) acknowledges the years gap honestly, (b) reframes around the breadth and seniority of stakeholders already managed (Heads of Risk, CIO-office, investment committees, Product Owners), and (c) shows readiness via concrete examples of mentoring, escalation ownership, and cross-functional squad leadership. Do not overclaim a Director-of-30 background.