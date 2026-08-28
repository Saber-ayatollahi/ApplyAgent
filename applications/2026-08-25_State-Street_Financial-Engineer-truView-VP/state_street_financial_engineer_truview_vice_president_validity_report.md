## Changes made

**Summary**
- Added the exact posting title verbatim ('Financial Engineer (VP), truView') to the opening sentence per Rule 8 — the draft only had a loose paraphrase.
- Softened 'reviewing market data' to 'reviewing curve construction (including underlying market data inputs)' — 'market data' as a standalone reviewed object is not separately evidenced in the repo; it is only defensible as embedded in curve construction, which is evidenced.

**Core skills**
- Removed '& Market Data' from 'Curve Construction, Spread Calibration & Market Data' — this is a JD noun (Rule 7) not independently evidenced as a distinct capability in Section 4.2 of the repo. Left as 'Curve Construction & Spread Calibration', which is directly evidenced.
- All other core_skills lines checked against Section 4 and the tagged bullet library — all grounded (derivatives review, multi-asset sensitivity, stress testing, ESG, model governance, aggregation, VaR/CVaR, and the Python/SQL/VBA/R/Excel stack per Section 4.8).

**Experience — Moody's, Modelling Services**
- Renamed section heading 'Valuation Models, Derivatives & Market Data' to 'Valuation, Derivatives & Curve Review' — 'Valuation Models' in a prime-slot heading risks implying he *builds* pricing models, which the repo does not support (he holds review/sign-off authority, not model-build ownership); 'Market Data' demoted out of the heading per the same logic as the core_skills fix.
- Renamed 'Model Governance, Testing & Production Tooling' to 'Model Governance, Validation & Production Tooling' — 'Testing' is lifted almost verbatim from the JD's 'Testing of new model implementations' work stream, which is not a named activity in the repo (the repo's actual vocabulary is validation/review/escalation, which is functionally adjacent but should not borrow the JD's exact term in a prime slot).
- Removed 'across global locations' from the escalation bullet — this phrase is lifted directly from the JD's 'coworkers located in a variety of global locations' line; the repo does not evidence global-location stakeholder interfacing for the Modelling Services role (only 'clients' Heads of Risk and investment stakeholders,' no geography claim).
- Verified the VBA-macro re-engineering bullet against Section 4.8: the repo confirms 'working knowledge — reading/maintaining/refactoring Excel macros in professional context,' which supports 're-engineered ... VBA macro workflows into Python' (a migration-away-from-VBA claim, not a VBA-development claim). Kept, correctly scoped.
- All other Moody's bullets cross-checked against the tagged bullet library — verbs (Led design, Validates, Reviews, Escalates, Built) all match repo-supported verb strength; no inflation found beyond the two fixes above.

**Cover letter**
- Restructured from 4 paragraphs to 3 paragraphs per the stated rule (opening capability claim / evidence / company-hook + close), merging the original paragraphs 2–3 and folding the closing sentence into paragraph 3. Word count now ~306, within the 300-350 band.
- Removed the unhedged claim of insurer clients on the truView/Moody's side; reattributed 'insurers' correctly to the EY IFRS 17 engagement (which genuinely served insurance clients), rather than implying Moody's or Ortec analytics clients included insurers — the repo does not evidence insurer clients for either.
- Left 'the same operating model as truView' — this is a permissible analogical framing (platform-delivered-as-a-service to institutional clients), consistent with how Template B frames the Aladdin/MSCI parallel; not a factual overclaim.
- Kept 'a call I have made under client deadline pressure' — directly supported by STAR Story 2 (escalation/48-hour hold), not fabricated.

## Relevance check (JD mirror)
JD core themes: (1) full-repricing derivatives valuation model dev/maintenance across rates/FX/inflation/exotics, (2) market data definition and evaluation, (3) model-spec-to-developer-to-test lifecycle and production support, (4) risk analytics aggregation and scenario/stress design, (5) stakeholder communication and (at VP level) small-team leadership. The corrected draft's prime slots (summary opener, headings, core_skills) now mirror themes 1, 2 (hedged), 3, and 4 using only repo-evidenced verbs (review/validate/escalate/lead-design), and do not claim theme 5's team-management dimension anywhere — correctly, since it isn't evidenced.

## Residual honest gaps to own in interview
- No claimed experience with **exotic interest-rate/FX derivatives, inflation derivatives as a distinct product class, or securitized products** (JD 'desirable' list) — correctly omitted; if asked, pivot to vanilla rates/FX/inflation validation depth and cross-asset sensitivity review.
- **VBA is maintenance-level** (reading/refactoring macros, not greenfield development) — if pressed on 'comfort with VBA' at a hands-on coding level, be honest that recent VBA work has been migration-out-of, not building new macros.
- **No C++/C# exposure** — the repo explicitly retired this claim; if asked, say 'not part of my production stack, Python is my language of choice for this kind of work.'
- **No formal people-management** of a team (the VP role 'usually manage[s] a small group') — the honest bridge is mentorship of junior colleagues and being the escalation/technical-liaison point across client and PO teams, not direct reports.
- The 'market data' review claim is real but indirect — Saber reviews curve/spread inputs as part of validation, not as a dedicated market-data-sourcing function; be ready to describe this distinction precisely if probed.