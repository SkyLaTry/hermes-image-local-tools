"""ComfyUI workflow discovery, inference, and user-writable workflow storage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_USER_WORKFLOW_DIR = Path.home() / ".hermes" / "image_gen" / "comfyui" / "workflows"
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def user_workflow_dir() -> Path:
    path = _USER_WORKFLOW_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)


def iter_nodes(workflow: Dict[str, Any]):
    for node_id, node in workflow.items():
        if node_id.startswith("_") or not isinstance(node, dict):
            continue
        if "class_type" in node:
            yield node_id, node


def infer_workflow_spec(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort injection map for an API-format ComfyUI workflow."""
    prompt_node: Optional[Tuple[str, str]] = None
    negative_node: Optional[Tuple[str, str]] = None
    latent_node: Optional[Tuple[str, str, str]] = None
    seed_fields: List[Tuple[str, str]] = []
    base_size = 1024

    for node_id, node in iter_nodes(workflow):
        cls = node.get("class_type")
        inputs = node.get("inputs") or {}
        title = str((node.get("_meta") or {}).get("title") or "").lower()

        if cls == "CLIPTextEncode":
            if "negative" in title and negative_node is None:
                negative_node = (node_id, "text")
            elif prompt_node is None and "negative" not in title:
                prompt_node = (node_id, "text")

        if cls in ("EmptyLatentImage", "EmptySD3LatentImage") and latent_node is None:
            latent_node = (node_id, "width", "height")
            try:
                base_size = int(inputs.get("width") or inputs.get("height") or base_size)
            except (TypeError, ValueError):
                pass

        if cls in ("KSampler", "KSamplerAdvanced") and "seed" in inputs:
            seed_fields.append((node_id, "seed"))
        if cls == "RandomNoise" and "noise_seed" in inputs:
            seed_fields.append((node_id, "noise_seed"))

    if prompt_node is None:
        for node_id, node in iter_nodes(workflow):
            if node.get("class_type") == "CLIPTextEncode":
                prompt_node = (node_id, "text")
                break

    return {
        "prompt": prompt_node,
        "negative": negative_node,
        "latent": latent_node,
        "seed_fields": seed_fields,
        "base_size": base_size,
    }


def discover_workflows(plugin_workflow_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Return {workflow_id: metadata} from bundled plugin dir + user dir."""
    catalog: Dict[str, Dict[str, Any]] = {}

    def _scan(directory: Path, *, source: str) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.json")):
            workflow_id = path.stem
            if workflow_id in catalog:
                workflow_id = f"{source}-{path.stem}"
            try:
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict):
                    continue
            except Exception:
                continue
            spec = infer_workflow_spec(data)
            catalog[workflow_id] = {
                "display": path.stem.replace("_", " ").title(),
                "workflow": path.name,
                "path": str(path),
                "source": source,
                "speed": "local",
                "strengths": f"ComfyUI workflow ({source})",
                "base_size": int(spec.get("base_size") or 1024),
                **spec,
            }

    _scan(plugin_workflow_dir, source="bundled")
    _scan(user_workflow_dir(), source="user")
    return catalog


def resolve_workflow_path(workflow_ref: str, plugin_workflow_dir: Path) -> Path:
    ref = (workflow_ref or "").strip()
    if not ref:
        raise ValueError("workflow reference is required")

    candidate = Path(ref).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    if not _SAFE_NAME_RE.match(ref):
        raise ValueError(f"invalid workflow name: {ref}")

    for directory in (user_workflow_dir(), plugin_workflow_dir):
        path = directory / f"{ref}.json"
        if path.is_file():
            return path.resolve()
        if (directory / ref).is_file():
            return (directory / ref).resolve()

    raise FileNotFoundError(f"workflow not found: {ref}")


def read_workflow(workflow_ref: str, plugin_workflow_dir: Path) -> Dict[str, Any]:
    path = resolve_workflow_path(workflow_ref, plugin_workflow_dir)
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"workflow JSON must be an object: {path}")
    return data


def write_workflow(name: str, workflow: Dict[str, Any], *, overwrite: bool = True) -> Path:
    if not _SAFE_NAME_RE.match(name):
        raise ValueError("workflow name must be alphanumeric with ._- only")
    path = user_workflow_dir() / f"{name}.json"
    if path.exists() and not overwrite:
        raise FileExistsError(f"workflow already exists: {name}")
    path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return path


def delete_workflow(name: str) -> bool:
    path = user_workflow_dir() / f"{name}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def list_workflow_names(plugin_workflow_dir: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for workflow_id, meta in discover_workflows(plugin_workflow_dir).items():
        rows.append(
            {
                "id": workflow_id,
                "display": str(meta.get("display") or workflow_id),
                "source": str(meta.get("source") or ""),
                "path": str(meta.get("path") or ""),
            }
        )
    return rows
