#!/usr/bin/env python3
"""Repair Gmail-misparsed rows where title and company collapsed into one
string, leaving company duplicated as the title prefix.

Symptom (May 18 2026 gmail scan, fixed in parser since): rows look like
    company = "Treasury Manager"
    title   = "Treasury Manager KOHO · Canada (Remote) 8 school alumni"
where the real shape is `<title> <real_company> · <location> <noise>`.

This script re-splits on the LinkedIn `·` separator — the bullet only ever
appears between company and location in alert digests, so anything before
it is `<title> <company>`. We then strip the duplicated title prefix to
recover the real company.

Targets three artifacts:
  - data/job_tracker_data.json  (live tracker)
  - automation/outputs/worklist.json  (current pool)
  - automation/outputs/worklist_scored.json  (scored pool)

Each gets a `.bak.<timestamp>` sidecar before any edit. Default is dry-run.

Usage:
    python automation/repair_misparsed_rows.py            # dry-run
    python automation/repair_misparsed_rows.py --commit   # write changes
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent


def is_misparsed(row: dict) -> bool:
    """Heuristic: title startswith company verbatim, with company > 5 chars
    so we don't false-positive on legit short company names that happen to
    start a title (e.g. company='RBC', title='RBC analyst').

    Restricted to gmail-source rows (and tracker rows promoted from gmail)
    because some scrape sources (notably Oliver Wyman on LinkedIn) legitimately
    format titles as `<company> <title>` — flipping those would corrupt them.
    """
    c = (row.get("company") or "").strip()
    t = (row.get("title") or "").strip()
    if len(c) <= 5 or not t.startswith(c):
        return False
    # Tail length: gmail rows where the tail got stripped down to just a
    # bank ticker (BMO, TD, BNY) only have 3-4 trailing chars. Loosen the
    # threshold; the source gate below stops false positives.
    if len(t) <= len(c) + 2:
        return False
    # Source gate: only fix gmail-derived rows. The misparse only ever
    # happened in the early Gmail parser. Scrape rows that look similar
    # (e.g. "Oliver Wyman - …") are real titles, not corruption.
    src = (row.get("source") or "").lower()
    # Tracker rows don't always carry source, so also accept rows whose
    # `id` was minted by auto_promote (prefix `auto-`) AND whose URL is a
    # linkedin.com/jobs/view path (the Gmail alert link shape).
    if "gmail" in src:
        return True
    rid = (row.get("id") or "")
    url = (row.get("url") or row.get("link") or "")
    if rid.startswith("auto-") and "linkedin.com/jobs/view" in url:
        return True
    return False


def repair_row(row: dict) -> tuple[bool, dict]:
    """Return (changed, repaired_row). Idempotent on already-clean rows."""
    if not is_misparsed(row):
        return False, row
    c_old = (row.get("company") or "").strip()
    t_old = (row.get("title") or "").strip()
    # Tail = everything after the duplicated company prefix
    tail = t_old[len(c_old):].strip()
    # LinkedIn alerts use middle-dot `·` to separate company from location.
    # Some older snippets had the unicode replacement char `�` instead
    # — handle both.
    sep = None
    for cand in (" · ", " · ", " � ", "·", "�"):
        if cand in tail:
            sep = cand
            break
    if sep is None:
        # No separator left in tail. This happens when the worklist/scored
        # cleanup pipeline already stripped LinkedIn cruft (location, alumni
        # counts, "Actively recruiting"), leaving JUST the real company in
        # the tail. Empirically true on every tracker/pool row inspected:
        # tail is a single company name, e.g. "Madison-Davis, LLC" or
        # "HOOPP (Healthcare of Ontario Pension Plan)". Trim trailing
        # status fragments and use the whole tail as company.
        real_company = tail.strip()
        # Defensive: if the tail still looks long enough to be multi-field,
        # downgrade to manual review rather than corrupt company further.
        if len(real_company) > 120:
            new_row = dict(row)
            new_row["title"] = c_old
            new_row["company"] = ""
            new_row["_repair_flag"] = "manual_review_long_tail"
            return True, new_row
    else:
        real_company, _, _ = tail.partition(sep)
        real_company = real_company.strip()
    new_row = dict(row)
    new_row["title"] = c_old        # original title was the duplicated prefix
    new_row["company"] = real_company
    new_row["_repaired_at"] = datetime.now().isoformat(timespec="seconds")
    return True, new_row


def repair_file(path: Path, rows_key: str = "results",
                  jobs_key: str | None = None,
                  commit: bool = False) -> dict:
    """Repair an artifact with `rows_key` (or `jobs_key` for tracker shape).
    Returns counts. Writes a backup + atomic update if commit=True."""
    if not path.exists():
        return {"error": f"not found: {path}", "scanned": 0, "fixed": 0,
                 "manual": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    container_key = jobs_key or rows_key
    rows = data.get(container_key) or []
    fixed_examples: list[tuple[str, str, str, str]] = []  # (c_old, c_new, t_old, t_new)
    manual = 0
    fixed = 0
    new_rows = []
    for r in rows:
        changed, nr = repair_row(r)
        if changed:
            if nr.get("_repair_flag") == "manual_review_no_separator":
                manual += 1
            else:
                fixed += 1
                if len(fixed_examples) < 5:
                    fixed_examples.append((
                        (r.get("company") or "")[:50],
                        (nr.get("company") or "")[:50],
                        (r.get("title") or "")[:80],
                        (nr.get("title") or "")[:80],
                    ))
        new_rows.append(nr)

    if commit and (fixed or manual):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = path.with_suffix(f".bak.{stamp}.json")
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        data[container_key] = new_rows
        # Stamp the file with repair metadata
        data.setdefault("_repairs", []).append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "fixed": fixed, "manual": manual,
            "tool": "repair_misparsed_rows.py",
        })
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return {
        "path": str(path),
        "scanned": len(rows),
        "fixed": fixed,
        "manual": manual,
        "examples": fixed_examples,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true",
                     help="Write changes (default: dry-run).")
    args = ap.parse_args()

    targets = [
        (ROOT / "data" / "job_tracker_data.json", "results", "jobs"),
        (ROOT / "automation" / "outputs" / "worklist.json", "results", None),
        (ROOT / "automation" / "outputs" / "worklist_scored.json", "results", None),
    ]
    print(f"[repair] mode = {'COMMIT' if args.commit else 'DRY-RUN'}\n")
    grand_fixed = grand_manual = 0
    for path, rk, jk in targets:
        r = repair_file(path, rows_key=rk, jobs_key=jk, commit=args.commit)
        if "error" in r:
            print(f"  {path.name}: {r['error']}")
            continue
        print(f"  {path.name}: scanned={r['scanned']:>5}  "
              f"fixed={r['fixed']:>3}  manual={r['manual']:>3}")
        for c_old, c_new, t_old, t_new in r["examples"]:
            print(f"    company {c_old!r:<52} → {c_new!r}")
            print(f"    title   {t_old!r:<52} → {t_new!r}")
        grand_fixed += r["fixed"]
        grand_manual += r["manual"]
    print(f"\n[repair] total: fixed={grand_fixed}  manual_review={grand_manual}")
    if not args.commit:
        print("[repair] dry-run — re-run with --commit to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
