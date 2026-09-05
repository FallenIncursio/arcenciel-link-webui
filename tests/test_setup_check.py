import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arcenciel_link import setup_check as setup

DATA = (b"Arc en Ciel Link setup check v1\n" * 200)[:4096]


class Response:
    def __init__(self, data=DATA, status=200):
        self.data, self.status_code = data, status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.data), chunk_size):
            yield self.data[offset : offset + chunk_size]


def session(data=DATA, status=200):
    return SimpleNamespace(get=Mock(return_value=Response(data, status)))


def test_real_write_readback_hash_and_cleanup(tmp_path):
    (tmp_path / "existing.model").write_bytes(b"keep")
    client = session()
    result = setup.probe(
        tmp_path, client, "https://link.example/api/link/setup/file/request-a", {"x-link-key": "private"}
    )
    assert result == {
        "ok": True,
        "code": "VERIFIED",
        "bytes": 4096,
        "sha256": hashlib.sha256(DATA).hexdigest(),
        "target": str(tmp_path),
        "freeBytes": result["freeBytes"],
        "cleaned": True,
    }
    assert result["sha256"] == setup.SHA256
    assert sorted(p.name for p in tmp_path.iterdir()) == ["existing.model"]
    assert (tmp_path / "existing.model").read_bytes() == b"keep"
    assert client.get.call_args.kwargs["allow_redirects"] is False
    assert client.get.call_args.kwargs["timeout"] == (5, 10)


@pytest.mark.parametrize(
    "data,status,code",
    [
        (b"short", 200, "HASH_MISMATCH"),
        (b"x" * 4096, 200, "HASH_MISMATCH"),
        (DATA + b"extra", 200, "HASH_MISMATCH"),
        (DATA, 302, "TRANSFER_FAILED"),
        (DATA, 403, "TRANSFER_FAILED"),
    ],
)
def test_bad_transfer_never_passes_and_is_cleaned(tmp_path, data, status, code):
    result = setup.probe(tmp_path, session(data, status), "https://link.example/probe", {})
    assert result["ok"] is False and result["code"] == code
    assert result["cleaned"] is True
    assert not list(tmp_path.iterdir())


def test_low_disk_prevents_download(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.shutil, "disk_usage", lambda _: SimpleNamespace(free=100))
    client = session()
    assert setup.probe(tmp_path, client, "https://link.example/probe", {})["code"] == "LOW_DISK_SPACE"
    client.get.assert_not_called()


@pytest.mark.parametrize(
    "failure,code",
    [
        ("root", "TARGET_UNAVAILABLE"),
        ("write", "WRITE_FAILED"),
        ("read", "WRITE_FAILED"),
        ("http", "TRANSFER_FAILED"),
        ("cleanup", "CLEANUP_FAILED"),
    ],
)
def test_stable_errors_do_not_leak_credentials(tmp_path, monkeypatch, failure, code):
    client = session()

    def fail(*args, **kwargs):
        raise OSError("private credential and path")

    if failure == "root":
        monkeypatch.setattr(Path, "mkdir", fail)
    if failure == "write":
        monkeypatch.setattr(setup.tempfile, "NamedTemporaryFile", fail)
    if failure == "read":
        monkeypatch.setattr(Path, "read_bytes", fail)
    if failure == "http":
        client.get.side_effect = fail
    if failure == "cleanup":
        monkeypatch.setattr(Path, "unlink", fail)
    result = setup.probe(tmp_path, client, "https://link.example/probe", {})
    assert result["code"] == code and result["ok"] is False
    assert "private" not in str(result)


def test_control_binds_runtime_category_nonce_and_configured_origin(tmp_path):
    client, replies = session(), []
    done = threading.Event()

    def reply(value):
        replies.append(value)
        done.set()

    def start(message, **extra):
        return setup.start_check(
            message,
            runtime_id="runtime-a",
            root_for=lambda category: tmp_path / category,
            session=client,
            base_url="https://link.example/api/link",
            headers={},
            reply=reply,
            **extra,
        )

    valid = {"requestId": "request-123", "runtimeId": "runtime-a", "kind": "lora", "url": "https://attacker.example"}
    for patch in [{"requestId": "../invalid"}, {"requestId": None}, {"runtimeId": "other"}, {"kind": "unknown"}]:
        assert not start({**valid, **patch})
    assert not start(valid, busy=True)
    assert replies[-1]["code"] == "BUSY"
    done.clear()
    assert start(valid)
    assert done.wait(3)
    assert replies[-1]["ok"] and replies[-1]["runtimeId"] == "runtime-a"
    assert replies[-1]["target"] == str(tmp_path / "models/Lora")
    assert client.get.call_args.args[0] == "https://link.example/api/link/setup/file/request-123"
    # The reply is sent just before releasing the lock.
    assert setup._lock.acquire(timeout=3)
    try:
        assert not start(valid)
        assert replies[-1]["code"] == "BUSY"
    finally:
        setup._lock.release()


def test_invalid_model_root_replies_without_transfer():
    done, replies = threading.Event(), []

    def root(_):
        raise ValueError("private host path")

    def reply(value):
        replies.append(value)
        done.set()

    client = session()
    assert setup.start_check(
        {"requestId": "request-123", "runtimeId": "runtime-a", "kind": "checkpoint"},
        runtime_id="runtime-a",
        root_for=root,
        session=client,
        base_url="https://link.example",
        headers={},
        reply=reply,
    )
    assert done.wait(3)
    assert replies[0]["code"] == "TARGET_UNAVAILABLE"
    client.get.assert_not_called()
    assert setup._lock.acquire(timeout=3)
    setup._lock.release()
