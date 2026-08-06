## Likely Technical Questions

**1. How would you structure a liquidity stress-testing framework for a multi-entity fintech?**
Draw on the Moody's cash-flow engine (Story 1): base / stress / reverse-stress scenarios, time-bucketed liquidity gaps (T+1 to multi-year), and behavioral cash-flow + prepayment assumptions layered with macro overlays. Emphasize auditability — the engine replaced non-auditable spreadsheets and embedded logging and validation.

**2. Walk me through how you'd design and monitor a capital risk-limits framework within risk appetite.**
Frame from the model-governance seat: define limits tied to internal/external ratios, monitor positions against appetite, and run periodic reviews/recalibrations. Tie to delegated sign-off discipline — escalate outputs that are mathematically defensible but economically unsupported (Story 2).

**3. Tell me about a time a model output looked right but wasn't.**
Use Story 2: portfolio sensitivities passed internal checks but failed the client's economic intuition under a rate shock. Held the release, decomposed by asset class, found a curve-calibration edge case, escalated to product and the client's Head of Risk. Release delayed 48 hours; client avoided acting on wrong numbers.

**4. How do you assess asset risk and duration on a balance sheet?**
Reference parallel/non-parallel shock analysis, duration-gap and repricing-mismatch analytics, and cross-asset interaction review from Moody's, plus funding-ratio and duration-mismatch work at Ortec. Keep it in balance-sheet/funding language, not banking-book jargon.

**5. How are you using AI to strengthen Treasury/finance modelling?**
Use Story 7: agentic workflows (Claude Code, Cursor) for first-pass code review, validation scaffolding, and documentation — human sign-off retained on governance-critical work. ~30-40% cycle-time reduction; a repeatable template rather than a one-off.

## Sharp Questions Saber Should Ask

1. Across the material legal entities, which capital/liquidity ratios are currently binding, and where is the framework most manual today?
2. How does Treasury's stress-testing and scenario design interact with FP&A's forecasting cadence — one model or two?
3. What does 'success in the first 12 months' look like for this role beyond keeping positions within appetite?

## The One Competency Gap to Prepare For

**Broker-dealer regulatory capital.** The JD wants deep knowledge of broker-dealer regulatory capital requirements (e.g., IIROC/CIRO net-capital-style rules) and 9+ years — Saber has ~7 years and no direct broker-dealer capital-rules experience. Prepare to own this honestly: strong general capital-ratio and ALM/liquidity fundamentals, fast ramp on a specific rule set, and demonstrated ability to learn regulatory frameworks (IFRS 17/9 at EY). Do NOT claim broker-dealer net-capital experience in the room.