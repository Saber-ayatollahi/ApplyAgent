# Resume Tailoring — Agent Instructions (the ONE instruction)

> **Purpose.** This is the single, authoritative procedure for producing a
> tailored resume for any job. Given a job description (JD), an AI agent follows
> these steps to generate **one** structured content file and render **one**
> branded `.docx` using **one** script. No ad-hoc resume building.

```
Master Repo (+ keyword bank)  +  JD
        │
        ▼  (this instruction — AI tailoring)
  resume_content.json   ──────►  automation/resume_render.py  ──────►  Saber_<Company>_<Role>.docx
        │                                  (style/template, code-encoded)
        └── validated, keyword-checked, 2-page-budgeted
```

The agent owns **content** (what the resume says). `resume_render.py` owns
**style** (how it looks). Never hand-edit the `.docx`; change the JSON and re-render.

---

## ⛔ THE TRACEABILITY RULE (most important — read first)

**Every line of the resume must trace to a specific statement in the Master
Repo. The Master Repo is the ceiling on claims; the JD is NOT a source of
experience.**

The single biggest failure mode is **importing the JD's responsibilities as if
they were the candidate's experience.** A job description lists what the role
*wants*; it is not evidence of what the candidate *did*. Pulling its verbs and
duties into the resume produces confident-sounding lines the candidate cannot
defend in an interview.

Concrete inflation traps (all real, all caught in review — do NOT repeat):

| Inflated (JD-imported / overstated) | Honest (Master-Repo-true) |
|---|---|
| "Build independently developed benchmark models; provide acceptance criteria to technology teams" | (not in repo → **delete**) "Review aggregation logic from security- to portfolio-level risk metrics" |
| "**Develop** derivatives pricing models" | "**Review and validate** derivatives pricing **outputs**" (repo says *validate outputs*) |
| "Counterparty Credit Risk (CCR)" in CORE SKILLS | (no CCR/PFE/xVA in repo → **remove**; own the gap in the cover letter) |
| "**Formal** sign-off authority" (sounds like title/portfolio authority) | "**Delegated** sign-off authority on specific outputs" |
| Naming a regulation the candidate hasn't worked under (CCAR, FRTB) as a capability | One hedged "**-style / -aligned / applied knowledge of**" reference at most |

**Verb discipline:** match the verb to the evidence. *Built/Developed/Led/Designed*
require the repo to show the candidate did the building. *Reviewed/Validated/
Analyzed/Supported/Contributed to* are the honest verbs when the repo shows a
review/support role. When unsure, downgrade the verb.

**Keyword honesty:** a JD must-have keyword goes on the resume ONLY if the
candidate genuinely has it. Never place a keyword in CORE SKILLS with no
supporting bullet — that "keyword without evidence" pattern passes the ATS but
fails the human screen and the interview. If a must-have is a genuine gap
(e.g., an ALM→market-risk pivot lacking CCR/FRTB/CCAR), **leave it off and let
the cover letter own the pivot.** A truthful 75% keyword match beats a fabricated
95%.

---

## Sources of truth (read these, in order)

1. `docs/Saber_Ayatollahi_Master_Repository.md` — the factual spine. **Every
   claim in the resume must trace to this file.** (Generated from
   `docs/master_repo/*.yaml`; the structured records live there and are loadable
   via `automation/master_repo.py`.)
2. `docs/master_repo/keyword_bank.yaml` — canonical skill phrases + ATS aliases.
3. The JD for the target role.

If a fact is not in the Master Repo, it does not go on the resume. Do not invent
employers, dates, metrics, tools, or regulatory experience.

---

## Step 1 — Analyse the JD

Extract and write down:
- **Title + seniority** and team/function.
- **Must-haves** vs **nice-to-haves** (verbatim).
- **Regulatory / domain frameworks** named (e.g., market risk, CCR, CCAR, FRTB,
  IRRBB, Basel, IFRS).
- **Hard ATS keywords** — the concrete nouns a parser scans for (languages,
  methods, regulations, products). These become `target.jd_keywords`.

## Step 2 — Choose positioning (honest, evidence-led)

Master Repo §7 defines two primary angles: **ALM / IRRBB / Model Governance**
and **Vendor-Platform / Client Solutions**. Pick the closest, then decide the
overlay:
- If the JD is sell-side / trading-book / market-risk / quant (e.g., RBC GRA),
  keep the ALM/balance-sheet spine but lead the summary and skills with the
  **quant / market-risk** overlay — map transferable evidence (derivatives
  valuation, stochastic/Monte Carlo scenario engines, model governance &
  sign-off, Python/MATLAB/SQL) into the JD's language.
- **Never claim direct experience Saber doesn't have.** Frame adjacent domains
  as *applied knowledge* / *analogous to* (e.g., "CCAR-style", "Basel
  market-risk frameworks"). Do **not** assert sell-side trading-desk, direct CCR
  desk, or FRTB delivery experience unless the Master Repo adds it.

## Step 3 — Select content from the Master Repo

- Pull bullets from the tagged bullet library (§5) that match the angle; prefer
  the JD's own verbs and nouns where the underlying fact supports it.
- Respect the non-negotiable framings: **~7 years** total experience (never
  "10+"); **sign-off authority** = role-delegated review authority on specific
  outputs; portfolios **"$5–25bn per engagement; $50bn+ cumulative"**.
- Keep Moody's as two sub-roles (Asst. Director, May 2023–Present; Client
  Service Specialist, May 2022–May 2023). Do not merge them or backdate the
  Assistant Director title.

## Step 4 — Write `resume_content.json`

Conform to the schema (`python automation/resume_render.py --schema`; example
via `--example`). Rules:
- **summary**: one paragraph, **60–85 words**, evidence-backed, opens on the
  angle from Step 2.
- **core_skills**: a **multiple of 3** (the grid is 3 columns; 9 is standard).
  Collectively they must cover the JD's must-have keywords.
- **experience**: employer → roles → sections. A section `heading` of `null`
  means plain bullets with no sub-header (used for EY/Ortec). Use sub-headers to
  theme a dense role (Moody's) around the JD's priorities.
- **education**: unchanged unless the JD calls for a specific credential to lead.
- **target.jd_keywords**: the Step-1 hard keywords, so the renderer can verify
  coverage. Use the literal token the ATS scans for (e.g., `"statistics"`, not
  only `"statistical"`).

Save to `automation/resume_data/<company>_<role-slug>.json`.

## Step 5 — Keyword discipline (ATS)

Walk `keyword_bank.yaml`. For every JD must-have, ensure the canonical phrase
**or one of its aliases appears verbatim** somewhere in the content. The renderer
reports any `target.jd_keywords` that are missing — drive that list to zero
**without fabricating**: surface a real, evidenced skill using the keyword's
wording rather than inventing experience.

## Step 6 — Length & formatting budget (two pages)

- **Role `title`** must fit on one line — abbreviate like the house style
  ("Asst. Director", not "Assistant Director"). `location_date` is rendered
  separately (non-bold italic) so keep it short ("Toronto, May 2023 – Present").
- Keep total bullets to roughly **≤ 22** and bullets to **1–2 lines**.
- The renderer prints a line-budget estimate; keep it under budget. Final proof
  is the page count from `--check-pages`.

## Step 7 — Render (folder with BOTH formats)

The renderer creates one folder per job, named by date + company + role, and
writes **both** the Word and PDF versions into it:

```bash
python automation/resume_render.py \
  --content automation/resume_data/<company>_<role-slug>.json \
  --check-pages
```

Produces:

```
applications/<YYYY-MM-DD>_<Company>_<Role>/
    Saber_Ayatollahi_<Company>_<Role>.docx
    Saber_Ayatollahi_<Company>_<Role>.pdf
```

Notes:
- Date defaults to today; override with `--date YYYY-MM-DD`. Base folder defaults
  to `applications/`; override with `--bundle-base`.
- PDF is produced via LibreOffice (`soffice`); if it is not installed the docx is
  still written and a warning is printed. Use `--no-pdf` to skip.
- `--out <path>` is a legacy single-file mode (writes one .docx, plus a .pdf
  beside it unless `--no-pdf`).

## Step 8 — Verify (must all pass)

1. `pages: 2 [OK]` (counted from the generated PDF; or 1 — never 3+). If over, trim bullets/skills and re-render.
2. `✓ all N target ATS keywords present`. If any missing, fix per Step 5.
3. **Traceability audit (do this line by line):** for EVERY summary clause, skill,
   and bullet, point to the specific Master-Repo statement that backs it. If you
   can't, cut or downgrade it. Specifically check: no JD-imported duties; verbs
   match evidence (no "build/develop" where the repo shows review/validate); no
   keyword in CORE SKILLS without a supporting bullet; sign-off worded as
   "delegated"; regulations only as hedged "-style/-aligned" references. Correct
   years/figures; Moody's two-role split intact.
4. Eyeball the rendered PDF: no role-title wrapping, headings correct, summary
   60–85 words.

Only after all four pass is the resume final.

---

## Hard rules (never break)

- No fabricated employers, titles, dates, metrics, tools, or regulatory
  experience. Master Repo is the ceiling on claims.
- Never "10+ years"; it's ~7. Never backdate the Assistant Director title.
- Adjacent domains (CCR, CCAR, FRTB, sell-side market risk) are *applied
  knowledge / analogous*, not direct experience, unless the Master Repo says so.
- One content JSON and one rendered `.docx` per job. Re-render from JSON; never
  hand-edit the `.docx`.

## File map

| Thing | Path |
|---|---|
| Renderer (style/template, code) | `automation/resume_render.py` |
| Schema / example | `python automation/resume_render.py --schema` / `--example` |
| Per-job content (input) | `automation/resume_data/<company>_<role>.json` |
| Per-job output (docx + pdf) | `applications/<date>_<company>_<role>/` |
| Worked example (RBC) | `automation/resume_data/rbc_global_risk_analytics.json` |
| Master Repo (facts) | `docs/Saber_Ayatollahi_Master_Repository.md` (+ `docs/master_repo/*.yaml`) |
| ATS aliases | `docs/master_repo/keyword_bank.yaml` |

## Naming convention

Folder:  `applications/<YYYY-MM-DD>_<Company>_<Role>/`
Output:  `Saber_Ayatollahi_<Company>_<Role>.docx` + `.pdf` (both, in that folder)
Content: `automation/resume_data/<company>_<role-slug>.json`

---

# Evidence-based rules (2026 research) — encode these

> Sources: Harvard/MIT/Stanford career centers, Microsoft/Adobe design guidance,
> Jobscan & Greenhouse (ATS), Resume Pilots (executive), Laszlo Bock (Google).
> These are the rules behind the renderer's design and the content steps above.

## A. Design / ATS-safety (the renderer enforces these — don't fight them)

- **Single column, no tables, no text boxes, no headers/footers.** Multi-column
  grids and tables are the #1 ATS parse failure: scanners read straight across
  columns and drop or scramble content (notably the skills and contact blocks).
  The renderer is fully linear; keep content in the JSON, never re-introduce
  tabular layout.
- **Standard section headings** the parser recognises: SUMMARY, CORE SKILLS,
  EXPERIENCE, EDUCATION. (Avoid cute headings like "Where I've Made Impact".)
- **Length: two pages is correct for this senior candidate** (1 page is a myth
  above ~10 yrs of relevant material; never spill to a 3rd page). Reverse-
  chronological order; most recent role first.
- **Type:** professional sans (Avenir Next LT Pro in Word; Montserrat for the
  rendered PDF). Name ~18–20pt, section heads ~11–12pt, body 10pt. Don't shrink
  body below 10pt to force fit — cut words instead.
- **Contact line** is plain text separated by dots (City • phone • email •
  linkedin) — never in a header/footer or table. Strip the URL scheme.

## B. Professional summary (Jobscan executive formula)

- Shape: **[exact target job title] + [years] + [top 2–3 JD skills] + [1–2
  quantified achievements] + [unique value]**. 3–5 sentences, **~60–90 words**.
- Use the **exact job title from the posting** somewhere in the summary — Jobscan
  data: exact-title resumes were ~10x more likely to get the interview.
- **No first-person pronouns** anywhere on the resume (I/me/my). Recast "where I
  develop…" as "developing…/with sign-off authority over…".
- A **summary**, never an "objective".

## C. Bullets — action verb + quantified result (XYZ / PAR)

- Formula: **"Accomplished [X] measured by [Y] by doing [Z]"** (Google/Bock) —
  i.e., strong past-tense action verb → quantified result → how.
- **Lead every role with its strongest, most JD-relevant bullet.**
- **Quantify.** Use %, $, count, scale, time saved. When exact figures aren't
  available, quantify honestly with **scope/scale/range/frequency** ("$5–25bn
  per engagement", "T+1 to multi-year", "all assigned accounts") — never invent
  precise numbers.
- One line each where possible; **1–2 lines max**. Vary the opening verb; avoid
  starting consecutive bullets with the same word.
- Keep total bullets to roughly **≤ 22** for the two-page budget.

## D. Core skills (highest-leverage ATS zone)

- **8–12** skills, **hard-skill-led (~70/30 hard/soft)**, each an **exact JD
  term** the candidate genuinely has. Recruiters filter on skills first.
- Include **acronym + long-form** pairs where the JD uses them (e.g.,
  "Counterparty Credit Risk (CCR)", "Sarbanes-Oxley (SOX)").
- Soft skills are **demonstrated in bullets**, not listed as adjectives.

## E. Keyword optimisation without stuffing

- **Mirror the JD's exact wording** for must-have/recurring terms (ATS filters
  on near-exact phrases; "led a team" may not match "executive leadership").
- Weave **~10–15 JD keywords** across summary, skills, and the **first bullet of
  each role**; each keyword ~2–3× in different contexts, never as a bare repeated
  list. Read it aloud — if it sounds repetitive, cut.
- Keep resume keywords consistent with the candidate's LinkedIn.

## F. Content mistakes that get senior/finance resumes screened out

- Empty buzzwords/clichés ("results-driven", "team player", "responsible for").
- Duties instead of results (no metric) — fatal at senior/finance level.
- Not tailoring / missing the exact title and must-have keywords.
- **Inflated or unverifiable claims** — titles, dates, scope, and metrics get
  checked in executive background checks and probed in interviews. Every line
  must be defensible. (See the hard rules above: Master Repo is the ceiling.)

## G. Per-job verification adds (in addition to Step 8)

- Match-rate intuition: aim for **~80%+** of the JD's must-have keywords present.
- No first-person pronouns; no consecutive bullets sharing an opening verb;
  summary contains the exact posting title; ≤ 2 pages.
