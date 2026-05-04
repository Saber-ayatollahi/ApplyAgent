"""API key manager for the Streamlit UI.

Stores the Anthropic API key in a user-level config file outside the repo so
it survives Streamlit reruns and UI sessions:

    ~/.applyagent/config.json      {"anthropic_api_key": "sk-ant-..."}

On load, the key is injected into os.environ so subprocesses (fit_scorer,
jd_tailor, run_pipeline) inherit it automatically.

Validation is cheap: the Anthropic SDK's `client.models.list()` is a GET with
no token cost. We cache the result in st.session_state so the sidebar
doesn't thrash the API on every rerun.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

CONFIG_DIR = Path.home() / ".applyagent"
CONFIG_PATH = CONFIG_DIR / "config.json"
ENV_VAR = "ANTHROPIC_API_KEY"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_config(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Restrict perms (no-op on Windows but harmless)
    try:
        os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def save_key(key: str):
    cfg = _read_config()
    cfg["anthropic_api_key"] = key.strip()
    cfg["saved_at"] = datetime.now().isoformat(timespec="seconds")
    _write_config(cfg)


def clear_key():
    cfg = _read_config()
    cfg.pop("anthropic_api_key", None)
    cfg.pop("saved_at", None)
    _write_config(cfg)
    os.environ.pop(ENV_VAR, None)


def load_key() -> Optional[str]:
    """Return the effective key: environment wins, then config file."""
    env_key = os.environ.get(ENV_VAR, "").strip()
    if env_key:
        return env_key
    cfg = _read_config()
    k = (cfg.get("anthropic_api_key") or "").strip()
    return k or None


def hydrate_env():
    """Inject the stored key into os.environ (once per process). Subprocesses
    inherit this env, so fit_scorer/jd_tailor pick up the key automatically."""
    if os.environ.get(ENV_VAR):
        return
    k = load_key()
    if k:
        os.environ[ENV_VAR] = k


def mask(key: str) -> str:
    if not key:
        return "—"
    if len(key) <= 14:
        return key[:4] + "…"
    return f"{key[:10]}…{key[-4:]}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    ok: bool
    message: str
    checked_at: str
    model_count: int = 0


def validate(key: str) -> ValidationResult:
    """Cheap GET /v1/models with the key. No token spend."""
    if not key or not key.strip():
        return ValidationResult(False, "Empty key", datetime.now().isoformat(timespec="seconds"))
    try:
        import anthropic  # type: ignore
    except ImportError:
        return ValidationResult(False, "anthropic package not installed",
                                 datetime.now().isoformat(timespec="seconds"))
    try:
        client = anthropic.Anthropic(api_key=key.strip())
        # models.list() returns a SyncPage; iterate to force the call
        page = client.models.list(limit=5)
        models = list(page.data) if hasattr(page, "data") else list(page)
        return ValidationResult(
            True,
            f"Valid — {len(models)} models visible",
            datetime.now().isoformat(timespec="seconds"),
            model_count=len(models),
        )
    except Exception as e:
        msg = str(e)
        # Trim verbose API error JSON
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return ValidationResult(False, msg, datetime.now().isoformat(timespec="seconds"))


# ---------------------------------------------------------------------------
# Streamlit sidebar widget
# ---------------------------------------------------------------------------
def render_sidebar():
    """Render the API-key section in the Streamlit sidebar."""
    hydrate_env()
    key = load_key()
    validation: ValidationResult | None = st.session_state.get("_anth_validation")

    # Auto-validate once per session if we have a key and no result yet
    if key and validation is None:
        validation = validate(key)
        st.session_state["_anth_validation"] = validation

    # Header badge
    if not key:
        st.sidebar.error("🔑 API key not set", icon="⚠️")
    elif validation and validation.ok:
        st.sidebar.success(f"🔑 Key valid · {mask(key)}", icon="✅")
    elif validation and not validation.ok:
        st.sidebar.error(f"🔑 Key invalid · {mask(key)}", icon="❌")
    else:
        st.sidebar.warning(f"🔑 Key unchecked · {mask(key)}", icon="❓")

    with st.sidebar.expander("Manage Anthropic API key", expanded=not bool(key)):
        st.caption(
            f"Stored at `{CONFIG_PATH}` (user-level, outside the repo). "
            "Persists across Streamlit restarts. Subprocesses inherit it via env."
        )
        new_key = st.text_input(
            "Paste API key",
            value="",
            type="password",
            placeholder="sk-ant-...",
            key="_anth_key_input",
            help="Get one at https://console.anthropic.com/settings/keys",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("💾 Save & validate", use_container_width=True, disabled=not new_key.strip()):
                save_key(new_key)
                os.environ[ENV_VAR] = new_key.strip()
                res = validate(new_key)
                st.session_state["_anth_validation"] = res
                if res.ok:
                    st.success(f"Saved. {res.message}")
                else:
                    st.error(f"Saved but invalid: {res.message}")
                st.rerun()
        with c2:
            if st.button("🔄 Re-validate", use_container_width=True, disabled=not key):
                res = validate(key or "")
                st.session_state["_anth_validation"] = res
                st.rerun()
        with c3:
            if st.button("🗑 Clear", use_container_width=True, disabled=not key):
                clear_key()
                st.session_state.pop("_anth_validation", None)
                st.warning("Key cleared.")
                st.rerun()

        if validation:
            if validation.ok:
                st.caption(f"✅ Checked {validation.checked_at} — {validation.message}")
            else:
                st.caption(f"❌ Checked {validation.checked_at} — {validation.message}")

        cfg = _read_config()
        if cfg.get("saved_at"):
            st.caption(f"Saved at: {cfg['saved_at']}")


def is_key_valid() -> bool:
    """Caller-facing helper: is there a key AND did validation succeed?"""
    v: ValidationResult | None = st.session_state.get("_anth_validation")
    return bool(v and v.ok)
