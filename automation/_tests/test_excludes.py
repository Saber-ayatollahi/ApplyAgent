"""Tests for automation/excludes.py — permanent company exclude-list.

Covers the module API, canonical matching (incl. National Bank French
aliases + shared-Workday-tenant siblings), the scrape-side target filter,
the Gmail row filter, and the worklist.rebuild() chokepoint that stops
on-disk envelopes from re-materializing excluded rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AUTO = HERE.parent
sys.path.insert(0, str(AUTO.parent))  # so `import automation.excludes` works

from automation import excludes as exc  # noqa: E402
from automation import brand_aliases  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Redirect exclude-list file paths into tmp_path with an empty seed."""
    live = tmp_path / "excludes.json"
    example = tmp_path / "excludes.example.json"
    example.write_text(
        json.dumps({"version": 1, "companies": []}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(exc, "LIVE_PATH", live)
    monkeypatch.setattr(exc, "EXAMPLE_PATH", example)
    return {"live": live, "example": example, "tmp": tmp_path}


# ---------------------------------------------------------------------------
# 1-2. lazy file creation
# ---------------------------------------------------------------------------
def test_load_lazy_creates_from_example(isolated):
    assert not isolated["live"].exists()
    assert exc.load() == set()
    assert isolated["live"].exists()


def test_load_lazy_creates_without_example(isolated, monkeypatch):
    monkeypatch.setattr(exc, "EXAMPLE_PATH", isolated["tmp"] / "nope.json")
    assert exc.load() == set()
    assert isolated["live"].exists()


# ---------------------------------------------------------------------------
# 3-4. add / idempotency / persistence
# ---------------------------------------------------------------------------
def test_persistence_roundtrip(isolated):
    assert exc.add("RBC") is True
    assert exc.add("TD Bank") is True
    assert exc.load() == {"rbc", "td"}
    rows = exc.list_excluded()
    assert {r["canonical_key"] for r in rows} == {"rbc", "td"}
    assert all(r.get("added_at") for r in rows)


def test_add_idempotent_same_canonical_key(isolated):
    assert exc.add("RBC") is True
    assert exc.add("Royal Bank of Canada") is False  # same canonical key
    assert exc.load() == {"rbc"}
    assert len(exc.list_excluded()) == 1


def test_add_blank_raises(isolated):
    with pytest.raises(ValueError):
        exc.add("")
    with pytest.raises(ValueError):
        exc.add("   ")


# ---------------------------------------------------------------------------
# 5-6. canonical matching
# ---------------------------------------------------------------------------
def test_canonical_match_company_variants(isolated):
    exc.add("RBC")
    for variant in ("RBC", "Royal Bank of Canada", "RBC Capital Markets",
                    "RBC Global Asset Management"):
        assert exc.is_excluded(variant) is True, variant
    assert exc.is_excluded("Acme Corp") is False


@pytest.mark.parametrize("name,key", [
    ("RBC", "rbc"),
    ("TD Bank", "td"),
    ("BMO", "bmo"),
    ("Scotiabank", "scotia"),
    ("CIBC", "cibc"),
    ("National Bank of Canada", "nbc"),
])
def test_canonical_match_all_big6(isolated, name, key):
    exc.add(name)
    assert exc.load() == {key}


def test_national_bank_french_aliases(isolated):
    """The brand_aliases fix: French/short variants must collapse onto nbc,
    else a Quebec-sourced 'Banque Nationale' row leaks past an NBC exclude."""
    for fr in ("Banque Nationale", "Banque Nationale du Canada", "BNC"):
        assert brand_aliases.canonical_brand(fr).lower() == "nbc", fr
    exc.add("National Bank of Canada")
    _, dropped = exc.filter_rows([{"company": "Banque Nationale"}])
    assert len(dropped) == 1


# ---------------------------------------------------------------------------
# 7-8. empty no-op, malformed, dormant fast-path
# ---------------------------------------------------------------------------
def test_empty_list_no_op(isolated):
    assert exc.is_excluded("RBC") is False
    targets = [{"name": "RBC"}, {"name": "HOOPP"}]
    assert exc.filter_targets(targets) is targets  # identity (signature-safe)
    rows = [{"company": "RBC"}]
    kept, dropped = exc.filter_rows(rows)
    assert kept is rows and dropped == []


def test_non_string_company_does_not_crash(isolated):
    exc.add("RBC")
    for bad in (None, 123, ["RBC"], {"x": 1}, ""):
        assert exc.is_excluded(bad) is False


def test_is_excluded_dormant_skips_canonical(isolated, monkeypatch):
    """Empty-set fast-path must precede canonical_brand so a dormant 1,400-row
    loop pays zero canonicalization cost."""
    def _boom(_name):
        raise AssertionError("canonical_brand called on empty-set fast-path")
    monkeypatch.setattr(exc.brand_aliases, "canonical_brand", _boom)
    assert exc.is_excluded("RBC", set()) is False


# ---------------------------------------------------------------------------
# 9-11. remove / no-ttl
# ---------------------------------------------------------------------------
def test_remove_clears_entry(isolated):
    exc.add("RBC")
    assert exc.remove("Royal Bank of Canada") is True  # canonical match
    assert exc.load() == set()
    assert exc.list_excluded() == []


def test_remove_noop_when_absent(isolated):
    assert exc.remove("RBC") is False


def test_entries_have_no_ttl_field(isolated):
    exc.add("RBC")
    entry = exc.list_excluded()[0]
    assert "until" not in entry
    assert "reason" not in entry


# ---------------------------------------------------------------------------
# 12-14. scrape-side filter_targets
# ---------------------------------------------------------------------------
def test_scrape_drops_bank_and_shared_tenant_siblings(isolated):
    """Excluding the bank must also drop its asset-management sibling, which
    shares a Workday tenant (TD/BMO AM). Canonical match, not raw name."""
    targets = [
        {"name": "TD Bank", "sector": "Canadian Big 6 Banks"},
        {"name": "TD Asset Management", "sector": "Canadian Asset Managers"},
        {"name": "BMO", "sector": "Canadian Big 6 Banks"},
        {"name": "BMO Asset Management", "sector": "Canadian Asset Managers"},
        {"name": "RBC Global Asset Management", "sector": "Canadian Asset Managers"},
        {"name": "HOOPP", "sector": "Canadian Pension Funds"},
    ]
    exc.add("TD Bank")
    exc.add("BMO")
    exc.add("RBC")
    kept = exc.filter_targets(targets)
    names = {t["name"] for t in kept}
    assert names == {"HOOPP"}, names  # every Big-6-canonical row gone


def test_scrape_filter_empty_returns_identity(isolated):
    targets = [{"name": "RBC"}]
    assert exc.filter_targets(targets) is targets


def test_scrape_filter_changes_targets_signature(isolated):
    """The post-exclude target set differs, which is what makes a stale
    --resume checkpoint mismatch rather than resurrect an excluded company."""
    from automation.jd_scraper import _targets_signature
    targets = [
        {"name": "RBC", "sector": "Canadian Big 6 Banks"},
        {"name": "HOOPP", "sector": "Canadian Pension Funds"},
    ]
    sig_before = _targets_signature(targets)
    exc.add("RBC")
    sig_after = _targets_signature(exc.filter_targets(targets))
    assert sig_before != sig_after
    # Empty set → identity → signature unchanged (no-resurrection invariant).
    assert exc.filter_targets(targets, set()) is targets


# ---------------------------------------------------------------------------
# 15-17. gmail row filter
# ---------------------------------------------------------------------------
def test_gmail_row_drop_by_canonical(isolated):
    exc.add("RBC")
    rows = [
        {"company": "RBC Capital Markets"},
        {"company": "RBC Global Asset Management"},
        {"company": "Acme"},
    ]
    kept, dropped = exc.filter_rows(rows)
    assert [r["company"] for r in kept] == ["Acme"]
    assert len(dropped) == 2


def test_gmail_row_unsectored_still_excluded(isolated):
    """Exclusion fires on company canonical_key only — an unsectored RBC row
    IS dropped (opposite of suppressions' conservative unsectored passthrough)."""
    exc.add("RBC")
    kept, dropped = exc.filter_rows([{"company": "RBC", "sector": ""}])
    assert kept == [] and len(dropped) == 1


def test_gmail_empty_list_keeps_all(isolated):
    rows = [{"company": "RBC"}, {"company": "Acme"}]
    kept, dropped = exc.filter_rows(rows)
    assert kept is rows and dropped == []
