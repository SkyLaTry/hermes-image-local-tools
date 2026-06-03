"""Auto-start and process management for local Lemonade and ComfyUI backends."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_HERMES_RUNTIME_DIR = Path.home() / ".hermes" / "image_gen" / "runtime"
_LEMONADE_PID_FILE = _HERMES_RUNTIME_DIR / "lemond.pid"
_COMFY_PID_FILE = _HERMES_RUNTIME_DIR / "comfyui.pid"


def _ensure_runtime_dir() -> Path:
    _HERMES_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return _HERMES_RUNTIME_DIR


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid(path: Path) -> Optional[int]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except Exception:
        return None


def _write_pid(path: Path, pid: int) -> None:
    _ensure_runtime_dir()
    path.write_text(str(pid), encoding="utf-8")


def _which(binary: str) -> Optional[str]:
    return shutil.which(binary)


def _run_quiet(cmd: List[str], *, timeout: float = 30.0) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except Exception as exc:
        return 1, str(exc)


def _remove_pid_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _kill_pid(pid: int, *, sig: int = 15) -> bool:
    if pid <= 0 or not _pid_alive(pid):
        return False
    try:
        os.kill(pid, sig)
        return True
    except OSError:
        return False


def _wait_http_ok(
    url: str,
    *,
    timeout: float = 60.0,
    interval: float = 1.0,
    expect_json: bool = False,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code != 200:
                pass
            elif expect_json:
                payload = resp.json()
                if isinstance(payload, (dict, list)):
                    return True
            else:
                return True
        except (requests.RequestException, ValueError):
            pass
        time.sleep(interval)
    return False


def _cleanup_failed_process(pid: int, pid_file: Path) -> None:
    if _kill_pid(pid, sig=15):
        time.sleep(0.5)
        if _pid_alive(pid):
            _kill_pid(pid, sig=9)
    _remove_pid_file(pid_file)


def lemonade_health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/models"


def comfy_health_url(host: str) -> str:
    host = host.rstrip("/")
    if "cloud.comfy.org" in host:
        return f"{host}/api/system_stats"
    return f"{host}/system_stats"


def lemonade_is_running(base_url: str) -> bool:
    return _wait_http_ok(
        lemonade_health_url(base_url),
        timeout=5,
        interval=0.5,
        expect_json=True,
    )


def comfy_is_running(host: str) -> bool:
    return _wait_http_ok(comfy_health_url(host), timeout=5, interval=0.5)


def start_lemonade(
    base_url: str = "http://127.0.0.1:13305/api/v1",
    *,
    wait_timeout: float = 90.0,
) -> Dict[str, Any]:
    """Start Lemonade if installed and not already responding."""
    if lemonade_is_running(base_url):
        return {"started": False, "status": "already_running", "base_url": base_url}

    existing = _read_pid(_LEMONADE_PID_FILE)
    if existing and _pid_alive(existing):
        if _wait_http_ok(
            lemonade_health_url(base_url),
            timeout=10,
            expect_json=True,
        ):
            return {"started": False, "status": "already_running", "pid": existing, "base_url": base_url}

    attempts: List[Dict[str, Any]] = []

    if _which("systemctl"):
        code, out = _run_quiet(["systemctl", "--user", "start", "lemond"], timeout=15)
        attempts.append({"method": "systemctl --user start lemond", "exit_code": code, "output": out[:300]})
        if _wait_http_ok(
            lemonade_health_url(base_url),
            timeout=15,
            expect_json=True,
        ):
            return {"started": True, "status": "running", "method": "systemd-user", "base_url": base_url, "attempts": attempts}

    lemond = _which("lemond")
    if lemond:
        log_path = _ensure_runtime_dir() / "lemond.log"
        with log_path.open("a", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(
                [lemond],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        _write_pid(_LEMONADE_PID_FILE, proc.pid)
        attempts.append({"method": f"{lemond} (background)", "pid": proc.pid, "log": str(log_path)})
        if _wait_http_ok(
            lemonade_health_url(base_url),
            timeout=wait_timeout,
            expect_json=True,
        ):
            return {
                "started": True,
                "status": "running",
                "method": "lemond",
                "pid": proc.pid,
                "base_url": base_url,
                "log": str(log_path),
                "attempts": attempts,
            }
        _cleanup_failed_process(proc.pid, _LEMONADE_PID_FILE)
        return {
            "started": False,
            "status": "start_failed",
            "error": f"Lemond launched (pid {proc.pid}) but server did not become ready in {int(wait_timeout)}s",
            "log": str(log_path),
            "attempts": attempts,
        }

    return {
        "started": False,
        "status": "not_installed",
        "error": "lemond binary not found on PATH",
        "attempts": attempts,
    }


def _resolve_comfy_bin() -> Optional[str]:
    for candidate in ("comfy", os.path.expanduser("~/.local/bin/comfy")):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return _which("comfy")


def start_comfyui(
    host: str = "http://127.0.0.1:8188",
    *,
    wait_timeout: float = 120.0,
) -> Dict[str, Any]:
    """Start ComfyUI via comfy-cli when available."""
    if comfy_is_running(host):
        return {"started": False, "status": "already_running", "host": host}

    attempts: List[Dict[str, Any]] = []
    comfy = _resolve_comfy_bin()
    if not comfy:
        return {
            "started": False,
            "status": "not_installed",
            "error": "comfy-cli not found (install with: pipx install comfy-cli)",
            "attempts": attempts,
        }

    port = "8188"
    try:
        from urllib.parse import urlparse

        parsed = urlparse(host)
        if parsed.port:
            port = str(parsed.port)
    except Exception:
        pass

    code, out = _run_quiet(
        [comfy, "launch", "--background", "--", "--port", port],
        timeout=120,
    )
    attempts.append({"method": f"{comfy} launch --background -- --port {port}", "exit_code": code, "output": out[:500]})
    if _wait_http_ok(comfy_health_url(host), timeout=wait_timeout):
        return {"started": True, "status": "running", "method": "comfy-cli", "host": host, "attempts": attempts}

    # Fallback: try foreground-detached main.py if comfy knows the workspace.
    which_out = _run_quiet([comfy, "which"], timeout=30)[1]
    workspace = which_out.strip().splitlines()[-1].strip() if which_out else ""
    main_py = Path(workspace) / "main.py" if workspace else None
    if main_py and main_py.is_file():
        log_path = _ensure_runtime_dir() / "comfyui.log"
        with log_path.open("a", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(
                ["python3", str(main_py), "--port", port],
                cwd=str(main_py.parent),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        _write_pid(_COMFY_PID_FILE, proc.pid)
        attempts.append({"method": f"python3 {main_py} --port {port}", "pid": proc.pid, "log": str(log_path)})
        if _wait_http_ok(comfy_health_url(host), timeout=wait_timeout):
            return {
                "started": True,
                "status": "running",
                "method": "main.py",
                "pid": proc.pid,
                "host": host,
                "log": str(log_path),
                "attempts": attempts,
            }
        _cleanup_failed_process(proc.pid, _COMFY_PID_FILE)

    return {
        "started": False,
        "status": "start_failed",
        "error": "ComfyUI did not become ready",
        "host": host,
        "attempts": attempts,
    }


def stop_lemonade() -> Dict[str, Any]:
    pid = _read_pid(_LEMONADE_PID_FILE)
    if pid and _pid_alive(pid):
        _cleanup_failed_process(pid, _LEMONADE_PID_FILE)
        return {"stopped": True, "method": "sigterm", "pid": pid}
    _remove_pid_file(_LEMONADE_PID_FILE)
    return {"stopped": False, "status": "not_running"}


def stop_comfyui() -> Dict[str, Any]:
    comfy = _resolve_comfy_bin()
    if comfy:
        code, out = _run_quiet([comfy, "stop"], timeout=30)
        if code == 0:
            return {"stopped": True, "method": "comfy stop", "output": out[:300]}
    pid = _read_pid(_COMFY_PID_FILE)
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, 15)
            _remove_pid_file(_COMFY_PID_FILE)
            return {"stopped": True, "method": "sigterm", "pid": pid}
        except OSError as exc:
            return {"stopped": False, "error": str(exc), "pid": pid}
    _remove_pid_file(_COMFY_PID_FILE)
    return {"stopped": False, "status": "not_running"}


def ensure_lemonade_running(base_url: str, *, wait_timeout: float = 90.0) -> Dict[str, Any]:
    if lemonade_is_running(base_url):
        return {"ok": True, "status": "running", "base_url": base_url}
    result = start_lemonade(base_url, wait_timeout=wait_timeout)
    result["ok"] = result.get("status") == "running" or result.get("started") is True or lemonade_is_running(base_url)
    return result


def ensure_comfyui_running(host: str, *, wait_timeout: float = 120.0) -> Dict[str, Any]:
    if comfy_is_running(host):
        return {"ok": True, "status": "running", "host": host}
    result = start_comfyui(host, wait_timeout=wait_timeout)
    result["ok"] = result.get("status") == "running" or comfy_is_running(host)
    return result
