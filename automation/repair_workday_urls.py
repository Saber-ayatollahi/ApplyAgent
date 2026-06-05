#!/usr/bin/env python3
"""Repair malformed Workday job URLs (missing the /<board> site segment).

The Workday scraper used to build links as ``https://<host>/job/...`` — missing
the site (board) segment — so Workday 404s and the browser bounces to
``community.workday.com/invalid-url``. The scraper is fixed going forward
(jd_scraper.fetch_workday_jobs); this repairs URLs already stored in the
tracker / worklist / scan artifacts.

Each Workday host's tenant maps to its board via jd_scraper.TARGETS (+ the
expansion list), then:

    https://<tenant>.<dc>.myworkdayjobs.com/job/<...>
 -> https://<tenant>.<dc>.myworkdayjobs.com/<board>/job/<...>

Usage:
    python repair_workday_urls.py --file ../data/job_tracker_data.json
    python repair_workday_urls.py --file ../data/job_tracker_data.json --commit
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# https://<tenant>.<anything>.myworkdayjobs.com/job/<rest>  (no /<board>/ before /job/)
_BROKEN = re.compile(
    r"^(https://([^./]+)\.[^/]*myworkdayjobs\.com)/job/(.+)$"
)

# URL-bearing keys to repair when walking nested JSON.
_URL_KEYS = ("url", "link", "portal_url", "job_url")


def build_tenant_board_map() -> dict[str, str]:
    """tenant -> board (siteId), from every Workday target spec."""
    import jd_scraper as J  # type: ignore
    try:
        from expansion_companies import EXPANSION_TARGETS  # type: ignore
    except Exception:
        EXPANSION_TARGETS = []
    m: dict[str, str] = {}
    for t in list(J.TARGETS) + list(EXPANSION_TARGETS):
        spec = t.get("workday")
        if not spec:
            continue
        if len(spec) == 3:
            tenant, _sub, board = spec
        else:
            tenant, board = spec
            tenant = str(tenant).split(".")[0]
        m[tenant] = board
    return m


def repair_url(u: str, tmap: dict[str, str]) -> str | None:
    """Return the repaired URL, or None if `u` isn't a broken Workday URL
    (or its tenant has no known board)."""
    if not isinstance(u, str):
        return None
    m = _BROKEN.match(u)
    if not m:
        return None
    host, tenant, rest = m.group(1), m.group(2), m.group(3)
    board = tmap.get(tenant)
    if not board:
        return None
    return f"{host}/{board}/job/{rest}"


def repair_obj(obj, tmap: dict[str, str]) -> int:
    """Recursively rewrite broken Workday URLs under _URL_KEYS. Returns count."""
    n = 0
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in _URL_KEYS and isinstance(v, str):
                fixed = repair_url(v, tmap)
                if fixed and fixed != v:
                    obj[k] = fixed
                    n += 1
            else:
                n += repair_obj(v, tmap)
    elif isinstance(obj, list):
        for item in obj:
            n += repair_obj(item, tmap)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="JSON file to repair")
    ap.add_argument("--commit", action="store_true",
                    help="Write the file (default: dry-run). Backs up to "
                         "<file>.bak_workday first.")
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERROR: {p} not found", file=sys.stderr)
        return 1
    original = p.read_text(encoding="utf-8")
    data = json.loads(original)
    tmap = build_tenant_board_map()
    n = repair_obj(data, tmap)
    print(f"{p.name}: {n} Workday URL(s) repaired")
    if not n:
        return 0
    if args.commit:
        bak = p.with_suffix(p.suffix + ".bak_workday")
        bak.write_text(original, encoding="utf-8")
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                     encoding="utf-8")
        print(f"  wrote {p.name} (backup: {bak.name})")
    else:
        print("  (dry-run — pass --commit to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
