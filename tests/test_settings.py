import importlib
import sys
from types import SimpleNamespace

import pytest

from arcenciel_link import client, config


@pytest.fixture
def settings(monkeypatch):
    for variable in ("ARCENCIEL_LINK_ENABLED", "ARCENCIEL_LINK_KEY", "ARCENCIEL_LINK_URL"):
        monkeypatch.delenv(variable, raising=False)
    options = {}
    data = {"arcenciel_link_enabled": False}
    shared = SimpleNamespace(
        opts=SimpleNamespace(data=data, add_option=lambda name, option: options.update({name: option})),
        OptionInfo=lambda default, _label, **kwargs: SimpleNamespace(default=default, **kwargs),
    )
    monkeypatch.setitem(
        sys.modules,
        "modules",
        SimpleNamespace(shared=shared, script_callbacks=SimpleNamespace(on_ui_settings=lambda _: None)),
    )
    monkeypatch.setattr(
        config,
        "load",
        lambda: {"enabled": True, "link_key": "lk_" + "a" * 32, "base_url": "https://link.arcenciel.io/api/link"},
    )
    monkeypatch.setattr(config, "save", lambda _: None)
    monkeypatch.setattr(config, "_detect_dev_mode", lambda: True)
    sys.modules.pop("arcenciel_link.settings", None)
    module = importlib.import_module("arcenciel_link.settings")
    calls = []
    monkeypatch.setattr(client, "apply_worker_state", lambda enable, **kwargs: calls.append(enable))
    monkeypatch.setattr(client, "_is_worker_running", lambda: True)
    yield module, shared, options, calls
    sys.modules.pop("arcenciel_link.settings", None)


def test_colab_startup_replaces_stale_disabled_ui_setting(settings, monkeypatch):
    module, shared, options, calls = settings
    monkeypatch.setenv("ARCENCIEL_LINK_ENABLED", "1")
    module.on_ui_settings()
    assert shared.opts.data["arcenciel_link_enabled"] is True
    options["arcenciel_link_access_key"].onchange()
    assert calls == [True]


def test_saving_connection_settings_preserves_running_worker(settings):
    module, shared, options, calls = settings
    module.on_ui_settings()
    assert shared.opts.data["arcenciel_link_enabled"] is False
    options["arcenciel_link_base_url"].onchange()
    options["arcenciel_link_access_key"].onchange()
    assert calls == [True, True]


def test_saving_settings_preserves_remote_pause_and_explicit_switch_resumes(settings, monkeypatch):
    module, shared, options, calls = settings
    monkeypatch.setenv("ARCENCIEL_LINK_ENABLED", "1")
    monkeypatch.setattr(client, "_is_worker_running", lambda: False)
    module.on_ui_settings()
    options["arcenciel_link_access_key"].onchange()
    assert calls == [False]
    shared.opts.data["arcenciel_link_enabled"] = True
    options["arcenciel_link_enabled"].onchange()
    shared.opts.data["arcenciel_link_enabled"] = False
    options["arcenciel_link_enabled"].onchange()
    assert calls == [False, True, False]


def test_environment_key_and_url_remain_managed(settings, monkeypatch):
    module, shared, _options, calls = settings
    monkeypatch.setenv("ARCENCIEL_LINK_KEY", "lk_" + "b" * 32)
    monkeypatch.setenv("ARCENCIEL_LINK_URL", "https://link.arcenciel.io/api/link/")
    shared.opts.data.update(
        arcenciel_link_access_key="lk_" + "c" * 32, arcenciel_link_base_url="https://wrong.example/api/link"
    )
    module._apply_opts()
    assert module._cfg["link_key"] == "lk_" + "b" * 32
    assert module._cfg["base_url"] == "https://link.arcenciel.io/api/link"
    assert calls == [True]
