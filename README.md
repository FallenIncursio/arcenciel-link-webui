# Arc en Ciel Link — AUTOMATIC1111 Extension

> Bring your Arc en Ciel models straight into Stable Diffusion WebUI with one click — now with secure link keys, remote worker controls, inventory sync, and a built-in progress UI.

---

## ✨ Features

- One-click **➕ Download** on every Arc en Ciel model card — no manual copy-paste.
- **Model-aware routing** → checkpoints, LoRAs, VAEs, and embeddings land in the correct folder automatically.
- Background worker with **retry back-off**, **disk-space guard**, **SHA-256 verification**, and a live console feed.
- Remote worker control keeps the queue synced and lets the dashboard push jobs, credentials, and folder picks.
- Secrets are stored in the OS keyring when available; config.json only keeps plain text if no keyring backend exists.
- Optional preview PNG, `.arcenciel.info` metadata, and HTML quick-view sidecars saved next to every model.
- Console status icons (🔴 not linked / 🔵 downloading / 🟢 done) for quick at-a-glance feedback.

---

## 🛠 Installation

### Fast way (GUI)

1. Open Stable Diffusion WebUI.
2. `Extensions → Install from URL`.
3. Paste the repo URL:

   ```bash
   https://github.com/FallenIncursio/arcenciel-link-webui.git
   ```

4. Click Install, then restart WebUI.
5. A new ArcEnCiel section appears under WebUI Settings.

### Manual / dev install

```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/FallenIncursio/arcenciel-link-webui.git
pip install -r arcenciel-link-webui/requirements.txt
# restart webui
```

---

## 🔑 First-time setup

1. On arcenciel.io open **Link Access** and create a Link Key (`lk_...`). API keys remain a legacy fallback.
2. In WebUI go to **Settings → ArcEnCiel**, paste the Link Key (or API key).
3. Click Save.

---

## 🛡️ Credentials and security

- Link Keys are the preferred credential. They can be rotated or revoked per worker from the Arc en Ciel dashboard.
- API keys still work, but only Link Keys unlock remote worker toggles and folder selection.
- At startup the extension migrates existing credentials into the OS keyring (`keyring` package). If no backend is available, the secrets remain in `arcenciel_link/config.json`.
- Environment variables override file and UI settings:
  - `ARCENCIEL_LINK_URL` — base API URL.
  - `ARCENCIEL_LINK_KEY` — Link Key (`lk_...`).
  - `ARCENCIEL_API_KEY` — legacy API key.
  - `ARCENCIEL_DEV` — allow HTTP endpoints and private origins for testing.
- Delete the keyring entry named `arcenciel-link` to revoke cached credentials on the machine.

---

## 🚀 How to use

- Press Download on any Arc en Ciel model card; the job appears in the ArcEnCiel Link queue in WebUI.
- The worker logs every step with colored progress messages and retries up to five times with exponential back-off. It pauses automatically if less than 2 GB free space remain.
- Inventory sync runs hourly and the dashboard skips anything you already have locally.
- When a Link Key is active, the dashboard can toggle the worker, inject new credentials, and pick destination folders via the private network-aware API.

### 🖼 Optional cover / metadata

If provided by the server the extension saves:

```text
model.safetensors
model.preview.png
model.arcenciel.info   # compact JSON
model.html             # WebUI-friendly quick view (disabled by default)
```

Enable HTML quick-views by setting `"save_html_preview": true` in `arcenciel_link/config.json` (or via the settings JSON after the first run).

---

## ⚙️ Advanced configuration

- `webui_root`, `min_free_mb`, `max_retries`, and `backoff_base` live in `arcenciel_link/config.json`.
- Passing `--dev` to WebUI or exporting `ARCENCIEL_DEV=1` allows HTTP endpoints (for example `http://localhost:3000/api/link`) and private network dashboards while testing.
- Additional folder overrides can be supplied through WebUI command-line arguments such as `--ckpt-dir` or `--lora-dir`; the worker honors them automatically.

---

## 📹 Video tutorial

https://github.com/user-attachments/assets/7c0557d6-6ec6-40d4-b186-cd1e51f61cae

---

## 🆘 Troubleshooting

| Symptom | Fix |
|---------|-----|
| Worker stays offline | Ensure the Link Key or API key is saved, then click Enable. Check the console for `[AEC-LINK] authentication failed` or scope warnings. |
| Browser reports private network blocked | Accept the Private Network Access prompt or add the origin (`https://arcenciel.io`) to your browser's allowed list. |
| Remote toggle does nothing | Verify the worker console shows `Access-Control-Allow-Private-Network: true`; re-save settings to refresh credentials. |
| Download stuck at 0% | Check free disk space and write permissions; the worker aborts below the configured `min_free_mb`. |
| Repeated `SHA256 mismatch` | Network issues or corrupted mirrors; the worker retries automatically. Contact Arc en Ciel with the model/version ID if it persists. |
| Need more diagnostics | Inspect `arcenciel_link/client-debug.log` for websocket events and control messages. |
| Sidecars missing | Ensure you are on the latest backend and that the model payload includes preview/meta data. |

---

## 🤝 Contributing

PRs and issue reports are welcome. Open a discussion before large feature work to avoid overlap.

---

## 📜 License

[MIT](LICENSE)
