"""jd_scraper.jobposting_from_ldjson — extract a posting from schema.org
JobPosting JSON-LD.

Regression: the ad-hoc "Tailor a resume for any job" fetch only handled
LinkedIn URLs; a Phenom-hosted career page (jobs.rbc.com) fell through to a
plain-text fetch that returned the JS SEO shell ("Find your next job… choose a
job you love…") with no company/title. Phenom/SuccessFactors/iCIMS sites embed
the full posting as JSON-LD, which this parses without a browser.

Network-free: requests.get is monkeypatched to return canned HTML.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jd_scraper as js  # type: ignore
from bs4 import BeautifulSoup  # type: ignore


class _Resp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status


def _page(*ldjson_objs: dict, body: str = "Find your next job. Choose a job "
          "you love and you will never have to work a day in your life.") -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(o)}</script>'
        for o in ldjson_objs)
    return f"<html><head>{scripts}</head><body>{body}</body></html>"


# description is HTML stored as an ESCAPED string, exactly like Phenom serves it.
_RBC_JOB = {
    "@context": "https://schema.org", "@type": "JobPosting",
    "title": "Associate Director - Project Manager - Risk Services",
    "hiringOrganization": {"@type": "Organization", "name": "Royal Bank of Canada"},
    "jobLocation": {"@type": "Place", "address": {
        "@type": "PostalAddress", "addressLocality": "Toronto", "addressRegion": "ON"}},
    "identifier": {"@type": "PropertyValue", "value": "R0000169839"},
    "description": "&lt;div&gt;&lt;p&gt;WHAT IS THE OPPORTUNITY?&lt;/p&gt;"
                   "&lt;p&gt;The Risk Services team within RBC Capital Markets.&lt;/p&gt;&lt;/div&gt;",
}


def _patch(monkeypatch, resp: _Resp):
    monkeypatch.setattr(js.requests, "get", lambda *a, **k: resp)


def test_extracts_phenom_jobposting(monkeypatch):
    _patch(monkeypatch, _Resp(_page(_RBC_JOB)))
    info = js.jobposting_from_ldjson("https://jobs.rbc.com/ca/en/job/x")
    assert info is not None
    assert info["company"] == "Royal Bank of Canada"
    assert info["title"].startswith("Associate Director")
    assert info["location"] == "Toronto"
    assert info["job_id"] == "R0000169839"
    txt = BeautifulSoup(info["jd_html"], "html.parser").get_text(" ").strip()
    assert "WHAT IS THE OPPORTUNITY" in txt
    assert "&lt;" not in txt and "<div>" not in txt  # unescaped + tags stripped
    assert "never have to work a day" not in txt.lower()  # not the SEO shell


def test_handles_graph_nesting(monkeypatch):
    doc = {"@context": "https://schema.org",
           "@graph": [{"@type": "WebSite"}, _RBC_JOB]}
    _patch(monkeypatch, _Resp(_page(doc)))
    info = js.jobposting_from_ldjson("https://example.com/job")
    assert info and info["title"].startswith("Associate Director")


def test_location_as_list(monkeypatch):
    job = dict(_RBC_JOB, jobLocation=[{"@type": "Place", "address": {
        "addressLocality": "Mississauga"}}])
    _patch(monkeypatch, _Resp(_page(job)))
    info = js.jobposting_from_ldjson("https://x/job")
    assert info["location"] == "Mississauga"


def test_returns_none_without_jobposting(monkeypatch):
    org = {"@context": "https://schema.org", "@type": "Organization", "name": "RBC"}
    _patch(monkeypatch, _Resp(_page(org)))
    assert js.jobposting_from_ldjson("https://x/careers") is None


def test_returns_none_on_http_error(monkeypatch):
    _patch(monkeypatch, _Resp("<html></html>", status=404))
    assert js.jobposting_from_ldjson("https://x/dead") is None


def test_returns_none_on_request_exception(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(js.requests, "get", _boom)
    assert js.jobposting_from_ldjson("https://x/job") is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
