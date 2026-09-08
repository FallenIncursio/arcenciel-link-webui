import hashlib
import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "tested_tools", Path(__file__).parents[1] / "arcenciel_link/device_tools.py"
)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


@pytest.fixture(autouse=True)
def reset(monkeypatch, tmp_path):
    from arcenciel_link import utils

    monkeypatch.setattr(utils, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(utils, "CACHE_FILE", tmp_path / "cache/hashes.json")
    monkeypatch.setattr(utils, "_CACHE_DATA", None)
    monkeypatch.setattr(utils, "_CACHE_DIRTY", False)
    tools._hash_cache.clear()


class Session:
    def __init__(self, fail=None, metas=None):
        self.calls = []
        self.fail = fail
        self.metas = metas or {}

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if self.fail and self.fail in url:
            return SimpleNamespace(status_code=503, json=lambda: {})
        return SimpleNamespace(
            status_code=200, json=lambda: self.metas if url.endswith("/sidecars/meta") else {"ok": True}
        )


def run(action="rescan", session=None):
    return tools.ToolRun(
        {"taskId": "task-123456", "action": action},
        "runtime-123",
        session or Session(),
        "https://example.test/api/link",
        {"x-link-key": "test-key"},
    )


def test_scan_all_roots_deduplicates_and_invalidates_size_and_mtime(tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()
    model = first / "a.safetensors"
    model.write_bytes(b"a")
    (second / "b.gguf").write_bytes(b"b")
    (second / "skip.json").write_text("ignore")
    hidden = first / ".hidden"
    hidden.mkdir()
    (hidden / "secret.pt").write_bytes(b"hidden")
    (first / "symlink").symlink_to(second, target_is_directory=True)
    (first / "alias.pt").symlink_to(model)
    values = tools.scan([first, first, second], lambda: None, lambda *args: None)
    assert len(values) == 2
    model.write_bytes(b"changed")
    again = tools.scan([first], lambda: None, lambda *args: None)
    assert again == [(hashlib.sha256(b"changed").hexdigest(), model)]
    model.unlink()
    assert tools.scan([first], lambda: None, lambda *args: None) == []
    assert tools._hash_cache == {}


def test_scan_cancellation_and_unreadable_root(tmp_path):
    model = tmp_path / "a.pt"
    model.write_bytes(b"x")
    with pytest.raises(tools.ToolFailure, match="SCAN_FAILED"):
        tools.scan([model], lambda: None, lambda *args: None)
    with pytest.raises(tools.ToolStopped):
        tools.scan([tmp_path], Mock(side_effect=tools.ToolStopped), lambda *args: None)


def test_empty_inventory_is_published_with_runtime_and_confirmed(tmp_path):
    session = Session()
    task = run(session=session)
    synced = Mock()
    task.execute(lambda: [tmp_path], Mock(), synced)
    assert task.state["state"] == "DONE"
    inventory = [kw for url, kw in session.calls if url.endswith("/inventory")]
    assert inventory[0]["json"] == {"hashes": [], "runtimeId": "runtime-123"}
    assert all(
        kw["headers"] == {"x-link-key": "test-key"} and kw["allow_redirects"] is False for _, kw in session.calls
    )
    synced.assert_called_once_with([])
    assert session.calls[-1][1]["json"]["state"] == "DONE"


def test_repair_batches_metadata_preserves_download_and_counts_warnings(tmp_path):
    for n in range(102):
        (tmp_path / f"{n}.pt").write_bytes(str(n).encode())
    metas = {hashlib.sha256(str(n).encode()).hexdigest(): {"modelId": n} for n in range(101)}
    task = run("repair_sidecars", Session(metas=metas))

    def repair(path, digest, meta, check):
        check()
        if meta["modelId"] == 0:
            raise OSError("private path and key")
        return True, meta["modelId"] == 1

    task.execute(lambda: [tmp_path], repair, Mock())
    assert task.state | {} == dict(
        task.state, state="DONE", processed=204, total=204, repaired=100, skipped=1, warnings=2
    )
    assert len([url for url, _ in task.session.calls if url.endswith("/sidecars/meta")]) == 2
    assert (tmp_path / "0.pt").read_bytes() == b"0"
    assert "private" not in str(task.state)


@pytest.mark.parametrize(
    "endpoint,code",
    [("/inventory", "INVENTORY_FAILED"), ("/sidecars/meta", "METADATA_FAILED"), ("/tools/progress", "TOOL_FAILED")],
)
def test_required_network_failures_do_not_report_success(tmp_path, endpoint, code):
    (tmp_path / "a.pt").write_bytes(b"a")
    task = run("repair_sidecars", Session(fail=endpoint))
    try:
        with pytest.raises(tools.ToolFailure, match=code):
            task.execute(lambda: [tmp_path], Mock(), Mock())
    finally:
        task.done.set()


def test_lost_lease_or_stale_server_stops_writes():
    task = run()
    task.last_ack = time.monotonic() - 46
    with pytest.raises(tools.ToolStopped):
        task.check()
    for code in [401, 403, 409]:
        task = run(session=SimpleNamespace(post=lambda *args, **kw: SimpleNamespace(status_code=code)))
        with pytest.raises(tools.ToolStopped):
            task.post("/tools/progress", {})
        assert task.stopped.is_set()


def test_atomic_missing_sidecars_preserve_custom_files_and_clean_temps(tmp_path, monkeypatch):
    model = tmp_path / "model.pt"
    model.write_bytes(b"model")
    sidecar = model.with_suffix(".json")
    sidecar.write_text("custom")
    meta = {"modelId": 1, "versionId": 2, "modelTitle": "<unsafe>", "activationTags": ["tag"]}
    changed, warning = tools.repair_missing(model, "hash", meta, lambda: None, Session(), True)
    assert changed and not warning
    assert sidecar.read_text() == "custom" and model.read_bytes() == b"model"
    assert "&lt;unsafe&gt;" in model.with_suffix(".arcenciel.html").read_text()
    assert tools.repair_missing(model, "hash", meta, lambda: None, Session(), True) == (False, False)
    with monkeypatch.context() as patch:
        patch.setattr(tools.os, "link", Mock(side_effect=OSError("disk full")))
        with pytest.raises(OSError):
            tools.write_missing(tmp_path / "failed.json", "data")
    assert not (tmp_path / "failed.json").exists()
    assert not list(tmp_path.glob(".aec-sidecar-*"))
    directory = tmp_path / "directory.json"
    directory.mkdir()
    with pytest.raises(tools.ToolFailure):
        tools.write_missing(directory, "data")


def test_preview_failure_is_a_warning_and_missing_metadata_still_written(tmp_path):
    model = tmp_path / "a.pt"
    model.write_bytes(b"unchanged")
    session = Mock()
    session.get.side_effect = OSError("private url")
    changed, warning = tools.repair_missing(
        model, "hash", {"modelId": 1, "preview": "https://example.test/preview"}, lambda: None, session
    )
    assert changed and warning and model.with_suffix(".arcenciel.info").exists()
    assert model.read_bytes() == b"unchanged"


def test_wrong_runtime_is_refused_and_cancellation_is_task_scoped(tmp_path):
    args = dict(
        runtime_id="runtime-123",
        session=Session(),
        base_url="https://example.test",
        headers={},
        roots=lambda: [tmp_path],
        repair=Mock(),
        sync_local=Mock(),
    )
    msg = {"taskId": "task-123456", "runtimeId": "wrong", "action": "rescan"}
    assert not tools.start(msg, **args)
    task = run()
    tools._active = task
    try:
        assert not tools.cancel({"taskId": task.task_id, "runtimeId": "wrong"}, task.runtime_id)
        assert not tools.cancel({"taskId": "other", "runtimeId": task.runtime_id}, task.runtime_id)
        assert tools.cancel({"taskId": task.task_id, "runtimeId": task.runtime_id}, task.runtime_id)
        assert task.stopped.is_set()
    finally:
        tools._active = None
