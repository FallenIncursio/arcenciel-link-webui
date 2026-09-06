"""Small native status panel. Device actions remain authenticated in the Link Hub."""

from . import client, device_tools, recipe, resources
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

    def configure_editor(demo):
        import json
        import math

        from modules import shared

        from . import native_fields

        if not native_fields.bridge:
            return []
        try:
            from modules import infotext_utils as paste
        except ImportError:
            from modules import generation_parameters_copypaste as paste
        registered = {
            getattr(field[0], "elem_id", None): field[0]
            for field in paste.paste_fields.get("txt2img", {}).get("fields", [])
        }
        registered.update(native_fields.registered)
        for component in getattr(shared, "settings_components", {}).values():
            registered[getattr(component, "elem_id", None)] = component
        try:
            from modules_forge import main_entry

            for name in ("ui_checkpoint", "ui_vae"):
                component = getattr(main_entry, name, None)
                if component is not None:
                    registered[component.elem_id] = component
        except ImportError:
            pass
        components = {key: registered[value] for key, value in native_fields.IDS.items() if value in registered}
        if "modules" in components:
            # Forge Neo uses the VAE/text encoder selector; the legacy sd_vae option is inert.
            components.pop("vae", None)
        native_fields.components = components
        settings = {
            "betaAlpha": "beta_dist_alpha",
            "betaBeta": "beta_dist_beta",
            "clipSkip": "CLIP_stop_at_last_layers",
            "vae": "sd_vae",
        }

        def values(raw):
            result = dict(zip(components, raw))
            for key in result:
                if key in ("betaAlpha", "betaBeta"):
                    result[key] = getattr(shared.opts, settings[key])
                elif key == "modules":
                    result[key] = json.dumps(result[key] or [], separators=(",", ":"))
                elif key == "seed":
                    result[key] = str(int(result[key]))
                elif key == "checkpoint":
                    result[key] = result[key] or ""
            return result

        def import_values(raw, *current):
            unchanged = [gr.skip() for _ in components]
            nonce = None
            try:
                payload = json.loads(raw)
                nonce = payload.get("nonce")
                before = values(current)
                if payload.get("action") == "read":
                    return [*unchanged, json.dumps({"nonce": nonce, "ok": True, "values": before})]
                if getattr(shared.state, "job_count", 0) > 0:
                    raise ValueError("Wait for the current generation")
                if payload.get("expected") is not None and payload["expected"] != before:
                    raise ValueError("The editor changed before import")
                fields = payload["fields"]
                if not isinstance(fields, dict) or not fields or set(fields) - components.keys():
                    raise ValueError("Unsupported native field")
                updates = {}
                for name, value in fields.items():
                    component = components[name]
                    if name == "modules":
                        value = json.loads(value)
                        from modules_forge import main_entry

                        if not isinstance(value, list) or any(
                            not isinstance(v, str) or v not in main_entry.module_list for v in value
                        ):
                            raise ValueError("Native module unavailable")
                    elif name in ("prompt", "negativePrompt", "sampler", "scheduler", "checkpoint", "vae"):
                        if not isinstance(value, str):
                            raise ValueError("Expected text")
                        choices = getattr(component, "choices", None)
                        if name == "checkpoint":
                            catalog, _ = resources.native_catalog(False)
                            choices = [n for kind, n, _ in catalog if kind == "checkpoint"]
                            # A saved current selection may use another native display alias.
                            choices += [getattr(shared.opts, "sd_model_checkpoint", ""), ""]
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
                    updates[name] = value
                # Validate all values before changing either Gradio state or host options.
                previous_options = {
                    key: getattr(shared.opts, key, None)
                    for key in [*settings.values(), "sd_model_checkpoint", "forge_additional_modules"]
                }
                try:
                    if "checkpoint" in updates or "modules" in updates:
                        try:
                            from modules_forge import main_entry
                        except ImportError:
                            main_entry = None
                        if "checkpoint" in updates:
                            if updates["checkpoint"] == "":
                                shared.opts.data["sd_model_checkpoint"] = ""
                            elif main_entry:
                                main_entry.checkpoint_change(updates["checkpoint"], None, save=False, refresh=False)
                            else:
                                shared.opts.set("sd_model_checkpoint", updates["checkpoint"])
                        if "modules" in updates:
                            main_entry.modules_change(updates["modules"], None, save=False, refresh=False)
                    for key, setting in settings.items():
                        if key in updates:
                            shared.opts.set(setting, updates[key])
                except Exception:
                    for key, value in previous_options.items():
                        shared.opts.data[key] = value
                    raise
                return [
                    *[gr.update(value=updates[key]) if key in updates else gr.skip() for key in components],
                    json.dumps({"nonce": nonce, "ok": True}),
                ]
            except Exception:
                return [*unchanged, json.dumps({"nonce": nonce, "ok": False, "unchanged": True})]

        with demo:
            native_fields.bridge["button"].click(
                fn=import_values,
                inputs=[native_fields.bridge["incoming"], *components.values()],
                outputs=[*components.values(), native_fields.bridge["receipt"]],
                queue=False,
            )
        demo.config = demo.get_config_file()

    def native_routes(_demo, app):
        if _demo is not None:
            configure_editor(_demo)
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

    from . import native_fields

    script_callbacks.on_after_component(native_fields.record)
    script_callbacks.on_app_started(native_routes)
