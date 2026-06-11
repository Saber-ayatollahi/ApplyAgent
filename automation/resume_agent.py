#!/usr/bin/env python3
"""resume_agent.py — one-shot agentic resume generator.

Wires the agentic resume pipeline behind a single command (and the UI's
"Generate resume" button):

    job (tracker) + JD  --[Claude tailoring, Master-Repo-grounded]-->
    resume_content.json  --[resume_render.py]-->  applications/<date>_<co>_<role>/ (.docx)
                         (+ a matching cover-letter .md in the same folder)

Reuses jd_tailor's infrastructure so there's ONE Master Repo, ONE JD
fetcher, ONE Claude client (Opus→Sonnet, cost-guarded): build_system_prompt
(the ~35KB Master Repo + narrative-discipline rules), fetch_jd_from_url,
load_tracker_entry, call_claude. The only new piece is the user prompt that
asks for the structured resume_content.json shape (+ cover letter) instead
of jd_tailor's markdown draft.

Usage:
    python resume_agent.py --job-id auto-hoopp-senior-director-total-portfolio-risk
    python resume_agent.py --job-id <id> --no-pdf
    python resume_agent.py --company HOOPP --role "Senior Director, Total Portfolio Risk" --jd-file jd.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jd_tailor  # type: ignore  # noqa: E402
import resume_render  # type: ignore  # noqa: E402

RESUME_DATA_DIR = HERE / "resume_data"
INSTRUCTIONS = ROOT / "docs" / "resume_agent_instructions.md"

# ── Cost tiers ──────────────────────────────────────────────────────────
# A resume generate is up to 3 Claude calls: draft → validity → keyword-fix.
# The DRAFT benefits from the strongest model; the validity/keyword passes
# are review/edit tasks a cheaper model handles well. Tier picks the model
# per call (and whether to verify). Rough cost per resume (PDFs are free):
#   max       Opus  / Opus   / verify ON   ~ $1.30  (best)
#   balanced  Opus  / Sonnet / verify ON   ~ $0.60  (default — Opus draft,
#                                                     cheap check)
#   cheap     Sonnet/ Sonnet / verify ON   ~ $0.25
#   draft     Sonnet/  —     / verify OFF  ~ $0.10  (fastest, no check)
_MODELS = {"opus": "claude-opus-4-7", "sonnet": "claude-sonnet-4-6",
           "haiku": "claude-haiku-4-5"}
_FALLBACK = {"opus": "claude-sonnet-4-6", "sonnet": "claude-haiku-4-5",
             "haiku": "claude-haiku-4-5"}
TIERS = {
    "max":      {"draft": "opus",   "verify": "opus",   "do_verify": True},
    "balanced": {"draft": "opus",   "verify": "sonnet", "do_verify": True},
    "cheap":    {"draft": "sonnet", "verify": "sonnet", "do_verify": True},
    "draft":    {"draft": "sonnet", "verify": "sonnet", "do_verify": False},
}
DEFAULT_TIER = os.environ.get("RESUME_AGENT_TIER", "balanced")


def _use_model(key: str) -> None:
    """Point jd_tailor.call_claude at a model tier (with a cheaper fallback)."""
    jd_tailor.MODEL = _MODELS.get(key, key)
    jd_tailor.FALLBACK_MODEL = _FALLBACK.get(key, jd_tailor.MODEL)


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s or "").strip("_").lower()


def _resolve_job(args) -> tuple[str, str, str, dict | None]:
    """Return (company, role, jd_text, tracker_entry)."""
    entry = None
    if args.job_id:
        entry = jd_tailor.load_tracker_entry(args.job_id)
        if entry is None:
            raise SystemExit(f"job-id {args.job_id!r} not found in the tracker")
    company = args.company or (entry or {}).get("company") or "Company"
    role = args.role or (entry or {}).get("title") or "Role"

    # JD text: explicit file > explicit url > tracker url (live) > fit notes.
    jd = ""
    if args.jd_file:
        jd = Path(args.jd_file).read_text(encoding="utf-8")
    elif args.jd_url:
        jd = jd_tailor.fetch_jd_from_url(args.jd_url)
    elif entry and entry.get("url"):
        try:
            jd = jd_tailor.fetch_jd_from_url(entry["url"])
        except Exception as e:  # noqa: BLE001
            print(f"  [resume_agent] live JD fetch failed ({e}); "
                  "falling back to tracker fit notes.", file=sys.stderr)
    if not jd or len(jd.strip()) < 200:
        # Fallback: synthesize a JD-ish brief from the tracker fields so the
        # model still has something role-specific to anchor on.
        fn = (entry or {}).get("fit_notes") or ""
        kw = ", ".join((entry or {}).get("keywords") or [])
        jd = (f"(Live JD unavailable — built from tracker fit notes.)\n"
              f"Role: {role} at {company}.\n"
              f"Fit notes: {fn}\nKeywords: {kw}")
    return company, role, jd, entry


def _build_user_prompt(company: str, role: str, jd: str) -> str:
    rules = ""
    try:
        # Embed the WHOLE instruction doc. A previous [:9000] cap silently cut
        # it mid-Step-8, so the evidence-based rules (keyword mirroring, the
        # summary formula, relevance checks) never reached the model. The doc
        # is ~17k chars ≈ 4k tokens — cheap next to the Master Repo system
        # message; the generous ceiling only guards against runaway growth.
        rules = INSTRUCTIONS.read_text(encoding="utf-8")[:24000]
    except Exception:
        rules = "(resume_agent_instructions.md unavailable)"
    schema = resume_render.SCHEMA
    example = json.dumps(resume_render.EXAMPLE, indent=2)
    return (
        f"# TASK\n"
        f"Produce a tailored resume for **{role}** at **{company}**, as a "
        f"structured `resume_content.json` object that "
        f"automation/resume_render.py can render directly, PLUS a matching "
        f"cover letter.\n\n"
        f"# JOB DESCRIPTION\n```\n{jd[:14000]}\n```\n\n"
        f"# THE PROCEDURE YOU MUST FOLLOW (resume_agent_instructions.md)\n"
        f"{rules}\n\n"
        f"# OUTPUT SCHEMA (resume_content.json)\n{schema}\n\n"
        f"# A CONCRETE EXAMPLE OF THE SHAPE\n```json\n{example}\n```\n\n"
        f"# HARD REQUIREMENTS\n"
        f"- TRACEABILITY: every line traces to the Master Repo (in the system "
        f"message). The JD is the target, NOT a source of experience. Do not "
        f"import JD responsibilities as if Saber did them.\n"
        f"- Pick the positioning lane the JD actually signals (e.g. Total "
        f"Portfolio Risk → lead VaR/CVaR + risk decomposition + LDI; banking "
        f"book → IRRBB/ALM). Hero the most-relevant employer by BULLET WEIGHT, "
        f"never by breaking reverse-chronological order.\n"
        f"- EMPHASIS FOLLOWS THE JD (relevance rule): first derive THIS JD's "
        f"3-5 core themes; the summary's opening sentence, every section "
        f"heading, and core_skills must map onto them. A lane keyword the JD "
        f"never mentions (e.g. IRRBB on a pension-investment JD) must NOT "
        f"appear in the summary, any heading, or core_skills — at most one "
        f"supporting mention deep in a bullet, reframed in the JD's own "
        f"vocabulary (pension JD: 'duration / funded-status sensitivity', "
        f"not 'IRRBB / banking book').\n"
        f"- SECTION HEADINGS ARE PER-JOB: write the Moody's sub-headers from "
        f"scratch in this JD's language (echo its Key Accountabilities "
        f"groupings); never default to generic platform/banking headings "
        f"('… Engine', '… Platform Delivery') the JD doesn't ask for.\n"
        f"- summary: 60-85 words; the FIRST sentence must contain the EXACT "
        f"posting title verbatim — \"{role}\" — plus the ~7-years qualifier "
        f"(exact-title resumes get ~10x more interviews; a generic label "
        f"like 'finance professional' fails this rule).\n"
        f"- KEYWORD HONESTY (hard rule): a JD keyword that lacks Master-Repo "
        f"support must NOT appear as a skill or claim — leave it out and let "
        f"the cover letter own the gap. NEVER claim tools (e.g. Bloomberg), "
        f"products/process domains (collateral ops, trade lifecycle, middle "
        f"office, break resolution), or regulations the repo doesn't "
        f"evidence. A truthful 75% keyword match beats a fabricated 95%.\n"
        f"- Keep it to a 2-page budget (~65-85 rendered lines). Be selective.\n"
        f"- `target.jd_keywords`: 12-15 ATS tokens that ACTUALLY appear in the "
        f"resume text you write (the renderer self-checks coverage).\n"
        f"- The cover letter: ~300-350 words, 3-4 paragraphs, plus a short "
        f"honest-gaps note (what to own in interview, NOT to put in the "
        f"resume).\n\n"
        f"# RETURN FORMAT\n"
        f"Return ONE JSON object inside a single ```json fenced block, with "
        f"exactly these top-level keys:\n"
        f'  "resume_content": <the resume_content.json object matching the '
        f'schema above>,\n'
        f'  "cover_letter": <the LETTER BODY ONLY — salutation '
        f'("Dear Hiring Team,"), 3-4 paragraphs (~300-350 words), and the '
        f'sign-off ("Sincerely,\\nSaber Ayatollahi, CFA"). NO contact header '
        f'or subject line (the renderer adds a branded header) and NO '
        f'honest-gaps note (that goes in "notes")>,\n'
        f'  "interview_brief": <markdown string: the 5 most likely technical '
        f'questions for THIS role with 2-3 sentence model answers drawn from '
        f'the Master Repo STAR stories; then 3 sharp questions Saber should '
        f'ask; then the 1 competency gap to prepare for>,\n'
        f'  "notes": <short string: honest gaps / risks to flag before '
        f'submitting>.\n'
        f"No prose outside the fenced JSON block."
    )


def _revise_for_keywords(rc: dict, missing: list[str], system: str) -> dict:
    """One focused follow-up call: weave the missing ATS keywords into the
    resume truthfully, or drop them from target.jd_keywords if they can't be
    supported by the Master Repo. Returns the revised resume_content."""
    user = (
        "Here is a resume_content.json you produced:\n```json\n"
        f"{json.dumps(rc, ensure_ascii=False, indent=2)}\n```\n\n"
        f"The renderer's ATS self-check found these target keywords listed in "
        f"target.jd_keywords but ABSENT from the resume text: "
        f"{', '.join(missing)}.\n\n"
        "For EACH missing keyword: (a) ONLY if the Master Repo (system "
        "message) EXPLICITLY supports it, weave it naturally into an existing "
        "summary/skill/bullet (no new claims, no inflation); else (b) remove "
        "it from target.jd_keywords. BE STRICT — when in doubt, DROP the "
        "keyword: a truthful 75% match beats a fabricated 95%. Never "
        "introduce tools, products, process domains, or regulations the repo "
        "doesn't evidence (this step has previously fabricated 'recovery "
        "planning' and 'collateral' skills — do not repeat that). Keep "
        "everything else identical and within the 2-page budget. Return ONLY "
        "the corrected resume_content.json inside a single ```json fenced "
        "block."
    )
    raw = jd_tailor.call_claude(system, user, max_tokens=12000)
    m = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL) \
        or re.search(r"(\{.*\})", raw, re.DOTALL)
    if not m:
        return rc
    revised = json.loads(m.group(1))
    # The model may return the bare content or wrap it under resume_content.
    revised = revised.get("resume_content", revised)
    _validate_content(revised)
    return revised


def _verify_pass(payload: dict, jd: str, company: str, role: str,
                 system: str) -> dict:
    """Adversarial validity/critique pass: audit the draft resume + cover
    against the Master Repo (in the system prompt) and FIX anything
    untraceable or inflated. Returns a revised payload (resume_content +
    cover_letter corrected, plus a validity_report). The interview_brief is
    carried over untouched to save tokens."""
    rc = payload.get("resume_content")
    cover = payload.get("cover_letter", "")
    user = (
        "You are an ADVERSARIAL reviewer. The Master Repo (system message) is "
        "the CEILING on claims; the JD is the target, never a source of "
        "experience.\n\nDraft to audit:\n```json\n"
        f"{json.dumps({'resume_content': rc, 'cover_letter': cover}, ensure_ascii=False, indent=2)}"
        f"\n```\n\nTarget: {role} @ {company}.\nJD:\n```\n{jd[:6000]}\n```\n\n"
        "Audit EVERY summary sentence, core_skill, and bullet. Flag AND FIX:\n"
        "1. JD-imported duties presented as Saber's experience → rewrite to "
        "what the repo supports, or delete.\n"
        "2. Inflated verbs (Built/Developed/Led/Designed where the repo only "
        "supports Reviewed/Validated/Analyzed) → downgrade to the truthful "
        "verb.\n"
        "3. Skills/tools in core_skills not grounded in the repo → remove.\n"
        "4. Named regulations/frameworks (CCAR, FRTB, Basel) claimed as a "
        "capability without repo support → hedge to '-aligned / applied "
        "knowledge of' or remove.\n"
        "5. Cover-letter claims not supported by the resume/repo → align.\n"
        "6. RELEVANCE (the mirror check): list this JD's 3-5 core themes, "
        "then audit the PRIME SLOTS — the summary's opening sentence, every "
        "section heading, and core_skills. Any term there that the JD never "
        "asks for (e.g. IRRBB/OSFI B-12/Basel on a pension-investment JD) → "
        "reframe into the JD's own vocabulary or demote out of the prime "
        "slot. Section headings must echo THIS JD's accountability themes, "
        "not generic platform/banking groupings.\n"
        "7. JD-KEYWORD IMPORTS (noun-level): cross-check EVERY core_skill "
        "noun and every tool/system/product/process-domain mentioned in the "
        "resume (e.g. Bloomberg, collateral, trade lifecycle, middle office, "
        "break resolution, recovery planning, PnL cadence) against the "
        "Master Repo. Present in the JD but NOT evidenced in the repo → "
        "REMOVE it or hedge to honest adjacency ('analogous to', 'exposure "
        "to'). This is the most common inflation vector: the JD's vocabulary "
        "quietly becoming the candidate's claimed experience.\n"
        "8. EXACT TITLE: the summary's first sentence must contain the exact "
        "posting title verbatim; if missing, add it without inflating "
        "anything else.\n\n"
        "Keep all the strong, TRUE material and the 2-page budget. Return ONE "
        "```json fenced block with keys: resume_content (corrected), "
        "cover_letter (corrected, body only), validity_report (markdown: what "
        "you changed + any residual honest gaps to own in interview). "
        "STRICT JSON: escape every double quote inside string values — in the "
        "validity_report prose, prefer single quotes around cited phrases."
    )
    raw = jd_tailor.call_claude(system, user, max_tokens=16000)
    try:
        revised = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        # The verifier's output is occasionally malformed JSON — typically an
        # unescaped double quote inside the validity_report markdown. One
        # focused retry with the parse error fed back recovers it; without
        # this the whole validity pass silently degraded to "use first draft"
        # (observed twice in one day at ~char 11k each time).
        print(f"  [verify] output failed JSON parse ({e}); retrying once…",
              file=sys.stderr)
        retry_user = (
            user
            + f"\n\nIMPORTANT: your previous response FAILED JSON parsing "
              f"({e}). Re-emit the complete response as ONE strictly valid "
              f"```json block — escape all double quotes inside string "
              f"values (use single quotes for cited phrases in "
              f"validity_report)."
        )
        raw = jd_tailor.call_claude(system, retry_user, max_tokens=16000)
        revised = _extract_json(raw)
    revised = revised if "resume_content" in revised else {"resume_content": revised}
    # carry over what the verifier doesn't regenerate
    revised.setdefault("interview_brief", payload.get("interview_brief", ""))
    revised.setdefault("notes", payload.get("notes", ""))
    revised.setdefault("cover_letter", cover)
    return revised


def _extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    blob = m.group(1) if m else None
    if blob is None:
        # last-ditch: first {...} that parses
        m2 = re.search(r"(\{.*\})", text, re.DOTALL)
        blob = m2.group(1) if m2 else None
    if blob is None:
        raise ValueError("no JSON object found in model output")
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # Salvage pass: parse the FIRST complete object and ignore whatever
        # trails it. Covers the model echoing stray text/a second block after
        # the close ("Extra data: … char 14289" — observed on a live draft).
        # raw_decode still raises if the object itself is malformed, which
        # the caller's API retry then handles.
        obj, _ = json.JSONDecoder().raw_decode(blob[blob.index("{"):])
        if isinstance(obj, dict):
            return obj
        raise


_REQUIRED = ("contact", "summary", "core_skills", "experience", "education")


def _validate_content(rc: dict) -> None:
    missing = [k for k in _REQUIRED if k not in rc]
    if missing:
        raise ValueError(f"resume_content missing required keys: {missing}")
    if not isinstance(rc.get("experience"), list) or not rc["experience"]:
        raise ValueError("resume_content.experience must be a non-empty list")
    if not (rc.get("contact") or {}).get("name"):
        raise ValueError("resume_content.contact.name is required")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-id", help="tracker job id")
    ap.add_argument("--company")
    ap.add_argument("--role")
    ap.add_argument("--jd-url")
    ap.add_argument("--jd-file")
    ap.add_argument("--no-pdf", action="store_true",
                    help="skip PDF (just .docx). Default renders PDFs via "
                         "libreoffice or MS Word.")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the adversarial validity/critique pass "
                         "(faster + cheaper, but no traceability check).")
    ap.add_argument("--tier", choices=list(TIERS), default=DEFAULT_TIER,
                    help="cost/quality tier (default: balanced). max=Opus all "
                         "(~$1.30); balanced=Opus draft + Sonnet check "
                         "(~$0.60); cheap=Sonnet all (~$0.25); draft=Sonnet, "
                         "no verify (~$0.10).")
    ap.add_argument("--model", help="override the DRAFT model explicitly")
    args = ap.parse_args()

    if not (args.job_id or (args.company and args.role)):
        ap.error("pass --job-id, or both --company and --role")

    tier = TIERS.get(args.tier, TIERS["balanced"])
    do_verify = tier["do_verify"] and not args.no_verify
    print(f"[resume_agent] tier={args.tier} "
          f"(draft={tier['draft']}, verify={tier['verify'] if do_verify else 'off'})",
          file=sys.stderr)

    jd_tailor.preflight_or_exit()  # API key + anthropic present
    company, role, jd, _entry = _resolve_job(args)
    print(f"[resume_agent] tailoring {role} @ {company} "
          f"(JD {len(jd)} chars)…", file=sys.stderr)

    system = jd_tailor.build_system_prompt()
    user = _build_user_prompt(company, role, jd)

    # Draft on the tier's draft model (or an explicit --model override).
    # Two attempts: like the verify pass, a long draft occasionally comes back
    # as malformed JSON (unescaped quote, stray text after the close). One
    # focused retry with the parse error fed back recovers it; without this a
    # ~$0.55 draft call was thrown away on a parse hiccup (observed live).
    _use_model(args.model or tier["draft"])
    raw = jd_tailor.call_claude(system, user, max_tokens=16000)
    payload = None
    for _attempt in (1, 2):
        try:
            payload = _extract_json(raw)
            rc = payload["resume_content"]
            _validate_content(rc)
            break
        except Exception as e:  # noqa: BLE001
            if _attempt == 1:
                print(f"[resume_agent] draft output unusable ({e}); "
                      "retrying once…", file=sys.stderr)
                raw = jd_tailor.call_claude(
                    system,
                    user + f"\n\nIMPORTANT: your previous response FAILED "
                           f"JSON parsing ({e}). Re-emit the complete "
                           f"response as ONE strictly valid ```json block — "
                           f"escape all double quotes inside string values, "
                           f"and output NOTHING after the closing fence.",
                    max_tokens=16000)
                continue
            print(f"[resume_agent] model output unusable: {e}", file=sys.stderr)
            dump = HERE / "outputs" / f"resume_agent_raw_{_slug(company)}.txt"
            dump.parent.mkdir(parents=True, exist_ok=True)
            dump.write_text(raw, encoding="utf-8")
            print(f"  raw output saved to {dump}", file=sys.stderr)
            return 2

    # ── Validity / critique pass — adversarially audit the draft resume +
    # cover against the Master Repo and fix JD-imported inflation, untruthful
    # verbs, ungrounded skills BEFORE rendering. Runs on the tier's (cheaper)
    # verify model; skippable per tier or with --no-verify.
    if do_verify:
        _use_model(tier["verify"])
        try:
            payload = _verify_pass(payload, jd, company, role, system)
            rc = payload["resume_content"]
            _validate_content(rc)
            print("[resume_agent] validity pass applied.", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"[resume_agent] validity pass skipped ({e}); using "
                  "first draft.", file=sys.stderr)

    # ── Render the resume in-process (resume .docx + .pdf via libreoffice or
    # the MS-Word/docx2pdf fallback) with an ATS-keyword retry. ──
    import resume_render as _RR  # noqa: WPS433
    make_pdf = not args.no_pdf
    apps_base = str(ROOT / "applications")

    def _render(content):
        _f, _dx, _pdf = _RR.bundle(content, apps_base, make_pdf=make_pdf)
        _kws, _miss = _RR.keyword_report(content)
        return _f, _miss

    try:
        folder, missing = _render(rc)
    except Exception as e:  # noqa: BLE001
        print(f"[resume_agent] render failed: {e}", file=sys.stderr)
        return 3
    if missing:
        print(f"[resume_agent] {len(missing)} ATS keyword(s) missing "
              f"({', '.join(missing)}); revising once…", file=sys.stderr)
        _use_model(tier["verify"])  # cheap edit task
        try:
            rc = _revise_for_keywords(rc, missing, system)
            folder, missing = _render(rc)
        except Exception as e:  # noqa: BLE001
            print(f"[resume_agent] keyword revision failed ({e}); keeping "
                  "the first draft.", file=sys.stderr)
    if missing:
        print(f"[resume_agent] note: still missing {', '.join(missing)}.",
              file=sys.stderr)

    # Persist the final structured content (input to the renderer).
    RESUME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    content_path = RESUME_DATA_DIR / f"{_slug(company)}_{_slug(role)[:50]}.json"
    content_path.write_text(json.dumps(rc, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    if folder is None or not folder.exists():
        apps = sorted((ROOT / "applications").glob("*/"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        folder = apps[0] if apps else None

    # ── Cover letter (branded .docx + .pdf, matching the resume) + interview
    # brief + validity report — one deliverable bundle. ──
    if folder is not None and folder.exists():
        base = f"{_slug(company)}_{_slug(role)[:50]}"
        cover = payload.get("cover_letter") or ""
        notes = payload.get("notes") or ""
        brief = payload.get("interview_brief") or ""
        report = payload.get("validity_report") or ""
        if cover:
            try:
                _cdocx = folder / f"{base}_cover.docx"
                _RR.render_cover(rc.get("contact") or {},
                                 rc.get("target") or {}, cover, str(_cdocx))
                if make_pdf:
                    _RR.to_pdf(_cdocx, folder)
            except Exception as e:  # noqa: BLE001
                print(f"[resume_agent] cover render failed ({e})",
                      file=sys.stderr)
            (folder / f"{base}_cover.md").write_text(
                cover + (f"\n\n---\n\n**Before submitting:** {notes}\n"
                         if notes else ""),
                encoding="utf-8")
        if brief:
            (folder / f"{base}_interview_brief.md").write_text(
                brief, encoding="utf-8")
        if report:
            (folder / f"{base}_validity_report.md").write_text(
                report, encoding="utf-8")
        print(f"[resume_agent] DONE -> {folder}", file=sys.stderr)
        # machine-readable last line for the UI to parse
        print(f"RESUME_AGENT_FOLDER={folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
