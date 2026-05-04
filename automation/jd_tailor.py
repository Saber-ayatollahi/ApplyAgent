#!/usr/bin/env python3
"""
jd_tailor.py — Resume + cover letter tailor for Saber Ayatollahi's job search.

Usage:
    python jd_tailor.py --job-id scot-001
    python jd_tailor.py --jd-file path/to/jd.txt --company Scotiabank --role "Director, ALM Modelling"
    python jd_tailor.py --jd-url "https://jobs.scotiabank.com/..." --job-id scot-001

Outputs:
    outputs/<company>_<role>_<date>_resume.md      tailored resume markdown
    outputs/<company>_<role>_<date>_cover.md       tailored cover letter
    outputs/<company>_<role>_<date>_brief.md       interview brief: top 5 predicted questions + model answers

All three outputs include a parse-log header showing which bullets from the bullet library were selected and why.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Preflight: collect missing requirements but defer hard-fail until main()
# so that --dry-run can run without the Anthropic SDK or API key.
# ---------------------------------------------------------------------------
_missing_api_key = not os.environ.get("ANTHROPIC_API_KEY")

try:
    import anthropic  # type: ignore
    _missing_anthropic = False
except ImportError:
    _missing_anthropic = True
    anthropic = None  # type: ignore

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
    HAVE_SCRAPING = True
except ImportError:
    HAVE_SCRAPING = False


def preflight_or_exit() -> None:
    missing = []
    if _missing_api_key:
        missing.append("ANTHROPIC_API_KEY environment variable is not set.")
    if _missing_anthropic:
        missing.append("`anthropic` package not installed.  Run: pip install anthropic")
    if not missing:
        return
    print("PREFLIGHT FAILED — fix these before running:", file=sys.stderr)
    for m in missing:
        print(f"  - {m}", file=sys.stderr)
    print("\nWindows PowerShell:", file=sys.stderr)
    print('  $env:ANTHROPIC_API_KEY = "sk-ant-..."', file=sys.stderr)
    print("  pip install anthropic requests beautifulsoup4", file=sys.stderr)
    print("\nmacOS / Linux bash:", file=sys.stderr)
    print("  export ANTHROPIC_API_KEY=sk-ant-...", file=sys.stderr)
    print("  pip install anthropic requests beautifulsoup4", file=sys.stderr)
    print("\nTip: run with --dry-run to build the prompt without calling the API.", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
MASTER_REPO = ROOT / "Saber_Ayatollahi_Master_Repository.md"
COVER_TEMPLATES = ROOT / "cover_letter_templates.md"
INTERVIEW_PREP = ROOT / "interview_prep.md"
TRACKER = ROOT / "job_tracker_data.json"
OUT_DIR = ROOT / "automation" / "outputs"

MODEL = os.environ.get("JD_TAILOR_MODEL", "claude-opus-4-7")  # override via env
FALLBACK_MODEL = os.environ.get("JD_TAILOR_FALLBACK", "claude-sonnet-4-6")


def slurp(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_tracker_entry(job_id: str) -> Optional[dict]:
    data = json.loads(slurp(TRACKER))
    for j in data.get("jobs", []):
        if j.get("id") == job_id:
            return j
    return None


def fetch_jd_from_url(url: str) -> str:
    if not HAVE_SCRAPING:
        raise RuntimeError("requests + beautifulsoup4 required for --jd-url. pip install requests beautifulsoup4")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Saber-JD-Tailor/1.0)"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # Strip script / style
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    # cap to something sensible
    return text[:40000]


def build_system_prompt() -> str:
    return (
        "You are a senior finance career strategist tailoring application materials for Saber Ayatollahi "
        "— CFA, dual MSc, 7+ years ALM/IRRBB/Moody's Analytics. You are disciplined about his narrative:\n"
        "- PRIMARY positioning: ALM / IRRBB / Model Governance.\n"
        "- SECONDARY positioning: Vendor-platform / Client Solutions.\n"
        "- RETIRED positioning (do not activate unless explicitly signaled by the JD): Portfolio Manager, "
        "Product Manager, Project/Program Manager, Valuations-as-primary, Asset Management Quant-as-primary.\n\n"
        "Rules:\n"
        "1. Every resume bullet MUST come from the tagged bullet library in the Master Repository (§5). "
        "   Pick bullets whose tags match the JD. Do NOT invent new accomplishments.\n"
        "2. Cover letter MUST be 300-350 words, 3 paragraphs, lead with regulatory hook or platform parallel.\n"
        "3. Year count is ~7.3 years. Do not say '8+' or '10+'.\n"
        "4. Sign-off authority framing: multi-asset institutional portfolios in the $5-25bn range per "
        "   engagement, cumulative ~$50bn book. Do not inflate.\n"
        "5. If the JD implies a skill Saber does not have (check §4 of Master Repo), do NOT claim it. "
        "   Address obliquely via adjacent skills.\n"
        "6. OSFI hook selection: E-23 for validation roles, B-12 for bank IRRBB roles, LAR 2026 for "
        "   liquidity roles, IFRS 17 for insurers, None for pensions and vendors.\n\n"
        "Output format: always return a single markdown document with three sections — PARSE LOG, "
        "RESUME, COVER LETTER, INTERVIEW BRIEF — in that order."
    )


def build_user_prompt(jd: str, company: str, role: str, tracker_entry: Optional[dict]) -> str:
    master_repo = slurp(MASTER_REPO)
    cover_templates = slurp(COVER_TEMPLATES)
    tracker_context = json.dumps(tracker_entry, indent=2) if tracker_entry else "(no tracker entry)"

    return f"""# TASK

Generate tailored application materials for the following role.

## Target company
{company}

## Target role
{role}

## Tracker entry (for context)
```json
{tracker_context}
```

## Job description
```
{jd}
```

## Master Repository (single source of truth for all claims)
```markdown
{master_repo}
```

## Cover letter templates
```markdown
{cover_templates}
```

# DELIVERABLES

Produce one markdown document with exactly these sections, in this order:

---

## § PARSE LOG
- Which positioning angle did you use: PRIMARY (ALM/IRRBB) or SECONDARY (Vendor-Platform) or AD-HOC (specify)?
- Which OSFI hook did you select, and why?
- Which bullets from the Master Repository tagged library did you select for the resume, and which did you drop? List each with its tag.
- Any risks you want Saber to be aware of before submitting (over-claims, gaps, interview-exposure).

---

## § RESUME

Produce a full resume in markdown, structured:
- Header (name + contacts + CFA + target role tagline — one line)
- Professional Summary (35-55 words, tailored)
- Professional Experience (Moody's, EY, Ortec) — bullets selected from the tagged library, filtered for JD relevance
- Education + CFA
- Technical Skills (from §4 Master Repo, pruned to what's relevant to the JD)
- Languages

Keep it a 1-2 page equivalent. No fake metrics. No bullets outside the library.

---

## § COVER LETTER

300-350 words, using Template A / B / C from `cover_letter_templates.md`. Fill the template slots. Replace `{{{{ }}}}` placeholders with specific content drawn from the JD and the Master Repo.

---

## § INTERVIEW BRIEF

- 5 most likely technical questions for this role, with 2-3 sentence model answers drawn from the Master Repo STAR stories and Interview Prep doc technical section.
- 3 questions Saber should ask the interviewer.
- 1 competency gap or risk area to prepare for.
"""


def call_claude(system: str, user: str, max_tokens: int = 16000) -> str:
    client = anthropic.Anthropic()
    for model in (MODEL, FALLBACK_MODEL):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        except Exception as e:
            print(f"WARN: model {model} failed: {e}", file=sys.stderr)
            continue
    raise RuntimeError("All models failed")


def main() -> int:
    ap = argparse.ArgumentParser(description="Tailor resume + cover letter for a single job.")
    ap.add_argument("--job-id", help="Tracker job id (e.g. scot-001) — will pull JD URL and context from tracker.")
    ap.add_argument("--jd-file", help="Path to a text file containing the JD.")
    ap.add_argument("--jd-url", help="URL of the JD to fetch.")
    ap.add_argument("--jd-text", help="JD text passed inline.")
    ap.add_argument("--company", help="Target company (override).")
    ap.add_argument("--role", help="Target role title (override).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the prompt and write it to outputs/<slug>_prompt.md, but do not call Claude. Useful for previewing before spending tokens.")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tracker_entry = load_tracker_entry(args.job_id) if args.job_id else None
    company = args.company or (tracker_entry and tracker_entry.get("company")) or "UnknownCompany"
    role = args.role or (tracker_entry and tracker_entry.get("title")) or "UnknownRole"

    jd: Optional[str] = None
    if args.jd_text:
        jd = args.jd_text
    elif args.jd_file:
        jd = Path(args.jd_file).read_text(encoding="utf-8")
    elif args.jd_url:
        jd = fetch_jd_from_url(args.jd_url)
    elif tracker_entry and tracker_entry.get("url"):
        try:
            jd = fetch_jd_from_url(tracker_entry["url"])
        except Exception as e:
            print(f"WARN: could not fetch JD from tracker URL: {e}", file=sys.stderr)

    if not jd:
        jd = (
            f"(JD not available — using tracker fit_notes as proxy.)\n\n"
            f"Company: {company}\nRole: {role}\n"
            f"Fit notes: {tracker_entry.get('fit_notes') if tracker_entry else ''}\n"
            f"Keywords: {tracker_entry.get('keywords') if tracker_entry else ''}\n"
        )

    system = build_system_prompt()
    user = build_user_prompt(jd, company, role, tracker_entry)

    stamp = datetime.now().strftime("%Y%m%d")
    safe_company = re.sub(r"[^a-zA-Z0-9]+", "_", company).strip("_")
    safe_role = re.sub(r"[^a-zA-Z0-9]+", "_", role)[:60].strip("_")

    if args.dry_run:
        prompt_path = OUT_DIR / f"{safe_company}_{safe_role}_{stamp}_prompt.md"
        prompt_path.write_text(
            f"# SYSTEM PROMPT\n\n{system}\n\n---\n\n# USER PROMPT\n\n{user}",
            encoding="utf-8",
        )
        print(f"[jd_tailor] DRY RUN — wrote prompt preview to {prompt_path}")
        print("[jd_tailor] Remove --dry-run to generate materials.")
        return 0

    # Real run — NOW we need the SDK + API key.
    preflight_or_exit()

    print(f"[jd_tailor] Tailoring for {company} / {role} ...", file=sys.stderr)
    result = call_claude(system, user)

    out_path = OUT_DIR / f"{safe_company}_{safe_role}_{stamp}.md"
    out_path.write_text(result, encoding="utf-8")

    print(f"[jd_tailor] Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
