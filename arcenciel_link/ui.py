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


def on_ui_tabs():
    with blocks_with_assets(_JS_FILE, _CSS_FILE) as root:

        with gr.Box(visible=False, elem_id="aec-auth-dialog") as auth_box:
            gr.Markdown("#### Arc en Ciel Link – Settings")
            with gr.Accordion("Advanced (self-host)", open=False):
                base_in = gr.Textbox(value=_cfg["base_url"], label="Backend URL")
            key_in = gr.Textbox(value=_cfg["api_key"],  type="password", label="API Key")
            test_out = gr.Markdown()

            with gr.Row():
                btn_save  = gr.Button("Save")
                btn_test  = gr.Button("Test")
                btn_close = gr.Button("Close")

        gr.Markdown("### Arc en Ciel Link – Download Queue")

        queue_tbl = gr.Dataframe(
            headers = ["id", "versionId", "state", "progress", "targetPath", "message"],
            datatype = ["number", "number", "str", "number", "str", "str"],
            height = 450,
            interactive=True,
            value=_refresh_jobs(),
        )

        sel_state  = gr.State([])

        def _toggle_selection(evt: gr.SelectData, current: list[int]|None):
            if evt is None or evt.value is None:
                return current or []
            row_id = int(evt.value[0])
            current = (current or []).copy()
            if row_id in current:
                current.remove(row_id)
            else:
                current.append(row_id)
            return current

        if IS_GR4:
            queue_tbl.select(fn=_toggle_selection, inputs=[sel_state], outputs=sel_state)

        with gr.Row():
            btn_refresh = gr.Button("Refresh")
            btn_cancel = gr.Button("🗑 Cancel selected")

        status_out = gr.Markdown(visible=False)

        btn_refresh.click(lambda: (_refresh_jobs(), []), inputs=None, outputs=[queue_tbl, sel_state])

        def _cancel(sel):
            ids = []
            if sel:
                if isinstance(sel, list) and isinstance(sel[0], int):
                    ids = sel
                elif isinstance(sel, list) and isinstance(sel[0], list):
                    ids = [int(r[0]) for r in sel]
                elif isinstance(sel, str):
                    ids = [int(sel)]
            ok = 0
            for jid in ids:
                try:
                    cancel_job(jid)
                    ok += 1
                except Exception as e:
                    print("cancel error:", e)
            txt = f"🗑 {ok} job{'s' if ok!=1 else ''} cancelled"
            return _refresh_jobs(), [], gr.update(value=txt, visible=True)
        
        btn_cancel.click(
            _cancel,
            inputs = sel_state,
            outputs=[queue_tbl, sel_state, status_out]
        )

        if not IS_GR4:
            id_box = gr.Textbox(label="Job-ID")
            btn_cancel.click(
                lambda jid: _cancel([int(jid.strip())]) if jid and jid.strip()
                        else (_refresh_jobs(), [], gr.update(value="❌ no id",visible=True)),
                inputs=id_box,
                outputs=[queue_tbl, sel_state, status_out]
            )

        register_load_event(root, _refresh_jobs, queue_tbl, every=5)

        def _save(base_url: str, api_key: str):
            _cfg.update(base_url=base_url.rstrip("/"), api_key=api_key.strip())
            save(_cfg)

            import arcenciel_link.client as client
            client.BASE_URL = _cfg["base_url"].rstrip("/")
            client.API_KEY = _cfg["api_key"]

            return gr.update(visible=False)

        def _test(base_url: str, api_key: str):
            try:
                r  = requests.get(
                        f"{base_url.rstrip('/')}/health",
                        timeout=4,
                        headers={"x-api-key": api_key},
                    )
                ok = r.status_code in (200, 204)
                return f"✅ Success ({r.status_code})" if ok else f"❌ {r.status_code}: {r.text}"
            except Exception as e:
                return f"❌ {e}"

        btn_save.click(_save, [base_in, key_in], outputs=auth_box)
        btn_test.click(_test, [base_in, key_in], outputs=test_out)
        btn_close.click(lambda: gr.update(visible=False), None, auth_box)

    return root, "ArcEnCiel Link", "arcenciel_link_queue"


def add_navbar_icon(*_, **__):
    comp = _[0] if _ else None 
    if getattr(comp, "elem_id", "") == "settings": 
        with comp.parent:
            gr.HTML(
                """<span id='aec-link-icon' style='cursor:pointer'>
                       <svg width="24" height="24" viewBox="0 0 24 24">
                           <path fill="currentColor"
                                 d="M10.59 13.41a1.996 1.996 0 0 1 0-2.82l2.18-2.18a2 2 0 0 1 2.83 2.83l-1.06 1.06
                                    1.41 1.41 1.06-1.06a4 4 0 0 0-5.66-5.66l-2.18 2.18a4 4 0 0 0 0 5.66l1.06 1.06 1.41-1.41-1.05-1.06Zm2.82-2.82a2 2 0 0 1 0 2.83l-2.18 2.18a2 2 0 0 1-2.83-2.83l1.06-1.06-1.41-1.41-1.06 1.06a4 4 0 1 0 5.66 5.66l2.18-2.18a4 4 0 0 0 0-5.66l-1.06-1.06-1.41 1.41 1.05 1.06Z"/>
                       </svg>
                   </span>"""
            )
