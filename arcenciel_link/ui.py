import gradio as gr, requests, os
from pathlib import Path
from .config import load, save
from .client import headers, cancel_job
from ._compat import blocks_with_assets, register_load_event, IS_GR4

_cfg       = load()
_THIS_DIR  = Path(__file__).parent
_JS_FILE   = _THIS_DIR / "script.js"
_CSS_FILE  = _THIS_DIR / "style.css"

def _refresh_jobs():
    if not _cfg["api_key"]:
        return gr.update(value=[["–","–","–","–","–","No API key set"]])
    try:
        r = requests.get(f"{_cfg['base_url']}/history?limit=50", headers=headers())
        r.raise_for_status()
        jobs = r.json()
        return [[j[k] for k in ("id","versionId","state","progress","targetPath","message")] for j in jobs]
    except Exception as e:
        return gr.update(value=[["–","–","–","–","–", str(e)]])


def _build_settings_body():
    with gr.Box(visible=False, elem_id="aec-auth-dialog") as auth_box:
        gr.Markdown("#### Arc en Ciel Link – Settings")
        with gr.Accordion("Advanced (self-host)", open=False):
            base_in = gr.Textbox(_cfg["base_url"], label="Backend URL")
        key_in = gr.Textbox(_cfg["api_key"],  type="password", label="API Key")
        test_out = gr.Markdown()

        with gr.Row():
            btn_save  = gr.Button("Save")
            btn_test  = gr.Button("Test")
            btn_close = gr.Button("Close")

    gr.Markdown("### Arc en Ciel Link - Download Queue")
    queue_tbl = gr.Dataframe(
        headers = ["id", "versionId", "state", "progress", "targetPath", "message"],
        datatype = ["number", "number", "str", "number", "str", "str"],
        height = 450,
        interactive=True,
        value=_refresh_jobs(),
    )
    sel_state  = gr.State([])

    if IS_GR4:
        def _toggle(evt: gr.SelectData, cur):
            if evt.value is None:
                return cur or []
            rid  = int(evt.value[0])
            cur  = (cur or []).copy()
            cur.remove(rid) if rid in cur else cur.append(rid)
            return cur
        queue_tbl.select(_toggle, [sel_state], sel_state)

    with gr.Row():
        btn_refresh = gr.Button("Refresh")
        btn_cancel = gr.Button("🗑 Cancel selected")

    status_out = gr.Markdown(visible=False)

    btn_refresh.click(lambda: (_refresh_jobs(), []), None, [queue_tbl, sel_state])

    def _cancel(sel):
        ids = [int(i) for i in (sel or [])]
        ok = 0
        for jid in ids:
            try:
                cancel_job(jid)
                ok += 1
            except Exception as e:
                print("cancel error:", e)
        txt = f"🗑 {ok} job{'s' if ok!=1 else ''} cancelled"
        return _refresh_jobs(), [], gr.update(value=txt, visible=True)
    btn_cancel.click(_cancel, sel_state,
                     [queue_tbl, sel_state, status_out])

    register_load_event(queue_tbl, _refresh_jobs, queue_tbl, every=5)

    def _save(base_url, api_key):
        _cfg.update(base_url=base_url.rstrip("/"), api_key=api_key.strip())
        save(_cfg)
        import arcenciel_link.client as client
        client.BASE_URL = _cfg["base_url"].rstrip("/")
        client.API_KEY = _cfg["api_key"]

        return gr.update(visible=False)

    def _test(base_url, api_key):
        try:
            r  = requests.get(
                    f"{base_url.rstrip('/')}/health",
                    timeout=4,
                    headers={"x-api-key": api_key})
            return "✅ OK" if r.status_code in (200,204) else \
                   f"❌ {r.status_code}: {r.text}"
        except Exception as e:
            return f"❌ {e}"

    btn_save .click(_save,  [base_in, key_in], auth_box)
    btn_test .click(_test,  [base_in, key_in], test_out)
    btn_close.click(lambda: gr.update(visible=False), None, auth_box)

def settings_panel():
    with blocks_with_assets(_JS_FILE, _CSS_FILE,
                            analytics_enabled=False) as outer:
        
        with gr.Accordion("Arc en Ciel Link", open=False):
            _build_settings_body()

    return outer