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

# Deterministic pre-analysis: JD → skill hits, variants, bullet shortlist.
# Loaded lazily so --dry-run still works without YAML sources available.
try:
    from jd_skill_extract import (  # type: ignore
        extract as _jd_extract,
        rank_bullets as _rank_bullets,
        format_bullet_shortlist as _format_bullet_shortlist,
    )
except ImportError:
    try:
        from .jd_skill_extract import (  # type: ignore
            extract as _jd_extract,
            rank_bullets as _rank_bullets,
            format_bullet_shortlist as _format_bullet_shortlist,
        )
    except Exception:
        _jd_extract = None           # type: ignore
        _rank_bullets = None         # type: ignore
        _format_bullet_shortlist = None  # type: ignore

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
    HAVE_SCRAPING = True
except ImportError:
    HAVE_SCRAPING = False

# Cost guard + ledger + central error log + API preflight. All optional —
# tailor still runs without them (legacy behavior) but with them we get:
#   - daily/per-run USD cap → no $20 surprise from a runaway tailor
#   - lifetime ledger entries → sidebar "lifetime spend" reflects tailor cost
#   - api_preflight → fail fast on revoked key / exhausted credits
#   - error_log → silent SDK exceptions become visible
try:
    from cost_guard import CostGuard as _CostGuard  # type: ignore
except ImportError:
    try:
        from .cost_guard import CostGuard as _CostGuard  # type: ignore
    except Exception:
        _CostGuard = None  # type: ignore

try:
    from cost_ledger import record as _ledger_record  # type: ignore
except ImportError:
    try:
        from .cost_ledger import record as _ledger_record  # type: ignore
    except Exception:
        _ledger_record = None  # type: ignore

try:
    from api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
except ImportError:
    try:
        from .api_preflight import preflight_or_exit as _cli_preflight  # type: ignore
    except Exception:
        _cli_preflight = None  # type: ignore

try:
    from error_log import log_error as _log_error  # type: ignore
except ImportError:
    try:
        from .error_log import log_error as _log_error  # type: ignore
    except Exception:
        _log_error = None  # type: ignore

# Per-1M-token prices (USD) — same source as fit_scorer._MODEL_PRICES.
# Tailor uses Opus by default, which is the most expensive model available.
_MODEL_PRICES = {
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 1.0,  "output": 5.0},
    "claude-haiku-4-5":          {"input": 1.0,  "output": 5.0},
}


def _estimate_cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
    p = _MODEL_PRICES.get(model) or _MODEL_PRICES.get(model.split("-2025")[0])
    if not p:
        return 0.0
    return (in_tokens * p["input"] + out_tokens * p["output"]) / 1_000_000


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
MASTER_REPO = ROOT / "docs" / "Saber_Ayatollahi_Master_Repository.md"
COVER_TEMPLATES = ROOT / "docs" / "cover_letter_templates.md"
INTERVIEW_PREP = ROOT / "docs" / "interview_prep.md"
TRACKER = ROOT / "data" / "job_tracker_data.json"
OUT_DIR = ROOT / "automation" / "outputs"
# Tailor outputs land in their own subdir so the file pickers (Scan history,
# scan_*.json globs, etc.) don't surface them as scan files. The UI glob
# for "draft ready" badges checks here first, then falls back to OUT_DIR
# for legacy *.md files written before this split.
TAILORED_DIR = OUT_DIR / "tailored"

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
    """Fetch + clean JD. Delegates to fit_scorer.fetch_jd so the tailor sees the
    same boilerplate-stripped, section-aware text the scorer already cached.
    Falls back to a minimal in-place implementation if that module isn't
    importable (e.g. tailor invoked standalone in a stripped-down env)."""
    if not HAVE_SCRAPING:
        raise RuntimeError("requests + beautifulsoup4 required for --jd-url. pip install requests beautifulsoup4")
    try:
        # Reuse the scorer's cleaner so cover letters get the same high-signal text
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fit_scorer import fetch_jd as _scorer_fetch_jd  # type: ignore
        # Tailor wants more context than the scorer (6K) — use a larger window
        return _scorer_fetch_jd(url, max_chars=15000)
    except Exception as e:
        # Fallback: minimal cleaner
        print(f"  [tailor] falling back to local JD fetch ({e})", file=sys.stderr)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Saber-JD-Tailor/1.0)"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
        return text[:40000]


def build_system_prompt() -> str:
    """Build the tailor system prompt.

    The Master Repository (~35KB) and cover-letter templates live in the
    SYSTEM message, not the user message, so prompt caching reuses them
    across every tailor call within the cache TTL. Before this change,
    each call paid full Master-Repo input tokens — measurable spend for
    sessions with multiple tailors.
    """
    master_repo = slurp(MASTER_REPO)
    cover_templates = slurp(COVER_TEMPLATES)
    rules = (
        "You are a senior finance career strategist tailoring application materials for Saber Ayatollahi "
        "— CFA, dual MSc, 7+ years ALM/IRRBB/Moody's Analytics. You are disciplined about his narrative:\n"
        "- PRIMARY positioning: ALM / IRRBB / Model Governance.\n"
        "- SECONDARY positioning: Vendor-platform / Client Solutions.\n"
        "- RETIRED positioning (do not activate unless explicitly signaled by the JD): Portfolio Manager, "
        "Product Manager, Project/Program Manager, Valuations-as-primary, Asset Management Quant-as-primary.\n\n"
        "Rules:\n"
        "1. Every resume bullet MUST come from the tagged bullet library in the Master Repository (§5). "
        "   Pick bullets whose tags match the JD. Do NOT invent new accomplishments.\n"
        "2. Cover letter MUST be 300-350 words, 3 paragraphs. OPEN on a concrete capability claim tied to\n"
        "   the specific employer/role (e.g., sign-off authority on a comparable book, a platform parallel,\n"
        "   a relevant EY/Moody's/Ortec engagement). Do NOT lead with regulatory-calendar narratives\n"
        "   (OSFI E-23 / B-12 / LAR / IFRS 17 etc.) — those read as generic and are explicitly de-emphasized.\n"
        "3. Year count is ~7.3 years. Do not say '8+' or '10+'.\n"
        "4. Sign-off authority framing: multi-asset institutional portfolios in the $5-25bn range per "
        "   engagement, cumulative ~$50bn book. Do not inflate.\n"
        "5. If the JD implies a skill Saber does not have (check §4 of Master Repo), do NOT claim it. "
        "   Address obliquely via adjacent skills.\n\n"
        "Output format: always return a single markdown document with three sections — PARSE LOG, "
        "RESUME, COVER LETTER, INTERVIEW BRIEF — in that order."
    )
    return (
        f"{rules}\n\n"
        "# Master Repository (single source of truth for all claims)\n\n"
        f"```markdown\n{master_repo}\n```\n\n"
        "# Cover letter templates\n\n"
        f"```markdown\n{cover_templates}\n```\n"
    )


def _deterministic_preamble(jd: str) -> str:
    """Build the deterministic analysis + ranked bullet shortlist that goes
    into the user prompt ABOVE the full Master Repo. The LLM is instructed
    to prefer the shortlist when assembling the resume but may still draw
    from §5 of the repo for secondary fits.

    Returns an empty string when the JD is missing or the extractor is not
    available (e.g. tests running without PyYAML)."""
    if not jd or _jd_extract is None:
        return ""
    try:
        ex = _jd_extract(jd)
    except Exception as e:
        print(f"  [tailor] deterministic extract failed: {e}", file=sys.stderr)
        return ""
    blocks: list[str] = [ex.as_prompt_block()]
    if _rank_bullets is not None and _format_bullet_shortlist is not None:
        try:
            ranked = _rank_bullets(ex, limit=18)
            blocks.append(_format_bullet_shortlist(ranked))
        except Exception as e:
            print(f"  [tailor] bullet ranking failed: {e}", file=sys.stderr)
    return "\n\n".join(blocks)


def build_user_prompt(jd: str, company: str, role: str, tracker_entry: Optional[dict]) -> str:
    # Master Repo and cover-letter templates live in the SYSTEM prompt
    # (cached) — do not duplicate them here.
    tracker_context = json.dumps(tracker_entry, indent=2) if tracker_entry else "(no tracker entry)"
    det_preamble = _deterministic_preamble(jd)

    # If deterministic extract produced output, instruct the LLM to ground
    # the PARSE LOG in it and prefer the pre-ranked bullet shortlist when
    # selecting resume bullets. Falls back silently if preamble is empty.
    det_instructions = ""
    if det_preamble:
        det_instructions = (
            "\n\nIMPORTANT: Read the `## Deterministic JD analysis` and "
            "`## Pre-ranked bullet shortlist` blocks below FIRST. They are "
            "computed deterministically from the Master Repository YAMLs — trust "
            "them. Prefer bullets from the shortlist (in rank order) when "
            "assembling the resume. Cite bullet IDs in your PARSE LOG. You may "
            "still pull additional bullets from §5 of the Master Repository if "
            "a narrative gap requires it, but NEVER invent new bullets."
        )

    return f"""# TASK

Generate tailored application materials for the following role.{det_instructions}

## Target company
{company}

## Target role
{role}

## Tracker entry (for context)
```json
{tracker_context}
```

{det_preamble}

## Job description
```
{jd}
```

# DELIVERABLES

Produce one markdown document with exactly these sections, in this order:

---

## § PARSE LOG
- Which positioning angle did you use: PRIMARY (ALM/IRRBB) or SECONDARY (Vendor-Platform) or AD-HOC (specify)?
- Which capability/experience hook did you open the cover letter on, and why? (Do NOT default to regulatory-calendar framing.)
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


def call_claude(system: str, user: str, max_tokens: int = 16000,
                cost_guard=None) -> str:
    """Call Claude with cost telemetry, ledger recording, and optional cost guard.

    Tailor runs at Opus pricing (default) — a single call is up to ~$1
    worst-case. Without ledger recording, the sidebar 'lifetime spend'
    widget would silently undercount. Without a cost guard, a misbehaving
    tracker entry could trigger several tailors via auto-tailor and burn
    real money. Both wrappers are optional so legacy importers still work.
    """
    client = anthropic.Anthropic()
    last_err: Exception | None = None
    for model in (MODEL, FALLBACK_MODEL):
        if cost_guard is not None and cost_guard.exceeded():
            print(f"  [tailor] cost_guard tripped before {model}: "
                  f"{cost_guard.reason}", file=sys.stderr)
            raise RuntimeError(f"cost_guard: {cost_guard.reason}")
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            )
            # Cost accounting BEFORE returning so a downstream parser failure
            # doesn't drop spend on the floor. cost_guard.record runs first
            # because it's the in-process bound; ledger.record is the
            # cross-process record. Either order works now that
            # CostGuard.exceeded uses max(ledger, run_spend) instead of summing.
            try:
                usage = resp.usage
                in_t = getattr(usage, "input_tokens", 0) or 0
                out_t = getattr(usage, "output_tokens", 0) or 0
                cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                cost = _estimate_cost_usd(model, in_t, out_t)
                if cost_guard is not None and cost > 0:
                    cost_guard.record(cost)
                if _ledger_record is not None:
                    try:
                        _ledger_record(
                            model=model, in_tokens=in_t, out_tokens=out_t,
                            cost_usd=cost, cache_create=cache_create,
                            cache_read=cache_read, cache_hit=False,
                        )
                    except Exception as _le:
                        if _log_error is not None:
                            _log_error("ledger_record", _le, module="jd_tailor")
                print(f"  [tailor] {model} cost ${cost:.3f} "
                      f"(in={in_t}, out={out_t}, cache_read={cache_read})",
                      file=sys.stderr)
            except Exception:
                # Telemetry is best-effort; never lose the response over it.
                pass
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        except Exception as e:
            last_err = e
            if _log_error is not None:
                _log_error("tailor_llm", e, module="jd_tailor",
                           extra={"model": model})
            print(f"WARN: model {model} failed: {e}", file=sys.stderr)
            continue
    raise RuntimeError(f"All models failed. Last error: {last_err}")


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

    TAILORED_DIR.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        prompt_path = TAILORED_DIR / f"{safe_company}_{safe_role}_{stamp}_prompt.md"
        prompt_path.write_text(
            f"# SYSTEM PROMPT\n\n{system}\n\n---\n\n# USER PROMPT\n\n{user}",
            encoding="utf-8",
        )
        print(f"[jd_tailor] DRY RUN — wrote prompt preview to {prompt_path}")
        print("[jd_tailor] Remove --dry-run to generate materials.")
        return 0

    # Real run — NOW we need the SDK + API key.
    preflight_or_exit()

    # API preflight: catch revoked keys + exhausted credits BEFORE building
    # the prompt and burning a 50KB upload. Bypass with APPLYAGENT_SKIP_PREFLIGHT=1.
    # The billing preflight inside check() always uses Haiku (cheap), so we
    # don't need to override the model here.
    if _cli_preflight is not None:
        _cli_preflight(module="jd_tailor")

    # Cost guard: tailor runs Opus by default — a single call can be ~$1.
    # Without this, a runaway batch (e.g. auto-promote spawning many tailors)
    # could burn real money before anyone notices. Honors the same env caps
    # as fit_scorer (COST_GUARD_DAILY_CAP_USD / COST_GUARD_PER_RUN_CAP_USD).
    guard = None
    if _CostGuard is not None:
        guard = _CostGuard.from_env()
        print(f"[cost_guard] {guard.summary()}", file=sys.stderr)
        guard.preflight_or_exit()

    print(f"[jd_tailor] Tailoring for {company} / {role} ...", file=sys.stderr)
    result = call_claude(system, user, cost_guard=guard)

    out_path = TAILORED_DIR / f"{safe_company}_{safe_role}_{stamp}.md"
    out_path.write_text(result, encoding="utf-8")

    print(f"[jd_tailor] Wrote: {out_path}")

    # Quality gate: scan paragraph 1 of the cover letter for banned regulatory
    # framing and rescue with one Sonnet call if needed. Advisory — never
    # blocks the tailor's exit code. See automation/tailor_quality_gate.py.
    try:
        from tailor_quality_gate import gate_check, gate_rescue, _atomic_write_text, _backup_path, _append_log  # type: ignore
        from datetime import timezone as _qg_tz
        _qg_md = out_path.read_text(encoding="utf-8")
        _qg_res = gate_check(_qg_md)
        _qg_ts = datetime.now(_qg_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if _qg_res.clean:
            print("[gate] OK")
            _append_log({"ts": _qg_ts, "file": str(out_path), "violations": [],
                         "action": "clean", "cost": 0.0, "via": "jd_tailor"})
        else:
            print(f"[gate] VIOLATIONS: {', '.join(_qg_res.violations)}",
                  file=sys.stderr)
            try:
                _qg_bak = _backup_path(out_path)
                import shutil as _qg_shutil
                _qg_shutil.copy2(out_path, _qg_bak)
                _qg_new, _qg_cost = gate_rescue(_qg_md, _qg_res)
                _atomic_write_text(out_path, _qg_new)
                print(f"[gate] RESCUED — rewrote paragraph 1 (cost ${_qg_cost:.4f})")
                _append_log({"ts": _qg_ts, "file": str(out_path),
                             "violations": _qg_res.violations,
                             "action": "rescued", "cost": round(_qg_cost, 6),
                             "backup": str(_qg_bak), "via": "jd_tailor"})
            except Exception as _qg_e:
                print(f"[gate] WARN: rescue failed ({_qg_e}); original left in place",
                      file=sys.stderr)
                _append_log({"ts": _qg_ts, "file": str(out_path),
                             "violations": _qg_res.violations,
                             "action": "warned", "cost": 0.0,
                             "warn": str(_qg_e)[:200], "via": "jd_tailor"})
    except Exception as _qg_outer:
        print(f"[gate] WARN: quality gate skipped ({_qg_outer})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
