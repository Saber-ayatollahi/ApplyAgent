"""Gmail sidebar widget + helpers for the Streamlit UI.

Pairs with automation/gmail_reader.py. Intentionally mirrors api_key.py's
shape so both credentials panels behave the same way in the sidebar.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

# Expose the automation module without hard-coding a path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "automation"))
import gmail_reader as gr  # noqa: E402

# Re-validation cadence. Without this, every page render hits IMAP if the
# previous result was a failure — fast on a closed-port network, but a 15s
# stall per page on a silent-drop network. TTL-cache both success and
# failure so the sidebar stays responsive.
_CHECK_TTL_OK_S = 15 * 60      # success: re-check every 15 min
_CHECK_TTL_FAIL_S = 5 * 60     # failure: retry every 5 min


def mask(email_addr: str | None) -> str:
    if not email_addr:
        return "—"
    at = email_addr.find("@")
    if at <= 2:
        return email_addr
    return email_addr[:2] + "…" + email_addr[at:]


def _is_login_rejected(check: gr.GmailCheck | None) -> bool:
    """Distinguish 'wrong creds' (user-fixable) from 'network/firewall' (env)."""
    if not check or check.ok:
        return False
    return "Login rejected" in (check.message or "")


def _is_tls_intercepted(check: gr.GmailCheck | None) -> bool:
    """Did the connection get killed mid-TLS-handshake? Signature of an
    antivirus / corporate-proxy / VPN doing TLS inspection on port 993.
    The TCP socket opened (we can reach the server) but TLS dies. Almost
    never the user's fault and almost never fixable from inside the app.
    """
    if not check or check.ok:
        return False
    msg = (check.message or "").lower()
    return ("10054" in msg
            or "wsaeconnreset" in msg
            or "forcibly closed" in msg
            or "tls" in msg and "handshake" in msg)


def _check_age_s(check: gr.GmailCheck | None) -> float | None:
    if not check or not check.checked_at:
        return None
    try:
        from datetime import datetime
        ts = datetime.fromisoformat(check.checked_at).timestamp()
        return max(time.time() - ts, 0.0)
    except Exception:
        return None


def render_sidebar():
    email_addr, pw = gr.load_credentials()
    check: gr.GmailCheck | None = st.session_state.get("_gmail_check")

    # Re-validate when either:
    #   - we have no result yet (first paint after creds saved), or
    #   - the cached result is older than its TTL (success: 15m, failure: 5m).
    # Without this gate, a transient network failure pinned the sidebar in
    # red error state for the entire session; a silent-drop network also
    # blocked rendering 15s per page.
    if email_addr and pw:
        age = _check_age_s(check)
        ttl = _CHECK_TTL_OK_S if (check and check.ok) else _CHECK_TTL_FAIL_S
        if check is None or (age is not None and age > ttl):
            check = gr.validate(email_addr, pw)
            st.session_state["_gmail_check"] = check

    # Header badge. Login-rejected = red (user must fix creds). Network /
    # connection failure = yellow (env, often firewall/VPN — not actionable
    # from the UI).
    if not email_addr:
        st.sidebar.warning("📬 Gmail not connected", icon="✉️")
    elif check and check.ok:
        st.sidebar.success(f"📬 Gmail OK · {mask(email_addr)}", icon="✅")
    elif check and not check.ok:
        if _is_login_rejected(check):
            st.sidebar.error(f"📬 Gmail login rejected · {mask(email_addr)}",
                              icon="❌")
        else:
            st.sidebar.warning(
                f"📬 Gmail unreachable · {mask(email_addr)}",
                icon="⚠️",
            )
    else:
        st.sidebar.info(f"📬 Gmail unchecked · {mask(email_addr)}", icon="❓")

    with st.sidebar.expander("Connect Gmail (read-only)",
                              expanded=not bool(email_addr)):
        st.caption(
            "Uses IMAP with a Gmail **app password** (not your normal password). "
            "Takes ~60s to set up: enable 2FA if not on, generate a password at "
            "[myaccount.google.com/apppasswords]"
            "(https://myaccount.google.com/apppasswords), paste below. "
            "Read-only — we never send or delete mail."
        )

        # Persistent save-result banner. The previous code did
        # st.success/st.error inside the click handler followed by
        # st.rerun() — which discards both before the user can read
        # them. Now we stash the verdict in session_state and surface
        # it on the *next* render so it stays visible.
        _save_msg = st.session_state.pop("_gmail_save_msg", None)
        if _save_msg:
            kind = _save_msg.get("kind", "info")
            txt = _save_msg.get("text", "")
            renderer = {
                "success": st.success,
                "error":   st.error,
                "warning": st.warning,
                "info":    st.info,
            }.get(kind, st.info)
            renderer(txt)

        new_email = st.text_input(
            "Gmail address",
            value=email_addr or "",
            placeholder="you@gmail.com",
            key="_gmail_email_input",
        )
        new_pw = st.text_input(
            "App password (16 characters)",
            value="",
            type="password",
            placeholder="xxxx xxxx xxxx xxxx",
            key="_gmail_pw_input",
            help="Generate at myaccount.google.com/apppasswords",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("💾 Save", width='stretch',
                         disabled=not (new_email.strip() and new_pw.strip()),
                         key="_gmail_save"):
                # Strip Gmail's habit of formatting with spaces
                pw_clean = new_pw.replace(" ", "").strip()
                try:
                    gr.save_credentials(new_email.strip(), pw_clean)
                except Exception as e:
                    st.session_state["_gmail_save_msg"] = {
                        "kind": "error",
                        "text": (f"❌ Save failed (filesystem error): {e}\n\n"
                                  f"Target path: `{gr.CONFIG_PATH}`"),
                    }
                    st.rerun()
                # Confirm the file actually landed and loads back what we wrote
                saved_email, saved_pw = gr.load_credentials()
                if not saved_email or saved_pw != pw_clean:
                    st.session_state["_gmail_save_msg"] = {
                        "kind": "error",
                        "text": ("❌ Save appeared to succeed but reading back "
                                  "failed or returned different data. Check "
                                  f"`{gr.CONFIG_PATH}` manually — it should "
                                  "contain gmail_address and gmail_app_password "
                                  "keys."),
                    }
                    st.rerun()
                res = gr.validate(new_email.strip(), pw_clean)
                st.session_state["_gmail_check"] = res
                # Distinguish "credentials saved" from "IMAP probe succeeded".
                # Past UI conflated them, so a yellow "Connection failed"
                # banner read like a save failure when in fact the file
                # WAS written and the credentials are persisted.
                if res.ok:
                    st.session_state["_gmail_save_msg"] = {
                        "kind": "success",
                        "text": (f"✅ **Credentials saved** to "
                                  f"`{gr.CONFIG_PATH.name}` and Gmail "
                                  f"connection verified ({res.message})."),
                    }
                elif _is_login_rejected(res):
                    st.session_state["_gmail_save_msg"] = {
                        "kind": "error",
                        "text": (f"💾 **Credentials saved** to "
                                  f"`{gr.CONFIG_PATH.name}` — but Gmail "
                                  f"REJECTED the login: {res.message}\n\n"
                                  "→ Generate a fresh app password at "
                                  "myaccount.google.com/apppasswords. "
                                  "Make sure 2FA is enabled."),
                    }
                else:
                    st.session_state["_gmail_save_msg"] = {
                        "kind": "warning",
                        "text": (f"💾 **Credentials saved** to "
                                  f"`{gr.CONFIG_PATH.name}` — but Gmail "
                                  f"was unreachable for the verify probe: "
                                  f"{res.message}\n\n"
                                  "Likely a firewall/VPN/network issue. "
                                  "Your password is persisted; click "
                                  "🔄 Test once the network is OK to verify."),
                    }
                st.rerun()
        with c2:
            if st.button("🔄 Test", width='stretch',
                         disabled=not (email_addr and pw),
                         key="_gmail_test"):
                res = gr.validate(email_addr, pw)
                st.session_state["_gmail_check"] = res
                st.rerun()
        with c3:
            if st.button("🗑 Clear", width='stretch',
                         disabled=not email_addr,
                         key="_gmail_clear"):
                gr.clear_credentials()
                st.session_state.pop("_gmail_check", None)
                st.warning("Cleared.")
                st.rerun()

        if check:
            if check.ok:
                st.caption(f"✅ Checked {check.checked_at} — {check.message}")
            else:
                st.caption(f"❌ Checked {check.checked_at} — {check.message}")
                # When the failure is the TLS-intercepted signature
                # (WinError 10054 / "forcibly closed"), surface the
                # remediation steps inline. The user shouldn't have to
                # run the diagnostic to learn this is an environmental
                # block, not anything they typed wrong.
                if _is_tls_intercepted(check):
                    st.warning(
                        "**This looks like a network-side TLS block** "
                        "(antivirus / corporate firewall / VPN intercepting "
                        "port 993). Your credentials are fine.",
                        icon="🛡️",
                    )
                    st.markdown(
                        "**What to try, in order:**\n"
                        "1. Disconnect any corporate VPN; click 🔄 Test.\n"
                        "2. Tether to your phone hotspot; click 🔄 Test. "
                        "If that works, your work network is blocking IMAP — "
                        "no fix from inside this app.\n"
                        "3. In your antivirus, exclude port 993 from "
                        "*TLS/SSL scanning* or *encrypted-traffic* inspection. "
                        "Common culprits: Kaspersky, McAfee, Symantec, ESET, "
                        "BitDefender.\n"
                        "4. Run 🩺 **Full diagnostic** below for a step-by-step "
                        "trace if you want to see exactly where it dies."
                    )

        # Diagnostic runner — walks DNS/TCP/TLS/LOGIN/SELECT/SEARCH/FETCH
        # and prints where it breaks. Useful when the one-line "Login rejected"
        # from validate() doesn't tell you whether it's creds, network, or a
        # firewall/proxy in the way.
        st.markdown("---")
        if st.button("🩺 Run full diagnostic",
                     disabled=not (email_addr and pw),
                     width='stretch',
                     key="_gmail_diagnose",
                     help="Step-by-step probe of config → DNS → TCP → TLS → "
                          "LOGIN → SELECT → SEARCH → FETCH. Takes ~5 seconds."):
            import subprocess
            try:
                script = (Path(__file__).resolve().parent.parent
                           / "automation" / "gmail_diagnose.py")
                r = subprocess.run(
                    [sys.executable, str(script), "--days", "14"],
                    capture_output=True, text=True, timeout=60,
                )
                out = r.stdout + (r.stderr if r.returncode else "")
                # Strip ANSI color codes for Streamlit code block
                import re as _re
                out = _re.sub(r"\x1b\[[0-9;]*m", "", out)
                if r.returncode == 0:
                    st.success("Diagnostic passed — Gmail is healthy.")
                else:
                    st.error(f"Diagnostic failed (exit {r.returncode}). See below.")
                st.code(out or "(no output)", language="text")
            except Exception as e:
                st.error(f"Could not run diagnostic: {e}")


def is_connected() -> bool:
    check: gr.GmailCheck | None = st.session_state.get("_gmail_check")
    return bool(check and check.ok)
