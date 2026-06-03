"""Load vendored modules from this plugin's lib/ without sys.path collisions."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_vendored(name: str, *, plugin_root: Path | None = None) -> ModuleType:
    root = plugin_root or Path(__file__).resolve().parent
    path = root / "lib" / f"{name}.py"
    if not path.is_file():
        raise ImportError(f"vendored module not found: {path}")
    mod_name = f"_{root.name}_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load vendored module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
