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
import re
import subprocess
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
        rules = INSTRUCTIONS.read_text(encoding="utf-8")[:9000]
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
        f"- summary: 60-85 words, opens with the target title + years.\n"
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
        f'  "cover_letter": <the cover letter as a markdown string>,\n'
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
        "For EACH missing keyword: (a) if it is TRUTHFUL per the Master Repo, "
        "weave it naturally into an existing summary/skill/bullet (do not add "
        "a new claim, do not inflate); else (b) remove it from "
        "target.jd_keywords. Keep everything else identical and within the "
        "2-page budget. Return ONLY the corrected resume_content.json inside a "
        "single ```json fenced block."
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


_MISSING_RE = re.compile(r"ATS keywords MISSING \(\d+/\d+\): (.+)$", re.MULTILINE)


def _render_and_check(content_path: Path, no_pdf: bool):
    """Run resume_render; return (returncode, folder|None, missing_keywords,
    combined_log)."""
    cmd = [sys.executable, str(HERE / "resume_render.py"),
           "--content", str(content_path)]
    if no_pdf:
        cmd.append("--no-pdf")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log = proc.stdout + proc.stderr
    folder = None
    mf = re.search(r"^folder\s+(.+)$", proc.stdout, re.MULTILINE)
    if mf:
        folder = Path(mf.group(1).strip())
    missing: list[str] = []
    mk = _MISSING_RE.search(log)
    if mk:
        missing = [k.strip() for k in mk.group(1).split(",") if k.strip()]
    return proc.returncode, folder, missing, log


def _extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    blob = m.group(1) if m else None
    if blob is None:
        # last-ditch: first {...} that parses
        m2 = re.search(r"(\{.*\})", text, re.DOTALL)
        blob = m2.group(1) if m2 else None
    if blob is None:
        raise ValueError("no JSON object found in model output")
    return json.loads(blob)


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
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--model", help="override the Claude model")
    args = ap.parse_args()

    if not (args.job_id or (args.company and args.role)):
        ap.error("pass --job-id, or both --company and --role")

    if args.model:
        jd_tailor.MODEL = args.model

    jd_tailor.preflight_or_exit()  # API key + anthropic present
    company, role, jd, _entry = _resolve_job(args)
    print(f"[resume_agent] tailoring {role} @ {company} "
          f"(JD {len(jd)} chars)…", file=sys.stderr)

    system = jd_tailor.build_system_prompt()
    user = _build_user_prompt(company, role, jd)

    raw = jd_tailor.call_claude(system, user, max_tokens=16000)
    try:
        payload = _extract_json(raw)
        rc = payload["resume_content"]
        _validate_content(rc)
    except Exception as e:  # noqa: BLE001
        print(f"[resume_agent] model output unusable: {e}", file=sys.stderr)
        dump = HERE / "outputs" / f"resume_agent_raw_{_slug(company)}.txt"
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(raw, encoding="utf-8")
        print(f"  raw output saved to {dump}", file=sys.stderr)
        return 2

    # Persist the structured content (input to the renderer).
    RESUME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    content_path = RESUME_DATA_DIR / f"{_slug(company)}_{_slug(role)[:50]}.json"
    content_path.write_text(json.dumps(rc, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    print(f"[resume_agent] wrote {content_path.name}", file=sys.stderr)

    # Render + ATS keyword self-check, with ONE revision pass if the model
    # listed keywords it didn't actually cover (the gap seen on the first
    # Scotiabank run — incorporate truthfully or drop, then re-render).
    code, folder, missing, log = _render_and_check(content_path, args.no_pdf)
    sys.stderr.write(log)
    if code != 0:
        print("[resume_agent] resume_render failed", file=sys.stderr)
        return 3
    if missing:
        print(f"[resume_agent] {len(missing)} ATS keyword(s) missing "
              f"({', '.join(missing)}); revising once…", file=sys.stderr)
        try:
            rc = _revise_for_keywords(rc, missing, system)
            content_path.write_text(
                json.dumps(rc, indent=2, ensure_ascii=False), encoding="utf-8")
            code, folder, missing, log = _render_and_check(
                content_path, args.no_pdf)
            sys.stderr.write(log)
        except Exception as e:  # noqa: BLE001
            print(f"[resume_agent] keyword revision failed ({e}); keeping "
                  "the first draft.", file=sys.stderr)
    if missing:
        print(f"[resume_agent] note: still missing {', '.join(missing)} "
              "(left as-is — review before submitting).", file=sys.stderr)

    if folder is None or not folder.exists():
        apps = sorted((ROOT / "applications").glob("*/"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        folder = apps[0] if apps else None

    # Drop the cover letter + interview brief into the same folder — one
    # deliverable bundle (resume .docx + cover + brief), replacing the
    # separate jd_tailor markdown outputs.
    if folder is not None and folder.exists():
        base = f"{_slug(company)}_{_slug(role)[:50]}"
        cover = payload.get("cover_letter") or ""
        notes = payload.get("notes") or ""
        brief = payload.get("interview_brief") or ""
        if cover:
            (folder / f"{base}_cover.md").write_text(
                cover + (f"\n\n---\n\n**Before submitting:** {notes}\n"
                         if notes else ""),
                encoding="utf-8")
        if brief:
            (folder / f"{base}_interview_brief.md").write_text(
                brief, encoding="utf-8")
        print(f"[resume_agent] DONE -> {folder}", file=sys.stderr)
        # machine-readable last line for the UI to parse
        print(f"RESUME_AGENT_FOLDER={folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
