"""Unit tests for gmail_fetch._emit_scan_shape's UID bookkeeping.

The cleanup bug: all-US LinkedIn alert emails (every job geo-dropped) never
entered the delete set because it was built only from KEPT rows
(contributing_uids), so they piled up in the inbox. The fix records
`processed_uids` — every alert we parsed and made a keep/drop decision on,
including all-US ones — and the UI trashes that broader set.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "automation"))

import gmail_fetch  # noqa: E402


def _row(uid: str, loc: str = "Toronto, ON") -> dict:
    return {"company": "Acme", "title": "Risk Analyst",
            "location": loc, "gmail_uid": uid, "link": f"https://x/{uid}"}


def test_processed_uids_is_superset_of_contributing():
    """The all-US alert's UID (only in processed_uids, not in any kept row)
    must still appear in processed_uids so cleanup trashes it."""
    kept = [_row("100"), _row("101")]            # produced kept rows
    # 'US-only' email 200 contributed only geo-dropped rows → not in `kept`,
    # but main() includes it in processed_uids (from raw_rows).
    env = gmail_fetch._emit_scan_shape(
        kept, "gmail_linkedin_alert",
        processed_uids=["100", "101", "200"])
    ga = env["gmail_alerts"]
    assert set(ga["contributing_uids"]) == {"100", "101"}
    assert set(ga["processed_uids"]) == {"100", "101", "200"}
    # processed must be a superset of contributing (the cleanup invariant).
    assert set(ga["contributing_uids"]).issubset(set(ga["processed_uids"]))


def test_processed_uids_defaults_to_contributing_when_absent():
    """Backward-compat: callers that don't pass processed_uids keep the old
    conservative behavior (processed == contributing)."""
    kept = [_row("100"), _row("101")]
    env = gmail_fetch._emit_scan_shape(kept, "gmail_linkedin_alert")
    ga = env["gmail_alerts"]
    assert set(ga["processed_uids"]) == set(ga["contributing_uids"]) == {"100", "101"}


def test_processed_uids_unions_in_any_missing_contributing():
    """Even if a caller passes a partial processed list, contributing UIDs are
    unioned in so the set is never smaller than contributing."""
    kept = [_row("100"), _row("101")]
    env = gmail_fetch._emit_scan_shape(
        kept, "gmail_linkedin_alert",
        processed_uids=["200"])  # forgot to include the kept ones
    ga = env["gmail_alerts"]
    assert set(ga["processed_uids"]) == {"100", "101", "200"}
