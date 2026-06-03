"""Import sibling common modules without a separate plugin package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_CACHE: dict[str, ModuleType] = {}


def load_common(name: str) -> ModuleType:
    mod_name = f"hermes_image_gen_common_{name}"
    cached = sys.modules.get(mod_name)
    if cached is not None:
        return cached
    if name in _CACHE:
        return _CACHE[name]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load common module: {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    _CACHE[name] = mod
    return mod
