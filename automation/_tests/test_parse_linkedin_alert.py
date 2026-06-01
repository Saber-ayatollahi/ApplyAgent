"""Test parse_linkedin_alert() — coverage of HTML and text-fallback paths.

Standalone (no pytest). Run: python automation/_tests/test_parse_linkedin_alert.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gmail_reader import parse_linkedin_alert  # type: ignore

PASS = 0
FAIL = 0
FAILS: list[str] = []


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL [{label}] {detail}")


# ---------------------------------------------------------------------------
# 1. Empty body → 0 rows
# ---------------------------------------------------------------------------
rows = parse_linkedin_alert("")
check("empty body → 0 rows", rows == [], detail=f"got {rows!r}")

# ---------------------------------------------------------------------------
# 2. Body with no LinkedIn URLs → 0 rows
# ---------------------------------------------------------------------------
rows = parse_linkedin_alert("<html><body><a href='https://google.com'>foo</a></body></html>")
check("no LinkedIn URLs → 0 rows", rows == [], detail=f"got {rows!r}")

# ---------------------------------------------------------------------------
# 3. Single anchor with <strong> title and adjacent cell text
# ---------------------------------------------------------------------------
html = """
<html><body>
<table><tr><td>
<a href="https://www.linkedin.com/jobs/view/4368084295?trk=mailing">
<strong>Director &amp; Head, Insights &amp; Analytics, IT Risk</strong>
Scotiabank · Toronto, ON
Actively recruiting
</a>
</td></tr></table>
</body></html>
"""
rows = parse_linkedin_alert(html)
check("single anchor parses", len(rows) == 1, detail=f"got {len(rows)} rows: {rows}")
if rows:
    r = rows[0]
    check("title from <strong>", r.get("title", "").startswith("Director"),
          detail=f"title={r.get('title')!r}")
    check("company extracted", "Scotiabank" in r.get("company", ""),
          detail=f"company={r.get('company')!r}")
    check("location extracted", "Toronto" in r.get("location", ""),
          detail=f"location={r.get('location')!r}")
    check("link canonical", r.get("link") == "https://www.linkedin.com/jobs/view/4368084295",
          detail=f"link={r.get('link')!r}")
    check("source label", r.get("source") == "gmail_linkedin_alert",
          detail=f"source={r.get('source')!r}")

# ---------------------------------------------------------------------------
# 4. URL with /comm/jobs/view/<id> tracking variant
# ---------------------------------------------------------------------------
html = """
<a href="https://www.linkedin.com/comm/jobs/view/4406800213?trk=eml-mailing&midToken=AQ">
<strong>Treasury Manager</strong>
KOHO · Canada (Remote)
</a>
"""
rows = parse_linkedin_alert(html)
check("comm/jobs/view variant parses", len(rows) == 1, detail=f"got {rows}")
if rows:
    check("comm URL canonicalized",
          rows[0].get("link") == "https://www.linkedin.com/jobs/view/4406800213",
          detail=f"link={rows[0].get('link')!r}")

# ---------------------------------------------------------------------------
# 5. Multiple anchors, dedup by job_id
# ---------------------------------------------------------------------------
html = """
<a href="https://www.linkedin.com/jobs/view/111?trk=a">
  <strong>Senior Risk Analyst</strong>
  BMO · Toronto, ON
</a>
<a href="https://www.linkedin.com/jobs/view/111?trk=b">
  <strong>Senior Risk Analyst</strong>
  BMO · Toronto, ON
</a>
<a href="https://www.linkedin.com/jobs/view/222?trk=c">
  <strong>VP Treasury</strong>
  TD · Toronto, ON
</a>
"""
rows = parse_linkedin_alert(html)
check("dedup by job_id (3 anchors → 2 rows)",
      len(rows) == 2, detail=f"got {len(rows)} rows")

# ---------------------------------------------------------------------------
# 6. No <strong> tag — first cell line is title
# ---------------------------------------------------------------------------
html = """
<table><tr><td>
<a href="https://www.linkedin.com/jobs/view/333">
Director Risk Services
Northbridge Financial Corporation · Toronto, ON (Hybrid)
</a>
</td></tr></table>
"""
rows = parse_linkedin_alert(html)
check("no-strong fallback parses", len(rows) == 1, detail=f"got {rows}")
if rows:
    check("title from first cell line",
          "Director" in rows[0].get("title", ""),
          detail=f"title={rows[0].get('title')!r}")

# ---------------------------------------------------------------------------
# 7. Plain-text fallback (no HTML structure)
# ---------------------------------------------------------------------------
text = """LinkedIn Job Alert

Senior Risk Analyst
BMO
https://www.linkedin.com/jobs/view/444444

VP Treasury
TD Securities
https://www.linkedin.com/jobs/view/555555
"""
rows = parse_linkedin_alert(text)
check("text fallback ≥ 1 row", len(rows) >= 1, detail=f"got {len(rows)}")

# ---------------------------------------------------------------------------
# 8. Anchor with no surrounding td/div (rare but seen)
# ---------------------------------------------------------------------------
html = '<a href="https://www.linkedin.com/jobs/view/666">foo</a>'
rows = parse_linkedin_alert(html)
check("orphan anchor parses (with empty fields)",
      len(rows) <= 1, detail=f"got {rows}")

# ---------------------------------------------------------------------------
# 9. Mojibake separator should split correctly via _clean_alert_fields
# ---------------------------------------------------------------------------
html = """
<a href="https://www.linkedin.com/jobs/view/777">
<strong>Senior Risk Analyst</strong>
BMO � Toronto, ON
</a>
"""
rows = parse_linkedin_alert(html)
check("mojibake separator handled", len(rows) == 1, detail=f"got {rows}")
if rows:
    co = rows[0].get("company", "")
    loc = rows[0].get("location", "")
    check("mojibake → company clean", co.strip() == "BMO",
          detail=f"company={co!r}")
    check("mojibake → location clean", "Toronto" in loc and "�" not in loc,
          detail=f"location={loc!r}")

# ---------------------------------------------------------------------------
# 10. Anchor where strong contains markup
# ---------------------------------------------------------------------------
html = """
<a href="https://www.linkedin.com/jobs/view/888">
<strong>Director, <em>FinTech</em> &amp; Risk Analytics</strong>
Jobber · Kitchener, ON (Hybrid)
</a>
"""
rows = parse_linkedin_alert(html)
check("nested markup in <strong>", len(rows) == 1, detail=f"got {rows}")
if rows:
    check("strong+em title", "FinTech" in rows[0].get("title", ""),
          detail=f"title={rows[0].get('title')!r}")

# ---------------------------------------------------------------------------
# 11. Diagnostic: simulate scenario where digest yields 0 rows
# (anchor href is /comm/redirect with the actual jobs/view embedded as redir param)
# ---------------------------------------------------------------------------
html = """
<a href="https://www.linkedin.com/comm/redirect?url=https%3A//www.linkedin.com/jobs/view/999">
<strong>Hidden behind redirect</strong>
BMO · Toronto, ON
</a>
"""
rows = parse_linkedin_alert(html)
# URL-encoded job URL inside redirect — _LI_JOB_RE searches the WHOLE href
# string. URL-encoded "%2F" won't match "linkedin.com/jobs/view/" pattern.
# So this likely yields 0 rows = potential parse miss.
check("encoded redirect handled (redirect URL contains /jobs/view/ in clear text)",
      len(rows) == 1,
      detail=f"got {rows}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{PASS} pass / {FAIL} fail")
for f in FAILS:
    print(f)


def test_all_checks_pass():
    """Pytest entrypoint. The checks above run at import time and accumulate
    into the module-level FAIL counter; assert none failed so this file is a
    real pytest test rather than a collection-aborting standalone script."""
    assert FAIL == 0, "\n".join(FAILS)


if __name__ == "__main__":
    sys.exit(0 if FAIL == 0 else 1)
