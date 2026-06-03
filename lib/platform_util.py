"""Cross-platform helpers — vendored copy per plugin (stdlib only)."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


@contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+", encoding="utf-8")
    try:
        if IS_WINDOWS:
            import msvcrt

            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if IS_WINDOWS:
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        pass
    if IS_LINUX and not IS_WINDOWS:
        try:
            proc = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass
    if IS_WINDOWS:
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"exit (Get-NetTCPConnection -LocalPort {int(port)} -ErrorAction SilentlyContinue | Measure-Object).Count",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass
    return False


def kill_process_tree(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
            return True
        except Exception:
            return False
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return False
    time.sleep(0.8)
    if pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                return False
    return True


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in (proc.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_processes_on_port(port: int) -> None:
    if port <= 0:
        return
    if IS_LINUX and not IS_WINDOWS:
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, check=False)
        except Exception:
            pass
    elif IS_WINDOWS:
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-NetTCPConnection -LocalPort {int(port)} -ErrorAction SilentlyContinue | "
                    "ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}",
                ],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except Exception:
            pass


def open_url(url: str) -> None:
    url = (url or "").strip()
    if not url:
        return
    if IS_WINDOWS:
        os.startfile(url)  # type: ignore[attr-defined]
        return
    if IS_MACOS:
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def default_local_app_dir(app_name: str) -> Path:
    return Path.home() / "Applications" / app_name


def default_local_state_dir(app_name: str) -> Path:
    home = Path.home()
    if IS_WINDOWS:
        return home / "AppData" / "Local" / app_name
    if IS_MACOS:
        return home / "Library" / "Application Support" / app_name
    return home / ".local" / "share" / app_name


def bun_path_prefix() -> str:
    home_bin = Path.home() / ".bun" / "bin"
    if not home_bin.is_dir():
        return ""
    return str(home_bin) + (os.pathsep if IS_WINDOWS else "")


def prepend_path(env: dict, extra: str) -> dict:
    if not extra:
        return env
    merged = dict(env)
    merged["PATH"] = f"{extra.rstrip(os.pathsep)}{os.pathsep}{merged.get('PATH', '')}".strip(os.pathsep)
    return merged


def discover_hermes_tui_entry_js() -> Optional[Path]:
    override = (os.environ.get("HERMES_TUI_ENTRY_JS") or "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
    try:
        import hermes_cli

        candidate = Path(hermes_cli.__file__).resolve().parent / "tui_dist" / "entry.js"
        if candidate.is_file():
            return candidate
    except Exception:
        pass
    for base in (Path("/opt/hermes-agent/venv/lib"), Path.home() / ".hermes/venv/lib"):
        if base.is_dir():
            for path in sorted(base.glob("python*/site-packages/hermes_cli/tui_dist/entry.js")):
                if path.is_file():
                    return path
    return None
