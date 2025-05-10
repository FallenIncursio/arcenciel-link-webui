import gradio as gr
from modules import script_callbacks
from arcenciel_link.config import load, save
from arcenciel_link.ui import _JS_FILE, _CSS_FILE

_cfg = load()

def _save_cfg(base_url: str, api_key: str):
    _cfg.update(base_url=base_url.rstrip("/"), api_key=api_key.strip())
    save(_cfg)
    return gr.update(value="✅ saved", visible=True)

def _test_cfg(base_url: str, api_key: str):
    import requests
    try:
        r = requests.get(f"{base_url.rstrip('/')}/health",
                         headers={"x-api-key": api_key}, timeout=4)
        return f"✅ {r.status_code}" if r.ok else f"❌ {r.status_code}: {r.text}"
    except Exception as e:
        return f"❌ {e}"

def on_ui_settings():
    with gr.Blocks(js=str(_JS_FILE), css=str(_CSS_FILE),
                   analytics_enabled=False) as blk:
        gr.Markdown("### Arc en Ciel Link – Connection")

        base_in = gr.Textbox(value=_cfg["base_url"], label="Backend URL")
        key_in  = gr.Textbox(value=_cfg["api_key"], type="password",
                             label="API Key")

        with gr.Row():
            btn_save = gr.Button("💾 Save")
            btn_test = gr.Button("🔍 Test")

        status = gr.Markdown(visible=False)

        btn_save.click(_save_cfg,  [base_in, key_in], status)
        btn_test.click(_test_cfg,  [base_in, key_in], status)

    return blk

script_callbacks.on_ui_settings(on_ui_settings)
