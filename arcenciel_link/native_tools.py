"""Small native status panel. Device actions remain authenticated in the Link Hub."""

from . import client, device_tools, recipe
from .downloader import RUNNING
from .version import VERSION


def summary():
    tool = device_tools.status()
    state = "Connected" if client._open_evt.is_set() else "Disconnected"
    text = f"Link {VERSION} · {state} · Downloads {'enabled' if RUNNING.is_set() else 'paused'}"
    text += f"\n{recipe.REPORT_STATE}"
    if tool:
        text += (
            f"\n{tool['action']}: {tool['state']} · {tool['processed']}/{tool['total']} · {tool['warnings']} warnings"
        )
    return text


def register():
    import gradio as gr
    from modules import script_callbacks

    def ui_tabs():
        import json
        import math

        try:
            from modules import infotext_utils as paste
        except ImportError:
            from modules import generation_parameters_copypaste as paste
        ids = {
            "prompt": "txt2img_prompt",
            "negativePrompt": "txt2img_neg_prompt",
            "seed": "txt2img_seed",
            "steps": "txt2img_steps",
            "cfg": "txt2img_cfg_scale",
            "width": "txt2img_width",
            "height": "txt2img_height",
            "sampler": "txt2img_sampling",
            "scheduler": "txt2img_scheduler",
        }
        registered = {
            getattr(field[0], "elem_id", None): field[0]
            for field in paste.paste_fields.get("txt2img", {}).get("fields", [])
        }
        components = {name: registered[elem_id] for name, elem_id in ids.items() if elem_id in registered}

        def import_values(raw):
            unchanged = [gr.skip() for _ in components]
            nonce = None
            try:
                payload = json.loads(raw)
                nonce = payload.get("nonce")
                fields = payload["fields"]
                if not isinstance(fields, dict) or not fields or set(fields) - components.keys():
                    raise ValueError("Unsupported native field")
                values = {}
                for name, value in fields.items():
                    component = components[name]
                    if name in ("prompt", "negativePrompt", "sampler", "scheduler"):
                        if not isinstance(value, str):
                            raise ValueError("Expected text")
                        choices = getattr(component, "choices", None)
                        if choices and value not in [c[1] if isinstance(c, (list, tuple)) else c for c in choices]:
                            raise ValueError("Native option unavailable")
                    else:
                        value = int(value) if name == "seed" else float(value)
                        if not math.isfinite(value) or (name == "seed" and not -1 <= value <= 9007199254740991):
                            raise ValueError("Invalid numeric value")
                        if getattr(component, "minimum", None) is not None and value < component.minimum:
                            raise ValueError("Value below native minimum")
                        if getattr(component, "maximum", None) is not None and value > component.maximum:
                            raise ValueError("Value above native maximum")
                    values[name] = value
                updates = [gr.update(value=values[name]) if name in values else gr.skip() for name in components]
                return [*updates, json.dumps({"nonce": nonce, "ok": True})]
            except Exception:
                return [*unchanged, json.dumps({"nonce": nonce, "ok": False})]

        with gr.Blocks() as panel:
            gr.Markdown("## Arc en Ciel Link\n[Open device tools and your library](https://arcenciel.io/link)")
            status = gr.Textbox(value=summary(), label="This host", interactive=False)
            refresh = gr.Button("Refresh Link status")
            refresh.click(fn=summary, inputs=[], outputs=[status])
            gr.HTML('<div id="aec-link-draft-inbox"></div>')
            incoming = gr.Textbox(
                label="Link internal draft input", elem_id="aec-link-native-input", elem_classes=["aec-link-internal"]
            )
            import_button = gr.Button(
                "Apply Link native fields", elem_id="aec-link-native-apply", elem_classes=["aec-link-internal"]
            )
            acknowledgement = gr.Textbox(
                label="Link internal draft receipt",
                elem_id="aec-link-native-receipt",
                elem_classes=["aec-link-internal"],
            )
            import_button.click(
                fn=import_values, inputs=[incoming], outputs=[*components.values(), acknowledgement], queue=False
            )
            gr.HTML("<style>.aec-link-internal { display: none !important; }</style>")
        return [(panel, "Arc en Ciel Link", "arcenciel_link_tools")]

    def native_routes(_demo, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        from . import drafts, job_attempt

        login_check = next((route.endpoint for route in app.routes if route.path == "/login_check"), None)
        if login_check is None:
            # Unsupported host authentication integration: keep the inbox closed.
            return

        @app.post("/arcenciel-link/editor/{action}", dependencies=[Depends(login_check)])
        async def inbox(action: str, request: Request):
            if (
                request.headers.get("x-aec-link-editor") != "1"
                or request.headers.get("sec-fetch-site") != "same-origin"
            ):
                raise HTTPException(status_code=403, detail="Native editor required")
            raw = await request.body()
            if len(raw) > 100_000:
                raise HTTPException(status_code=413, detail="Draft event too large")
            import asyncio
            import json

            try:
                body = json.loads(raw)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid draft event") from None
            result, status_code = await asyncio.to_thread(drafts.post, client, job_attempt.RUNTIME_ID, action, body)
            return JSONResponse(result, status_code=status_code, headers={"Cache-Control": "no-store"})

    script_callbacks.on_app_started(native_routes)
    script_callbacks.on_ui_tabs(ui_tabs)
