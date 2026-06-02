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
    "jobs-listings@linkedin.com",   # LinkedIn job listing digests
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
    """Best-effort: return the richest body we can.

    LinkedIn job-alert digests are multipart/alternative: the text/plain
    part has a 'See all jobs' CTA but NO per-job URLs — every /jobs/view/<id>
    link lives ONLY in the text/html part. The previous implementation
    preferred text/plain, so the parser received a body with nothing to
    extract and `harvested 0 raw alert row(s)` even when the inbox had
    dozens of digests. We now prefer HTML for alert senders and fall
    back to plain only when no HTML part exists. We also return the raw
    HTML (not tag-stripped) so parse_linkedin_alert's bs4 anchor walker
    has structure to work with.
    """
    if msg.is_multipart():
        html_body = ""
        text_body = ""
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    continue
            elif ct == "text/plain" and not text_body:
                try:
                    text_body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    continue
        # HTML wins: parse_linkedin_alert preferentially uses bs4 anchors
        # when '<' and '>' both appear, falling back to text regex otherwise.
        if html_body:
            return html_body
        return text_body
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


def fetch_inbox_signals(days: int = 14, limit: int = 100,
                         include_body: bool = False) -> list[InboxMessage]:
    """Search recent mail for job alerts + recruiter emails. Read-only.

    If `include_body=True`, each InboxMessage carries the full decoded body in
    `.snippet` (truncated only to 200k chars to cap memory). Default keeps the
    legacy 280-char snippet behavior so existing callers don't pay for body
    decode they don't need.
    """
    email_addr, pw = load_credentials()
    if not email_addr or not pw:
        return []
    out: list[InboxMessage] = []
    m = _connect(email_addr, pw)
    try:
        # Build a multi-sender search. IMAP allows OR, but Gmail's IMAP is
        # friendlier to X-GM-RAW queries. Use from: filter.
        all_senders = ALERT_SENDERS + [f"@{d}" for d in RECRUITER_DOMAINS]
        from_query = " OR ".join(f"from:{s}" for s in all_senders)
        gm_query = f'({from_query}) newer_than:{days}d'
        uids: list[bytes] = []
        try:
            typ, data = m.uid("search", None, "X-GM-RAW", f'"{gm_query}"')
            if typ == "OK" and data and data[0]:
                uids = data[0].split()
        except imaplib.IMAP4.error:
            uids = []

        # Fallback: IMAP OR-chained from: search over the date window. Avoids
        # the prior behavior of returning every message in the last N days.
        if not uids:
            since = _since_query(days)
            for sender in all_senders:
                try:
                    typ, data = m.uid(
                        "search", None,
                        f'(SINCE {since} FROM "{sender}")',
                    )
                    if typ == "OK" and data and data[0]:
                        uids.extend(data[0].split())
                except imaplib.IMAP4.error:
                    continue
            # Dedup while preserving order
            uids = list(dict.fromkeys(uids))

        if not uids:
            return []
        uids = uids[-limit:]  # most recent N
        for uid in reversed(uids):
            try:
                # RFC822 fetches the complete raw message in one shot.
                # BODY.PEEK[HEADER]+BODY.PEEK[TEXT] reassembly was dropping
                # headers in some Gmail IMAP responses, leaving sender_email=""
                # and every email classified as kind="other" (skipped).
                typ, msg_data = m.uid("fetch", uid, "(RFC822)")
                if typ != "OK" or not msg_data:
                    continue
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
                if include_body:
                    # Cap at 200k chars — LinkedIn digests rarely exceed ~60k.
                    payload_text = body[:200_000]
                else:
                    payload_text = re.sub(r"\s+", " ", body).strip()[:280]
                kind = _classify_sender(addr)
                out.append(InboxMessage(
                    uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    date=iso,
                    sender=name or addr,
                    sender_email=addr,
                    subject=subject,
                    snippet=payload_text,
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
try:
    from bs4 import BeautifulSoup  # type: ignore
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False


# Strip LinkedIn's tracking wrappers (t.email.linkedin.com redirect + query
# params) so the canonical jobs/view URL collapses to one per posting.
_LI_JOB_RE = re.compile(r"https?://[^\s\"'<>]*linkedin\.com/[^\s\"'<>]*jobs/view/(\d+)[^\s\"'<>]*",
                        re.IGNORECASE)


def _canonical_li_job_url(raw_url: str) -> str | None:
    """Return canonical https://www.linkedin.com/jobs/view/<id> or None if not a
    job URL. Handles tracking redirects (linkedin.com/comm/jobs/view/...,
    url?trk=...) by collapsing to the job id."""
    m = _LI_JOB_RE.search(raw_url or "")
    if not m:
        return None
    return f"https://www.linkedin.com/jobs/view/{m.group(1)}"


# LinkedIn alert digest cards pack title + company + location + activity-text
# into one cell. When cell_lines splitting goes sideways (multiple anchors,
# encoding mojibake of the · separator, single-line cells), we end up with
# trailing junk in `title` ("Senior Manager … BMO · Toronto, ON 12 connections"),
# location stuffed into `company`, or activity-text in `location`. This pass
# normalizes after-the-fact so dedup keys are clean.
#
# Treats both real `· ` (U+00B7) and the mojibake `�` (replacement char
# from broken UTF-8 round-trips) as separators — we've seen the latter on
# scans persisted before stdio was reconfigured.
_ALERT_SEP = r"\s+(?:[·�]|[-–—])\s+"
# Title-only separator: the company·location subtitle cell is ALWAYS introduced
# by the LinkedIn middle-dot (·) or its mojibake (�), NEVER by a hyphen. A bare
# dash in a title is part of the role name ("Senior Manager - Customer Risk
# Analysis"), so splitting titles on it truncates distinct roles into generic
# stems ("Senior Manager") and drives false near-dup merges. Mode C uses THIS;
# the company/location splits keep _ALERT_SEP (their cells can use a dash).
_ALERT_TITLE_SEP = r"\s+[·�]\s+"
_ALERT_ACTIVITY_PHRASE = (
    r"(?:Actively recruiting|"
    r"\d+\s+(?:connection|connections|company alumni|school alumni|alumni)|"
    r"Promoted)"
)
_ALERT_ACTIVITY_TAIL = re.compile(
    rf"\s+{_ALERT_ACTIVITY_PHRASE}\s*$",
    re.IGNORECASE,
)
# Used when the activity phrase IS the whole field (e.g. location='23 connections')
_ALERT_ACTIVITY_BARE = re.compile(
    rf"^{_ALERT_ACTIVITY_PHRASE}$",
    re.IGNORECASE,
)
_ALERT_MODE_TAIL = re.compile(
    r"\s*\((?:Hybrid|On-?site|Remote)\)\s*$",
    re.IGNORECASE,
)


def _clean_alert_fields(title: str, company: str, location: str
                         ) -> tuple[str, str, str]:
    """Normalize LinkedIn-alert (title, company, location) so dedup keys match
    web-scrape rows. See module-level comment for the failure modes this fixes."""
    # Strip activity-text tails (trailing) that might have stuck to any field
    title = _ALERT_ACTIVITY_TAIL.sub("", title or "").strip()
    company = _ALERT_ACTIVITY_TAIL.sub("", company or "").strip()
    location = _ALERT_ACTIVITY_TAIL.sub("", location or "").strip()

    # Failure mode A: activity text IS the entire location (e.g. "23 connections",
    # "Actively recruiting"). Bare-form match — drop it.
    if location and _ALERT_ACTIVITY_BARE.match(location):
        location = ""

    # Failure mode B: `company` field contains "<co> · <loc>" — split it
    if company and re.search(_ALERT_SEP, company):
        parts = re.split(_ALERT_SEP, company, maxsplit=1)
        if len(parts) == 2:
            company = parts[0].strip()
            new_loc = parts[1].strip()
            new_loc = _ALERT_MODE_TAIL.sub("", new_loc).strip()
            if not location:
                location = new_loc

    # Failure mode C: `title` field has the company-and-location echo trailing.
    # Drop everything from the middle-dot onward — the cell joins title to
    # subtitle that way. Split ONLY on the middle-dot (_ALERT_TITLE_SEP), never
    # a bare dash, so a hyphenated role ("Senior Manager - Customer Risk
    # Analysis") keeps its specialization instead of collapsing to "Senior
    # Manager" and false-merging with other roles at the same company.
    if title and re.search(_ALERT_TITLE_SEP, title):
        title = re.split(_ALERT_TITLE_SEP, title, maxsplit=1)[0].strip()

    # Failure mode D: title ends with the full company name redundantly. E.g.
    # "Treasury Manager KOHO" — drop the trailing company token if present.
    if title and company and len(company) >= 3:
        # Match company at end of title, allowing a leading space.
        co_re = re.escape(company)
        title = re.sub(rf"\s+{co_re}\s*$", "", title, flags=re.IGNORECASE).strip()

    # Location may also contain "<company> · <city>" from LinkedIn's
    # misrouted cell text. Keep only the rightmost segment (the actual geo).
    if location and re.search(_ALERT_SEP, location):
        location = re.split(_ALERT_SEP, location)[-1].strip()

    # Strip work-mode tail off location for parity with web scrape
    location = _ALERT_MODE_TAIL.sub("", location or "").strip()

    # Failure mode E: the title still carries a trailing location echo joined by
    # a bare dash ("<role> - Toronto, ON"). Mode C now splits titles ONLY on the
    # middle-dot (to preserve hyphenated role names), so a dash-joined location
    # echo survives into the title and pollutes the dedup key vs the web-scrape
    # lane (whose titles have no echo). Strip it, but ONLY when the trailing
    # segment matches the cleaned location field (full string or its city part),
    # so genuine hyphenated roles ("… Manager - Canada & HQ/DCs") are preserved.
    if title and location:
        _echoes = {location.strip().lower()}
        _city = location.split(",", 1)[0].strip()
        if _city:
            _echoes.add(_city.lower())
        # Test the suffix after EACH " - " separator (from the last inward).
        # The suffix may itself contain dashes (so hyphenated places like
        # "Winston-Salem, NC" match), but is only stripped when the whole
        # suffix equals a known echo — exact set membership, so a genuine
        # hyphenated role ("… Manager - Canada & HQ/DCs") is never removed.
        for _sep in re.finditer(r"\s+[-–—]\s+", title):
            if title[_sep.end():].strip().lower() in _echoes:
                title = title[: _sep.start()].strip()
                break
    # Mode D may have stripped a trailing company token that equalled the city,
    # leaving a dangling separator ("Senior Analyst -"); drop it for a clean key.
    title = re.sub(r"\s*[-–—]\s*$", "", title).strip()

    return title[:180], company[:120], location[:120]


def parse_linkedin_alert(body: str) -> list[dict]:
    """Extract job rows from a LinkedIn alert email body.

    Strategy:
      1. If the body has HTML, parse anchors. LinkedIn digest emails render
         each job card as <a href=".../jobs/view/<id>..."> wrapping both the
         title and (in a following cell) the company — reliable signal.
      2. Fallback to text parsing if no HTML anchors matched.

    Returns list of {company, title, link, source, sector, location} rows.
    `link` is always the canonical https://www.linkedin.com/jobs/view/<id>.
    Duplicate job ids are collapsed, keeping the richest (title,company) pair.
    """
    rows_by_id: dict[str, dict] = {}
    if _HAS_BS4 and "<" in body and ">" in body:
        try:
            soup = BeautifulSoup(body, "html.parser")
        except Exception:
            soup = None
        if soup is not None:
            for a in soup.find_all("a", href=True):
                canon = _canonical_li_job_url(a["href"])
                if not canon:
                    continue
                job_id = canon.rsplit("/", 1)[-1]

                # LinkedIn digest cards pack the whole job into ONE anchor's
                # text in this shape:
                #     <title> <company> · <location> <activity-text>
                # Where:
                #   - "title" is the role title (often inside <strong>)
                #   - "company · location" sits in the next cell line
                #   - "activity-text" is "Actively recruiting" / "N connections"
                # Older code grabbed the entire anchor text as `title` and
                # the second cell line as `company` — but that line was
                # "company · location" so we ended up with company=
                # "BMO · Toronto, ON" and title containing everything.
                # New strategy: pull title from <strong> if present, else
                # use the FIRST non-empty cell line; pull company+location
                # by splitting the SECOND cell line on the LinkedIn middle
                # dot (· U+00B7) or em-dash; drop the activity-text line.
                title = ""
                strong = a.find("strong")
                if strong:
                    title = " ".join(strong.get_text(" ", strip=True).split())

                company = ""
                location = ""
                cell = a.find_parent(["td", "div"])
                cell_lines: list[str] = []
                if cell is not None:
                    cell_text = cell.get_text("\n", strip=True)
                    cell_lines = [l.strip() for l in cell_text.split("\n") if l.strip()]
                elif a is not None:
                    anchor_text = a.get_text("\n", strip=True)
                    cell_lines = [l.strip() for l in anchor_text.split("\n") if l.strip()]

                if not title and cell_lines:
                    # Without <strong>, the first cell line is the title
                    title = cell_lines[0]

                # Find the company+location line — usually cell_lines[1].
                # Pattern: "Company · City, Region (Mode)" or "Company - City"
                co_loc = ""
                for line in cell_lines[1:]:
                    if title and line.startswith(title[:30]):
                        continue  # skip if it's the title repeating
                    co_loc = line
                    break

                if co_loc:
                    # Try common separators in priority order. " · " is the
                    # most common; em-dash and " - " are fallbacks.
                    for sep in (" · ", " · ", " — ", " – ", " - "):
                        if sep in co_loc:
                            company, _, location = co_loc.partition(sep)
                            break
                    else:
                        # No separator — assume the whole thing is the company
                        company = co_loc

                # Strip "(Hybrid)" / "(On-site)" / "(Remote)" tail from location
                # so the row is comparable to web-scrape rows from Workday.
                location = re.sub(r"\s*\((Hybrid|On-?site|Remote)\)\s*$",
                                   "", location, flags=re.IGNORECASE)

                title = title[:180]
                company = company.strip()[:120]
                location = location.strip()[:120]

                title, company, location = _clean_alert_fields(
                    title, company, location)

                existing = rows_by_id.get(job_id)
                if existing is None or (not existing.get("company") and company):
                    rows_by_id[job_id] = {
                        "title": title,
                        "company": company,
                        "link": canon,
                        "location": location,
                        "source": "gmail_linkedin_alert",
                        "sector": "",
                    }

    if rows_by_id:
        return [r for r in rows_by_id.values() if r.get("title") or r.get("company")]

    # Text fallback — digests sometimes arrive as plain text
    for match in _LI_JOB_RE.finditer(body):
        canon = _canonical_li_job_url(match.group(0))
        if not canon:
            continue
        job_id = canon.rsplit("/", 1)[-1]
        if job_id in rows_by_id:
            continue
        # Pull the two text lines preceding the URL as (title, company)
        idx = match.start()
        context = body[max(0, idx - 400):idx]
        lines = [l.strip() for l in context.split("\n") if l.strip()]
        title = lines[-2] if len(lines) >= 2 else ""
        company = lines[-1] if lines else ""
        title, company, location = _clean_alert_fields(
            title[:180], company[:120], "")
        rows_by_id[job_id] = {
            "title": title,
            "company": company,
            "link": canon,
            "source": "gmail_linkedin_alert",
            "sector": "",
            "location": location,
        }
    return [r for r in rows_by_id.values() if r.get("title") or r.get("company")]


def scrape_from_inbox(days: int = 14) -> list[dict]:
    """Pull LinkedIn alert emails from the last N days and parse them into scan rows.
    Format matches what jd_scraper.scan() emits, so these feed the same dedup +
    triage + scoring pipeline.

    Each returned row carries:
      - source: "gmail_linkedin_alert"
      - posted_date: the email's arrival date (best proxy we have for
        "when the recruiter surfaced this"). jd_scraper's stamp_found_at
        will overwrite found_at if the URL was seen earlier.
      - gmail_uid: IMAP UID of the source email, so the UI can later
        request deletion of only the alerts that produced rows.
    """
    messages = fetch_inbox_signals(days=days, limit=200, include_body=True)
    rows: list[dict] = []
    for msg in messages:
        if msg.kind != "alert":
            continue
        if "linkedin.com" not in msg.sender_email.lower():
            continue
        for row in parse_linkedin_alert(msg.snippet):
            row["posted_date"] = msg.date or None
            row["gmail_uid"] = msg.uid
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Mailbox mutation — move alert emails to Trash after we've harvested them.
# Read-only path stays the default everywhere else; this is the ONE function
# that opens IMAP read-write.
# ---------------------------------------------------------------------------
@dataclass
class TrashResult:
    moved: int
    failed: int
    errors: list[str]


# Gmail's localized-name Trash mailbox. The IMAP server advertises the
# canonical name via the \Trash special-use flag, but for English accounts
# this literal is the standard label and avoids a LIST round-trip.
_GMAIL_TRASH = "[Gmail]/Trash"


def _resolve_trash_mailbox(m: imaplib.IMAP4_SSL) -> str:
    """Find the trash mailbox by \\Trash flag; fall back to [Gmail]/Trash.

    Non-English Gmail accounts localize the label (e.g., [Gmail]/Papelera
    in Spanish). Walking LIST and looking for the \\Trash flag is the
    only reliable way to handle this without a config knob."""
    try:
        typ, data = m.list()
        if typ == "OK" and data:
            for line in data:
                if not line:
                    continue
                txt = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
                if "\\Trash" in txt:
                    # Format: '(\HasNoChildren \Trash) "/" "[Gmail]/Trash"'
                    # Split on quotes, take last quoted segment.
                    parts = txt.split('"')
                    if len(parts) >= 2:
                        return parts[-2]
    except Exception:
        pass
    return _GMAIL_TRASH


def delete_messages(uids: Iterable[str]) -> TrashResult:
    """Move the given IMAP UIDs to Gmail's Trash. Reversible (Gmail
    auto-purges Trash after 30 days; user can also restore manually).

    Uses UID MOVE (RFC 6851) when the server advertises it; falls back
    to UID COPY + UID STORE +Deleted + EXPUNGE on older servers."""
    uids = [str(u).strip() for u in uids if str(u).strip()]
    if not uids:
        return TrashResult(0, 0, [])
    email_addr, pw = load_credentials()
    if not email_addr or not pw:
        return TrashResult(0, len(uids), ["No Gmail credentials saved."])

    errors: list[str] = []
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=30)
        m.login(email_addr, pw)
    except Exception as e:
        return TrashResult(0, len(uids), [f"IMAP login failed: {e}"])

    moved = 0
    failed = 0
    try:
        # MUST select read-write; default elsewhere in this module is readonly.
        typ, _ = m.select("INBOX", readonly=False)
        if typ != "OK":
            return TrashResult(0, len(uids), ["INBOX SELECT failed"])

        trash = _resolve_trash_mailbox(m)
        # Capability check for UID MOVE
        has_move = False
        try:
            typ, caps = m.capability()
            if typ == "OK" and caps:
                cap_text = b" ".join(caps).decode("ascii", errors="replace").upper()
                has_move = "MOVE" in cap_text.split()
        except Exception:
            has_move = False

        # Batch into comma-separated UID set (IMAP supports 1,2,3 syntax).
        # Cap batches at 500 UIDs to stay well under server line-length limits.
        for i in range(0, len(uids), 500):
            chunk = uids[i:i + 500]
            uid_set = ",".join(chunk)
            try:
                if has_move:
                    typ, resp = m.uid("MOVE", uid_set, trash)
                    if typ == "OK":
                        moved += len(chunk)
                    else:
                        failed += len(chunk)
                        errors.append(f"UID MOVE failed: {resp}")
                else:
                    typ, resp = m.uid("COPY", uid_set, trash)
                    if typ != "OK":
                        failed += len(chunk)
                        errors.append(f"UID COPY failed: {resp}")
                        continue
                    typ, _ = m.uid("STORE", uid_set, "+FLAGS", r"(\Deleted)")
                    if typ != "OK":
                        failed += len(chunk)
                        errors.append("UID STORE +Deleted failed")
                        continue
                    m.expunge()
                    moved += len(chunk)
            except Exception as e:
                failed += len(chunk)
                errors.append(f"chunk failed: {e}")
    finally:
        try:
            m.close()
        except Exception:
            pass
        try:
            m.logout()
        except Exception:
            pass

    return TrashResult(moved=moved, failed=failed, errors=errors)
