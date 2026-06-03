"""Hermes compatibility layer — vendored copy per plugin (stdlib + public Hermes APIs only).

Avoid importing other SkyLaTry plugins. Uses gateway.session_context, hermes_cli.config,
and environment variables with graceful fallbacks when Hermes internals change.
"""

from __future__ import annotations

import functools
import logging
import os
import re
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_PLATFORM_ALIASES = {
    "": "cli",
    "local": "cli",
    "cli": "cli",
    "terminal": "cli",
    "tui": "cli",
}


def normalize_platform_key(raw: str) -> str:
    key = (raw or "").strip().lower()
    key = _PLATFORM_ALIASES.get(key, key or "cli")
    safe = re.sub(r"[^a-z0-9_-]", "", key)
    return safe or "cli"


def _session_env(name: str, default: str = "") -> str:
    try:
        from gateway.session_context import get_session_env

        return str(get_session_env(name, default) or default).strip()
    except Exception:
        return str(os.getenv(name, default) or default).strip()


def get_current_platform_key() -> str:
    platform = _session_env("HERMES_SESSION_PLATFORM") or _session_env("HERMES_SESSION_SOURCE")
    return normalize_platform_key(platform)


def get_current_chat_id() -> str:
    return _session_env("HERMES_SESSION_CHAT_ID")


def get_current_session_key() -> str:
    return _session_env("HERMES_SESSION_KEY")


def load_hermes_config() -> dict:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def save_config_key(*parts: str, value: Any) -> bool:
    """Best-effort config write via public CLI helpers."""
    try:
        from cli import save_config_value

        save_config_value(*parts, value=value)
        return True
    except Exception:
        pass
    try:
        from hermes_cli.config import load_config, save_config

        cfg = load_config()
        if not isinstance(cfg, dict):
            return False
        node: Any = cfg
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
        save_config(cfg)
        return True
    except Exception as exc:
        logger.debug("hermes_compat: save_config_key failed: %s", exc)
        return False


def gateway_runner():
    try:
        from gateway.run import _gateway_runner_ref

        return _gateway_runner_ref()
    except Exception:
        return None


def patch_method_once(
    cls: type,
    method_name: str,
    wrapper_factory: Callable[[Any], Any],
    *,
    tag: str,
) -> bool:
    """Idempotent monkey-patch with a tag attribute on the wrapper."""
    original = getattr(cls, method_name, None)
    if original is None:
        logger.debug("hermes_compat: %s.%s missing — skip patch %s", cls.__name__, method_name, tag)
        return False
    if getattr(original, f"_hermes_patch_{tag}", False):
        return True
    wrapped = wrapper_factory(original)
    setattr(wrapped, f"_hermes_patch_{tag}", True)
    setattr(cls, method_name, wrapped)
    return True


def chain_async_method(original, wrapper):
    """Decorator helper for async gateway methods."""

    @functools.wraps(original)
    async def inner(*args, **kwargs):
        return await wrapper(original, *args, **kwargs)

    return inner


def tui_entry_js():
    from .platform_util import discover_hermes_tui_entry_js

    return discover_hermes_tui_entry_js()


def apply_js_patch(source: str, replacements: list[tuple[str, str]], *, marker: str) -> Optional[str]:
    """Apply text replacements only when all needles exist; return None if any missing."""
    if marker in source:
        return source
    for needle, repl in replacements:
        if needle not in source:
            logger.warning("hermes_compat: JS anchor missing for %s: %r", marker, needle[:80])
            return None
    out = source
    for needle, repl in replacements:
        out = out.replace(needle, repl, 1)
    if marker not in out:
        out = marker + "\n" + out
    return out
