# hermes-image-local-tools

**ComfyUI + agent tooling for local image generation in Hermes** — workflows, model management, and LLM schema hints in one plugin.

**Author:** [SkyLaTry](https://github.com/SkyLaTry) · **Hermes:** 0.15.1+ · **Plugin ID:** `image_gen/local-tools` · **Version:** 1.3.0 · **Repo:** [SkyLaTry/hermes-image-local-tools](https://github.com/SkyLaTry/hermes-image-local-tools)

Part of the [SkyLaTry Hermes plugin set](https://github.com/SkyLaTry/hermes-essentials/blob/main/PLUGINS.md).

Pair with **[hermes-lemonade-llm-image-support](https://github.com/SkyLaTry/hermes-lemonade-llm-image-support)** for a Lemonade-only backend, or use this plugin’s built-in **ComfyUI** provider.

---

## What it does

`local-tools` is the **power-user** image stack for Hermes:

- **ComfyUI backend** — SD 1.5, SDXL, and Flux Dev workflows included under `workflows/`
- **Agent tools** — `comfyui_manage`, `lemonade_manage` for start/stop, workflows, models, and nodes
- **LLM guidance** — `pre_llm_call` hook teaches the agent how to call `image_generate` correctly

ComfyUI is **bundled in this plugin** (not a separate SkyLaTry repo). Install path: `image_gen/local-tools/`.

---

## Use cases

| Scenario | What you get |
|----------|----------------|
| **Custom ComfyUI graphs** | Ship or edit JSON workflows; agent runs them via ComfyUI on your GPU. |
| **Project asset pipelines** | Generate UI mockups, textures, sprites, or concept art without leaving the agent chat. |
| **Local-first creative work** | No cloud image APIs; full control over models and nodes on your machine. |
| **Agent-operated ComfyUI** | Start/stop ComfyUI, list workflows, install models — via `comfyui_manage` tool calls. |
| **Dual-backend setup** | ComfyUI for complex graphs; [Lemonade](https://github.com/SkyLaTry/hermes-lemonade-llm-image-support) for fast txt2img — switch with `image_gen.provider`. |
| **Onboarding the model** | Schema hints reduce bad `image_generate` calls (wrong sizes, missing prompts, etc.). |

**Included workflows:** `workflows/sd15_txt2img.json`, `sdxl_txt2img.json`, `flux_dev_txt2img.json`.

---

## Quick start

```bash
# Hermes (once)
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# This plugin → ~/.hermes/plugins/image_gen/local-tools/
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-image-local-tools/main/install.sh | bash
hermes gateway restart
```

> **Important:** Must install under `image_gen/local-tools/`. Plain `hermes plugins install` puts files in the wrong directory.

**Manual install:**

```bash
mkdir -p ~/.hermes/plugins/image_gen
git clone https://github.com/SkyLaTry/hermes-image-local-tools.git \
  ~/.hermes/plugins/image_gen/local-tools
hermes plugins enable image_gen/local-tools
hermes gateway restart
```

See [INSTALL.md](INSTALL.md) for a short checklist.

---

## Enable in config

```yaml
plugins:
  enabled:
    - image_gen/local-tools
    - image_gen/lemonade-llm-image-support   # optional second backend

image_gen:
  provider: comfyui   # or lemonade

  comfyui:
    host: http://127.0.0.1:8188

  lemonade:
    base_url: http://127.0.0.1:13305/api/v1
```

Environment: `COMFYUI_HOST`, `LEMONADE_BASE_URL`, etc.

---

## Agent tools

| Tool | Purpose |
|------|---------|
| `comfyui_manage` | Lifecycle, workflows, models, nodes for ComfyUI |
| `lemonade_manage` | Start/stop/status Lemonade Server (pairs with lemonade plugin) |

The agent also receives **pre-LLM schema hints** so image requests use the right parameters for your enabled provider.

---

## Example flows

1. **“Start ComfyUI and generate a Flux wallpaper”** — agent uses `comfyui_manage` + `image_generate`.
2. **Batch concept art** — iterate prompts in TUI; files land on disk for your art pipeline.
3. **Lemonade-only laptop** — enable lemonade plugin, set `provider: lemonade`, keep local-tools for `lemonade_manage` and shared guidance.

---

## Migration from `image_gen/comfyui`

Remove legacy `image_gen/comfyui` from `plugins.enabled`. Enable only `image_gen/local-tools` and set `image_gen.provider: comfyui`.

---

## Related SkyLaTry plugins

See [PLUGINS.md](PLUGINS.md) for the full index.

| Plugin | Repository |
|--------|------------|
| Hermes Essentials | [hermes-essentials](https://github.com/SkyLaTry/hermes-essentials) |
| Screen Awareness | [hermes-screen-awareness](https://github.com/SkyLaTry/hermes-screen-awareness) |
| Sys Controll | [hermes-sys-controll](https://github.com/SkyLaTry/hermes-sys-controll) |
| Lemonade LLM Image | [hermes-lemonade-llm-image-support](https://github.com/SkyLaTry/hermes-lemonade-llm-image-support) |
| **Image Local Tools** *(this repo)* | [hermes-image-local-tools](https://github.com/SkyLaTry/hermes-image-local-tools) |

---

## License

SkyLaTry Shared Source License — see [LICENSE](LICENSE) and [LICENSING.md](LICENSING.md).
