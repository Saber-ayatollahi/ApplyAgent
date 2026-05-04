#!/usr/bin/env python3
"""
fit_scorer.py — Smart fit-scoring for scan results.

Takes a scraper-output JSON (scan_v4.json) and scores every candidate against Saber's
Master Repository profile. Outputs a scored JSON with per-role:

  - fit_score (1-10)
  - fit_verdict ("apply_now" | "tailor_and_apply" | "watch" | "skip")
  - top_3_reasons (why this matches)
  - skill_gaps (what Saber lacks for this role)
  - osfi_hook (which OSFI angle to lead the cover letter with)
  - tier (1-4)
  - summary (30-word pitch of why to apply)

Uses a 2-stage pipeline:
  Stage 1: fast rule-based triage (title + company + keywords) → drop junk, cheap.
  Stage 2: LLM scoring for surviving candidates, with JD fetched, 1 call per role.

JD fetch is cached to disk (jd_cache/) so re-runs on the same scan are free.

Usage:
    python fit_scorer.py                              # score latest scan
    python fit_scorer.py --scan scan_v4.json
    python fit_scorer.py --scan scan_v4.json --limit 50
    python fit_scorer.py --dry-run                    # rule-stage only, no API calls
    python fit_scorer.py --only "Director" --only "VP"  # regex filter titles
    python fit_scorer.py --rescore                    # ignore cache, re-call LLM

Outputs:
    automation/outputs/scan_v4_scored.json            # full scored list
    automation/outputs/scan_v4_scored.md              # human-readable report
    automation/outputs/jd_cache/<url-hash>.txt        # cached JD text (persistent)
    automation/outputs/fit_cache/<url-hash>.json      # cached fit scores (persistent)
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    print("ERROR: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

try:
    import anthropic  # type: ignore
except ImportError:
    anthropic = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
JD_CACHE = OUT_DIR / "jd_cache"
FIT_CACHE = OUT_DIR / "fit_cache"
MASTER_REPO = ROOT / "Saber_Ayatollahi_Master_Repository.md"

MODEL = os.environ.get("FIT_SCORER_MODEL", "claude-sonnet-4-6")
FALLBACK_MODEL = "claude-haiku-4-5-20251001"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Stage 1 — rule-based triage.
# ---------------------------------------------------------------------------
NEG_TITLE_TERMS = [
    "intern", "co-op", "coop", "student", "graduate program",
    "retail branch", "teller", "branch manager", "customer service",
    "sales representative", "account executive", "marketing",
    "social media", "content writer", "cleaning", "janitor", "facilities",
    "receptionist", "administrative assistant", "mobile mortgage",
    "scientist, chemistry", "mechanical engineer", "electrical engineer",
    "web developer", "front end", "frontend", "ui/ux", "ux designer",
    "software developer (junior)", "sdet", "qa analyst",
]
POS_TITLE_TERMS = [
    "alm", "asset liability", "asset-liability",
    "irrbb", "interest rate risk",
    "model validation", "model risk", "model vetting", "model governance",
    "treasury", "balance sheet", "ftp", "funds transfer", "funding",
    "ldi", "liability driven", "liability-driven",
    "fixed income", "derivatives", "rates ", "rates,", "rates -",
    "liquidity risk", "market risk", "credit risk model",
    "risk analytics", "quantitative risk", "risk modelling", "risk modeling",
    "enterprise risk", "valuation", "portfolio risk",
    "aladdin", "ifrs 17", "ifrs17", "ifrs 9", "ifrs9",
    "actuarial", "reserve", "capital model", "stress test",
    "financial risk", "investment risk", "financial modeling", "financial modelling",
    "osfi", "basel", "b-12", "e-23", "lar", "lcr", "nsfr",
    "risk officer", "chief risk", "head of risk",
    "risk director", "risk vp",
]
LEVEL_TERMS = [
    "director", "senior director", "vp", "vice president", "avp",
    "head of", "principal", "managing director", "associate director",
    "senior vice", "senior manager", "sr manager", "sr. manager",
    "senior consultant", "chief",
]


def rule_triage(title: str) -> dict:
    """Return {stage1_pass: bool, rough_tier: int, rule_reasons: [..]}."""
    t = title.lower()
    reasons = []
    if any(n in t for n in NEG_TITLE_TERMS):
        return {"stage1_pass": False, "rough_tier": 5, "rule_reasons": ["negative_title_term"]}
    pos_hits = [p for p in POS_TITLE_TERMS if p in t]
    level_hits = [l for l in LEVEL_TERMS if l in t]
    # Must have at least one positive signal OR at least one target-level signal
    if not pos_hits and not level_hits:
        return {"stage1_pass": False, "rough_tier": 5,
                "rule_reasons": ["no_positive_or_level_signal"]}
    # Rough tiering
    has_dir = any(l in t for l in ("director", "vp", "vice president", "head of",
                                    "principal", "managing director", "associate director",
                                    "chief", "avp"))
    has_mgr = any(l in t for l in ("senior manager", "sr manager", "sr. manager"))
    if pos_hits and has_dir:
        rough = 1
    elif pos_hits and has_mgr:
        rough = 2
    elif pos_hits:
        rough = 3
    elif has_dir:
        rough = 3  # vague Director title — JD may still be on-profile
    else:
        rough = 4
    if pos_hits:
        reasons.append(f"positive_hits={pos_hits[:3]}")
    if level_hits:
        reasons.append(f"level_hits={level_hits[:2]}")
    return {"stage1_pass": True, "rough_tier": rough, "rule_reasons": reasons}


# ---------------------------------------------------------------------------
# JD fetching (cached to disk)
# ---------------------------------------------------------------------------
def _url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def fetch_jd(url: str, max_chars: int = 20000) -> str:
    """Fetch & strip the JD text. Cached."""
    JD_CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = JD_CACHE / f"{_url_hash(url)}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")[:max_chars]
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "button", "form"]):
            tag.decompose()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip()[:max_chars]
        cache_path.write_text(text, encoding="utf-8")
        return text
    except Exception as e:
        print(f"  [fetch_jd] err {url}: {e}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Stage 2 — LLM scoring (cached)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a hard-nosed senior finance career strategist assessing job fit for Saber Ayatollahi.\n"
    "\n"
    "Saber's profile (do not over-interpret — stick to this):\n"
    "- CFA charterholder. Dual MSc (Financial Modelling + Chemical Engineering).\n"
    "- ~7.3 years experience: Moody's Analytics (May 2022-present, Assistant Director Modelling Services),\n"
    "  EY (Sep 2021-Apr 2022, Sr Consultant IFRS 17/9), Ortec Finance (Feb 2019-Sep 2021, ALM/LDI).\n"
    "- Core competencies: ALM, IRRBB, Model Validation/Governance, Cash-Flow Projection, LDI,\n"
    "  Derivatives Pricing, Stochastic Scenario Generation, IFRS 17/9, Python, agentic AI workflows.\n"
    "- Formal sign-off authority on multi-asset institutional portfolios $5-25bn.\n"
    "- TARGET POSITIONING: (1) Primary = ALM/IRRBB/Model Governance Director/VP; \n"
    "  (2) Secondary = Vendor-Platform / Client Solutions (Aladdin, Bloomberg, MSCI, S&P Global).\n"
    "- RETIRED from outbound: pure Product Manager, Project Manager, generalist PM, pure asset-management\n"
    "  quant-research at boutique HFs. If a role is primarily in these lanes, it's NOT a fit.\n"
    "- Toronto-based, not relocating.\n"
    "\n"
    "Regulatory tailwinds relevant to this search:\n"
    "- OSFI E-23 Model Risk Management (eff. 2027-05-01, AI/ML scope).\n"
    "- OSFI B-12 IRRBB revision (Q1 2026 consultations).\n"
    "- OSFI LAR 2026 Liquidity Adequacy.\n"
    "- IFRS 17/9 (insurers/banks).\n"
    "\n"
    "You score each role. Return ONLY valid JSON matching the schema given, no prose, no markdown.\n"
)

SCHEMA = """{
  "fit_score": 1-10 integer,
  "fit_verdict": "apply_now" | "tailor_and_apply" | "watch" | "skip",
  "top_3_reasons": ["...", "...", "..."],
  "skill_gaps": ["..."],   // can be empty
  "osfi_hook": "E-23 Model Risk Management" | "B-12 IRRBB revision" | "LAR 2026 Liquidity Adequacy" | "IFRS 17" | "None",
  "tier": 1-4 integer (1=top tier apply-this-week; 4=watch-only),
  "summary": "30-word-ish pitch for Saber of why to apply (or why not)"
}"""


def _cache_path_fit(url: str) -> Path:
    FIT_CACHE.mkdir(parents=True, exist_ok=True)
    return FIT_CACHE / f"{_url_hash(url)}.json"


def score_with_llm(client, role: dict, jd_text: str) -> dict:
    """Call Claude with role+JD. Cache by URL hash."""
    cache = _cache_path_fit(role["link"])
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    user = (
        f"# ROLE\n"
        f"Company: {role['company']}\n"
        f"Sector: {role.get('sector', '')}\n"
        f"Title: {role['title']}\n"
        f"Location: {role.get('location', '')}\n"
        f"URL: {role['link']}\n"
        f"Source: {role.get('source', '')}\n"
        f"\n# JOB DESCRIPTION (may be partial)\n"
        f"{jd_text[:12000] if jd_text else '(JD not available — score from title/company only.)'}\n"
        f"\n# YOUR OUTPUT\n"
        f"Return ONLY valid JSON, no prose, matching this schema:\n"
        f"{SCHEMA}\n"
    )

    for model in (MODEL, FALLBACK_MODEL):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=800,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            # Extract first {...} block
            m = re.search(r"\{.*\}", text, flags=re.S)
            if not m:
                continue
            parsed = json.loads(m.group(0))
            # Defensive: coerce fields
            parsed.setdefault("fit_score", 1)
            parsed.setdefault("fit_verdict", "skip")
            parsed.setdefault("top_3_reasons", [])
            parsed.setdefault("skill_gaps", [])
            parsed.setdefault("osfi_hook", "None")
            parsed.setdefault("tier", 4)
            parsed.setdefault("summary", "")
            cache.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            return parsed
        except Exception as e:
            print(f"  [score_llm] {model} failed: {e}", file=sys.stderr)
            continue
    return {"fit_score": 0, "fit_verdict": "skip", "top_3_reasons": ["LLM_failure"],
            "skill_gaps": [], "osfi_hook": "None", "tier": 4, "summary": "LLM scoring failed."}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default="scan_v4.json",
                    help="Filename in automation/outputs/ of the scraper output to score.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Limit to N roles after stage 1 triage (0=all).")
    ap.add_argument("--only", action="append", default=[],
                    help="Only score titles matching this regex (can pass multiple).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Stage 1 only; don't call LLM.")
    ap.add_argument("--rescore", action="store_true",
                    help="Ignore fit cache; re-call LLM for every role.")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="Parallel LLM calls (default 4).")
    args = ap.parse_args()

    scan_path = OUT_DIR / args.scan
    if not scan_path.exists():
        print(f"ERROR: {scan_path} not found", file=sys.stderr)
        return 1

    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    roles = scan.get("results", [])
    print(f"[fit_scorer] Loaded {len(roles)} roles from {scan_path.name}", file=sys.stderr)

    # Stage 1 — rule triage
    triaged = []
    skipped = 0
    for r in roles:
        tri = rule_triage(r["title"])
        r["_triage"] = tri
        if not tri["stage1_pass"]:
            skipped += 1
            continue
        if args.only and not any(re.search(p, r["title"], re.I) for p in args.only):
            continue
        triaged.append(r)

    print(f"[fit_scorer] Stage 1: {len(triaged)} pass / {skipped} drop / "
          f"{len(roles) - len(triaged) - skipped} filtered by --only", file=sys.stderr)

    if args.limit:
        triaged = triaged[: args.limit]
        print(f"[fit_scorer] Limiting to {len(triaged)} for this run.", file=sys.stderr)

    if args.dry_run:
        out = {"scan_date": scan.get("scan_date"), "stage1_only": True,
               "total_input": len(roles), "stage1_passed": len(triaged),
               "results": triaged}
        (OUT_DIR / (Path(args.scan).stem + "_scored.json")).write_text(
            json.dumps(out, indent=2), encoding="utf-8")
        print(f"[fit_scorer] DRY RUN complete. Wrote {args.scan} "
              f"-> {Path(args.scan).stem}_scored.json", file=sys.stderr)
        return 0

    # Stage 2 — LLM scoring (parallel)
    if anthropic is None:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    if args.rescore:
        # Nuke fit cache for each triaged role
        for r in triaged:
            p = _cache_path_fit(r["link"])
            if p.exists():
                p.unlink()

    client = anthropic.Anthropic()
    t0 = time.time()

    def score_one(r):
        jd = fetch_jd(r["link"])
        r["_jd_len"] = len(jd)
        r["fit"] = score_with_llm(client, r, jd)
        return r

    scored = []
    # Cache hits are instant; real LLM calls parallelize.
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(score_one, r) for r in triaged]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            scored.append(r)
            if i % 25 == 0 or i == len(futures):
                print(f"  [fit_scorer] scored {i}/{len(futures)} "
                      f"({(time.time() - t0) / 60:.1f} min)", file=sys.stderr)

    # Sort by (fit_score desc, tier asc)
    scored.sort(key=lambda r: (-r["fit"].get("fit_score", 0), r["fit"].get("tier", 4)))

    out = {
        "scan_date": scan.get("scan_date"),
        "scored_at": datetime.utcnow().isoformat() + "Z",
        "total_input": len(roles),
        "stage1_passed": len(triaged),
        "stage2_scored": len(scored),
        "results": scored,
    }
    json_out = OUT_DIR / (Path(args.scan).stem + "_scored.json")
    json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Human-readable MD
    md_lines = [
        f"# Fit-Scored Report -- {scan.get('scan_date')}",
        "",
        f"- Scan source: `{args.scan}`",
        f"- Total candidates input: {len(roles)}",
        f"- Passed rule-triage: {len(triaged)}",
        f"- LLM-scored: {len(scored)}",
        f"- Runtime: {(time.time() - t0) / 60:.1f} min",
        "",
        "## Verdict distribution",
        "",
    ]
    by_verdict = {}
    for r in scored:
        v = r["fit"].get("fit_verdict", "?")
        by_verdict[v] = by_verdict.get(v, 0) + 1
    for v, n in sorted(by_verdict.items(), key=lambda x: -x[1]):
        md_lines.append(f"- **{v}**: {n}")
    md_lines += ["", "## Top 40 by fit score", "",
                 "| Score | Verdict | Tier | Sector | Company | Title | OSFI hook | Summary | Link |",
                 "|---|---|---|---|---|---|---|---|---|"]
    for r in scored[:40]:
        f = r["fit"]
        title = r["title"].replace("|", "/")
        summary = f.get("summary", "").replace("|", "/").replace("\n", " ")[:140]
        md_lines.append(
            f"| {f.get('fit_score')} | {f.get('fit_verdict')} | {f.get('tier')} | "
            f"{r.get('sector', '')} | {r['company']} | {title} | "
            f"{f.get('osfi_hook', '')} | {summary} | [open]({r['link']}) |"
        )

    md_out = OUT_DIR / (Path(args.scan).stem + "_scored.md")
    md_out.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[fit_scorer] Wrote {json_out}", file=sys.stderr)
    print(f"[fit_scorer] Wrote {md_out}", file=sys.stderr)
    print(f"[fit_scorer] Verdict counts: {by_verdict}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
