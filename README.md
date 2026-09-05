# ArcEnCiel Link for Forge / Stable Diffusion WebUI

ArcEnCiel Link sends one-click model downloads from [arcenciel.io](https://arcenciel.io) to Forge Classic and compatible Stable Diffusion WebUIs.

## Version 2.1

- Link Keys (`lk_...`) are the only supported Link credential.
- Private downloads use a short-lived header grant bound to the configured ArcEnCiel HTTPS origin; redirects are refused.
- Worker enablement survives WebUI restarts.
- Checkpoint, LoRA, VAE, embedding, GGUF, `.sft`, and plural Forge directory overrides are included in inventory scans.
- A dedicated loopback-only bridge on port `8501` keeps CORS/PNA scoped to the extension routes.
- Generated HTML sidecars escape all remote metadata.

## Features

- Model-aware routing for checkpoints, LoRAs, VAEs, and embeddings.
- Retry back-off, free-space guard, SHA-256 verification, and live progress.
- Hourly full inventory reconciliation so nested or externally added files are detected.
- Optional `.preview.png`, `.arcenciel.info`, `.json`, and `.arcenciel.html` sidecars.
- OS keyring storage when available, with a mode-`0600` config fallback.

## Installation

In Forge/WebUI, open `Extensions -> Install from URL` and use:

```text
https://github.com/FallenIncursio/arcenciel-link-webui.git
```

Restart the WebUI after installation. For a manual development install:

```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/FallenIncursio/arcenciel-link-webui.git
pip install -r arcenciel-link-webui/requirements.txt
```

## Connect

1. Start Forge/WebUI with the extension installed.
2. Open the ArcEnCiel Link panel on [arcenciel.io](https://arcenciel.io).
3. Generate or select a Link Key and press **Connect**.
4. Select the detected `8501` endpoint if more than one WebUI is running.

The fallback settings are under `Settings -> ArcEnCiel`. The worker only starts automatically when `Enable ArcEnCiel Link worker` is set.

### Google Colab and other hosted runtimes

The browser cannot reach a WebUI loopback bridge running inside Colab. Configure the same Link Key in the hosted runtime before the WebUI
starts, then leave the website endpoint on **Remote / Colab**:

```python
from google.colab import userdata
import os

os.environ["ARCENCIEL_LINK_KEY"] = userdata.get("ARCENCIEL_LINK_KEY").strip()
os.environ["ARCENCIEL_LINK_ENABLED"] = "1"
```

Store `ARCENCIEL_LINK_KEY` in Colab Secrets; do not paste it into a shared notebook. The extension connects outbound over HTTPS/WSS, so
port `8501` remains loopback-only and must not be exposed through a public tunnel.

## Hosted configuration (2.1.0)

All three Link workers use the same runtime variables. Set them **before starting the host**:

| Variable                 | Meaning                                                                    |
| ------------------------ | -------------------------------------------------------------------------- |
| `ARCENCIEL_LINK_URL`     | HTTPS API base; normally `https://link.arcenciel.io/api/link`.             |
| `ARCENCIEL_LINK_KEY`     | Dedicated Link Key from Colab Secrets or your runtime secret store.        |
| `ARCENCIEL_LINK_ENABLED` | Startup preference: `1/true/yes/on` or `0/false/no/off`, case-insensitive. |

Explicit environment variables override saved desktop settings, including explicitly empty values. An empty key never falls back to a saved key. Missing/invalid credentials or an invalid enabled value prevent automatic downloads and produce a value-free diagnostic. Environment values are not written to the extension config or OS keyring when you pause or resume; previous desktop settings remain available after removing the overrides.

Pause/resume works during the current process. On restart, `ARCENCIEL_LINK_ENABLED` takes effect again. Changing an environment-managed key through the browser is rejected: update the runtime secret and restart the host. Existing desktop installations with valid settings need no migration. Protocol 2 and the browser toggle payload are unchanged.

For an existing notebook host, use the [versioned Link setup notebook](https://github.com/FallenIncursio/arcenciel-link-webui/blob/v2.1.1/notebooks/ArcEnCiel_Link_Setup.ipynb). It supports WebUI/Forge, ComfyUI, and SwarmUI, validates the host checkout, installs the tagged extension, and loads Colab Secrets. It does not install a model or the host itself. Select **Remote / Colab** on the website and keep the bridge private. A health-probe log alone is not proof of an authenticated worker or a completed download.

## Configuration and security

The production API endpoint is `https://link.arcenciel.io/api/link`. HTTP endpoints and private origins are accepted only when `ARCENCIEL_DEV=1` or the WebUI `--dev` flag is present.

Environment overrides:

- `ARCENCIEL_LINK_URL`
- `ARCENCIEL_LINK_KEY`
- `ARCENCIEL_LINK_ENABLED=1|0`
- `ARCENCIEL_DEV=1`

Configuration is stored in `arcenciel_link/config.json`; the Link Key is moved to the OS keyring when a usable backend exists. Old retired credential fields are removed when the config is loaded and saved. The browser bridge defaults to `bridge_port: 8501`; set it to `0` only when Forge itself is launched with a compatible explicit CORS configuration.

## Local routes

- `GET /arcenciel-link/ping`
- `POST /arcenciel-link/toggle_link`
- `GET /arcenciel-link/folders/{kind}`
- `POST /arcenciel-link/generate_sidecars`

Only these extension routes emit ArcEnCiel CORS/PNA headers. Forge's own server consumes cross-origin preflights before extension routes run, so the default bridge binds only to `127.0.0.1:8501`; the host WebUI middleware is not modified.

## Development

Use Python 3.10 or newer:

```bash
python -m pip install -r requirements.txt pytest ruff fastapi
ruff format --check .
ruff check .
pytest -q
```

Tags must match both `pyproject.toml` and `arcenciel_link/version.py`. A `vX.Y.Z` tag creates a GitHub Release asset.

## Troubleshooting

| Symptom                      | Check                                                                                   |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| Worker offline               | Confirm a valid Link Key and enabled worker; inspect `arcenciel_link/client-debug.log`. |
| WebUI not detected           | Use **Find WebUIs** or assign a custom loopback endpoint.                               |
| Browser blocks local request | Accept the Private Network Access prompt and keep the public site on HTTPS.             |
| Download stays at 0%         | Check free disk space and model-directory permissions.                                  |
| SHA-256 mismatch             | Retry and check network or mirror stability.                                            |

## License

[MIT](LICENSE)
