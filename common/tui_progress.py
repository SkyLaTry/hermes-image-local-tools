"""User-visible progress for long Lemonade model downloads in Hermes TUI/CLI."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

StatusCallback = Callable[..., None]
ToolProgressCallback = Callable[..., None]

_tls = threading.local()
_THROTTLE_SEC = 0.4
_MIN_PERCENT_STEP = 3
_last_report: Dict[str, Dict[str, Any]] = {}


def set_status_callback(cb: Optional[StatusCallback]) -> None:
    _tls.status_callback = cb


def set_tool_progress_callback(cb: Optional[ToolProgressCallback]) -> None:
    _tls.tool_progress_callback = cb


def clear_callbacks() -> None:
    _tls.status_callback = None
    _tls.tool_progress_callback = None


def _get_status_callback() -> Optional[StatusCallback]:
    return getattr(_tls, "status_callback", None)


def _get_tool_progress_callback() -> Optional[ToolProgressCallback]:
    return getattr(_tls, "tool_progress_callback", None)


def _should_emit(key: str, *, percent: Optional[int], phase: str) -> bool:
    now = time.monotonic()
    prev = _last_report.get(key)
    if prev is None:
        return True
    if prev.get("phase") != phase:
        return True
    if percent is not None and prev.get("percent") is not None:
        if abs(int(percent) - int(prev["percent"])) >= _MIN_PERCENT_STEP:
            return True
        if int(percent) >= 100:
            return True
    return (now - float(prev.get("at") or 0.0)) >= _THROTTLE_SEC


def _remember(key: str, *, percent: Optional[int], phase: str) -> None:
    _last_report[key] = {
        "at": time.monotonic(),
        "percent": percent,
        "phase": phase,
    }


def report_model_progress(
    tool_name: str,
    model_id: str,
    *,
    phase: str,
    percent: Optional[int] = None,
    detail: Optional[str] = None,
) -> None:
    """Push download/load progress to the Hermes status line and tool card."""
    key = f"{tool_name}:{model_id}:{phase}"
    pct = int(percent) if isinstance(percent, (int, float)) else None
    if not _should_emit(key, percent=pct, phase=phase):
        return
    _remember(key, percent=pct, phase=phase)

    if phase == "pull":
        headline = f"Downloading Lemonade model {model_id}"
    elif phase == "load":
        headline = f"Loading Lemonade model {model_id}"
    elif phase == "verify":
        headline = f"Verifying Lemonade model {model_id}"
    else:
        headline = f"Preparing Lemonade model {model_id}"

    parts = [headline]
    if pct is not None:
        parts.append(f"{max(0, min(100, pct))}%")
    if detail:
        parts.append(str(detail).strip())
    preview = " · ".join(p for p in parts if p)

    status_cb = _get_status_callback()
    if status_cb:
        try:
            status_cb("process", preview)
        except Exception as exc:
            logger.debug("status_callback failed: %s", exc)

    progress_cb = _get_tool_progress_callback()
    if progress_cb:
        try:
            progress_cb("tool.progress", tool_name, preview, None)
        except Exception as exc:
            logger.debug("tool_progress_callback failed: %s", exc)


def lemonade_pull_progress_callback(
    tool_name: str,
    model_id: str,
) -> Callable[[Dict[str, Any]], None]:
    """Build an on_progress handler for lemonade_models pull/load helpers."""

    def _on_progress(data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        phase = str(data.get("phase") or "pull")
        percent = data.get("percent")
        status = str(data.get("status") or data.get("state") or "").strip()
        detail = status if status else None
        report_model_progress(
            tool_name,
            model_id,
            phase=phase,
            percent=int(percent) if isinstance(percent, (int, float)) else None,
            detail=detail,
        )

    return _on_progress
