import importlib
import os
import shutil

import pytest

try:
    from arcenciel_link import hash_cache as cache
    from arcenciel_link import utils
except ImportError:
    import aec_link_hash_cache as cache
    import aec_link_utils as utils


@pytest.fixture
def model(tmp_path):
    p = tmp_path / "model.safetensors"
    p.write_bytes(b"fixture data" * 20000)
    return p


def test_reuses_unchanged_and_moved_local_file(model):
    entries = {}
    first, _, source = cache.resolve(model, entries)
    assert source == "hashed"
    assert cache.resolve(model, entries) == (first, False, "cached")
    identity = entries[str(model)]["identity"]
    destination = model.parent / "folder" / "renamed.safetensors"
    destination.parent.mkdir()
    model.rename(destination)
    digest, _, source = cache.resolve(destination, entries)
    assert digest == first
    assert source == ("moved" if identity else "hashed")
    assert cache.resolve(destination, entries, force=True)[2] == "hashed"


def test_copy_is_never_identified_by_sample_size_or_name(model):
    entries = {}
    first, _, _ = cache.resolve(model, entries)
    target = model.with_name("copy.safetensors")
    shutil.copy2(model, target)
    model.unlink()
    digest, _, source = cache.resolve(target, entries)
    assert digest == first and source == "hashed"


def test_network_or_unknown_identity_rehashes_moves(model, monkeypatch):
    monkeypatch.setattr(cache, "identity", lambda *args: None)
    entries = {}
    cache.resolve(model, entries)
    dest = model.with_name("moved.safetensors")
    model.rename(dest)
    assert cache.resolve(dest, entries)[2] == "hashed"


def test_changed_content_with_restored_mtime_is_invalidated(model):
    entries = {}
    first, _, _ = cache.resolve(model, entries)
    stat = model.stat()
    model.write_bytes(b"x" * stat.st_size)
    os.utime(model, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    digest, _, source = cache.resolve(model, entries)
    assert digest != first and source == "hashed"


def test_move_sample_rejects_changed_content_with_preserved_size_mtime(model):
    entries = {}
    first, _, _ = cache.resolve(model, entries)
    stat = model.stat()
    dest = model.with_name("moved.safetensors")
    model.rename(dest)
    dest.write_bytes(b"x" * stat.st_size)
    os.utime(dest, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert cache.resolve(dest, entries)[0] != first


def test_cancellation_keeps_completed_cache_and_never_records_partial(model):
    entries = {}
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls > 1:
            raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError):
        cache.resolve(model, entries, check)
    assert entries == {}


def test_inventory_and_maintenance_share_persistent_cache(model, monkeypatch):
    monkeypatch.setattr(utils, "CACHE_DIR", model.parent / "cache")
    monkeypatch.setattr(utils, "CACHE_FILE", model.parent / "cache/hashes.json")
    monkeypatch.setattr(utils, "_CACHE_DATA", None)
    monkeypatch.setattr(utils, "_CACHE_DIRTY", False)
    digest = utils.cached_model_hash(model)
    utils.flush_hash_cache()
    tools = importlib.import_module(
        "arcenciel_link.device_tools" if utils.__name__.startswith("arcenciel_link.") else "aec_link_device_tools"
    )
    seen = []
    original = cache.resolve

    def resolve(*args, **kwargs):
        result = original(*args, **kwargs)
        seen.append(result[2])
        return result

    monkeypatch.setattr(cache, "resolve", resolve)
    monkeypatch.setattr(utils, "_CACHE_DATA", None)
    assert tools.scan([model.parent], lambda: None, lambda *args: None) == [(digest, model)]
    assert seen == ["cached"]
    assert not list(utils.CACHE_DIR.glob(".hashes-*"))


@pytest.mark.parametrize("corrupt", ["[1,2]", "{broken", '{"bad":null}'])
def test_corrupt_cache_recovers_without_trusting_bad_entries(model, monkeypatch, corrupt):
    monkeypatch.setattr(utils, "CACHE_DIR", model.parent)
    monkeypatch.setattr(utils, "CACHE_FILE", model.parent / "hashes.json")
    monkeypatch.setattr(utils, "_CACHE_DATA", None)
    utils.CACHE_FILE.write_text(corrupt)
    assert len(utils.cached_model_hash(model)) == 64
    utils.flush_hash_cache()


def test_download_inventory_does_not_resurrect_deleted_cache_entries(model, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(utils, "CACHE_FILE", tmp_path / "cache/hashes.json")
    monkeypatch.setattr(utils, "_CACHE_DATA", None)
    digest = utils.cached_model_hash(model)
    model.unlink()
    new = tmp_path / "new.safetensors"
    new.write_bytes(b"new file")
    assert utils.update_cached_hash(new, "b" * 64) == ["b" * 64]
    assert digest not in utils.update_cached_hash(new, "b" * 64)
