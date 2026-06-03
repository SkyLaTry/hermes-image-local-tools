"""Lemonade model pull/load helpers — auto-download and wait until ready."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[Dict[str, Any]], None]

_DEFAULT_PULL_TIMEOUT = 7200.0
_DEFAULT_LOAD_TIMEOUT = 600.0


def _auth_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def fetch_model_record(
    base_url: str,
    model_id: str,
    *,
    api_key: str = "lemonade",
    show_all: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return the model dict from GET /models, or None if unknown."""
    params = {"show_all": "true"} if show_all else {}
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/models",
            headers=_auth_headers(api_key),
            params=params,
            timeout=15,
        )
        if not resp.ok:
            return None
        data = resp.json()
        for item in data.get("data") or []:
            if isinstance(item, dict) and item.get("id") == model_id:
                return item
    except Exception as exc:
        logger.debug("fetch_model_record(%s) failed: %s", model_id, exc)
    return None


def is_model_downloaded(
    base_url: str,
    model_id: str,
    *,
    api_key: str = "lemonade",
) -> bool:
    record = fetch_model_record(base_url, model_id, api_key=api_key, show_all=True)
    if record is None:
        return False
    return bool(record.get("downloaded"))


def wait_for_downloaded(
    base_url: str,
    model_id: str,
    *,
    api_key: str = "lemonade",
    timeout: float = _DEFAULT_PULL_TIMEOUT,
    poll_interval: float = 3.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_model_downloaded(base_url, model_id, api_key=api_key):
            return True
        time.sleep(poll_interval)
    return is_model_downloaded(base_url, model_id, api_key=api_key)


def pull_model(
    base_url: str,
    model_id: str,
    *,
    api_key: str = "lemonade",
    timeout: float = _DEFAULT_PULL_TIMEOUT,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Stream POST /pull until complete or error. Blocks until done."""
    url = f"{base_url.rstrip('/')}/pull"
    events: List[Dict[str, Any]] = []
    last_percent = 0
    last_log_percent = -1

    try:
        with requests.post(
            url,
            headers=_auth_headers(api_key),
            json={"model_name": model_id, "stream": True},
            stream=True,
            timeout=(30, timeout),
        ) as resp:
            if resp.status_code >= 400:
                body = resp.text[:800]
                try:
                    body = json.dumps(resp.json())[:800]
                except Exception:
                    pass
                return {
                    "success": False,
                    "model": model_id,
                    "error": f"pull HTTP {resp.status_code}: {body}",
                }

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                events.append(data)
                if on_progress:
                    try:
                        on_progress(data)
                    except Exception:
                        pass

                status = str(data.get("status") or data.get("state") or "").lower()
                percent = data.get("percent")
                if isinstance(percent, (int, float)):
                    last_percent = int(percent)
                    if last_percent >= last_log_percent + 5:
                        last_log_percent = last_percent
                        logger.info(
                            "Lemonade downloading %s: %s%%",
                            model_id,
                            last_percent,
                        )

                if status in {"complete", "completed", "success", "done", "finished"}:
                    return {
                        "success": True,
                        "model": model_id,
                        "percent": 100,
                        "status": status,
                        "events_tail": events[-3:],
                    }
                if status in {"error", "failed", "cancelled"}:
                    return {
                        "success": False,
                        "model": model_id,
                        "error": data.get("message") or data.get("error") or str(data),
                        "events_tail": events[-3:],
                    }
                if data.get("error"):
                    return {
                        "success": False,
                        "model": model_id,
                        "error": str(data.get("error")),
                        "events_tail": events[-3:],
                    }

    except requests.RequestException as exc:
        return {"success": False, "model": model_id, "error": f"pull request failed: {exc}"}

    # Stream ended — confirm via /models
    if wait_for_downloaded(base_url, model_id, api_key=api_key, timeout=min(120, timeout / 10)):
        return {
            "success": True,
            "model": model_id,
            "percent": max(last_percent, 100),
            "status": "verified_downloaded",
        }
    return {
        "success": False,
        "model": model_id,
        "error": "pull stream ended but model is still not marked downloaded",
        "last_percent": last_percent,
        "events_tail": events[-5:],
    }


def load_model(
    base_url: str,
    model_id: str,
    *,
    api_key: str = "lemonade",
    timeout: float = _DEFAULT_LOAD_TIMEOUT,
) -> Dict[str, Any]:
    """POST /load for a model (after download)."""
    url = f"{base_url.rstrip('/')}/load"
    try:
        resp = requests.post(
            url,
            headers=_auth_headers(api_key),
            json={"model_name": model_id},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return {"success": False, "model": model_id, "error": f"load request failed: {exc}"}

    if resp.status_code >= 400:
        detail = resp.text[:800]
        try:
            detail = json.dumps(resp.json())[:800]
        except Exception:
            pass
        return {"success": False, "model": model_id, "error": f"load HTTP {resp.status_code}: {detail}"}

    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:200]}
    return {"success": True, "model": model_id, "response": body}


def ensure_model_ready(
    base_url: str,
    model_id: str,
    *,
    api_key: str = "lemonade",
    pull_timeout: float = _DEFAULT_PULL_TIMEOUT,
    load_timeout: float = _DEFAULT_LOAD_TIMEOUT,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Ensure model is downloaded and loaded. Pulls automatically if needed."""
    started = time.monotonic()
    result: Dict[str, Any] = {
        "model": model_id,
        "downloaded": False,
        "loaded": False,
        "pulled": False,
    }

    if is_model_downloaded(base_url, model_id, api_key=api_key):
        result["downloaded"] = True
    else:
        logger.info("Lemonade model %s not downloaded — starting automatic pull", model_id)
        if on_progress:
            try:
                on_progress({"phase": "pull", "status": "starting", "percent": 0})
            except Exception:
                pass
        pull = pull_model(
            base_url,
            model_id,
            api_key=api_key,
            timeout=pull_timeout,
            on_progress=on_progress,
        )
        result["pull"] = pull
        result["pulled"] = True
        if not pull.get("success"):
            result["success"] = False
            result["error"] = pull.get("error") or "pull failed"
            result["elapsed_seconds"] = round(time.monotonic() - started, 1)
            return result
        result["downloaded"] = True

    if on_progress:
        try:
            on_progress({"phase": "load", "status": "loading"})
        except Exception:
            pass

    load = load_model(base_url, model_id, api_key=api_key, timeout=load_timeout)
    result["load"] = load
    if not load.get("success"):
        result["success"] = False
        result["error"] = load.get("error") or "load failed"
        result["elapsed_seconds"] = round(time.monotonic() - started, 1)
        return result

    result["loaded"] = True
    result["success"] = True
    result["elapsed_seconds"] = round(time.monotonic() - started, 1)
    return result
