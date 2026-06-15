"""fetch_inbox_signals sender-scoping + message-cap warning.

Bug: the harvest OR'd all ALERT_SENDERS + RECRUITER_DOMAINS into one query and
capped the COMBINED set at `limit` (newest-first), so heavy recruiter mail
could silently push the oldest LinkedIn alert digests out of the 30-day
window. Fix: a `senders` param lets gmail_fetch scope the query to the
parseable LinkedIn senders, and a >limit match now warns loudly.

Mocks the IMAP connection (no network) and records the actual X-GM-RAW query.
"""
from __future__ import annotations

import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gmail_reader as gr  # noqa: E402


class _FakeIMAP:
    """Records the X-GM-RAW query; returns `uids` for search and a minimal
    RFC822 message per fetch."""
    def __init__(self, uids):
        self._uids = uids
        self.queries = []

    def uid(self, cmd, *args):
        if cmd == "search":
            if "X-GM-RAW" in args:
                self.queries.append(args[-1])
                return ("OK", [b" ".join(self._uids)])
            return ("OK", [b""])
        if cmd == "fetch":
            u = args[0]
            m = EmailMessage()
            m["From"] = "LinkedIn <jobalerts-noreply@linkedin.com>"
            m["Subject"] = "jobs for you"
            m["Date"] = "Sat, 14 Jun 2026 09:00:00 -0400"
            m.set_content("body")
            return ("OK", [(f"{u} (RFC822)".encode(), m.as_bytes())])
        return ("OK", [b""])

    def close(self):  # noqa: D401
        pass

    def logout(self):
        pass


def _patch(monkeypatch, uids):
    fake = _FakeIMAP(uids)
    monkeypatch.setattr(gr, "load_credentials", lambda: ("x@y.com", "pw"))
    monkeypatch.setattr(gr, "_connect", lambda e, p: fake)
    return fake


def test_senders_param_scopes_the_query(monkeypatch):
    fake = _patch(monkeypatch, [b"10", b"11"])
    gr.fetch_inbox_signals(days=30, limit=400, include_body=True,
                           senders=["jobalerts-noreply@linkedin.com"])
    q = fake.queries[0]
    assert "from:jobalerts-noreply@linkedin.com" in q
    # recruiter domains must NOT be in the scoped query
    assert "linkedin.com/comm" not in q
    for dom in gr.RECRUITER_DOMAINS:
        assert f"@{dom}" not in q


def test_default_query_includes_recruiter_domains(monkeypatch):
    fake = _patch(monkeypatch, [b"10"])
    gr.fetch_inbox_signals(days=30, limit=400, senders=None)
    q = fake.queries[0]
    assert "from:jobalerts-noreply@linkedin.com" in q
    assert any(f"@{d}" in q for d in gr.RECRUITER_DOMAINS)   # unscoped default


def test_cap_warns_and_truncates_to_newest(monkeypatch, capsys):
    # 5 matches, limit 2 → keep the NEWEST 2 (14,15) and warn about 3 dropped.
    _patch(monkeypatch, [b"11", b"12", b"13", b"14", b"15"])
    out = gr.fetch_inbox_signals(days=30, limit=2,
                                 senders=["jobalerts-noreply@linkedin.com"])
    assert len(out) == 2
    assert {m.uid for m in out} == {"14", "15"}
    err = capsys.readouterr().err
    assert "capped at limit=2" in err and "dropped the oldest 3" in err


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
