#!/usr/bin/env python3
"""score_url.py — One-shot: paste a JD URL, get an LLM fit score.

Use when:
  - The scraper missed a role you care about (e.g., Citi jobs.citi.com listings
    that Phenom doesn't surface in its own search results).
  - Someone Slacked / emailed / tweeted a JD and you want a fit read before tailoring.
  - You want to score a role from a friend's employer whose ATS isn't in TARGETS.

What it does:
  1. Fetches the JD via fit_scorer.fetch_jd (cached to disk, same as the scan path).
  2. Infers company/title from the URL + page title when not supplied.
  3. Runs the scorer's Master-Repository-driven LLM scoring, with the full cache
     + retry + cost telemetry infrastructure the pipeline uses.
  4. Prints the verdict JSON to stdout. With --add-to-tracker, writes the result
     straight into job_tracker_data.json (backed up first) so you can track it.

Cost: ~$0.001 at Haiku, < 1 second wall time after JD fetch.

Usage:
    python score_url.py https://jobs.citi.com/job/mississauga/non-trading-market-risk-officer-vice-president/287/93536402784
    python score_url.py <url> --company Citi --title "VP Non-Trading Market Risk"
    python score_url.py <url> --add-to-tracker
    python score_url.py <url> --rescore          # bypass fit cache
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "automation" / "outputs"
TRACKER = ROOT / "data" / "job_tracker_data.json"

# Reuse the fit_scorer infrastructure
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_scorer  # noqa: E402


# Rough host → company map so we can infer when the user doesn't pass --company.
# Only companies that matter enough to special-case; everything else falls back to
# the hostname token.
_HOST_COMPANY_HINTS = {
    "jobs.citi.com": "Citi",
    "careers.osfi-bsif.gc.ca": "OSFI",
    "jobs.rbc.com": "RBC",
    "careers.scotiabank.com": "Scotiabank",
    "jobs.td.com": "TD Bank",
    "bmocareers.com": "BMO",
    "cibc.com": "CIBC",
    "careers.hoopp.com": "HOOPP",
    "careers.otpp.com": "Ontario Teachers' Pension Plan",
    "cppinvestments.com": "CPP Investments",
    "careers.blackrock.com": "BlackRock",
    "jobs.moodys.com": "Moody's",
    "careers.ey.com": "EY",
    "careers.spglobal.com": "S&P Global",
    "careers.msci.com": "MSCI",
    "careers.bloomberg.com": "Bloomberg",
    "careers.manulife.com": "Manulife",
    "careers.sunlife.com": "Sun Life",
}


def _infer_company(url: str, fallback: str = "") -> str:
    host = (urlparse(url).hostname or "").lower()
    # Exact host match
    if host in _HOST_COMPANY_HINTS:
        return _HOST_COMPANY_HINTS[host]
    # Suffix match (jobs.citi.com contains citi.com)
    for h, name in _HOST_COMPANY_HINTS.items():
        if host.endswith("." + h) or h.endswith("." + host):
            return name
    # Fallback: take the second-level domain, title-cased
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2].title()
    return fallback or "Unknown"


def _infer_title_from_jd(jd_text: str, url: str) -> str:
    """Best-effort title extraction. If the JD starts with a short line, it's
    usually the title."""
    if jd_text:
        for line in jd_text.splitlines():
            s = line.strip()
            if 8 <= len(s) <= 120 and not s.endswith("."):
                return s
    # Fallback: derive from URL slug
    path = urlparse(url).path
    # /job/mississauga/non-trading-market-risk-officer-vice-president/287/93536402784
    m = re.search(r"/job/[^/]+/([a-z0-9\-]+)/\d+", path)
    if m:
        return m.group(1).replace("-", " ").title()
    return "(unknown title)"


def _parse_sector_hint(company: str) -> str:
    """Approximate sector — used so the Master-Repo-driven scorer has sector context.
    Doesn't need to be perfect; scorer reads company directly too."""
    m = {
        "Citi": "US Banks (Toronto)",
        "RBC": "Canadian Big 6 Banks",
        "TD Bank": "Canadian Big 6 Banks",
        "BMO": "Canadian Big 6 Banks",
        "Scotiabank": "Canadian Big 6 Banks",
        "CIBC": "Canadian Big 6 Banks",
        "HOOPP": "Canadian Pension Funds",
        "CPP Investments": "Canadian Pension Funds",
        "Ontario Teachers' Pension Plan": "Canadian Pension Funds",
        "BlackRock": "US & Global Asset Managers",
        "Moody's": "Analytics & Risk Vendors",
        "S&P Global": "Analytics & Risk Vendors",
        "MSCI": "Analytics & Risk Vendors",
        "Bloomberg": "Analytics & Risk Vendors",
        "Manulife": "Canadian Insurers",
        "Sun Life": "Canadian Insurers",
        "OSFI": "Regulators & Crown",
        "EY": "Big 4 Risk Advisory",
    }
    return m.get(company, "")


def _add_to_tracker(url: str, role: dict, fit: dict) -> str | None:
    """Append a minimal tracker entry for this role. Idempotent on URL.

    Holds the tracker file lock for the entire read-check-write, so a
    concurrent UI or auto_promote writer can't land between our dedupe check
    and our append."""
    if not TRACKER.exists():
        print("[score_url] tracker file not found; skipping --add-to-tracker",
              file=sys.stderr)
        return None

    variants = fit.get("applicable_resume_variants") or []
    verdict = fit.get("fit_verdict") or "watch"
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    num_score = int(fit.get("fit_score") or 0)
    fit_category = ("High" if num_score >= 8
                    else "Medium" if num_score >= 6 else "Low")

    added_id: list[str | None] = [None]  # mutable closure capture

    def _mutator(tr):
        if not isinstance(tr, dict) or "jobs" not in tr:
            return tr
        if any(j.get("url") == url for j in tr.get("jobs", [])):
            # Dedupe inside the lock — caller sees added_id=None on return.
            print(f"[score_url] Already in tracker (url match): {url}",
                  file=sys.stderr)
            return tr
        new_id = f"manual-{stamp}"
        while any(j.get("id") == new_id for j in tr.get("jobs", [])):
            new_id += "a"
        tr["jobs"].append({
            "id": new_id,
            "company": role["company"],
            "title": role["title"],
            "sector": role.get("sector", ""),
            "url": url,
            "source": "manual_score_url",
            "tier": fit.get("tier", 3),
            "status": "Found" if verdict == "apply_now" else "Watch",
            "fit_score": fit_category,
            "fit_score_numeric": num_score,
            "fit_verdict": verdict,
            "fit_notes": (fit.get("summary") or "")
                         + " | Reasons: " + "; ".join(fit.get("top_3_reasons") or [])[:300],
            "resume_variants": variants,
            "primary_variant": variants[0] if variants else "",
            "urgency": "High" if verdict == "apply_now" else "Medium",
            "date_found": date.today().isoformat(),
            "next_action": (fit.get("top_3_reasons") or [""])[0][:160],
            "followup_schedule": {"next_due": None, "cadence_days": [3, 10, 21]},
            "outreach_log": [],
        })
        tr.setdefault("meta", {})["total_roles"] = len(tr["jobs"])
        added_id[0] = new_id
        return tr

    # Back up outside the lock (file copy does its own OS-level atomicity);
    # then mutate under the lock.
    bak = TRACKER.with_suffix(f".bak.score_url_{stamp}.json")
    shutil.copy2(TRACKER, bak)
    try:
        from safe_json import mutate_json  # type: ignore
        mutate_json(TRACKER, _mutator)
    except ImportError:
        tr = json.loads(TRACKER.read_text(encoding="utf-8"))
        _mutator(tr)
        TRACKER.write_text(json.dumps(tr, indent=2), encoding="utf-8")

    if added_id[0]:
        print(f"[score_url] Added {added_id[0]} to tracker. Backup at {bak.name}",
              file=sys.stderr)
    return added_id[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="JD URL to score")
    ap.add_argument("--company", help="Company name (inferred from URL if omitted)")
    ap.add_argument("--title", help="Role title (inferred from JD if omitted)")
    ap.add_argument("--sector", help="Sector (inferred from company if omitted)")
    ap.add_argument("--rescore", action="store_true",
                    help="Bypass fit cache; force a fresh LLM call")
    ap.add_argument("--add-to-tracker", action="store_true",
                    help="Append the result to job_tracker_data.json (with backup)")
    ap.add_argument("--json-only", action="store_true",
                    help="Emit only the fit JSON on stdout (for piping)")
    args = ap.parse_args()

    url = args.url.strip()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Try config file (same path as the UI + nightly refresh)
        cfg_path = Path.home() / ".applyagent" / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                k = cfg.get("anthropic_api_key")
                if k:
                    os.environ["ANTHROPIC_API_KEY"] = k
            except Exception:
                pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set (sidebar/env/config.json)",
              file=sys.stderr)
        return 2

    try:
        import anthropic  # noqa: F401
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 2

    # Fetch JD
    print(f"[score_url] Fetching JD: {url}", file=sys.stderr)
    jd = fit_scorer.fetch_jd(url)
    print(f"[score_url] JD length: {len(jd)} chars", file=sys.stderr)

    # Build role
    company = args.company or _infer_company(url)
    title = args.title or _infer_title_from_jd(jd, url)
    sector = args.sector or _parse_sector_hint(company)

    role = {
        "company": company,
        "title": title,
        "sector": sector,
        "location": "",
        "link": url,
        "source": "manual_score_url",
    }
    print(f"[score_url] Role: {company} — {title} ({sector or 'sector unknown'})",
          file=sys.stderr)

    # Bypass cache if rescore requested
    if args.rescore:
        cache = fit_scorer._cache_path_fit(url)
        if cache.exists():
            cache.unlink()
            print("[score_url] Cleared existing fit cache entry.", file=sys.stderr)

    # Score
    from anthropic import Anthropic
    client = Anthropic()
    fit = fit_scorer.score_with_llm(client, role, jd)

    # Output
    if args.json_only:
        print(json.dumps(fit, indent=2))
    else:
        print()
        print("=" * 70)
        print(f"  {company} — {title}")
        print("=" * 70)
        print(json.dumps(fit, indent=2))
        print()

    if args.add_to_tracker:
        _add_to_tracker(url, role, fit)

    return 0


if __name__ == "__main__":
    sys.exit(main())
