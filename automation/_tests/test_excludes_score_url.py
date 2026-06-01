"""score_url.py is the ONE deliberate manual-override path for the exclude
list: it WARNS (does not block) when a pasted URL's company is excluded, then
scores + optionally adds to the tracker anyway.

These tests pin two things that would otherwise break silently:
  1. The warn-but-allow CONTRACT — score_url consults excludes.is_excluded and
     emits a stable marker phrase; it does NOT short-circuit/return on a hit.
  2. The marker-phrase COUPLING — ui/app.py greps the merged log for the exact
     phrase score_url emits. If either side edits the string, the UI banner
     goes silently dark. We assert both sides share the literal.

score_url.main() imports `anthropic` and calls the live API, so we test at the
source/seam level rather than executing it.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
ROOT = AUTO.parent
sys.path.insert(0, str(ROOT))  # `import automation.<m>`

from automation import excludes as exc  # noqa: E402


# The single source of truth for the cross-file string coupling.
MARKER = "on the permanent exclude-list"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. The is_excluded seam score_url depends on resolves the manual case.
# ---------------------------------------------------------------------------
def test_is_excluded_resolves_score_url_company(tmp_path, monkeypatch):
    import json
    example = tmp_path / "excludes.example.json"
    example.write_text(json.dumps({"version": 1, "companies": []}))
    monkeypatch.setattr(exc, "LIVE_PATH", tmp_path / "excludes.json")
    monkeypatch.setattr(exc, "EXAMPLE_PATH", example)

    exc.add("RBC")
    # The canonical match score_url relies on (a pasted RBC Capital Markets URL
    # whose company was inferred) fires; an unrelated company does not.
    assert exc.is_excluded("RBC Capital Markets") is True
    assert exc.is_excluded("Citi") is False
    # _canon is used in the warning string — confirm it's importable + correct.
    assert exc._canon("RBC Capital Markets") == "rbc"


# ---------------------------------------------------------------------------
# 2. score_url WARNS but does not BLOCK (warn-but-allow contract).
# ---------------------------------------------------------------------------
def test_score_url_warns_but_does_not_block():
    src = _read(AUTO / "score_url.py")
    # It consults the exclude list...
    assert "excludes.is_excluded(company)" in src
    # ...and the warning is emitted via print() (a WARN, surfaced to stderr/UI)
    # rather than a return/raise that would block scoring.
    assert f'the permanent exclude-list' in src
    # Locate the `is_excluded(company)` GUARD inside main() (the first one — the
    # warn branch) and the unconditional scoring call that must follow it.
    guard_idx = src.index("if excludes.is_excluded(company):")
    score_idx = src.index("fit = fit_scorer.score_with_llm(")
    assert guard_idx < score_idx, "exclude guard must precede scoring"
    # Between the guard and the scoring call there must be a print (the warning)
    # and NO `return` (warn-but-allow — scoring is never short-circuited).
    between = src[guard_idx:score_idx]
    assert "print(" in between, "exclude branch must emit a warning"
    assert "return" not in between, "exclude branch must NOT block scoring"


# ---------------------------------------------------------------------------
# 3. Marker phrase is shared by BOTH score_url (emitter) and the UI (consumer).
# ---------------------------------------------------------------------------
def test_marker_phrase_coupling_score_url_and_ui():
    score_url_src = _read(AUTO / "score_url.py")
    ui_src = _read(ROOT / "ui" / "app.py")
    assert MARKER in score_url_src, "score_url.py no longer emits the marker"
    assert MARKER in ui_src, "ui/app.py no longer greps for the marker"


# ---------------------------------------------------------------------------
# 4. Tracker-add path also surfaces an excluded override (never silent).
# ---------------------------------------------------------------------------
def test_add_to_tracker_announces_excluded_override():
    src = _read(AUTO / "score_url.py")
    # Within the --add-to-tracker branch we re-announce the excluded override.
    assert "Adding an EXCLUDED company" in src
