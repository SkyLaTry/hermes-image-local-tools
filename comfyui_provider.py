"""ComfyUI workflow image generation backend (part of hermes-image-local-tools)."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    success_response,
)

from .comfyui_runner import (
    ComfyUIClient,
    ComfyUIError,
    aspect_to_size,
    first_output_image,
    inject_workflow,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sdxl"
_PLUGIN_DIR = Path(__file__).resolve().parent
_WORKFLOW_DIR = _PLUGIN_DIR / "workflows"


def _common_dir() -> Path:
    bundled = _PLUGIN_DIR / "common"
    if bundled.is_dir():
        return bundled
    return _PLUGIN_DIR.parent / "common"


def _load_common(name: str):
    path = _common_dir() / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hermes_image_gen_common_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"missing common module: {name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _workflow_catalog() -> Dict[str, Dict[str, Any]]:
    comfy_workflows = _load_common("comfy_workflows")
    return comfy_workflows.discover_workflows(_WORKFLOW_DIR)


def _load_comfy_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        if not isinstance(section, dict):
            return {}
        nested = section.get("comfyui")
        return nested if isinstance(nested, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen.comfyui config: %s", exc)
        return {}


def _comfy_host() -> str:
    env = (os.environ.get("COMFYUI_HOST") or os.environ.get("COMFY_HOST") or "").strip()
    if env:
        return env.rstrip("/")
    cfg = _load_comfy_config()
    host = str(cfg.get("host") or "").strip()
    if host:
        return host.rstrip("/")
    return "http://127.0.0.1:8188"


def _comfy_api_key() -> str:
    env = (os.environ.get("COMFY_CLOUD_API_KEY") or os.environ.get("COMFYUI_API_KEY") or "").strip()
    if env:
        return env
    cfg = _load_comfy_config()
    return str(cfg.get("api_key") or "")


def _comfy_timeout() -> float:
    cfg = _load_comfy_config()
    try:
        return float(cfg.get("timeout", 600.0))
    except (TypeError, ValueError):
        return 600.0


def _resolve_model(requested: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    catalog = _workflow_catalog()
    candidates: List[str] = []
    if requested:
        candidates.append(requested.strip())
    env_override = (os.environ.get("COMFYUI_IMAGE_WORKFLOW") or "").strip()
    if env_override:
        candidates.append(env_override)
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        if isinstance(section, dict):
            for key in ("model",):
                val = section.get(key)
                if isinstance(val, str) and val.strip():
                    candidates.append(val.strip())
            nested = section.get("comfyui")
            if isinstance(nested, dict):
                val = nested.get("model") or nested.get("workflow")
                if isinstance(val, str) and val.strip():
                    candidates.append(val.strip())
    except Exception:
        pass

    for candidate in candidates:
        if candidate in catalog:
            return candidate, catalog[candidate]
        stem = Path(candidate).stem
        if stem in catalog:
            return stem, catalog[stem]
    if DEFAULT_MODEL in catalog:
        return DEFAULT_MODEL, catalog[DEFAULT_MODEL]
    if catalog:
        first = next(iter(catalog))
        return first, catalog[first]
    raise KeyError("no ComfyUI workflows found")


def _ensure_server() -> Dict[str, Any]:
    runtime = _load_common("runtime")
    return runtime.ensure_comfyui_running(_comfy_host(), wait_timeout=_comfy_timeout())


class ComfyUIImageGenProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return "comfyui"

    @property
    def display_name(self) -> str:
        return "ComfyUI (local)"

    def is_available(self) -> bool:
        runtime = _load_common("runtime")
        if runtime.comfy_is_running(_comfy_host()):
            return True
        result = _ensure_server()
        return bool(result.get("ok"))

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta.get("display", model_id),
                "speed": meta.get("speed", "local"),
                "strengths": meta.get("strengths", "ComfyUI workflow"),
                "price": "local",
            }
            for model_id, meta in _workflow_catalog().items()
        ]

    def default_model(self) -> Optional[str]:
        try:
            model_id, _ = _resolve_model()
            return model_id
        except KeyError:
            return None

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "ComfyUI (local/cloud)",
            "badge": "free · local",
            "tag": "ComfyUI backend is built into hermes-image-local-tools (comfyui_manage)",
            "env_vars": [
                {
                    "key": "COMFYUI_HOST",
                    "prompt": "ComfyUI server URL (default http://127.0.0.1:8188)",
                    "url": "https://github.com/comfyanonymous/ComfyUI",
                },
                {
                    "key": "COMFY_CLOUD_API_KEY",
                    "prompt": "Comfy Cloud API key (only if using cloud.comfy.org)",
                    "url": "https://cloud.comfy.org",
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        aspect = resolve_aspect_ratio(aspect_ratio)
        try:
            model_id, spec = _resolve_model(
                str(kwargs.get("model")).strip() if kwargs.get("model") else None
            )
        except KeyError as exc:
            return error_response(
                error=str(exc),
                error_type="config_error",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        if not prompt or not str(prompt).strip():
            return error_response(
                error="Prompt is required",
                error_type="validation_error",
                provider=self.name,
                model=model_id,
                prompt=prompt or "",
                aspect_ratio=aspect,
            )

        start = _ensure_server()
        if not start.get("ok"):
            return error_response(
                error=f"ComfyUI server not reachable at {_comfy_host()}: {start}",
                error_type="backend_unavailable",
                provider=self.name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        comfy_workflows = _load_common("comfy_workflows")
        try:
            workflow = comfy_workflows.read_workflow(
                str(spec.get("path") or model_id),
                _WORKFLOW_DIR,
            )
        except Exception as exc:
            return error_response(
                error=f"Failed to load ComfyUI workflow: {exc}",
                error_type="config_error",
                provider=self.name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        if not spec.get("prompt"):
            spec = comfy_workflows.infer_workflow_spec(workflow)

        width, height = aspect_to_size(aspect, int(spec.get("base_size", 1024)))
        try:
            prepared = inject_workflow(
                workflow,
                prompt=str(prompt).strip(),
                width=width,
                height=height,
                seed=kwargs.get("seed"),
                spec=spec,
                negative_prompt=str(kwargs.get("negative_prompt") or ""),
            )
        except Exception as exc:
            return error_response(
                error=f"Failed to prepare ComfyUI workflow: {exc}",
                error_type="validation_error",
                provider=self.name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        client = ComfyUIClient(_comfy_host(), _comfy_api_key(), timeout=_comfy_timeout())
        try:
            prompt_id = client.submit(prepared)
            result = client.poll(prompt_id)
            filename, subfolder, file_type = first_output_image(result)
            image_bytes = client.download_image(filename, subfolder=subfolder, file_type=file_type)
        except ComfyUIError as exc:
            return error_response(
                error=str(exc),
                error_type="api_error",
                provider=self.name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except Exception as exc:
            return error_response(
                error=f"ComfyUI generation failed: {exc}",
                error_type="provider_error",
                provider=self.name,
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        from agent.image_gen_provider import _images_cache_dir

        out_dir = _images_cache_dir()
        out_path = out_dir / f"comfyui_{model_id}_{prompt_id[:8]}.png"
        out_path.write_bytes(image_bytes)

        return success_response(
            image=str(out_path),
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider=self.name,
            extra={
                "workflow": spec.get("workflow") or model_id,
                "workflow_path": spec.get("path"),
                "comfy_prompt_id": prompt_id,
                "width": width,
                "height": height,
                "host": _comfy_host(),
                "autostart": start,
            },
        )


def register_comfyui_provider(ctx) -> None:
    ctx.register_image_gen_provider(ComfyUIImageGenProvider())
