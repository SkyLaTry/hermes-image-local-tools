"""Local image backends: ComfyUI provider, Lemonade/ComfyUI agent tools, LLM guidance."""

from __future__ import annotations

from .comfyui_provider import register_comfyui_provider
from .tools import register_tools


def register(ctx) -> None:
    register_tools(ctx)
    register_comfyui_provider(ctx)
