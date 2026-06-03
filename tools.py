"""Agent management tools for Lemonade and ComfyUI local image backends."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_DIR = Path(__file__).resolve().parent


def _image_gen_root() -> Path:
    """Monorepo: plugins/image_gen. Standalone repo: plugin root (has common/)."""
    if (_PLUGIN_DIR / "common").is_dir():
        return _PLUGIN_DIR
    return _PLUGIN_DIR.parent


def _comfy_workflows_dir() -> Path:
    local = _PLUGIN_DIR / "workflows"
    if local.is_dir():
        return local
    legacy = _PLUGIN_DIR.parent / "comfyui" / "workflows"
    return legacy if legacy.is_dir() else local


def _load_common(name: str):
    mod_name = f"hermes_image_gen_common_{name}"
    cached = sys.modules.get(mod_name)
    if cached is not None:
        return cached
    path = _image_gen_root() / "common" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"missing common module: {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)


def _lemonade_base_url() -> str:
    env = (os.environ.get("LEMONADE_BASE_URL") or "").strip()
    if env:
        return env.rstrip("/")
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        if isinstance(section, dict):
            nested = section.get("lemonade")
            if isinstance(nested, dict):
                url = str(nested.get("base_url") or "").strip()
                if url:
                    return url.rstrip("/")
            providers = cfg.get("custom_providers")
            if isinstance(providers, list):
                for entry in providers:
                    if isinstance(entry, dict) and str(entry.get("name") or "").lower() == "lemonade":
                        base = str(entry.get("base_url") or "").strip()
                        if base:
                            return base.rstrip("/")
    except Exception:
        pass
    return "http://127.0.0.1:13305/api/v1"


def _comfy_host() -> str:
    env = (os.environ.get("COMFYUI_HOST") or os.environ.get("COMFY_HOST") or "").strip()
    if env:
        return env.rstrip("/")
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        if isinstance(section, dict):
            nested = section.get("comfyui")
            if isinstance(nested, dict):
                host = str(nested.get("host") or "").strip()
                if host:
                    return host.rstrip("/")
    except Exception:
        pass
    return "http://127.0.0.1:8188"


def _run_cli(cmd: List[str], *, timeout: float = 600.0) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": cmd,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-8000:],
            "stderr": (proc.stderr or "")[-4000:],
            "success": proc.returncode == 0,
        }
    except Exception as exc:
        return {"command": cmd, "success": False, "error": str(exc)}


def handle_lemonade_manage(args: Dict[str, Any], **kwargs: Any) -> str:
    action = str(args.get("action") or "").strip().lower()
    runtime = _load_common("runtime")
    base = _lemonade_base_url()

    if action == "status":
        return _json(
            {
                "base_url": base,
                "running": runtime.lemonade_is_running(base),
            }
        )

    if action == "start":
        return _json(runtime.start_lemonade(base))

    if action == "list_models":
        import requests

        try:
            resp = requests.get(f"{base}/models", params={"show_all": "true"}, timeout=10)
            resp.raise_for_status()
            return _json(resp.json())
        except Exception as exc:
            start = runtime.start_lemonade(base)
            if not start.get("started") and not runtime.lemonade_is_running(base):
                return _json({"error": str(exc), "autostart": start})
            resp = requests.get(f"{base}/models", params={"show_all": "true"}, timeout=10)
            return _json({"autostart": start, "models": resp.json()})

    if action == "pull":
        model = str(args.get("model") or "").strip()
        if not model:
            return _json({"error": "model is required for pull"})
        runtime.ensure_lemonade_running(base)
        lm = _load_common("lemonade_models")
        tp = _load_common("tui_progress")
        pull_timeout = float(args.get("pull_timeout") or 7200)
        result = lm.pull_model(
            base,
            model,
            timeout=pull_timeout,
            on_progress=tp.lemonade_pull_progress_callback("lemonade_manage", model),
        )
        return _json(result)

    if action == "load":
        model = str(args.get("model") or "").strip()
        if not model:
            return _json({"error": "model is required for load"})
        runtime.ensure_lemonade_running(base)
        lm = _load_common("lemonade_models")
        load_timeout = float(args.get("load_timeout") or 600)
        return _json(lm.load_model(base, model, timeout=load_timeout))

    if action == "ensure_ready":
        model = str(args.get("model") or "").strip()
        if not model:
            return _json({"error": "model is required for ensure_ready"})
        runtime.ensure_lemonade_running(base)
        lm = _load_common("lemonade_models")
        tp = _load_common("tui_progress")
        return _json(
            lm.ensure_model_ready(
                base,
                model,
                pull_timeout=float(args.get("pull_timeout") or 7200),
                load_timeout=float(args.get("load_timeout") or 600),
                on_progress=tp.lemonade_pull_progress_callback("lemonade_manage", model),
            )
        )

    if action == "unload":
        runtime.ensure_lemonade_running(base)
        model = str(args.get("model") or "").strip()
        cmd = ["lemonade", "unload"] + ([model] if model else [])
        return _json(_run_cli(cmd, timeout=120))

    if action == "delete":
        model = str(args.get("model") or "").strip()
        if not model:
            return _json({"error": "model is required for delete"})
        runtime.ensure_lemonade_running(base)
        return _json(_run_cli(["lemonade", "delete", model], timeout=300))

    return _json({"error": f"unknown action: {action}", "allowed": [
        "status", "start", "list_models", "pull", "load", "ensure_ready", "unload", "delete",
    ]})


def handle_comfyui_manage(args: Dict[str, Any], **kwargs: Any) -> str:
    action = str(args.get("action") or "").strip().lower()
    runtime = _load_common("runtime")
    comfy_workflows = _load_common("comfy_workflows")
    host = _comfy_host()

    if action == "status":
        return _json({"host": host, "running": runtime.comfy_is_running(host)})

    if action == "start":
        return _json(runtime.start_comfyui(host))

    if action == "stop":
        return _json(runtime.stop_comfyui())

    if action == "list_workflows":
        return _json({"workflows": comfy_workflows.list_workflow_names(_comfy_workflows_dir())})

    if action == "read_workflow":
        ref = str(args.get("workflow") or args.get("name") or "").strip()
        if not ref:
            return _json({"error": "workflow is required"})
        try:
            data = comfy_workflows.read_workflow(ref, _comfy_workflows_dir())
            spec = comfy_workflows.infer_workflow_spec(data)
            return _json({"workflow": ref, "spec": spec, "data": data})
        except Exception as exc:
            return _json({"error": str(exc)})

    if action == "write_workflow":
        name = str(args.get("name") or args.get("workflow") or "").strip()
        workflow = args.get("workflow_json")
        if not name:
            return _json({"error": "name is required"})
        if not isinstance(workflow, dict):
            return _json({"error": "workflow_json object is required"})
        try:
            path = comfy_workflows.write_workflow(
                name,
                workflow,
                overwrite=bool(args.get("overwrite", True)),
            )
            return _json({"saved": str(path), "name": name})
        except Exception as exc:
            return _json({"error": str(exc)})

    if action == "delete_workflow":
        name = str(args.get("name") or args.get("workflow") or "").strip()
        if not name:
            return _json({"error": "name is required"})
        deleted = comfy_workflows.delete_workflow(name)
        return _json({"deleted": deleted, "name": name})

    if action == "run_workflow":
        ref = str(args.get("workflow") or args.get("name") or "").strip()
        prompt = str(args.get("prompt") or "").strip()
        if not ref or not prompt:
            return _json({"error": "workflow and prompt are required"})
        start = runtime.ensure_comfyui_running(host)
        if not start.get("ok"):
            return _json({"error": "ComfyUI not running", "autostart": start})

        from agent.image_gen_registry import get_provider

        provider = get_provider("comfyui")
        if provider is None:
            return _json({"error": "comfyui provider not registered — enable image_gen/local-tools"})
        aspect = str(args.get("aspect_ratio") or "landscape")
        extra_args = args.get("args") if isinstance(args.get("args"), dict) else {}
        model = Path(ref).stem if "/" in ref or ref.endswith(".json") else ref
        call_kwargs = {"model": model, **extra_args}
        if args.get("seed") is not None:
            call_kwargs["seed"] = args.get("seed")
        if args.get("negative_prompt"):
            call_kwargs["negative_prompt"] = args.get("negative_prompt")
        result = provider.generate(prompt=prompt, aspect_ratio=aspect, **call_kwargs)
        return _json(result)

    if action == "install_model":
        runtime.ensure_comfyui_running(host)
        url = str(args.get("url") or "").strip()
        rel = str(args.get("relative_path") or "models/checkpoints").strip()
        if not url:
            return _json({"error": "url is required"})
        comfy = runtime._resolve_comfy_bin()  # noqa: SLF001 — shared helper
        if not comfy:
            return _json({"error": "comfy-cli not installed"})
        return _json(_run_cli([comfy, "model", "download", "--url", url, "--relative-path", rel], timeout=1800))

    if action == "install_node":
        runtime.ensure_comfyui_running(host)
        package = str(args.get("package") or args.get("node") or "").strip()
        if not package:
            return _json({"error": "package is required"})
        comfy = runtime._resolve_comfy_bin()  # noqa: SLF001
        if not comfy:
            return _json({"error": "comfy-cli not installed"})
        return _json(_run_cli([comfy, "node", "install", package], timeout=1800))

    if action == "list_models":
        runtime.ensure_comfyui_running(host)
        import requests

        try:
            resp = requests.get(f"{host.rstrip('/')}/models/checkpoints", timeout=15)
            if resp.status_code == 200:
                return _json({"checkpoints": resp.json()})
        except Exception:
            pass
        comfy = runtime._resolve_comfy_bin()  # noqa: SLF001
        if comfy:
            return _json(_run_cli([comfy, "model", "list"], timeout=120))
        return _json({"error": "could not list models"})

    if action == "install_comfyui":
        skill_setup = Path("/opt/hermes-agent/skills/creative/comfyui/scripts/comfyui_setup.sh")
        if not skill_setup.is_file():
            skill_setup = Path.home() / ".hermes/skills/creative/comfyui/scripts/comfyui_setup.sh"
        if not skill_setup.is_file():
            return _json({"error": f"comfyui_setup.sh not found"})
        gpu = str(args.get("gpu_flag") or "--nvidia")
        port = str(args.get("port") or "8188")
        return _json(_run_cli(["bash", str(skill_setup), gpu, f"--port={port}"], timeout=3600))

    return _json({"error": f"unknown action: {action}", "allowed": [
        "status", "start", "stop", "list_workflows", "read_workflow", "write_workflow",
        "delete_workflow", "run_workflow", "install_model", "install_node", "list_models",
        "install_comfyui",
    ]})


LEMONADE_MANAGE_SCHEMA = {
    "name": "lemonade_manage",
    "description": (
        "Optional Lemonade server diagnostics and maintenance (auto-start lemond, status, "
        "list_models, ensure_ready, unload, delete). Normal image requests should use "
        "image_generate only — it auto-starts Lemonade, auto-downloads missing models, waits "
        "with visible progress, and generates without manual pull/load steps."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "start", "list_models", "pull", "load", "ensure_ready", "unload", "delete"],
                "description": (
                    "status/start/list_models for health checks; pull/load/ensure_ready only for debugging "
                    "(image_generate handles download+load automatically)."
                ),
            },
            "model": {
                "type": "string",
                "description": "Model id for pull/load/unload/delete (e.g. SD-Turbo, Flux-2-Klein-4B).",
            },
        },
        "required": ["action"],
    },
}

COMFYUI_MANAGE_SCHEMA = {
    "name": "comfyui_manage",
    "description": (
        "ComfyUI maintenance and advanced workflows: auto-start/stop, list/read/write/delete workflow JSON "
        "under bundled workflows/ or ~/.hermes/image_gen/comfyui/workflows/, run workflows, install models/nodes, or bootstrap "
        "ComfyUI. For ordinary generation with image_gen.provider=comfyui, prefer image_generate; use this "
        "tool when creating custom workflows or installing assets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status", "start", "stop", "list_workflows", "read_workflow", "write_workflow",
                    "delete_workflow", "run_workflow", "install_model", "install_node", "list_models",
                    "install_comfyui",
                ],
            },
            "workflow": {"type": "string", "description": "Workflow id/path for read/run/delete."},
            "name": {"type": "string", "description": "Workflow name for write/delete (saved as name.json)."},
            "workflow_json": {
                "type": "object",
                "description": "Full ComfyUI API-format workflow object for write_workflow.",
            },
            "prompt": {"type": "string", "description": "Positive prompt for run_workflow."},
            "negative_prompt": {"type": "string", "description": "Optional negative prompt for run_workflow."},
            "aspect_ratio": {
                "type": "string",
                "enum": ["landscape", "square", "portrait"],
                "description": "Aspect ratio for run_workflow.",
            },
            "seed": {"type": "integer", "description": "Optional seed for run_workflow."},
            "args": {
                "type": "object",
                "description": "Extra kwargs forwarded to the ComfyUI image provider.",
            },
            "url": {"type": "string", "description": "Model download URL for install_model."},
            "relative_path": {
                "type": "string",
                "description": "Target folder for install_model (default models/checkpoints).",
            },
            "package": {"type": "string", "description": "Custom node package name for install_node."},
            "gpu_flag": {
                "type": "string",
                "description": "GPU flag for install_comfyui (--nvidia, --amd, --cpu).",
            },
            "port": {"type": "string", "description": "HTTP port for install_comfyui (default 8188)."},
            "overwrite": {"type": "boolean", "description": "Allow overwriting an existing workflow file."},
        },
        "required": ["action"],
    },
}


def _build_image_generate_schema() -> Dict[str, Any]:
    import copy

    from tools.image_generation_tool import IMAGE_GENERATE_SCHEMA

    schema = copy.deepcopy(IMAGE_GENERATE_SCHEMA)
    guidance = _load_common("agent_guidance")
    schema["description"] = guidance.image_generate_tool_description()
    return schema


def _handle_image_generate_patched(args: Dict[str, Any], **kwargs: Any) -> str:
    from tools.image_generation_tool import _handle_image_generate

    return _handle_image_generate(args, **kwargs)


def _image_generate_check_fn() -> bool:
    from tools.image_generation_tool import check_image_generation_requirements

    return check_image_generation_requirements()


def _on_pre_llm_call(**_kwargs: Any) -> Optional[Dict[str, str]]:
    guidance = _load_common("agent_guidance")
    context = guidance.build_pre_llm_context()
    if context:
        return {"context": context}
    return None


def register_tools(ctx) -> None:
    _load_common("display_patch").ensure_display_patch()
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_tool(
        name="image_generate",
        toolset="image_gen",
        schema=_build_image_generate_schema(),
        handler=_handle_image_generate_patched,
        check_fn=_image_generate_check_fn,
        description="Generate images (local Lemonade/ComfyUI-aware description)",
        emoji="🎨",
        override=True,
    )
    ctx.register_tool(
        name="lemonade_manage",
        toolset="image_gen",
        schema=LEMONADE_MANAGE_SCHEMA,
        handler=handle_lemonade_manage,
        description=LEMONADE_MANAGE_SCHEMA["description"],
        emoji="🍋",
    )
    ctx.register_tool(
        name="comfyui_manage",
        toolset="image_gen",
        schema=COMFYUI_MANAGE_SCHEMA,
        handler=handle_comfyui_manage,
        description=COMFYUI_MANAGE_SCHEMA["description"],
        emoji="🧩",
    )
