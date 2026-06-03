"""Wire Hermes display callbacks into image_gen plugin worker threads."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False
_COMMON_DIR = Path(__file__).resolve().parent


def _load_common(name: str):
    mod_name = f"hermes_image_gen_common_{name}"
    cached = sys.modules.get(mod_name)
    if cached is not None:
        return cached
    path = _COMMON_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"missing common module: {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def ensure_display_patch() -> None:
    """Install once: propagate agent status/tool-progress into tool worker threads."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    tui_progress = _load_common("tui_progress")

    try:
        import tools.environments.base as env_base
    except Exception as exc:
        logger.debug("image_gen display patch skipped (env base): %s", exc)
        return

    if getattr(env_base, "_image_gen_display_patch", False):
        return

    original = env_base.set_activity_callback

    def set_activity_callback(cb: Any) -> None:
        original(cb)
        agent = getattr(cb, "__self__", None) if cb is not None else None
        if agent is None or not hasattr(agent, "tool_progress_callback"):
            tui_progress.clear_callbacks()
            return
        tui_progress.set_status_callback(getattr(agent, "status_callback", None))
        tui_progress.set_tool_progress_callback(getattr(agent, "tool_progress_callback", None))

    env_base.set_activity_callback = set_activity_callback
    env_base._image_gen_display_patch = True

    _patch_tui_gateway()
    _patch_cli_progress()


def _patch_tui_gateway() -> None:
    try:
        import tui_gateway.server as tgs
    except Exception:
        return
    if getattr(tgs, "_image_gen_tool_progress_patched", False):
        return

    original = tgs._on_tool_progress

    def _on_tool_progress(
        sid: str,
        event_type: str,
        name: str | None = None,
        preview: str | None = None,
        _args: dict | None = None,
        **_kwargs,
    ):
        if event_type == "tool.progress" and name:
            if tgs._tool_progress_enabled(sid):
                tgs._emit("tool.progress", sid, {"name": name, "preview": preview or ""})
            return
        return original(sid, event_type, name, preview, _args, **_kwargs)

    tgs._on_tool_progress = _on_tool_progress
    tgs._image_gen_tool_progress_patched = True


def _patch_cli_progress() -> None:
    try:
        import cli as cli_mod
    except Exception:
        return
    if getattr(cli_mod, "_image_gen_tool_progress_patched", False):
        return

    # HermesCLI._on_tool_progress is defined on the class; patch once on the class.
    original = cli_mod.HermesCLI._on_tool_progress

    def _on_tool_progress(
        self,
        event_type: str,
        function_name: str = None,
        preview: str = None,
        function_args: dict = None,
        **kwargs,
    ):
        if event_type == "tool.progress" and function_name and preview:
            try:
                from agent.display import get_tool_emoji

                emoji = get_tool_emoji(function_name)
                self._spinner_text = f"{emoji} {preview}"
                self._invalidate()
            except Exception:
                pass
            return
        return original(self, event_type, function_name, preview, function_args, **kwargs)

    cli_mod.HermesCLI._on_tool_progress = _on_tool_progress
    cli_mod._image_gen_tool_progress_patched = True
