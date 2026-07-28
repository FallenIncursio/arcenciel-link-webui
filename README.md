# Arc en Ciel Link - AUTOMATIC1111 Extension

> Bring your Arc en Ciel models straight into Stable Diffusion WebUI with one click - with Link Key auth, remote worker controls, inventory sync, and local sidecar generation.

---

## Release Notes (latest)

- Updated onboarding to a **Connect-first** flow: with the extension installed and local UI running, open ArcEnCiel Link panel on [arcenciel.io](https://arcenciel.io) and click **Connect**.
- Documented auto-detect behavior for local endpoints: `127.0.0.1` / `localhost` on ports `7860`, `7861`, `7801`, `8000`, `8501`.
- Added explicit **Custom endpoint** fallback guidance for non-standard host/port setups.
- Corrected queue/progress wording: status is shown in the **ArcEnCiel Link panel** and local worker logs.
- Updated credential messaging: **Link Key (`lk_...`) is primary**; **API key is legacy/deprecated** for current websocket flow.
- Replaced outdated setup/video references and aligned troubleshooting with current Connect + endpoint flow.

---

## ✨ Features

- One-click **➕ Download** on Arc en Ciel model cards.
- **Model-aware routing** for checkpoints, LoRAs, VAEs, and embeddings.
- Background worker with retry back-off, disk-space guard, SHA-256 verification, and live console logs.
- Remote worker control from the ArcEnCiel Link panel (website) through the local bridge endpoint.
- Hourly inventory sync so duplicates are skipped when hashes already exist locally.
- Optional sidecars next to downloaded models (`.preview.png`, `.arcenciel.info`, optional `.html`).
- Secrets stored in the OS keyring when available; `config.json` fallback when no secure backend exists.

---

## 🛠 Installation

### Fast way (GUI)

1. Open Stable Diffusion WebUI.
2. Go to `Extensions -> Install from URL`.
3. Paste:

   ```bash
   https://github.com/FallenIncursio/arcenciel-link-webui.git
   ```

4. Click Install, then restart WebUI.
5. The ArcEnCiel settings section appears in WebUI.

### Manual / dev install

```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/FallenIncursio/arcenciel-link-webui.git
pip install -r arcenciel-link-webui/requirements.txt
# restart webui
```

---

## 🔑 First-time setup (Connect-first)

1. Install/update the extension and make sure WebUI is running.
2. On [arcenciel.io](https://arcenciel.io) open the **ArcEnCiel Link panel**, create or select a **Link Key (`lk_...`)**, then click **Connect**.
3. If only one local endpoint is detected, ArcEnCiel assigns it and enables the worker automatically.
4. If WebUI runs on a non-standard host/port, use **Find WebUIs** and select an endpoint (or **Custom...**).
5. Fallback: set credentials manually in WebUI `Settings -> ArcEnCiel`.

---

## 🛡️ Credentials and security

- **Link Key (`lk_...`) is the primary credential** for current ArcEnCiel worker websocket auth.
- API key fields remain for legacy/self-hosted compatibility, but Link Keys are recommended for all active setups.
- At startup, existing credentials are migrated into the OS keyring (`keyring` package) when available.
- If no keyring backend exists, secrets remain in `arcenciel_link/config.json`.
- Environment variables override file/UI settings:
  - `ARCENCIEL_LINK_URL` - base API URL.
  - `ARCENCIEL_LINK_KEY` - Link Key (`lk_...`).
  - `ARCENCIEL_API_KEY` - API key (legacy).
  - `ARCENCIEL_DEV` - allow HTTP endpoints and private origins for testing.
- Delete the `arcenciel-link` keyring entry to revoke cached credentials on the machine.

---

## 🚀 How to use

- Press Download on any Arc en Ciel model card.
- Queue/progress state is visible in the ArcEnCiel Link panel and in local WebUI worker console logs.
- The worker retries failed downloads with exponential back-off and pauses below `min_free_mb`.
- Inventory sync runs hourly and the backend skips models already installed locally.
- With Link Keys, the dashboard can remotely toggle the worker, push credentials, and request folder lists.

### 🖼 Optional cover / metadata

When provided by the backend, the extension saves:

```text
model.safetensors
model.preview.png
model.arcenciel.info   # compact JSON
model.html             # optional quick-view (disabled by default)
```

Enable HTML quick-views with `"save_html_preview": true` in `arcenciel_link/config.json`.

---

## ⚙️ Advanced configuration

- `webui_root`, `min_free_mb`, `max_retries`, and `backoff_base` live in `arcenciel_link/config.json`.
- Passing `--dev` to WebUI or setting `ARCENCIEL_DEV=1` enables HTTP endpoints (for example `http://localhost:3000/api/link`) and private origins for testing.
- Folder overrides from WebUI args (`--ckpt-dir`, `--lora-dir`, etc.) are honored automatically.

---

## 📹 Video tutorial

Updated walkthrough video: coming soon (previous video has been retired).

---

## 🆘 Troubleshooting

| Symptom                                            | Fix                                                                                                                                                                                                        |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Worker stays offline                               | Use a valid Link Key (`lk_...`) and click Connect in the ArcEnCiel Link panel. Check WebUI logs for `[AEC-LINK] authentication failed` or scope errors.                                                    |
| Connect only works after manual endpoint selection | ArcEnCiel auto-detect scans `127.0.0.1` and `localhost` on ports `7860`, `7861`, `7801`, `8000`, `8501`. For custom host/port, assign the endpoint manually via **Custom...** in the ArcEnCiel Link panel. |
| Browser reports private network blocked            | Accept the Private Network Access prompt or allow origin `https://arcenciel.io` in browser/network policy.                                                                                                 |
| Remote toggle does nothing                         | Confirm the local bridge returns `Access-Control-Allow-Private-Network: true` and that WebUI is still running.                                                                                             |
| Download stuck at 0%                               | Check free disk space and write permissions; the worker aborts below configured `min_free_mb`.                                                                                                             |
| Repeated `SHA256 mismatch`                         | Usually unstable mirrors/network. Worker retries automatically; contact Arc en Ciel if persistent for one model/version.                                                                                   |
| API key no longer connects worker                  | API keys are legacy. For current ArcEnCiel websocket auth, use a Link Key.                                                                                                                                 |
| Need more diagnostics                              | Inspect `arcenciel_link/client-debug.log` for websocket/control details.                                                                                                                                   |

---

## 🤝 Contributing

PRs and issue reports are welcome. Open a discussion before large feature work to avoid overlap.

---

## 📜 License

[MIT](LICENSE)
