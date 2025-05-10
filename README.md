# Arc en Ciel Link — AUTOMATIC1111 Extension

> Bring your **Arc en Ciel** models straight into Stable-Diffusion WebUI with one click – now with model-aware routing, live queue, inventory sync **and a shiny built-in progress UI**.

---

## ✨ Features

One-click **➕ Download** on every Arc en Ciel model card – no manual copy-paste.

**Model-aware routing** → checkpoints, LoRAs, VAEs, embeddings land in the correct sub-folder automatically.

Background worker with **retry back-off**, **disk-space guard** and **SHA-256 verification**.

**Live queue tab** inside WebUI: ▸ coloured progress bars  ▸ status-icon (🔴 not linked / 🟢 OK / 🔵 actively downloading).

Hourly **inventory sync** – server skips anything you already have.

**Cover image & arcenciel.info** side-car: preview + JSON metadata + HTML quick-view saved next to each file.

---

## 🛠 Installation

### Fast way (GUI)

1. Open **Stable-Diffusion WebUI**  
2. `Extensions → Install from URL`  
3. Paste the repo URL

   ```bash
   https://github.com/FallenIncursio/arcenciel-link-webui.git
   ```

4. **Install** → restart WebUI  
5. You’ll see a new tab **“ArcEnCiel Link”** and a small chain-icon next to the settings cog.

### Manual / dev install

```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/FallenIncursio/arcenciel-link-webui.git
pip install -r arcenciel-link-webui/requirements.txt
# restart webui
```

---

## 🔑 First-time setup

1. On [Arc en Ciel](https://arcenciel.io) → **Settings → API Keys → Generate**  
2. In WebUI click the **chain-icon** (red = not linked) and enter your freshly generated api key.
3. **Save → Test**.  **✅ Success**?  You’re done!

---

## 🚀 How to use

* Hit **➕** on a model → it pops up in the *ArcEnCiel Link* queue.  
* Progress is shown as a green bar; the chain-icon turns **🔵 blue** while something is downloading.  
* Finished items flip to **DONE**; icon returns to **🟢 green**.  
* LoRAs → `models/Lora`   ·   Checkpoints → `models/Stable-diffusion`   ·   VAEs → `models/VAE`   ·   Embeddings → `embeddings/`  
* Worker retries 5 × (`2^n` back-off) and aborts gracefully if < 2 GB free.

### Optional cover / metadata

If the server provides them the extension also saves:

```js
model.safetensors
model.preview.png
model.arcenciel.info   # compact JSON
model.html             # pretty quick-view
```

> *You can open the `.html` file right inside WebUI’s file browser.*

---

## 🆘 Troubleshooting

| Symptom | Fix |
|---------|-----|
| **🔴 red icon** | API key missing/invalid → open the chain-icon and re-enter. |
| Job sticks in “DOWNLOADING 0 %” | Check free disk space & write permissions. |
| “SHA256 mismatch” error | Download corrupted; worker will retry – if it keeps failing, report the version ID to Arc en Ciel support. |
| Covers/metadata not saved | Ensure you pulled the latest backend (needs `*.preview.png` / `*.arcenciel.info` in the job payload). |

---

## 🤝 Contributing

PRs & issue reports welcome – for bigger features open a discussion first.

---

## 📜 License

[MIT](LICENSE)
