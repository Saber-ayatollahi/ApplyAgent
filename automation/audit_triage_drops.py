#!/usr/bin/env python3
"""Adversarial LLM audit of the stage-1 triage drops.

The rule triage (fit_scorer.rule_triage) is a CHEAP, title-only pre-filter: it
hard-drops roles whose titles lack a recognized risk/ALM/treasury/quant signal
so we don't spend LLM budget scoring obvious non-fits. But a keyword filter
can't enumerate every in-lane phrasing — bank acronyms (CCR, GRM), French-
Canadian titles (trésorerie, tarification), and novel wording slip through as
false-negatives.

This tool is the safety check on that filter. It re-applies the CURRENT triage
to a scan, then asks an LLM to independently second-guess EVERY dropped role
against the candidate profile — a recall-biased sweep (cheap model) optionally
confirmed by a stronger model. The output is the set of drops a model thinks
could actually be a fit: the false-negatives to review (or feed back into the
vocabulary / safety net).

It is deliberately separate from the scoring path: run it on demand after a
scan to be sure the funnel isn't quietly discarding good roles.

Usage:
    python automation/audit_triage_drops.py                 # latest scan, sweep+confirm
    python automation/audit_triage_drops.py --quick         # haiku sweep only (cheaper)
    python automation/audit_triage_drops.py --scan automation/outputs/worklist_triage.json
    python automation/audit_triage_drops.py --limit 100     # smoke-test on first 100

Writes triage_audit_<YYYYMMDD_HHMMSS>.{json,md} to automation/outputs/ and
prints the confirmed false-negatives. API spend is recorded in the cost ledger.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
sys.path.insert(0, str(ROOT / "ui"))

import fit_scorer  # noqa: E402
import jd_tailor    # noqa: E402

OUT_DIR = ROOT / "automation" / "outputs"

SYSTEM = """You audit a job-board pre-filter for ONE candidate. The pre-filter
DROPPED the titles below as 'not a fit'. Catch any DROP that was a MISTAKE.

CANDIDATE: senior finance QUANT (Manager -> Director/VP/Head). Core lane:
- model validation / model risk / MRM / model governance
- ALM, IRRBB, balance-sheet, FTP, interest-rate risk
- treasury, liquidity, funding, capital (regulatory/economic, stress testing, ICAAP, Basel, OSFI)
- market risk, fixed income, rates, derivatives/XVA valuation
- credit-risk modelling (PD/LGD/ECL, IFRS 9), loss forecasting
- quantitative risk analytics, scenario/stress modelling, actuarial / insurance investment (IFRS 17)
- enterprise risk, total-portfolio / investment risk
He is a quant / modeller / risk specialist, NOT a generalist.

CLEARLY OUT OF LANE (correct to drop):
- retail/branch banking, teller, customer service, personal banking
- sales, business development, marketing, wealth/investment advisor, relationship manager
- pure software/IT: developer, SWE, devops, data engineer, ML/cloud/security engineer, solutions architect, QA
- equity research, investment banking (M&A/coverage/origination)
- fund accounting / fund administration / operations / settlements
- pension administration / benefits / member services
- compliance, legal, audit-only, internal audit, HR, procurement
- generic project/product/program management, business analysis
- junior/intern/co-op/new-grad/student/rotational
- cyber/information-security risk, third-party/vendor risk, AML/fraud (risk-function but off-lane)

Judge on title + company ONLY. Bias toward RECALL: if a title PLAUSIBLY could be
an in-lane risk/ALM/treasury/quant role (incl. ambiguous acronyms or unusual
phrasing), FLAG it. Only omit titles that are CLEARLY out-of-lane or junior.

OUTPUT: a JSON array ONLY (no prose). For each title to FLAG:
{"n": <number>, "why": "<<=10 words why it might fit>"}. If none, output [].
"""


def _latest_triage() -> Path | None:
    files = sorted(OUT_DIR.glob("worklist_triage*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _all_rows(scan: dict) -> list[dict]:
    return (scan.get("results") or []) + (scan.get("triage_drops") or [])


def _current_drops(rows: list[dict]) -> list[dict]:
    """Re-apply the CURRENT rule triage so the audit reflects live code, not
    whatever vocab was active when the scan file was written."""
    out = []
    for r in rows:
        res = fit_scorer.rule_triage(r.get("title", ""), row=r)
        if not res.get("stage1_pass"):
            out.append(r)
    return out


def _dedup(rows: list[dict]) -> list[dict]:
    seen, uniq = set(), []
    for r in rows:
        k = ((r.get("title") or "").strip().lower(),
             (r.get("company") or "").strip().lower())
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def _extract_json(txt: str) -> list:
    m = re.search(r"\[.*\]", txt, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


def judge(rows: list[dict], model: str, fallback: str,
          batch: int = 50, max_tokens: int = 2000,
          label: str = "judge") -> list[dict]:
    """Run the LLM judge over rows in batches; return the flagged subset."""
    jd_tailor.MODEL, jd_tailor.FALLBACK_MODEL = model, fallback
    flagged: list[dict] = []
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        listing = "\n".join(
            f"{j+1}. {r.get('title','')} -- {r.get('company','')}"
            for j, r in enumerate(chunk))
        try:
            txt = jd_tailor.call_claude(SYSTEM, "Titles:\n" + listing,
                                        max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            print(f"  [{label}] batch {i//batch}: ERROR {e}", file=sys.stderr)
            continue
        for item in _extract_json(txt):
            n = item.get("n")
            if isinstance(n, int) and 1 <= n <= len(chunk):
                r = chunk[n - 1]
                flagged.append({"company": r.get("company", ""),
                                "title": r.get("title", ""),
                                "source": r.get("source", ""),
                                "link": r.get("link", ""),
                                "why": item.get("why", "")})
        print(f"  [{label}] {min(i+batch, len(rows))}/{len(rows)} "
              f"(flagged {len(flagged)})", file=sys.stderr)
    return flagged


def _write_report(confirmed: list[dict], meta: dict, stamp: str) -> tuple[Path, Path]:
    jpath = OUT_DIR / f"triage_audit_{stamp}.json"
    mpath = OUT_DIR / f"triage_audit_{stamp}.md"
    jpath.write_text(json.dumps({"meta": meta, "confirmed": confirmed},
                                indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"# Triage drop audit — {meta['generated_at']}",
        "",
        f"- Scan: `{meta['scan']}`",
        f"- Dropped roles audited: **{meta['audited']}** "
        f"(unique {meta['unique']})",
        f"- Sweep model: `{meta['sweep_model']}`"
        + (f" → confirm `{meta['confirm_model']}`" if meta.get("confirm_model")
           else " (no confirm)"),
        f"- Possible false-negatives: **{len(confirmed)}**",
        "",
        "| Company | Title | Source | Why it might fit |",
        "|---|---|---|---|",
    ]
    for c in confirmed:
        why = (c.get("why") or "").replace("|", "/")
        lines.append(f"| {c['company']} | {c['title']} | {c.get('source','')} "
                     f"| {why} |")
    mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jpath, mpath


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", type=Path, default=None,
                    help="triage scan json (default: latest worklist_triage*.json)")
    ap.add_argument("--sweep-model", default="claude-haiku-4-5")
    ap.add_argument("--confirm-model", default="claude-sonnet-5")
    ap.add_argument("--quick", action="store_true",
                    help="sweep only, skip the confirm pass (cheaper)")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--limit", type=int, default=0,
                    help="audit only the first N drops (smoke test)")
    args = ap.parse_args()

    import api_key  # noqa: WPS433  (ui/api_key.py)
    api_key.hydrate_env()

    scan_path = args.scan or _latest_triage()
    if not scan_path or not scan_path.exists():
        print("No triage scan found — run the scorer first.", file=sys.stderr)
        return 2
    scan = json.loads(scan_path.read_text(encoding="utf-8"))

    drops = _dedup(_current_drops(_all_rows(scan)))
    if args.limit:
        drops = drops[:args.limit]
    print(f"Auditing {len(drops)} current drops from {scan_path.name}",
          file=sys.stderr)

    t0 = time.time()
    flagged = judge(drops, args.sweep_model,
                    args.sweep_model, batch=args.batch, label="sweep")
    confirm_model = None
    confirmed = flagged
    if not args.quick and flagged:
        confirm_model = args.confirm_model
        confirmed = judge(flagged, args.confirm_model, args.sweep_model,
                          batch=max(20, args.batch // 2), label="confirm")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scan": scan_path.name,
        "audited": len(drops),
        "unique": len(drops),
        "sweep_model": args.sweep_model,
        "confirm_model": confirm_model,
        "sweep_flagged": len(flagged),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jpath, mpath = _write_report(confirmed, meta, stamp)

    print(f"\n=== {len(confirmed)} possible false-negative(s) "
          f"(of {len(drops)} drops) ===")
    for c in confirmed:
        print(f"  + [{c['company'][:16]:<16}] {c['title'][:52]:<52} | {c['why']}")
    print(f"\nReport: {mpath}\n        {jpath}")
    print("(API spend recorded in the cost ledger.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
