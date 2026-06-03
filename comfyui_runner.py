"""Minimal ComfyUI REST client for Hermes image generation."""

from __future__ import annotations

import copy
import json
import logging
import random
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://127.0.0.1:8188"
DEFAULT_TIMEOUT = 600.0


def _random_seed() -> int:
    return random.randint(0, 2**32 - 1)


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(self, host: str, api_key: str = "", timeout: float = DEFAULT_TIMEOUT):
        self.host = host.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex
        self.is_cloud = "cloud.comfy.org" in self.host

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        if self.is_cloud and not path.startswith("/api/"):
            path = "/api" + path
        return f"{self.host}{path}"

    def check_server(self) -> bool:
        try:
            resp = requests.get(self._url("/system_stats"), headers=self._headers(), timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def submit(self, workflow: Dict[str, Any]) -> str:
        body = {"prompt": workflow, "client_id": self.client_id}
        resp = requests.post(
            self._url("/prompt"),
            headers=self._headers(),
            json=body,
            timeout=60,
        )
        if resp.status_code >= 400:
            raise ComfyUIError(f"ComfyUI prompt submit failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        if not isinstance(data, dict):
            raise ComfyUIError("ComfyUI prompt submit returned non-object JSON")
        node_errors = data.get("node_errors") or {}
        if node_errors:
            raise ComfyUIError(f"ComfyUI workflow validation failed: {json.dumps(node_errors)[:500]}")
        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUIError("ComfyUI prompt submit missing prompt_id")
        return prompt_id

    def poll(self, prompt_id: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        interval = 1.0
        while time.monotonic() < deadline:
            if self.is_cloud:
                resp = requests.get(
                    self._url(f"/job/{prompt_id}/status"),
                    headers=self._headers(),
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json() if resp.content else {}
                    status = data.get("status") if isinstance(data, dict) else None
                    if status == "completed":
                        job = requests.get(
                            self._url(f"/jobs/{prompt_id}"),
                            headers=self._headers(),
                            timeout=60,
                        )
                        if job.status_code == 200 and isinstance(job.json(), dict):
                            return job.json()
                    if status in {"failed", "cancelled"}:
                        raise ComfyUIError(f"ComfyUI job {prompt_id} {status}")
            else:
                resp = requests.get(
                    self._url(f"/history/{prompt_id}"),
                    headers=self._headers(),
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json() if resp.content else {}
                    entry = data.get(prompt_id) if isinstance(data, dict) else None
                    if isinstance(entry, dict):
                        status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
                        if status.get("status_str") == "error":
                            raise ComfyUIError(f"ComfyUI execution error: {json.dumps(status)[:500]}")
                        if status.get("completed"):
                            return entry
            time.sleep(interval)
            interval = min(5.0, interval * 1.3)
        raise ComfyUIError(f"ComfyUI job {prompt_id} timed out after {int(self.timeout)}s")

    def download_image(self, filename: str, subfolder: str = "", file_type: str = "output") -> bytes:
        params = urlencode({"filename": filename, "subfolder": subfolder, "type": file_type})
        resp = requests.get(
            self._url(f"/view?{params}"),
            headers=self._headers(),
            timeout=120,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            raise ComfyUIError(f"ComfyUI download failed ({resp.status_code}) for {filename}")
        return resp.content


def inject_workflow(
    workflow: Dict[str, Any],
    *,
    prompt: str,
    width: int,
    height: int,
    seed: Optional[int] = None,
    spec: Dict[str, Any],
    negative_prompt: str = "",
) -> Dict[str, Any]:
    wf = copy.deepcopy(workflow)
    prompt_target = spec.get("prompt")
    if not prompt_target:
        raise ComfyUIError("Workflow has no injectable prompt node (CLIPTextEncode)")
    prompt_node, prompt_field = prompt_target
    wf[prompt_node]["inputs"][prompt_field] = prompt

    negative_target = spec.get("negative")
    if negative_target and negative_prompt:
        neg_node, neg_field = negative_target
        wf[neg_node]["inputs"][neg_field] = negative_prompt

    latent_node = spec.get("latent")
    if latent_node:
        node_id, w_field, h_field = latent_node
        wf[node_id]["inputs"][w_field] = width
        wf[node_id]["inputs"][h_field] = height

    seed_targets: List[Tuple[str, str]] = list(spec.get("seed_fields") or [])
    if seed is None:
        seed = _random_seed()
    for node_id, field in seed_targets:
        if node_id in wf and isinstance(wf[node_id], dict):
            inputs = wf[node_id].setdefault("inputs", {})
            if field in inputs and not _is_link(inputs.get(field)):
                inputs[field] = seed
    return wf


def _is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)


def first_output_image(result: Dict[str, Any]) -> Tuple[str, str, str]:
    outputs = result.get("outputs") if isinstance(result, dict) else None
    if not isinstance(outputs, dict):
        raise ComfyUIError("ComfyUI result missing outputs")
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        images = node_output.get("images")
        if not isinstance(images, list) or not images:
            continue
        first = images[0]
        if not isinstance(first, dict):
            continue
        filename = str(first.get("filename") or "").strip()
        if filename:
            return (
                filename,
                str(first.get("subfolder") or ""),
                str(first.get("type") or "output"),
            )
    raise ComfyUIError("ComfyUI outputs contained no images")


def aspect_to_size(aspect_ratio: str, base: int = 1024) -> Tuple[int, int]:
    if aspect_ratio == "portrait":
        w, h = int(base * 0.75), base
    elif aspect_ratio == "landscape":
        w, h = base, int(base * 0.75)
    else:
        w, h = base, base
    w = max(256, (w // 8) * 8)
    h = max(256, (h // 8) * 8)
    return w, h
