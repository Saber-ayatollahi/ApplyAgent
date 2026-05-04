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
# Failure categories — the UI distinguishes these so the user knows what to fix.
CATEGORY_OK = "ok"
CATEGORY_EMPTY = "empty"
CATEGORY_NO_SDK = "no_sdk"
CATEGORY_AUTH = "auth"          # invalid key / permission_denied
CATEGORY_CREDIT = "credit"      # valid key, but billing exhausted
CATEGORY_RATE = "rate_limit"    # 429
CATEGORY_NETWORK = "network"    # connection / timeout
CATEGORY_OTHER = "other"


@dataclass
class ValidationResult:
    ok: bool
    message: str
    checked_at: str
    category: str = CATEGORY_OTHER
    model_count: int = 0
    preflight_ok: bool = False   # True only if we confirmed credits/billing work


def _classify(err_msg: str) -> str:
    em = err_msg.lower()
    if "credit balance" in em or "billing" in em or "insufficient" in em:
        return CATEGORY_CREDIT
    if ("invalid_api_key" in em or "authentication" in em
            or "permission_denied" in em or "401" in em or "403" in em):
        return CATEGORY_AUTH
    if "rate_limit" in em or "429" in em:
        return CATEGORY_RATE
    if ("connection" in em or "timeout" in em or "timed out" in em
            or "getaddrinfo" in em or "networkerror" in em):
        return CATEGORY_NETWORK
    return CATEGORY_OTHER


def validate(key: str, preflight: bool = True) -> ValidationResult:
    """Validate the Anthropic API key.

    Two-step:
      1. Cheap GET /v1/models — confirms the key is well-formed and authenticated.
      2. (preflight=True) A 1-token messages.create call — confirms billing/credits
         are actually available. This is what catches 'credit balance too low'
         before the scorer burns 40 min producing 482 skip-verdicts.

    Total cost: ~1 input token + 1 output token per preflight. Essentially free.
    """
    now = lambda: datetime.now().isoformat(timespec="seconds")

    if not key or not key.strip():
        return ValidationResult(False, "Empty key", now(), category=CATEGORY_EMPTY)

    try:
        import anthropic  # type: ignore
    except ImportError:
        return ValidationResult(False, "anthropic package not installed",
                                 now(), category=CATEGORY_NO_SDK)

    key = key.strip()
    client = anthropic.Anthropic(api_key=key)

    # ── Step 1: auth check ────────────────────────────────────────────────
    try:
        page = client.models.list(limit=5)
        models = list(page.data) if hasattr(page, "data") else list(page)
        model_count = len(models)
    except Exception as e:
        msg = str(e)
        cat = _classify(msg)
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return ValidationResult(False, f"Auth failed: {msg}", now(), category=cat)

    if not preflight:
        return ValidationResult(
            True, f"Key authenticated — {model_count} models visible (preflight skipped)",
            now(), category=CATEGORY_OK, model_count=model_count, preflight_ok=False,
        )

    # ── Step 2: credit preflight — tiny messages.create ───────────────────
    try:
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
    except Exception as e:
        msg = str(e)
        cat = _classify(msg)
        if cat == CATEGORY_CREDIT:
            return ValidationResult(
                False,
                "Key authenticated but credits exhausted — top up at console.anthropic.com/settings/billing",
                now(), category=CATEGORY_CREDIT, model_count=model_count,
            )
        if cat == CATEGORY_RATE:
            # Rate-limited preflight isn't a blocker; treat as "probably OK"
            return ValidationResult(
                True,
                f"Authenticated; preflight hit rate limit (usually OK) — {model_count} models",
                now(), category=CATEGORY_RATE, model_count=model_count, preflight_ok=False,
            )
        if cat == CATEGORY_AUTH:
            return ValidationResult(
                False, f"Authenticated for models.list but messages blocked: {msg[:180]}",
                now(), category=CATEGORY_AUTH, model_count=model_count,
            )
        if len(msg) > 200:
            msg = msg[:200] + "…"
        return ValidationResult(False, f"Preflight failed: {msg}",
                                 now(), category=cat, model_count=model_count)

    return ValidationResult(
        True, f"Valid & credits OK — {model_count} models, billing works",
        now(), category=CATEGORY_OK, model_count=model_count, preflight_ok=True,
    )


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

    # Header badge — category-aware
    if not key:
        st.sidebar.error("🔑 API key not set", icon="⚠️")
    elif validation and validation.ok and validation.category == CATEGORY_OK:
        st.sidebar.success(f"🔑 Key valid · credits OK · {mask(key)}", icon="✅")
    elif validation and validation.category == CATEGORY_CREDIT:
        st.sidebar.error(f"💳 CREDITS EXHAUSTED · {mask(key)}", icon="🛑")
    elif validation and validation.category == CATEGORY_AUTH:
        st.sidebar.error(f"🔑 Key rejected · {mask(key)}", icon="❌")
    elif validation and validation.category == CATEGORY_NETWORK:
        st.sidebar.warning(f"🔑 Network issue · {mask(key)}", icon="🌐")
    elif validation and validation.ok:
        st.sidebar.info(f"🔑 Authenticated (preflight skipped) · {mask(key)}", icon="ℹ️")
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
            cat = validation.category
            stamp = validation.checked_at
            if cat == CATEGORY_OK:
                st.success(f"✅ {validation.message}\n\nChecked {stamp}")
            elif cat == CATEGORY_CREDIT:
                st.error(
                    f"💳 **Credits exhausted** — the key authenticates but your "
                    f"Anthropic account has no billing credit. The scorer would run "
                    f"through every candidate producing empty 'skip' verdicts.\n\n"
                    f"**Fix:** top up at "
                    f"[console.anthropic.com/settings/billing]"
                    f"(https://console.anthropic.com/settings/billing), "
                    f"then hit 🔄 Re-validate.\n\n"
                    f"Checked {stamp}"
                )
            elif cat == CATEGORY_AUTH:
                st.error(
                    f"❌ **Key rejected by the API.** Usually means the key was "
                    f"revoked, mistyped, or belongs to a deleted workspace.\n\n"
                    f"**Fix:** generate a new key at "
                    f"[console.anthropic.com/settings/keys]"
                    f"(https://console.anthropic.com/settings/keys) and paste it above.\n\n"
                    f"Checked {stamp} — {validation.message}"
                )
            elif cat == CATEGORY_NETWORK:
                st.warning(
                    f"🌐 **Network error** reaching the API. Check connectivity or "
                    f"VPN/proxy settings, then 🔄 Re-validate.\n\n"
                    f"Checked {stamp} — {validation.message}"
                )
            elif cat == CATEGORY_RATE:
                st.info(
                    f"⏱ **Rate-limited** during preflight. The key is probably fine; "
                    f"wait a moment and 🔄 Re-validate.\n\n"
                    f"Checked {stamp}"
                )
            else:
                st.warning(f"❓ {validation.message}\n\nChecked {stamp}")

        cfg = _read_config()
        if cfg.get("saved_at"):
            st.caption(f"Saved at: {cfg['saved_at']}")


def is_key_valid() -> bool:
    """Caller-facing helper: is the key authenticated AND did the credit preflight pass?

    Scorer / tailor / pipeline buttons depend on this. Returning False when credits are
    exhausted is what prevents the 482-skip-verdicts silent-failure scenario.
    """
    v: ValidationResult | None = st.session_state.get("_anth_validation")
    return bool(v and v.ok and v.preflight_ok)
