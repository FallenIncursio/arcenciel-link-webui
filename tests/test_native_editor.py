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
    modules.script_callbacks = callback_module
    modules.shared = shared
    modules.infotext_utils = SimpleNamespace(paste_fields={})
    monkeypatch.setitem(sys.modules, "modules", modules)
    monkeypatch.setitem(sys.modules, "modules.infotext_utils", modules.infotext_utils)
    native = importlib.import_module("native_editor_test.native_tools")
    fields = importlib.import_module("native_editor_test.native_fields")
    native.register()

    def build():
        callbacks["reset"]()
        with gr.Blocks() as txt2img:
            prompt = gr.Textbox(value="keep my work", elem_id="txt2img_prompt")
            steps = gr.Slider(value=20, minimum=1, maximum=150, elem_id="txt2img_steps")
            sampler = gr.Dropdown(["Euler", "DPM++"], value="Euler", elem_id="txt2img_sampling")
            for component in (prompt, steps, sampler):
                callbacks["component"](component)
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
