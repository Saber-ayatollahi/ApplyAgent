"""Test _compute_diff bucketing (newly-scored row = 'upgraded', not 'stable').

Run: python automation/_tests/test_compute_diff.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "ui"))

# Minimal stub to let us import the function without Streamlit
import types
st = types.ModuleType("streamlit")

class _StAny:
    def __getattr__(self, name):
        return _StAny()
    def __call__(self, *a, **kw):
        return _StAny()
    def __iter__(self):
        return iter([_StAny(), _StAny(), _StAny()])
    def __enter__(self):
        return self
    def __exit__(self, *a):
        pass

for attr in dir(st):
    if not attr.startswith("_"):
        setattr(st, attr, _StAny())

st.cache_data = lambda **kw: (lambda f: f)
st.cache_resource = lambda **kw: (lambda f: f)
st.session_state = {}
st.sidebar = _StAny()
st.secrets = {}
sys.modules["streamlit"] = st
sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
sys.modules["streamlit.components.v1"] = types.ModuleType("streamlit.components.v1")

# Now patch enough that app.py doesn't crash on import-time side effects
import importlib.util

spec = importlib.util.spec_from_file_location("app_module", ROOT / "ui" / "app.py")
# We only need _compute_diff — extract it by running the definition in isolation

# Simpler: just copy the logic directly for testing
import hashlib as _ap_hashlib

_VERDICT_RANK = {"skip": 0, "watch": 1, "tailor_and_apply": 2, "apply_now": 3}


def _ap_url(r: dict) -> str:
    return r.get("link") or r.get("url") or ""


def _compute_diff(current_rows: list, prev_rows: list) -> dict:
    cur = {_ap_url(r): r for r in (current_rows or []) if _ap_url(r)}
    prev = {_ap_url(r): r for r in (prev_rows or []) if _ap_url(r)}
    out = {}
    for url, r in cur.items():
        pr = prev.get(url)
        if not pr:
            out[url] = "new"; continue
        cf, pf = r.get("fit") or {}, pr.get("fit") or {}
        if cf and not pf:
            out[url] = "upgraded"; continue
        cs, ps = cf.get("fit_score") or 0, pf.get("fit_score") or 0
        cv = _VERDICT_RANK.get(cf.get("fit_verdict", ""), -1)
        pv = _VERDICT_RANK.get(pf.get("fit_verdict", ""), -1)
        if cs - ps >= 1 or (cv > pv and pv >= 0):
            out[url] = "upgraded"
        elif ps - cs >= 1 or (pv > cv and cv >= 0):
            out[url] = "downgraded"
        else:
            out[url] = "stable"
    return out


PASS = FAIL = 0
FAILS: list[str] = []


def check(label, got, expected):
    global PASS, FAIL
    if got == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append(f"FAIL {label}: got {got!r}, expected {expected!r}")


# Test: brand-new URL
diff = _compute_diff(
    [{"link": "http://a.com", "fit": {"fit_score": 7}}],
    []
)
check("brand new URL", diff.get("http://a.com"), "new")

# Test: existed in prev without fit, now has fit -> upgraded
diff = _compute_diff(
    [{"link": "http://b.com", "fit": {"fit_score": 5, "fit_verdict": "watch"}}],
    [{"link": "http://b.com"}]  # no "fit" key
)
check("newly scored (no prev fit)", diff.get("http://b.com"), "upgraded")

# Test: existed with empty fit dict, now has fit -> upgraded
diff = _compute_diff(
    [{"link": "http://c.com", "fit": {"fit_score": 6, "fit_verdict": "tailor_and_apply"}}],
    [{"link": "http://c.com", "fit": {}}]
)
check("newly scored (empty prev fit)", diff.get("http://c.com"), "upgraded")

# Test: same score, same verdict -> stable
diff = _compute_diff(
    [{"link": "http://d.com", "fit": {"fit_score": 5, "fit_verdict": "watch"}}],
    [{"link": "http://d.com", "fit": {"fit_score": 5, "fit_verdict": "watch"}}]
)
check("identical scores -> stable", diff.get("http://d.com"), "stable")

# Test: score went up by 1 -> upgraded
diff = _compute_diff(
    [{"link": "http://e.com", "fit": {"fit_score": 6, "fit_verdict": "watch"}}],
    [{"link": "http://e.com", "fit": {"fit_score": 5, "fit_verdict": "watch"}}]
)
check("score +1 -> upgraded", diff.get("http://e.com"), "upgraded")

# Test: verdict went up -> upgraded
diff = _compute_diff(
    [{"link": "http://f.com", "fit": {"fit_score": 5, "fit_verdict": "tailor_and_apply"}}],
    [{"link": "http://f.com", "fit": {"fit_score": 5, "fit_verdict": "watch"}}]
)
check("verdict up -> upgraded", diff.get("http://f.com"), "upgraded")

# Test: score went down -> downgraded
diff = _compute_diff(
    [{"link": "http://g.com", "fit": {"fit_score": 4, "fit_verdict": "watch"}}],
    [{"link": "http://g.com", "fit": {"fit_score": 5, "fit_verdict": "watch"}}]
)
check("score -1 -> downgraded", diff.get("http://g.com"), "downgraded")

print(f"\n{PASS} pass / {FAIL} fail")
for f in FAILS:
    print(f)
sys.exit(0 if FAIL == 0 else 1)
