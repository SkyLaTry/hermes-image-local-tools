"""Ephemeral agent guidance for local Lemonade / ComfyUI image generation."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set

_LEMONADE_MODELS = (
    "SD-Turbo",
    "SD-Turbo-GGUF",
    "SD-1.5",
    "SDXL-Base-1.0",
    "SDXL-Turbo",
    "Flux-2-Klein-4B",
    "Flux-2-Klein-9B-GGUF",
    "Qwen-Image-GGUF",
    "Qwen-Image-2512-GGUF",
    "Z-Image-Turbo",
)


def _load_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _image_gen_section(cfg: Dict[str, Any]) -> Dict[str, Any]:
    section = cfg.get("image_gen")
    return section if isinstance(section, dict) else {}


def configured_image_provider() -> str:
    section = _image_gen_section(_load_config())
    provider = section.get("provider")
    return str(provider).strip().lower() if isinstance(provider, str) else ""


def configured_image_model() -> str:
    section = _image_gen_section(_load_config())
    for key in ("model",):
        val = section.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    nested = section.get(configured_image_provider())
    if isinstance(nested, dict):
        val = nested.get("model")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _lemonade_guidance(*, model: str, auto_pull: bool) -> str:
    model_line = f"Configured default model: `{model}`." if model else ""
    pull_line = (
        "Missing models are downloaded automatically before generation; "
        "the UI shows download progress and Hermes waits until the model is ready. "
        "Do not ask the user to run `lemonade pull` or use Model Manager."
        if auto_pull
        else "Auto-pull is off — use lemonade_manage ensure_ready if a model is missing."
    )
    models = ", ".join(_LEMONADE_MODELS)
    return (
        "<image_generation_backend provider=\"lemonade\">\n"
        "Local image generation uses Lemonade (stable-diffusion.cpp).\n"
        f"{model_line}\n"
        "- Primary tool: `image_generate(prompt, aspect_ratio)` — call this directly for normal requests.\n"
        f"- {pull_line}\n"
        "- First use of a large model can take several minutes while it downloads.\n"
        "- Results return a local filesystem path in `image`; show it with markdown `![description](path)`.\n"
        "- `lemonade_manage` is optional diagnostics only (status, list_models, ensure_ready). "
        "Do not call pull/load before every image unless debugging.\n"
        f"- Lemonade image model ids include: {models}.\n"
        "- Model and provider are user-configured; do not try to switch backends unless the user asks.\n"
        "</image_generation_backend>"
    )


def _comfyui_guidance(*, model: str) -> str:
    model_line = f"Configured workflow/model alias: `{model}`." if model else ""
    return (
        "<image_generation_backend provider=\"comfyui\">\n"
        "Local image generation uses ComfyUI workflows.\n"
        f"{model_line}\n"
        "- Primary tool: `image_generate(prompt, aspect_ratio)` when image_gen.provider=comfyui.\n"
        "- Backend auto-starts ComfyUI when needed.\n"
        "- `comfyui_manage` can list/read/write/run workflows (bundled templates + "
        "~/.hermes/image_gen/comfyui/workflows/ overrides), "
        "install models/nodes, or bootstrap ComfyUI — use when the user wants custom workflows or missing assets.\n"
        "- Results return a local path in `image`; display with markdown `![description](path)`.\n"
        "</image_generation_backend>"
    )


def build_pre_llm_context(*, valid_tool_names: Optional[Set[str]] = None) -> str:
    """Return guidance to inject when local image tools are relevant."""
    tools = {str(t) for t in (valid_tool_names or set())}
    if tools and "image_generate" not in tools and "lemonade_manage" not in tools and "comfyui_manage" not in tools:
        return ""

    provider = configured_image_provider()
    if not provider:
        return ""

    section = _image_gen_section(_load_config())
    model = configured_image_model()
    if provider == "lemonade":
        nested = section.get("lemonade")
        auto_pull = True
        if isinstance(nested, dict) and "auto_pull" in nested:
            auto_pull = bool(nested.get("auto_pull"))
        return _lemonade_guidance(model=model, auto_pull=auto_pull)
    if provider == "comfyui":
        return _comfyui_guidance(model=model)
    return ""


def image_generate_tool_description() -> str:
    """Agent-facing description for the image_generate tool schema."""
    provider = configured_image_provider()
    model = configured_image_model()
    base = (
        "Generate images from text prompts. Backend and model are user-configured "
        "(not selectable per call). Returns a URL or absolute local file path in `image`; "
        "display with markdown `![description](url-or-path)`."
    )
    if provider == "lemonade":
        extra = (
            " Active backend: Lemonade (local). Call this tool directly — it auto-starts the server, "
            "downloads any missing model automatically, waits with visible progress, then generates. "
            "Do not manually pull models or ask the user to install anything first."
        )
        if model:
            extra += f" Default model: {model}."
        return base + extra
    if provider == "comfyui":
        extra = (
            " Active backend: ComfyUI (local workflows). The server is auto-started when needed. "
            "Use comfyui_manage only for workflow/model maintenance, not for ordinary generation."
        )
        if model:
            extra += f" Default workflow/model: {model}."
        return base + extra
    return base
