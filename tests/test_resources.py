import importlib.util
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def resources(monkeypatch, tmp_path):
    root = Path(__file__).parents[1]
    source = root / "aec_link_resources.py"
    utils = ModuleType("resource_test_utils")
    utils._CACHE_LOCK = threading.Lock()
    utils._ensure_cache = Mock(return_value={})
    utils.MODEL_EXTS = {".safetensors", ".ckpt", ".pt"}
    tools = ModuleType("resource_test_tools")
    tools._hash_cache = {}
    if source.exists():
        name = "tested_resources"
        monkeypatch.setitem(sys.modules, "aec_link_utils", utils)
        monkeypatch.setitem(sys.modules, "aec_link_device_tools", tools)
    else:
        source = root / "arcenciel_link" / "resources.py"
        package = ModuleType("resource_test_package")
        package.__path__ = []
        monkeypatch.setitem(sys.modules, "resource_test_package", package)
        monkeypatch.setitem(sys.modules, "resource_test_package.utils", utils)
        monkeypatch.setitem(sys.modules, "resource_test_package.device_tools", tools)
        name = "resource_test_package.resources"
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.original_catalog = module.native_catalog
    module.native_catalog = Mock(return_value=([], [("lora", tmp_path)]))
    return module, utils, tools


def cached(path, digest="a" * 64):
    stat = path.stat()
    return {"hash": digest, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def test_recognizes_exact_native_selection_and_keeps_paths_private(resources, tmp_path):
    module, utils, _ = resources
    path = tmp_path / "renamed.safetensors"
    path.write_bytes(b"model fixture")
    utils._ensure_cache.return_value = {str(path): cached(path)}
    module.native_catalog.return_value = ([("lora", "renamed", path)], [("lora", tmp_path)])
    result = module.collect()
    assert result == {
        "schemaVersion": 1,
        "complete": True,
        "entries": [
            {"kind": "lora", "sha256": "a" * 64, "selectionName": "renamed", "sizeBytes": 13, "selectable": True}
        ],
    }
    assert str(tmp_path) not in str(result)
    module.native_catalog.assert_called_once_with(True)
    module.collect()
    module.native_catalog.assert_called_with(False)
    module.request_refresh()
    module.collect()
    module.native_catalog.assert_called_with(True)


def test_uncached_file_blocks_missing_claim_without_hashing_or_loading(resources, tmp_path):
    module, _, _ = resources
    (tmp_path / "new.safetensors").write_bytes(b"new")
    assert module.collect() == {"schemaVersion": 1, "complete": False, "entries": []}


def test_file_outside_native_catalog_is_found_but_not_selectable(resources, tmp_path):
    module, utils, _ = resources
    path = tmp_path / "manual.pt"
    path.write_bytes(b"manual")
    utils._ensure_cache.return_value = {str(path): cached(path)}
    result = module.collect()
    assert result["complete"] is True
    assert result["entries"][0]["selectable"] is False
    assert result["entries"][0]["selectionName"] == "manual.pt"


@pytest.mark.parametrize("change", [{"mtime_ns": 0}, {"size": 0}, {"hash": "short"}, {"hash": None}])
def test_stale_or_corrupt_hash_cache_never_proves_readiness(resources, tmp_path, change):
    module, utils, _ = resources
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"fixture")
    utils._ensure_cache.return_value = {str(path): {**cached(path), **change}}
    assert module.collect()["complete"] is False
    assert module.collect()["entries"] == []


def test_explicit_device_scan_refresh_supplies_verified_hashes(resources, tmp_path):
    module, _, tools = resources
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"fixture")
    stat = path.stat()
    tools._hash_cache[str(path)] = (stat.st_mtime_ns, stat.st_size, "b" * 64)
    module.native_catalog.return_value = ([("lora", "model", path)], [("lora", tmp_path)])
    assert module.collect()["entries"][0]["sha256"] == "b" * 64
    path.write_bytes(b"changed fixture")
    assert module.collect()["complete"] is False


def test_duplicate_selection_names_are_not_claimed_as_two_selectable_models(resources, tmp_path):
    module, utils, _ = resources
    first, second = tmp_path / "a.safetensors", tmp_path / "b.safetensors"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    utils._ensure_cache.return_value = {str(p): cached(p) for p in [first, second]}
    module.native_catalog.return_value = ([("lora", "same", first), ("lora", "same", second)], [("lora", tmp_path)])
    result = module.collect()
    assert len(result["entries"]) == 1
    assert result["complete"] is False


def test_report_uses_authenticated_runtime_and_refuses_redirects(resources):
    module, _, _ = resources
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    client = SimpleNamespace(
        SESSION=Mock(), BASE_URL="https://link.example/api/link", headers=lambda: {"x-link-key": "fixture"}
    )
    client.SESSION.post.return_value = response
    module.report(client, "runtime-current")
    args, kwargs = client.SESSION.post.call_args
    assert args == ("https://link.example/api/link/resources/inventory",)
    assert kwargs["json"]["runtimeId"] == "runtime-current"
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == 20
    response.raise_for_status.assert_called_once()


@pytest.mark.parametrize("legacy", [False, True])
def test_native_catalog_supports_forge_neo_and_legacy_webui_without_loading_embeddings(
    resources, tmp_path, monkeypatch, legacy
):
    module, utils, _ = resources
    model = tmp_path / "style.safetensors"
    model.write_bytes(b"fixture")
    embedding = tmp_path / "token.pt"
    embedding.write_bytes(b"fixture")
    native = ModuleType("modules")
    native.sd_models = SimpleNamespace(model_path=str(tmp_path), checkpoints_list={})
    native.sd_vae = SimpleNamespace(vae_dict={})
    native.shared = SimpleNamespace(
        cmd_opts=SimpleNamespace(ckpt_dirs=[], ckpt_dir=None),
        opts=SimpleNamespace(sd_checkpoint_dropdown_use_short=False),
    )
    monkeypatch.setitem(sys.modules, "modules", native)
    monkeypatch.setitem(
        sys.modules, "networks", SimpleNamespace(available_networks={"style": SimpleNamespace(filename=str(model))})
    )
    monkeypatch.delitem(sys.modules, "modules.sd_hijack", raising=False)
    monkeypatch.delitem(sys.modules, "modules.ui_extra_networks_textual_inversion", raising=False)
    registry = SimpleNamespace(word_embeddings={"token": SimpleNamespace(filename=str(embedding))})
    if legacy:
        monkeypatch.setitem(
            sys.modules, "modules.sd_hijack", SimpleNamespace(model_hijack=SimpleNamespace(embedding_db=registry))
        )
    else:
        monkeypatch.setitem(
            sys.modules, "modules.ui_extra_networks_textual_inversion", SimpleNamespace(embedding_db=registry)
        )
    utils.get_model_path = lambda _target: tmp_path
    catalog, _roots = module.original_catalog(False)
    assert ("lora", "style", model) in catalog
    assert ("embedding", "token", embedding) in catalog


def test_deleted_and_modified_files_do_not_short_circuit_downloads(resources, tmp_path):
    module, utils, tools = resources
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"fixture")
    cache = cached(path)
    utils._ensure_cache.return_value = {str(path): cache}
    assert module.has_verified_file("a" * 64) is True
    assert module.has_verified_file(None) is False
    assert module.has_verified_file("short") is False
    assert module.has_verified_file("b" * 64) is False
    path.unlink()
    assert module.has_verified_file("a" * 64) is False
    path.write_bytes(b"replacement")
    assert module.has_verified_file("a" * 64) is False
    stat = path.stat()
    tools._hash_cache[str(path)] = (stat.st_mtime_ns, stat.st_size, "b" * 64)
    assert module.has_verified_file("b" * 64) is True
    path.write_bytes(b"changed again")
    assert module.has_verified_file("b" * 64) is False
