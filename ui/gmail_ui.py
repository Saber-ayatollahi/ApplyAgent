"""Gmail sidebar widget + helpers for the Streamlit UI.

Pairs with automation/gmail_reader.py. Intentionally mirrors api_key.py's
shape so both credentials panels behave the same way in the sidebar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Expose the automation module without hard-coding a path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "automation"))
import gmail_reader as gr  # noqa: E402


def mask(email_addr: str | None) -> str:
    if not email_addr:
        return "—"
    at = email_addr.find("@")
    if at <= 2:
        return email_addr
    return email_addr[:2] + "…" + email_addr[at:]


def render_sidebar():
    email_addr, pw = gr.load_credentials()
    check: gr.GmailCheck | None = st.session_state.get("_gmail_check")

    # Auto-validate once per session if we have creds and no result
    if email_addr and pw and check is None:
        check = gr.validate(email_addr, pw)
        st.session_state["_gmail_check"] = check

    # Header badge
    if not email_addr:
        st.sidebar.warning("📬 Gmail not connected", icon="✉️")
    elif check and check.ok:
        st.sidebar.success(f"📬 Gmail OK · {mask(email_addr)}", icon="✅")
    elif check and not check.ok:
        st.sidebar.error(f"📬 Gmail error · {mask(email_addr)}", icon="❌")
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
                    st.error(f"Save failed (filesystem error): {e}")
                    st.caption(f"Target path: `{gr.CONFIG_PATH}`")
                    st.stop()
                # Confirm the file actually landed and loads back what we wrote
                saved_email, saved_pw = gr.load_credentials()
                if not saved_email or saved_pw != pw_clean:
                    st.error(
                        "Save appeared to succeed but reading back failed or "
                        f"returned different data. Check `{gr.CONFIG_PATH}` "
                        "manually — it should contain gmail_address and "
                        "gmail_app_password keys."
                    )
                    st.stop()
                res = gr.validate(new_email.strip(), pw_clean)
                st.session_state["_gmail_check"] = res
                if res.ok:
                    st.success(f"Saved to {gr.CONFIG_PATH.name}. {res.message}")
                else:
                    st.error(f"Saved to {gr.CONFIG_PATH.name}, but: {res.message}")
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
