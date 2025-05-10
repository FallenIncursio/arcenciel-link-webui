import gradio as gr, requests, os
from pathlib import Path
from .config import load
from .client import headers, cancel_job
from ._compat import blocks_with_assets, register_load_event, IS_GR4

_THIS_DIR  = Path(__file__).parent
_JS_FILE   = _THIS_DIR / "script.js"
_CSS_FILE  = _THIS_DIR / "style.css"

def _refresh_jobs():
    _cfg = load()
    if not _cfg["api_key"]:
        return gr.update(value=[["–","–","–","–","–","No API key set"]])
    try:
        r = requests.get(f"{_cfg['base_url']}/history?limit=50", headers=headers())
        r.raise_for_status()
        jobs = r.json()
        return [[j[k] for k in ("id","versionId","state","progress","targetPath","message")] for j in jobs]
    except Exception as e:
        return gr.update(value=[["–","–","–","–","–", str(e)]])


def build_tab():
    with blocks_with_assets(_JS_FILE, _CSS_FILE) as root:
        gr.Markdown("### Arc en Ciel Link – Download Queue")

        queue_tbl = gr.Dataframe(
            headers = ["id", "versionId", "state", "progress", "targetPath", "message"],
            datatype = ["number", "number", "str", "number", "str", "str"],
            height = 450,
            interactive=True,
            value=_refresh_jobs(),
        )

        sel_state  = gr.State([])

        if IS_GR4:
            def _toggle(evt: gr.SelectData, cur: list[int]|None):
                if evt is None or evt.value is None:
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
            ids = [int(x) for x in (sel or [])]
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

        register_load_event(root, _refresh_jobs, queue_tbl, every=5)

    return root