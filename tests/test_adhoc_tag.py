"""Ad-hoc jobs (added via the "Tailor a resume for any job" form) must be
visibly tagged so they're distinguishable from scraped / Gmail-sourced leads.

app._is_adhoc_job is the single predicate behind all three tags: the ✍️ prefix
on the Company column, the ✍️ Src badge, and the "✍️ Ad-hoc" pill in the
Inspect/edit header. Those entries are stamped source="manual_adhoc" and an id
prefixed "adhoc-"; either marker is sufficient (an ad-hoc row whose source was
later rewritten still reads as ad-hoc via its id, and vice-versa).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT / "automation"))

import app  # noqa: E402  (runs the module top-level; bare-mode st calls just warn)


def test_is_adhoc_job_true_cases():
    f = app._is_adhoc_job
    assert f({"source": "manual_adhoc", "id": "adhoc-x"})
    assert f({"source": "manual_adhoc", "id": "anything"})        # source alone
    assert f({"source": "scraper+fit_scorer",
              "id": "adhoc-royal-bank-of-canada-x"})              # id alone


def test_is_adhoc_job_false_cases():
    f = app._is_adhoc_job
    assert not f({"source": "scraper+fit_scorer", "id": "auto-bmo-director"})
    assert not f({"source": "gmail_linkedin_alert+fit_scorer", "id": "auto-x"})
    assert not f({"source": "", "id": ""})
    assert not f({})


def test_is_adhoc_job_handles_bad_input():
    f = app._is_adhoc_job
    assert not f(None)
    assert not f("notadict")
    assert not f(123)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
