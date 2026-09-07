"""Real Gradio lifecycle and transactional editor validation, without loading models."""

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


def test_callback_exists_in_first_session_and_ui_restart_replaces_it(monkeypatch):
    gr = pytest.importorskip("gradio")
    from gradio.state_holder import SessionState

    package = ModuleType("native_editor_test")
    package.__path__ = [str(Path(__file__).parents[1] / "arcenciel_link")]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    for name in ["client", "device_tools", "recipe", "resources", "downloader", "version"]:
        module = ModuleType(f"{package.__name__}.{name}")
        monkeypatch.setitem(sys.modules, module.__name__, module)
    sys.modules["native_editor_test.downloader"].RUNNING = Mock()
    sys.modules["native_editor_test.version"].VERSION = "test"
    callbacks = {}
    callback_module = SimpleNamespace(
        on_before_ui=lambda fn: callbacks.update(reset=fn),
        on_after_component=lambda fn: callbacks.update(component=fn),
        on_app_started=lambda fn: callbacks.update(started=fn),
    )
    opts = SimpleNamespace(data={"beta_dist_alpha": 0.6, "beta_dist_beta": 0.6})
    opts.set = lambda key, value: opts.data.update({key: value})
    shared = SimpleNamespace(opts=opts, state=SimpleNamespace(job_count=0), settings_components={})
    modules = ModuleType("modules")
    import threading

    modules.call_queue = SimpleNamespace(queue_lock=threading.Lock())
    monkeypatch.setitem(sys.modules, "modules.call_queue", modules.call_queue)
    modules.script_callbacks = callback_module
    modules.shared = shared
    modules.infotext_utils = SimpleNamespace(paste_fields={})
    monkeypatch.setitem(sys.modules, "modules", modules)
    monkeypatch.setitem(sys.modules, "modules.infotext_utils", modules.infotext_utils)
    native = importlib.import_module("native_editor_test.native_tools")
    fields = importlib.import_module("native_editor_test.native_fields")
    native.register()

    with_models = False

    def build():
        callbacks["reset"]()
        with gr.Blocks() as txt2img:
            prompt = gr.Textbox(value="keep my work", elem_id="txt2img_prompt")
            steps = gr.Slider(value=20, minimum=1, maximum=150, elem_id="txt2img_steps")
            sampler = gr.Dropdown(["Euler", "DPM++"], value="Euler", elem_id="txt2img_sampling")
            for component in (prompt, steps, sampler):
                callbacks["component"](component)
            if with_models:
                callbacks["component"](gr.Dropdown(["A", "B"], value="A", elem_id="setting_sd_model_checkpoint"))
                callbacks["component"](
                    gr.Dropdown(["vae-A", "vae-B"], value=["vae-A"], multiselect=True, elem_id="setting_sd_modules")
                )
            fields.bridge.update(incoming=gr.Textbox(), receipt=gr.Textbox(), button=gr.Button())
        with gr.Blocks() as demo:
            txt2img.render()
            callbacks["component"](gr.HTML(elem_id="footer"))
        return demo

    demo = build()
    callback = next(fn for fn in demo.fns.values() if fn.fn and fn.fn.__name__ == "import_values")
    session = SessionState(demo)
    assert callback._id in session.blocks_config.fns
    assert any(d["js"] and "AECLinkNative.take" in d["js"] for d in demo.config["dependencies"])
    assert fields.bridge["configured"]
    first_id = fields.ui_id
    assert list(fields.components) == ["prompt", "steps", "sampler"]

    def call(action, values=None, **extra):
        response = callback.fn(
            json.dumps({"uiId": first_id, "nonce": "correlation", "action": action, "fields": values, **extra}),
            "keep my work",
            20,
            "Euler",
        )
        return response, json.loads(response[-1])

    _, result = call("read")
    assert result["values"] == {"prompt": "keep my work", "steps": 20, "sampler": "Euler"}
    before = result["values"]
    updates, result = call("apply", {"prompt": "new draft", "steps": 24}, expected=before)
    assert result["ok"] and updates[0]["value"] == "new draft" and updates[1]["value"] == 24
    _, result = call("apply", {"steps": 151})
    assert result == {
        "nonce": "correlation",
        "ok": False,
        "unchanged": True,
        "code": "NATIVE_VALIDATION_FAILED",
        "field": "steps",
    }
    _, result = call("apply", {"prompt": "new", "sampler": "not installed"})
    assert result["unchanged"] and result["field"] == "sampler"
    _, result = call("apply", {"prompt": "new"}, expected={})
    assert result["code"] == "EDITOR_CHANGED"
    shared.state.job_count = 1
    _, result = call("apply", {"prompt": "new"})
    assert result["code"] == "GENERATOR_BUSY"
    _, result = call("read")
    assert result["ok"]  # Connection checks do not interfere with generation.
    _, result = call("apply", {"prompt": "new"}, uiId="stale")
    assert result["code"] == "EDITOR_STALE"
    next_demo = build()
    assert fields.ui_id != first_id
    assert len([fn for fn in next_demo.fns.values() if fn.fn and fn.fn.__name__ == "import_values"]) == 1
    assert fields.components["prompt"] is not demo.blocks[callback.inputs[1]._id]

    # The native import must update the loader, not only the visible selectors.
    with_models = True
    catalog = {
        name: SimpleNamespace(filename=name + ".safetensors", title=name + " [1234567890]", name=name, short_title=name)
        for name in ["A", "B"]
    }
    aliases = {**catalog, **{info.title: info for info in catalog.values()}}
    opts.sd_model_checkpoint = "A"
    opts.forge_additional_modules = ["vae-A"]
    opts.set = lambda key, value: (opts.data.update({key: value}), setattr(opts, key, value))
    opts.data.update(sd_model_checkpoint="A", forge_additional_modules=["vae-A"])
    data = SimpleNamespace(forge_loading_parameters={"checkpoint_info": catalog["A"], "additional_modules": ["vae-A"]})
    sd_models = SimpleNamespace(model_data=data, get_closet_checkpoint_match=aliases.get, checkpoints_list=catalog)
    modules.sd_models = sd_models
    modules.processing = SimpleNamespace(need_global_unload=False)
    monkeypatch.setitem(sys.modules, "modules.sd_models", sd_models)
    dynamic = SimpleNamespace(online_lora=False)
    backend = ModuleType("backend")
    backend.args = SimpleNamespace(dynamic_args=dynamic)
    monkeypatch.setitem(sys.modules, "backend", backend)
    monkeypatch.setitem(sys.modules, "backend.args", backend.args)

    def refresh():
        data.forge_loading_parameters = {
            "checkpoint_info": aliases[opts.sd_model_checkpoint],
            "additional_modules": list(opts.forge_additional_modules),
        }
        modules.processing.need_global_unload = True

    main = SimpleNamespace(
        module_list={"vae-A": "vae-A", "vae-B": "vae-B"},
        checkpoint_change=lambda value, *args, **kwargs: opts.set("sd_model_checkpoint", value),
        modules_change=lambda value, *args, **kwargs: opts.set("forge_additional_modules", value),
        refresh_model_loading_parameters=Mock(side_effect=refresh),
    )
    forge = ModuleType("modules_forge")
    forge.main_entry = main
    monkeypatch.setitem(sys.modules, "modules_forge", forge)
    sys.modules["native_editor_test.resources"].native_catalog = lambda refresh: (
        [("checkpoint", key, Path(info.filename)) for key, info in catalog.items()],
        [],
    )
    model_demo = build()
    callback = next(fn for fn in model_demo.fns.values() if fn.fn and fn.fn.__name__ == "import_values")
    shared.state.job_count = 0

    def model_call(values):
        return json.loads(
            callback.fn(
                json.dumps({"uiId": fields.ui_id, "nonce": "models", "action": "apply", "fields": values}),
                "keep my work",
                20,
                "Euler",
                "A",
                ["vae-A"],
            )[-1]
        )

    assert model_call({"checkpoint": "B", "modules": '["vae-B"]'})["ok"]
    assert data.forge_loading_parameters == {"checkpoint_info": catalog["B"], "additional_modules": ["vae-B"]}
    assert main.refresh_model_loading_parameters.call_count == 1
    # Repair an already changed option with a stale loading plan as left by 2.5.2.
    data.forge_loading_parameters["checkpoint_info"] = catalog["A"]
    assert model_call({"checkpoint": "B"})["ok"]
    assert data.forge_loading_parameters["checkpoint_info"] == catalog["B"]
    # Undo follows the same loading-plan path.
    assert model_call({"checkpoint": "A", "modules": '["vae-A"]'})["ok"]
    assert data.forge_loading_parameters["checkpoint_info"] == catalog["A"]
    assert model_call({"checkpoint": "A [1234567890]"})["ok"]
    assert data.forge_loading_parameters["checkpoint_info"] == catalog["A"]
    assert model_call({"checkpoint": "invented [1234567890]"})["unchanged"]
    assert model_call({"checkpoint": "A"})["ok"]
    # An initially blank quicksetting must back up Forge's selected startup model.
    opts.sd_model_checkpoint = ""
    read = json.loads(
        callback.fn(
            json.dumps({"uiId": fields.ui_id, "nonce": "startup", "action": "read"}),
            "keep my work",
            20,
            "Euler",
            "",
            ["vae-A"],
        )[-1]
    )
    assert read["values"]["checkpoint"] == "A"
    opts.sd_model_checkpoint = "A"
    # A competing generation owns this same native lock.
    modules.call_queue.queue_lock.acquire()
    try:
        assert model_call({"checkpoint": "B"})["code"] == "GENERATOR_BUSY"
    finally:
        modules.call_queue.queue_lock.release()
    # Reject a failed native refresh and restore the previous plan.
    main.refresh_model_loading_parameters.side_effect = RuntimeError("native failure")
    assert model_call({"checkpoint": "B"})["unchanged"]
    assert opts.data["sd_model_checkpoint"] == "A"
    assert data.forge_loading_parameters["checkpoint_info"] == catalog["A"]
