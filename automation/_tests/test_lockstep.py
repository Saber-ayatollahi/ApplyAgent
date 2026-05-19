"""Audit: are jd_scraper._normalize_title and worklist._normalize_title identical?"""
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Dev\ApplyAgent\automation")

def extract_func(path: Path, fname: str) -> tuple[int, list[str]]:
    """Return (start_line, body_lines) for the named function definition."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"def {fname}("):
            # Read until next top-level def/class or EOF
            body = [line]
            for j in range(i + 1, len(lines)):
                ln = lines[j]
                if ln and not ln.startswith((" ", "\t")) and ln.lstrip().startswith(("def ", "class ", "@")):
                    return (i + 1, body)
                body.append(ln)
            return (i + 1, body)
    return (0, [])

scraper_start, scraper_body = extract_func(ROOT / "jd_scraper.py", "_normalize_title")
worklist_start, worklist_body = extract_func(ROOT / "worklist.py", "_normalize_title")

print(f"jd_scraper._normalize_title @ line {scraper_start}, body length={len(scraper_body)}")
print(f"worklist._normalize_title @ line {worklist_start}, body length={len(worklist_body)}")
print()

# Strip docstrings/comments and compare actual logic lines
def code_lines(body: list[str]) -> list[str]:
    """Strip docstring + blank + pure comments. Keep code (incl. inline comments)."""
    out = []
    in_doc = False
    doc_close = None
    for ln in body[1:]:  # skip def line
        s = ln.strip()
        if not s:
            continue
        if not in_doc:
            if s.startswith(('"""', "'''")):
                quote = s[:3]
                # Single-line docstring?
                if s.endswith(quote) and len(s) > 3:
                    continue
                in_doc = True
                doc_close = quote
                continue
            if s.startswith("#"):
                continue
            out.append(ln.rstrip())
        else:
            if doc_close in s:
                in_doc = False
            continue
    return out

scraper_code = code_lines(scraper_body)
worklist_code = code_lines(worklist_body)

print("=== jd_scraper code lines ===")
for ln in scraper_code:
    print(repr(ln))
print()
print("=== worklist code lines ===")
for ln in worklist_code:
    print(repr(ln))
print()

# Compare regex semantically - but with whitespace differences flagged
print("=== Diff (line-by-line, whitespace-insensitive after first column) ===")
import difflib
diff = list(difflib.unified_diff(
    [l.strip() for l in scraper_code],
    [l.strip() for l in worklist_code],
    lineterm="",
    fromfile="jd_scraper",
    tofile="worklist",
))
if diff:
    for line in diff:
        print(line)
else:
    print("IDENTICAL (whitespace-stripped)")
print()

# Also diff with whitespace
print("=== Diff (with whitespace) ===")
diff_ws = list(difflib.unified_diff(
    scraper_code,
    worklist_code,
    lineterm="",
    fromfile="jd_scraper",
    tofile="worklist",
))
if diff_ws:
    for line in diff_ws:
        print(line)
else:
    print("IDENTICAL")

# Behavioral test: import both and apply to a battery of titles
sys.path.insert(0, str(ROOT))
# We need to extract the function without executing module-level network code
# Approach: read the function body and exec in sandboxed namespace
def load_func(path: Path, fname: str):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"def {fname}("):
            body = [line]
            for j in range(i + 1, len(lines)):
                ln = lines[j]
                if ln and not ln.startswith((" ", "\t")) and ln.lstrip().startswith(("def ", "class ", "@")):
                    break
                body.append(ln)
            ns = {"re": re}
            exec("\n".join(body), ns)
            return ns[fname]
    return None

f1 = load_func(ROOT / "jd_scraper.py", "_normalize_title")
f2 = load_func(ROOT / "worklist.py", "_normalize_title")

print()
print("=== Behavioral test ===")
TEST_TITLES = [
    "Sr. Risk Analyst",
    "Sr Risk Analyst",
    "Snr Manager, Treasury",
    "Vice President, Quantitative Risk",
    "Vice-President of ALM",
    "Director, Risk & Capital",
    "Senior Manager - Toronto",
    "Risk Analyst (12 month contract)",
    "Risk Analyst (Hybrid)",
    "Manager (4451)",
    "Director / Capital Markets",
    "Assistant VP, Risk",
    "Risk Mgr — Toronto, Ontario",
]
for t in TEST_TITLES:
    a = f1(t)
    b = f2(t)
    flag = "OK " if a == b else "DRIFT"
    print(f"{flag}  {t!r:55}  scraper={a!r:35}  worklist={b!r}")
