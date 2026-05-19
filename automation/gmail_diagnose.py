#!/usr/bin/env python3
"""gmail_diagnose.py -- Walk the Gmail IMAP connection end-to-end and print
exactly where it fails. Run this when the sidebar says "Gmail error" or when
scrape_from_inbox returns nothing and you can't tell why.

Steps checked, in order:
  1. Config file readable at ~/.applyagent/config.json
  2. Credentials present and look well-formed
  3. DNS resolves imap.gmail.com
  4. TCP socket reaches imap.gmail.com:993
  5. SSL handshake completes
  6. LOGIN accepted
  7. SELECT INBOX works (readonly)
  8. A small SEARCH returns without error
  9. Fetching one recent message header works
 10. Gmail X-GM-RAW extension is available

Usage:
    python automation/gmail_diagnose.py
    python automation/gmail_diagnose.py --days 7      # narrower test window
    python automation/gmail_diagnose.py --verbose     # print full IMAP traffic
"""
from __future__ import annotations

import argparse
import imaplib
import socket
import ssl
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
import gmail_reader as gr  # noqa: E402


def _ok(msg: str):   print(f"  \033[32m[PASS]\033[0m {msg}")
def _warn(msg: str): print(f"  \033[33m[WARN]\033[0m {msg}")
def _fail(msg: str): print(f"  \033[31m[FAIL]\033[0m {msg}")
def _info(msg: str): print(f"         {msg}")


def step(n: int, title: str):
    print(f"\n[{n}] {title}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14,
                    help="How many days back to test SEARCH (default 14).")
    ap.add_argument("--verbose", action="store_true",
                    help="Print full IMAP protocol traffic (noisy but diagnostic).")
    args = ap.parse_args()

    if args.verbose:
        imaplib.Debug = 4  # dumps every command/response

    # ---- 1. Config file ----
    step(1, f"Config file at {gr.CONFIG_PATH}")
    if not gr.CONFIG_PATH.exists():
        _fail(f"No config file. Save credentials via the UI sidebar, or create "
              f"{gr.CONFIG_PATH} manually with gmail_address + gmail_app_password keys.")
        return 1
    _ok(f"File exists ({gr.CONFIG_PATH.stat().st_size} bytes)")

    # ---- 2. Credentials look well-formed ----
    step(2, "Credentials load and look well-formed")
    email_addr, pw = gr.load_credentials()
    if not email_addr:
        _fail("gmail_address is missing from config.json")
        return 1
    if not pw:
        _fail("gmail_app_password is missing from config.json")
        return 1
    _ok(f"email: {email_addr}")
    if "@" not in email_addr:
        _warn(f"email looks malformed (no @): {email_addr}")
    pw_stripped = pw.replace(" ", "")
    if len(pw_stripped) != 16:
        _warn(f"app password is {len(pw_stripped)} chars (Gmail app passwords are 16). "
              "Could be intentional but usually indicates a copy-paste error.")
    else:
        _ok("app password is 16 characters (expected shape)")

    # ---- 3. DNS ----
    step(3, f"DNS resolves {gr.IMAP_HOST}")
    try:
        ip = socket.gethostbyname(gr.IMAP_HOST)
        _ok(f"{gr.IMAP_HOST} -> {ip}")
    except socket.gaierror as e:
        _fail(f"DNS lookup failed: {e}. Check network / VPN / corporate DNS.")
        return 1

    # ---- 4. TCP + 5. TLS ----
    step(4, f"TCP reach {gr.IMAP_HOST}:{gr.IMAP_PORT}")
    try:
        sock = socket.create_connection((gr.IMAP_HOST, gr.IMAP_PORT), timeout=10)
        _ok("TCP connected")
    except socket.timeout:
        _fail(f"TCP timeout. Port {gr.IMAP_PORT} likely blocked by firewall/proxy. "
              "If you're on a corporate network, try from a personal hotspot.")
        return 1
    except OSError as e:
        _fail(f"TCP failed: {e}")
        return 1

    step(5, "TLS handshake")
    try:
        ctx = ssl.create_default_context()
        tls = ctx.wrap_socket(sock, server_hostname=gr.IMAP_HOST)
        cert = tls.getpeercert()
        subject = dict(x[0] for x in cert.get("subject", []))
        _ok(f"TLS OK · cert CN={subject.get('commonName', '?')}")
        tls.close()
    except ssl.SSLError as e:
        _fail(f"TLS handshake failed: {e}.")
        _info("Almost always a corporate MITM/AV doing TLS inspection on")
        _info("port 993, OR an outdated Python CA bundle. Try the same")
        _info("remediation as WinError 10054 (below).")
        sock.close()
        return 1
    except Exception as e:
        msg = str(e)
        _fail(f"TLS wrapper failed: {msg}")
        # WinError 10054 / WSAECONNRESET / "forcibly closed" is the
        # signature of antivirus or corporate-firewall TLS interception
        # on port 993. The TCP socket opens (step 4 passes) but the TLS
        # handshake gets killed as soon as the server cert is presented.
        if ("10054" in msg or "WSAECONNRESET" in msg
                or "forcibly closed" in msg.lower()):
            print()
            _info("Diagnosis: a security product on this machine or")
            _info("network is intercepting TLS on port 993 and breaking")
            _info("the handshake. Common culprits:")
            _info("  • Antivirus with 'TLS scanning' / 'SSL inspection'")
            _info("    (Kaspersky, McAfee, Symantec, ESET, BitDefender)")
            _info("  • Corporate proxy / TLS inspection appliance")
            _info("    (Zscaler, Netskope, Forcepoint, Cisco Umbrella)")
            _info("  • VPN forcing all traffic through a corporate gateway")
            _info("  • Local firewall rule blocking outbound 993")
            print()
            _info("What to try, in order of likelihood:")
            _info("  1. Disconnect any corporate VPN, retry.")
            _info("  2. Tether to your phone hotspot, retry.")
            _info("     If it works on hotspot, your work network is")
            _info("     blocking IMAP — there's no fix from this app side.")
            _info("  3. In your AV settings, exclude port 993 from")
            _info("     'TLS / encrypted-traffic scanning'.")
            _info("  4. If you have admin rights: temporarily disable")
            _info("     the AV's network-protection module and retry.")
            print()
            _info("Note: your saved credentials are fine. This is purely")
            _info("a network-path issue between this machine and Gmail.")
        sock.close()
        return 1

    # ---- 6. LOGIN ----
    step(6, "IMAP LOGIN")
    try:
        M = imaplib.IMAP4_SSL(gr.IMAP_HOST, gr.IMAP_PORT, timeout=20)
    except Exception as e:
        _fail(f"IMAP4_SSL construction failed: {e}")
        return 1
    try:
        typ, data = M.login(email_addr, pw_stripped)
        _ok(f"LOGIN accepted · response: {typ} {data}")
    except imaplib.IMAP4.error as e:
        msg = str(e)
        _fail(f"LOGIN rejected: {msg}")
        if "Invalid credentials" in msg or "AUTHENTICATIONFAILED" in msg:
            print()
            _info("Fix:")
            _info("  1. Confirm 2-Step Verification is ON at myaccount.google.com/security")
            _info("  2. Generate a fresh app password at myaccount.google.com/apppasswords")
            _info("     (old app passwords can be silently revoked after long inactivity,")
            _info("      password change, or enabling a new 2FA method)")
            _info("  3. Paste the new 16-char password in the UI (spaces auto-stripped)")
        elif "BLOCKED" in msg or "suspicious" in msg.lower():
            _info("Google may have blocked this sign-in. Check gmail.com -> Recent security events.")
        return 1

    # ---- 7. SELECT INBOX ----
    step(7, "SELECT INBOX (readonly)")
    try:
        typ, data = M.select("INBOX", readonly=True)
        if typ != "OK":
            _fail(f"SELECT INBOX returned {typ}: {data}")
            M.logout()
            return 1
        try:
            count = int(data[0].decode() if isinstance(data[0], bytes) else data[0])
            _ok(f"INBOX opened · ~{count} messages total")
        except Exception:
            _ok(f"INBOX opened · response: {data}")
    except Exception as e:
        _fail(f"SELECT INBOX failed: {e}")
        M.logout()
        return 1

    # ---- 8. SEARCH ----
    step(8, f"SEARCH recent ({args.days} days)")
    since = (date.today() - timedelta(days=args.days)).strftime("%d-%b-%Y")
    try:
        typ, data = M.uid("search", None, f"(SINCE {since})")
        if typ != "OK":
            _fail(f"SEARCH returned {typ}: {data}")
            M.logout()
            return 1
        uids = (data[0] or b"").split()
        _ok(f"SEARCH returned {len(uids)} UID(s) from the last {args.days} days")
        if not uids:
            _warn("Zero messages in window - gmail_reader will have nothing to parse. "
                  "Widen --days or check that alerts actually arrive in the inbox "
                  "(are they filtered into a label/folder?).")
    except Exception as e:
        _fail(f"SEARCH failed: {e}")
        M.logout()
        return 1

    # ---- 9. FETCH ----
    step(9, "FETCH most recent message header")
    if uids:
        try:
            last_uid = uids[-1]
            typ, resp = M.uid("fetch", last_uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK":
                _fail(f"FETCH returned {typ}")
            else:
                header_bytes = b""
                for part in resp:
                    if isinstance(part, tuple) and len(part) >= 2:
                        header_bytes += part[1]
                header_text = header_bytes.decode("utf-8", errors="replace")
                _ok("FETCH returned a header block")
                for line in header_text.splitlines()[:6]:
                    if line.strip():
                        _info(line[:120])
        except Exception as e:
            _fail(f"FETCH failed: {e}")
    else:
        _warn("No UIDs to fetch; skipping FETCH test")

    # ---- 10. Gmail extension ----
    step(10, "Gmail X-GM-RAW extension (used by gmail_reader's primary query)")
    try:
        typ, data = M.uid("search", None, "X-GM-RAW",
                           f'"from:jobalerts-noreply@linkedin.com newer_than:{args.days}d"')
        if typ == "OK":
            li_uids = (data[0] or b"").split()
            _ok(f"X-GM-RAW accepted · {len(li_uids)} LinkedIn alert(s) in last {args.days}d")
        else:
            _warn(f"X-GM-RAW returned {typ}: {data} (gmail_reader will fall back to per-sender SINCE)")
    except imaplib.IMAP4.error as e:
        _warn(f"X-GM-RAW not supported: {e}. Fallback will activate.")
    except Exception as e:
        _warn(f"X-GM-RAW query errored: {e}")

    # ---- Cleanup ----
    try:
        M.close()
    except Exception:
        pass
    M.logout()

    # ---- Integration probe ----
    step(11, "gmail_reader.fetch_inbox_signals smoke test")
    try:
        rows = gr.fetch_inbox_signals(days=args.days, limit=20)
        _ok(f"fetch_inbox_signals returned {len(rows)} message(s)")
        by_kind: dict[str, int] = {}
        for r in rows:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        for k, n in sorted(by_kind.items(), key=lambda x: -x[1]):
            _info(f"{k}: {n}")
    except Exception as e:
        _fail(f"fetch_inbox_signals raised: {e}")
        return 1

    print()
    print("=" * 60)
    print("  All steps passed. Gmail integration is healthy.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
