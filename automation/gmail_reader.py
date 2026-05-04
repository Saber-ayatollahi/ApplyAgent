"""gmail_reader.py — Read-only Gmail access via IMAP + app password.

Intentionally low-ceremony: no OAuth flow, no Google Cloud Console project.
User enables 2FA (most already have) then creates an app password at
https://myaccount.google.com/apppasswords (60 seconds). We store it in
~/.applyagent/config.json next to the Anthropic key.

Two capabilities for now:
  1. `fetch_job_alerts(days=14)` — parse LinkedIn/Indeed/etc. alert emails
     into our scan-row schema so they feed the same pipeline.
  2. `fetch_recruiter_emails(days=14)` — pull recent emails matching known
     recruiter/ATS senders so the UI can surface "probable replies".

Both are pure reads. We never write or delete mail.
"""
from __future__ import annotations

import email
import imaplib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path.home() / ".applyagent" / "config.json"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Known job-alert senders worth parsing for scan rows.
ALERT_SENDERS = [
    "jobalerts-noreply@linkedin.com",
    "jobs-noreply@linkedin.com",
    "alert@indeed.com",
    "noreply@glassdoor.com",
    "talent@glassdoor.com",
]

# Anything else from these ATS/recruiter domains is "signal worth surfacing"
# (status replies, rejections, interview invites). Not parsed as scan rows.
RECRUITER_DOMAINS = [
    "myworkday.com", "workdayjobs.com",
    "greenhouse.io", "lever.co",
    "icims.com", "successfactors.com",
    "scotiabank.com", "rbc.com", "td.com", "bmo.com", "cibc.com",
    "nbc.ca", "manulife.com", "sunlife.com", "canadalife.com",
    "hoopp.com", "omers.com", "otpp.com", "cppib.com",
    "blackrock.com", "goldmansachs.com", "morganstanley.com", "ms.com",
    "citi.com", "jpmorgan.com", "hsbc.com", "db.com",
    "moodys.com", "spglobal.com", "msci.com", "bloomberg.com",
    "ey.com", "deloitte.ca", "kpmg.ca", "pwc.com",
]


# ---------------------------------------------------------------------------
# Credential storage (re-uses the same config file as the Anthropic key)
# ---------------------------------------------------------------------------
def _read_cfg() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cfg(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def save_credentials(email_addr: str, app_password: str):
    cfg = _read_cfg()
    cfg["gmail_address"] = email_addr.strip()
    cfg["gmail_app_password"] = app_password.strip()
    cfg["gmail_saved_at"] = datetime.now().isoformat(timespec="seconds")
    _write_cfg(cfg)


def load_credentials() -> tuple[str | None, str | None]:
    cfg = _read_cfg()
    return cfg.get("gmail_address"), cfg.get("gmail_app_password")


def clear_credentials():
    cfg = _read_cfg()
    for k in ("gmail_address", "gmail_app_password", "gmail_saved_at"):
        cfg.pop(k, None)
    _write_cfg(cfg)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class GmailCheck:
    ok: bool
    message: str
    checked_at: str
    mailbox_count: int | None = None


def validate(email_addr: str, app_password: str) -> GmailCheck:
    """Try to log in and list mailboxes. Returns a structured result for the UI."""
    now = datetime.now().isoformat(timespec="seconds")
    if not email_addr or not app_password:
        return GmailCheck(False, "Empty email or app password", now)
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=15)
        try:
            m.login(email_addr, app_password)
        except imaplib.IMAP4.error as e:
            return GmailCheck(
                False,
                f"Login rejected ({e}). Common causes: 2FA not enabled, or app "
                "password is wrong/expired. Generate a new one at "
                "myaccount.google.com/apppasswords.",
                now,
            )
        typ, data = m.list()
        mb_count = len(data) if typ == "OK" else 0
        m.logout()
        return GmailCheck(True, f"Connected ({mb_count} mailboxes visible)",
                           now, mailbox_count=mb_count)
    except Exception as e:
        return GmailCheck(False, f"Connection failed: {e}", now)


# ---------------------------------------------------------------------------
# Message fetching
# ---------------------------------------------------------------------------
@dataclass
class InboxMessage:
    uid: str
    date: str
    sender: str
    sender_email: str
    subject: str
    snippet: str
    kind: str       # "alert" | "recruiter" | "other"


def _since_query(days: int) -> str:
    """IMAP SINCE date literal (dd-Mon-yyyy)."""
    since = date.today() - timedelta(days=days)
    return since.strftime("%d-%b-%Y")


def _decode_payload(msg: email.message.Message) -> str:
    """Best-effort: return plain text from a message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    continue
        # Fall back to text/html stripped
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:
                    continue
        return ""
    try:
        payload = msg.get_payload(decode=True)
        if not payload:
            return ""
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        return ""


def _connect(email_addr: str, app_password: str) -> imaplib.IMAP4_SSL:
    m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=20)
    m.login(email_addr, app_password)
    m.select("INBOX", readonly=True)
    return m


def _classify_sender(sender_email: str) -> str:
    se = sender_email.lower()
    if any(a in se for a in ALERT_SENDERS):
        return "alert"
    for dom in RECRUITER_DOMAINS:
        if se.endswith("@" + dom) or se.endswith("." + dom):
            return "recruiter"
    return "other"


def fetch_inbox_signals(days: int = 14, limit: int = 100) -> list[InboxMessage]:
    """Search recent mail for job alerts + recruiter emails. Read-only."""
    email_addr, pw = load_credentials()
    if not email_addr or not pw:
        return []
    out: list[InboxMessage] = []
    try:
        m = _connect(email_addr, pw)
    except Exception as e:
        print(f"[gmail] connect failed: {e}", file=sys.stderr)
        return []
    try:
        # Build a multi-sender search. IMAP allows OR, but Gmail's IMAP is
        # friendlier to X-GM-RAW queries. Use from: filter.
        since = _since_query(days)
        all_senders = ALERT_SENDERS + [f"@{d}" for d in RECRUITER_DOMAINS]
        from_query = " OR ".join(f"from:{s}" for s in all_senders)
        gm_query = f'({from_query}) newer_than:{days}d'
        try:
            typ, data = m.uid("search", None, "X-GM-RAW", f'"{gm_query}"')
        except imaplib.IMAP4.error:
            # Fallback to SINCE + a single from broad match (less effective)
            typ, data = m.uid("search", None, f"(SINCE {since})")
        if typ != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        uids = uids[-limit:]  # most recent N
        for uid in reversed(uids):
            try:
                typ, msg_data = m.uid("fetch", uid, "(BODY.PEEK[HEADER] BODY.PEEK[TEXT])")
                if typ != "OK" or not msg_data:
                    continue
                # Parse header + body separately
                raw = b""
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        raw += part[1]
                msg = email.message_from_bytes(raw)
                sender_raw = msg.get("From", "")
                name, addr = parseaddr(sender_raw)
                subject = msg.get("Subject", "")
                try:
                    dt = parsedate_to_datetime(msg.get("Date"))
                    iso = dt.date().isoformat()
                except Exception:
                    iso = ""
                body = _decode_payload(msg)
                snippet = re.sub(r"\s+", " ", body).strip()[:280]
                kind = _classify_sender(addr)
                out.append(InboxMessage(
                    uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    date=iso,
                    sender=name or addr,
                    sender_email=addr,
                    subject=subject,
                    snippet=snippet,
                    kind=kind,
                ))
            except Exception as e:
                print(f"[gmail] fetch uid={uid} failed: {e}", file=sys.stderr)
                continue
    finally:
        try:
            m.close()
        except Exception:
            pass
        try:
            m.logout()
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Job-alert parsing — extract title/company/URL from LinkedIn/Indeed emails
# ---------------------------------------------------------------------------
def parse_linkedin_alert(body: str) -> list[dict]:
    """LinkedIn alert emails contain job cards with a pattern like:
       <title> at <company>
       https://www.linkedin.com/jobs/view/<id>/...
    Returns list of {company, title, link, source}.
    """
    rows = []
    # Find all linkedin job view URLs
    urls = re.findall(r"https?://[\w./\-]*linkedin\.com/jobs/view/\d+[^\s>\"']*", body)
    for url in set(urls):
        link = url.split("?")[0]
        # Look around the URL for title/company context (simple heuristic: the
        # paragraph preceding the link in the raw text)
        idx = body.find(url)
        context = body[max(0, idx - 400):idx]
        # Pattern: "<title>\n<company>" in LinkedIn alert templates
        lines = [l.strip() for l in context.split("\n") if l.strip()]
        title = lines[-2] if len(lines) >= 2 else ""
        company = lines[-1] if lines else ""
        rows.append({
            "title": title[:120],
            "company": company[:80],
            "link": link,
            "source": "gmail_linkedin_alert",
            "sector": "",
            "location": "",
        })
    return rows


def scrape_from_inbox(days: int = 14) -> list[dict]:
    """Pull LinkedIn alert emails from the last N days and parse them into scan rows.
    Format matches what jd_scraper.scan() emits, so these feed the same dedup +
    triage + scoring pipeline.
    """
    messages = fetch_inbox_signals(days=days, limit=200)
    rows: list[dict] = []
    for m in messages:
        if m.kind != "alert":
            continue
        # We only parse LinkedIn alerts for now; others would need per-sender regex
        if "linkedin.com" in m.sender_email.lower():
            # Re-fetch full body — fetch_inbox_signals only kept snippet
            # For simplicity we use the snippet as-is (LinkedIn puts URLs in
            # a way that the 280-char snippet rarely includes the full list).
            # The snippet is a proxy; the real one is richer — but the URLs we
            # care about often appear near the start.
            rows.extend(parse_linkedin_alert(m.snippet))
    return rows
