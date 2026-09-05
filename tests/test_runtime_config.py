import json
import warnings
from pathlib import Path

import pytest

from arcenciel_link import config
from arcenciel_link.runtime_config import validate_worker_change

load = config.load
save = config.save
CASES = json.loads((Path(__file__).parent / "fixtures/runtime-config-v1.json").read_text())["cases"]


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    for name in [
        "ARCENCIEL_LINK_URL",
        "ARCENCIEL_LINK_KEY",
        "ARCENCIEL_LINK_ENABLED",
        "ARCENCIEL_DEV",
        "COMMANDLINE_ARGS",
    ]:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "_CFG", path)
    monkeypatch.setattr(config, "is_secure_storage_available", lambda: False)
    monkeypatch.setattr(config, "get_secret", lambda _key: None)
    monkeypatch.setattr(config, "set_secret", lambda *_args: None)
    monkeypatch.setattr(config, "migrate_legacy_secret", lambda *_args: None)

    return path


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_startup_contract(case, isolated_config, monkeypatch):
    if case["stored"] is not None:
        isolated_config.write_text(json.dumps(case["stored"]))
    for name, value in case["env"].items():
        monkeypatch.setenv(name, value)
    with warnings.catch_warnings(record=True):
        loaded = load()
    for field, expected in case["expected"].items():
        assert loaded[field] == expected


def test_pause_resume_does_not_persist_environment_secret(isolated_config, monkeypatch):
    desktop_key = "lk_" + "a" * 32
    hosted_key = "lk_" + "b" * 32
    isolated_config.write_text(json.dumps({"link_key": desktop_key, "enabled": False}))
    monkeypatch.setenv("ARCENCIEL_LINK_KEY", hosted_key)
    monkeypatch.setenv("ARCENCIEL_LINK_ENABLED", "1")
    cfg = load()
    validate_worker_change(cfg, False, None)
    cfg["enabled"] = False
    save(cfg)
    assert hosted_key not in isolated_config.read_text()
    assert json.loads(isolated_config.read_text())["link_key"] == desktop_key
    assert load()["enabled"] is True  # Restart restores the declared startup preference.
    monkeypatch.delenv("ARCENCIEL_LINK_KEY")
    monkeypatch.delenv("ARCENCIEL_LINK_ENABLED")
    assert load()["link_key"] == desktop_key
    assert load()["enabled"] is False


def test_environment_key_cannot_be_silently_replaced(monkeypatch):
    monkeypatch.setenv("ARCENCIEL_LINK_KEY", "lk_" + "b" * 32)
    cfg = load()
    with pytest.raises(ValueError, match="managed by the runtime environment"):
        validate_worker_change(cfg, True, "lk_" + "c" * 32)
    validate_worker_change(cfg, True, "lk_" + "b" * 32)


def test_missing_key_cannot_be_manually_started():
    with pytest.raises(ValueError, match="Link key is required"):
        validate_worker_change(load(), True, None)


def test_new_host_never_writes_environment_credentials(isolated_config, monkeypatch):
    monkeypatch.setenv("ARCENCIEL_LINK_KEY", "lk_" + "b" * 32)
    monkeypatch.setenv("ARCENCIEL_LINK_ENABLED", "1")
    save(load())
    payload = json.loads(isolated_config.read_text())
    assert not payload.get("link_key")
    assert all(not name.startswith("_") for name in payload)


def test_desktop_key_can_be_repaired_without_an_environment_override(isolated_config):
    isolated_config.write_text(json.dumps({"enabled": True, "link_key": ""}))
    with warnings.catch_warnings(record=True):
        cfg = load()
    validate_worker_change(cfg, True, "lk_" + "c" * 32)
