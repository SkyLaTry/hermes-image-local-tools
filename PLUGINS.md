# SkyLaTry Hermes plugins

Companion plugins for [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.15.1+** by [SkyLaTry](https://github.com/SkyLaTry).

**Start here:** [hermes-essentials](https://github.com/SkyLaTry/hermes-essentials) — personalities, memory routing, `/forget`, proactive mode, camera-in, TTS, `/themes`, and `/deps`. Most other plugins build on or pair with it.

## Plugin index

| Plugin | Repository | Hermes plugin ID |
|--------|------------|------------------|
| **Hermes Essentials** | [SkyLaTry/hermes-essentials](https://github.com/SkyLaTry/hermes-essentials) | `hermes-essentials` |
| Screen Awareness | [SkyLaTry/hermes-screen-awareness](https://github.com/SkyLaTry/hermes-screen-awareness) | `screen-awareness` |
| Sys Controll | [SkyLaTry/hermes-sys-controll](https://github.com/SkyLaTry/hermes-sys-controll) | `sys-controll` |
| Lemonade LLM Image | [SkyLaTry/hermes-lemonade-llm-image-support](https://github.com/SkyLaTry/hermes-lemonade-llm-image-support) | `image_gen/lemonade-llm-image-support` |
| Image Local Tools | [SkyLaTry/hermes-image-local-tools](https://github.com/SkyLaTry/hermes-image-local-tools) | `image_gen/local-tools` |

Machine-readable catalog: [plugins-catalog.json](https://raw.githubusercontent.com/SkyLaTry/hermes-essentials/main/plugins-catalog.json) (hosted on essentials).

## Install

### Hermes Essentials

```bash
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-essentials/main/install.sh | bash
hermes gateway restart
```

Or: `hermes plugins install SkyLaTry/hermes-essentials --enable`

### Screen Awareness · Sys Controll

Flat plugins — install to `~/.hermes/plugins/<name>/`:

```bash
hermes plugins install SkyLaTry/hermes-essentials --enable
hermes plugins install SkyLaTry/hermes-screen-awareness --enable   # or hermes-sys-controll
hermes gateway restart
```

Or one-liner per repo (pulls essentials if the script says so):

```bash
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-screen-awareness/main/install.sh | bash
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-sys-controll/main/install.sh | bash
```

### Image generation (Lemonade · ComfyUI tools)

**Must** use each repo's `install.sh` — Hermes expects these under `image_gen/`, not the flat plugins folder:

```bash
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-lemonade-llm-image-support/main/install.sh | bash
curl -fsSL https://raw.githubusercontent.com/SkyLaTry/hermes-image-local-tools/main/install.sh | bash
hermes gateway restart
```

Enable in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - image_gen/lemonade-llm-image-support
    - image_gen/local-tools
```

## Suggested stack

| Use case | Plugins |
|----------|---------|
| Core agent UX | essentials |
| + Monitor vision | essentials + screen-awareness |
| + Bridge Telegram → local TUI | essentials + sys-controll |
| + Local image gen | essentials + local-tools (+ lemonade optional) |

## License

SkyLaTry Shared Source License — see LICENSE and LICENSING.md in each repository.
