# ArcEnCiel Link for Forge / Stable Diffusion WebUI

ArcEnCiel Link connects [arcenciel.io](https://arcenciel.io) to Forge/WebUI: download models, review image settings in your generator, and prepare the resources they require.

## Send image settings and prepare resources (2.5.1)

Use **Send to Link** on an Arc image or in its metadata to check the original settings against this
host. Unambiguous Steps, CFG, seed, size and sampling settings remain transferable when the image also
uses ADetailer or Hires; additional stages have their own compatibility warnings. Verified Arc resources
use the native catalog name, including renamed LoRAs and their recorded strengths. Missing or ambiguous
resources remain visible before sending.

New transfers arrive directly in **txt2img**, with no additional Link tab. Keep that editor open; a
new transfer applies after confirmation in Arc when the receiving tab has not been edited. Existing
pending transfers and edited tabs show **Apply to txt2img**. One browser tab receives automatically.
The previous settings are saved locally and **Undo import** restores them if no later edit was made.
Shift, Beta scheduler parameters and VAE/text encoder modules are supported when the host exposes them.

Sending settings never starts generation. Device draft permission is controlled in the Arc Link Hub;
ordinary downloads continue to use the existing device key and model folders. Restart the host after
upgrading the extension. A changed runtime or source requires a fresh check rather than replaying an old draft.

## Version 2.3

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

For an existing notebook host, use the [versioned Link setup notebook](https://github.com/FallenIncursio/arcenciel-link-webui/blob/v2.5.1/notebooks/ArcEnCiel_Link_Setup.ipynb). It supports WebUI/Forge, ComfyUI, and SwarmUI, validates the host checkout, installs the tagged extension, and loads Colab Secrets. It does not install a model or the host itself. Select **Remote / Colab** on the website and keep the bridge private. A health-probe log alone is not proof of an authenticated worker or a completed download.

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

## Reliable download attempts (2.2.0)

The worker negotiates `job_lease_v1` with ArcEnCiel. Each device accepts one reserved download at a time and
acknowledges the attempt before opening a file. A fresh runtime identity, periodic heartbeats and attempt IDs
prevent stale workers from changing completed or cancelled jobs. The server retries expired attempts at most
three times, then reports an actionable error. Restarting a lost transfer currently downloads the file again.

Cancel interrupts the stream, hash check and retry wait, cleans this attempt's partial file and confirms cleanup.
If cancellation arrives after the atomic file commit, the installed model stays on disk. Legacy server compatibility
is retained; automatic recovery requires the updated ArcEnCiel server. Keep each device on its own Link Key.

## Guided setup (2.4.0)

Open [Link Hub](https://arcenciel.io/link) to choose your host and location, create or import a device key, and verify the setup. Local discovery runs only when requested; another computer or Google Colab connects directly without a local browser scan. Existing keys and downloads remain compatible.

Workers advertise `setup_check_v1`. A setup check transfers a fixed 4 KiB file into the selected native model folder, flushes and reads it back, verifies SHA-256, and deletes the temporary file. The result is bound to one key and runtime; shared keys, paused or busy workers cannot complete the check. Stable errors explain storage, write, transfer and cleanup failures. The check does not install a model or alter download history. The `Finish setup` button appears only after verification.

## Device tools (2.4.0)

Select this device in [Link Hub](https://arcenciel.io/link) and open **Device tools** to scan its library, inspect its download
subfolders or repair missing sidecars. The same actions work on another computer and in Google Colab through the outbound
Link connection. Use a separate Link key with inventory permission for each host/runtime.

Scans publish empty inventories as well as changes. Repair fills missing metadata and previews for models visible to your
account, preserves existing sidecars and never changes model bytes. A sidecar failure after download leaves the model completed
and shows a warning; correct permissions and retry repair. Tools show progress and support cancellation. Reconnect and start a
new scan after a timeout; interrupted work is not replayed automatically. Upgrade and restart the host to advertise `device_tools_v1`.
A small native Link panel shows the extension version and latest operation. Folder choices use the native download destination;
inventories also include other configured model roots.

## Release verification (2.4.2)

The broker reports its source revision and active deployment color. A broker retirement reconnects the worker without changing its runtime ID or cancelling an acknowledged download. Existing 2.4.0 workers remain compatible. The Link operations runbook records tested host/browser versions and transfer evidence; a healthy socket alone is not a completed-download check.
