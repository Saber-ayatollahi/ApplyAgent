"""visa_tagger.py — visa/sponsorship intelligence for the job pipeline.

Two independent signals, combined into one row tag:

1. JD-TEXT signal (free, per-posting): US postings frequently state their
   sponsorship posture outright ("unable to sponsor", "must be authorized to
   work in the US", or conversely "sponsorship available"). Regex detection
   over the fetched JD text.

2. EMPLOYER H-1B HISTORY (public record, per-company): the USCIS H-1B
   Employer Data Hub publishes every petitioner's approval counts. A firm
   with a filing history has an immigration function — the best available
   proxy for visa-friendliness. TN (Saber's actual route — Canadian citizen,
   Economist/Statistician framing) has NO public filings because border TNs
   never touch USCIS; H-1B history is used as the willingness proxy, and the
   JD-text signal catches the explicit "no sponsorship" blockers that ALSO
   usually preclude TN support.

Data file: data/h1b_sponsors.json
  - seeded with reputational entries (well-documented major filers), and
  - refreshable from a real Data Hub CSV export via:
        python automation/visa_tagger.py ingest <datahub_export.csv>
    Export source: https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
    (choose a fiscal year, export all employers, or filter to finance NAICS 52).

Usage as a library:
    from visa_tagger import jd_sponsorship_signal, employer_h1b, visa_tag
    visa_tag(company="BlackRock", jd_text=...)  ->
        {"jd_signal": "no_sponsorship|sponsorship_stated|silent",
         "h1b_history": "known_filer|seed_known_filer|none_on_record",
         "verdict": "blocked|friendly|likely_friendly|unknown"}

CLI:
    python automation/visa_tagger.py query "BlackRock"
    python automation/visa_tagger.py scan-jd path/to/jd.txt
    python automation/visa_tagger.py ingest datahub.csv --min-approvals 5
    python automation/visa_tagger.py --smoke
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "h1b_sponsors.json"

# Canonicalize via the repo's brand_aliases when available (package or bare),
# else a lowercase-strip fallback so the module works standalone.
try:
    from . import brand_aliases as _ba  # type: ignore
except Exception:  # bare-script / standalone context
    try:
        import brand_aliases as _ba  # type: ignore
    except Exception:
        _ba = None


def _canon(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        return ""
    if _ba is not None:
        try:
            return _ba.canonical_brand(name.strip()).lower()
        except Exception:
            pass
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


# ── 1. JD-text signal ────────────────────────────────────────────────────
# Order matters: NO-sponsorship phrasings are checked first because posts
# like "we are unable to provide visa sponsorship" also contain the token
# "visa sponsorship".
_NO_SPONSOR = [
    r"without (?:the need for )?(?:visa )?sponsorship",
    r"(?:unable|not able) to (?:provide|offer|support) (?:visa |work )?sponsorship",
    r"(?:will|can|do(?:es)?) ?not (?:provide|offer|support|be providing) (?:visa |work |h-?1b )?sponsorship",
    r"sponsorship (?:is )?not (?:available|offered|provided)",
    r"no (?:visa |work |h-?1b )?sponsorship",
    r"cannot sponsor",
    r"will not sponsor",
    r"must (?:be|currently be) (?:legally )?(?:authorized|eligible) to work",
    r"(?:existing|current) (?:right|authorization) to work",
    r"without (?:company )?sponsorship now or in the future",
]
_YES_SPONSOR = [
    r"sponsorship (?:is )?(?:available|offered|provided)",
    r"(?:will|able to|happy to|can) (?:provide|offer|support) (?:visa |work |h-?1b )?sponsorship",
    r"h-?1b (?:transfer|sponsorship|cap)",
    r"visa sponsorship",
    r"immigration (?:support|assistance|sponsorship)",
    r"tn (?:visa|status)",
    r"work (?:visa|permit) (?:support|assistance)",
]
_NO_RX = [re.compile(p, re.IGNORECASE) for p in _NO_SPONSOR]
_YES_RX = [re.compile(p, re.IGNORECASE) for p in _YES_SPONSOR]


def jd_sponsorship_signal(jd_text: str | None) -> str:
    """'no_sponsorship' | 'sponsorship_stated' | 'silent' for a JD's text."""
    t = jd_text or ""
    if not t.strip():
        return "silent"
    if any(rx.search(t) for rx in _NO_RX):
        return "no_sponsorship"
    if any(rx.search(t) for rx in _YES_RX):
        return "sponsorship_stated"
    return "silent"


# ── 2. Employer H-1B history ─────────────────────────────────────────────
def _load() -> dict:
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "employers": {}}


def employer_h1b(company: str, db: dict | None = None) -> dict | None:
    """Return the employer record (or None). Matches on canonical key first,
    then substring of stored display names (Data Hub names are long-form
    legal entities: 'BLACKROCK FINANCIAL MANAGEMENT INC')."""
    db = db or _load()
    key = _canon(company)
    if not key:
        return None
    emp = db.get("employers", {})
    if key in emp:
        return emp[key]
    for k, rec in emp.items():
        disp = str(rec.get("name", "")).lower()
        if key and (key in disp or k in _canon(disp)):
            return rec
    return None


def visa_tag(company: str = "", jd_text: str | None = None,
             db: dict | None = None) -> dict:
    """Combined per-row verdict.

    blocked          — JD explicitly rules sponsorship out (usually rules TN
                       support out too; treat as US-remote/EOR-only at best)
    friendly         — JD states sponsorship, or silent JD + known filer
    likely_friendly  — silent JD + seed-level (reputational) filer
    unknown          — silent JD, no record
    """
    sig = jd_sponsorship_signal(jd_text)
    rec = employer_h1b(company, db=db) if company else None
    hist = ("known_filer" if rec and rec.get("basis") == "uscis_data_hub"
            else "seed_known_filer" if rec
            else "none_on_record")
    if sig == "no_sponsorship":
        verdict = "blocked"
    elif sig == "sponsorship_stated" or hist == "known_filer":
        verdict = "friendly"
    elif hist == "seed_known_filer":
        verdict = "likely_friendly"
    else:
        verdict = "unknown"
    return {"jd_signal": sig, "h1b_history": hist, "verdict": verdict}


# ── ingest: USCIS Data Hub CSV → data/h1b_sponsors.json ─────────────────
def ingest(csv_path: str, min_approvals: int = 1) -> int:
    """Merge a Data Hub export into the db. Handles the Hub's column names
    across year formats ('Employer (Petitioner) Name', 'Initial Approval',
    'Continuing Approval'). Rows below min_approvals are skipped."""
    db = _load()
    emp = db.setdefault("employers", {})
    added = 0
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        rdr = csv.DictReader(f)
        cols = {c.lower().strip(): c for c in (rdr.fieldnames or [])}

        def _col(*names):
            for n in names:
                for lc, orig in cols.items():
                    if n in lc:
                        return orig
            return None

        c_name = _col("employer", "petitioner")
        c_init = _col("initial approval")
        c_cont = _col("continuing approval")
        c_year = _col("fiscal year")
        if not c_name:
            raise SystemExit(f"unrecognized CSV format; columns: {rdr.fieldnames}")
        for row in rdr:
            name = (row.get(c_name) or "").strip()
            if not name:
                continue

            def _n(c):
                try:
                    return int(str(row.get(c) or "0").replace(",", ""))
                except ValueError:
                    return 0
            approvals = _n(c_init) + _n(c_cont)
            if approvals < min_approvals:
                continue
            key = _canon(name)
            rec = emp.get(key) or {"name": name, "approvals": 0}
            rec["name"] = name
            rec["approvals"] = int(rec.get("approvals") or 0) + approvals
            rec["basis"] = "uscis_data_hub"
            if c_year and row.get(c_year):
                rec["latest_fy"] = str(row[c_year])
            emp[key] = rec
            added += 1
    db["updated"] = date.today().isoformat()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(db, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    print(f"ingested {added} employer rows (min_approvals={min_approvals}) "
          f"-> {DATA_PATH}")
    return 0


# ── CLI / smoke ──────────────────────────────────────────────────────────
def _smoke() -> int:
    assert jd_sponsorship_signal(
        "Applicants must be legally authorized to work in the United States "
        "without sponsorship now or in the future.") == "no_sponsorship"
    assert jd_sponsorship_signal(
        "We are unable to provide visa sponsorship for this position."
    ) == "no_sponsorship"
    assert jd_sponsorship_signal(
        "H-1B sponsorship available for qualified candidates."
    ) == "sponsorship_stated"
    assert jd_sponsorship_signal(
        "This role offers visa sponsorship and relocation support."
    ) == "sponsorship_stated"
    assert jd_sponsorship_signal("We value teamwork and Python.") == "silent"
    assert jd_sponsorship_signal(None) == "silent"
    # combined verdicts
    db = {"employers": {"blackrock": {"name": "BLACKROCK INC",
                                      "basis": "seed", "approvals": None}}}
    assert visa_tag("BlackRock", "great job", db=db)["verdict"] == "likely_friendly"
    db["employers"]["blackrock"]["basis"] = "uscis_data_hub"
    assert visa_tag("BlackRock", "great job", db=db)["verdict"] == "friendly"
    assert visa_tag("BlackRock", "no visa sponsorship", db=db)["verdict"] == "blocked"
    assert visa_tag("Acme Corp", "", db={"employers": {}})["verdict"] == "unknown"
    print("OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python automation/visa_tagger.py")
    ap.add_argument("--smoke", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p_q = sub.add_parser("query"); p_q.add_argument("company")
    p_s = sub.add_parser("scan-jd"); p_s.add_argument("jd_file")
    p_i = sub.add_parser("ingest"); p_i.add_argument("csv_path")
    p_i.add_argument("--min-approvals", type=int, default=1)
    args = ap.parse_args(argv)
    if args.smoke:
        return _smoke()
    if args.cmd == "query":
        rec = employer_h1b(args.company)
        tag = visa_tag(args.company)
        print(json.dumps({"record": rec, "tag": tag}, indent=2))
        return 0
    if args.cmd == "scan-jd":
        text = Path(args.jd_file).read_text(encoding="utf-8", errors="replace")
        print(jd_sponsorship_signal(text))
        return 0
    if args.cmd == "ingest":
        return ingest(args.csv_path, args.min_approvals)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
