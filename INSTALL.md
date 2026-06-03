# Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) 0.15.1+.

**One command:**

```bash
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-image-local-tools/main/install.sh | bash
hermes gateway restart
```

**Manual:**

```bash
mkdir -p ~/.hermes/plugins/image_gen
git clone https://github.com/SkyLaTry/hermes-image-local-tools.git \
  ~/.hermes/plugins/image_gen/local-tools
hermes plugins enable image_gen/local-tools
hermes gateway restart
```

Includes **ComfyUI backend** (`workflows/`, `comfyui_provider.py`) — no separate comfyui plugin.

```yaml
plugins:
  enabled:
    - image_gen/local-tools
    - image_gen/lemonade-llm-image-support   # optional, for provider: lemonade

image_gen:
  provider: comfyui   # or lemonade
```

See [README.md](README.md) for configuration and migration notes.
