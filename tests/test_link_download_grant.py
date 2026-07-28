from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_utils_module():
    spec = importlib.util.spec_from_file_location(
        "arcenciel_link_utils_for_test",
        REPO_ROOT / "arcenciel_link" / "utils.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_downloader_module(monkeypatch: pytest.MonkeyPatch):
    package = types.ModuleType("arcenciel_link")
    package.__path__ = [str(REPO_ROOT / "arcenciel_link")]
    monkeypatch.setitem(sys.modules, "arcenciel_link", package)

    config = types.ModuleType("arcenciel_link.config")
    config.load = lambda: {
        "_dev_mode": False,
        "min_free_mb": 2048,
        "max_retries": 1,
        "backoff_base": 1,
    }
    monkeypatch.setitem(sys.modules, "arcenciel_link.config", config)

    client = types.ModuleType("arcenciel_link.client")
    client.BASE_URL = "https://link.arcenciel.io/api/link"
    client.queue_next_job = Mock()
    client.report_progress = Mock()
    client.push_inventory = Mock()
    client._sock = Mock()
    client._open_evt = Mock()
    client.headers = Mock(return_value={})
    monkeypatch.setitem(sys.modules, "arcenciel_link.client", client)

    utils = types.ModuleType("arcenciel_link.utils")
    utils.download_file = Mock()
    utils.sha256_of_file = Mock()
    utils.get_model_path = Mock()
    utils.list_model_hashes = Mock()
    utils.update_cached_hash = Mock()
    utils.get_http_session = Mock(return_value=Mock())
    monkeypatch.setitem(sys.modules, "arcenciel_link.utils", utils)

    spec = importlib.util.spec_from_file_location(
        "arcenciel_link.downloader",
        REPO_ROOT / "arcenciel_link" / "downloader.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "arcenciel_link.downloader", module)
    spec.loader.exec_module(module)
    return module


def load_client_module(monkeypatch: pytest.MonkeyPatch):
    package = types.ModuleType("arcenciel_link")
    package.__path__ = [str(REPO_ROOT / "arcenciel_link")]
    monkeypatch.setitem(sys.modules, "arcenciel_link", package)

    config = types.ModuleType("arcenciel_link.config")
    config.load = lambda: {
        "_dev_mode": False,
        "base_url": "https://link.arcenciel.io/api/link",
        "link_key": "",
        "api_key": "",
    }
    config.save = Mock()
    monkeypatch.setitem(sys.modules, "arcenciel_link.config", config)

    utils = types.ModuleType("arcenciel_link.utils")
    utils.list_subfolders = Mock()
    utils.get_http_session = Mock(return_value=Mock())
    monkeypatch.setitem(sys.modules, "arcenciel_link.utils", utils)

    websocket = types.ModuleType("websocket")
    websocket.WebSocketApp = Mock()
    monkeypatch.setitem(sys.modules, "websocket", websocket)

    import signal

    monkeypatch.setattr(signal, "signal", Mock())
    spec = importlib.util.spec_from_file_location(
        "arcenciel_link.client",
        REPO_ROOT / "arcenciel_link" / "client.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "arcenciel_link.client", module)
    spec.loader.exec_module(module)
    return module


def test_download_file_sends_grant_header_without_following_redirects(tmp_path):
    module = load_utils_module()
    response = Mock()
    response.headers = {"content-length": "4"}
    response.iter_content.return_value = [b"data"]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    session = Mock()
    session.get.return_value = response
    module._SESSION = session

    destination = tmp_path / "model.part"
    module.download_file(
        "https://arcenciel.io/api/link/queue/7/download/model.safetensors",
        destination,
        Mock(),
        request_headers={"X-ArcEnCiel-Link-Grant": "secret-token"},
    )

    session.get.assert_called_once_with(
        "https://arcenciel.io/api/link/queue/7/download/model.safetensors",
        stream=True,
        timeout=60,
        headers={"X-ArcEnCiel-Link-Grant": "secret-token"},
        allow_redirects=False,
    )
    assert destination.read_bytes() == b"data"


def test_regular_downloads_keep_redirect_support(tmp_path):
    module = load_utils_module()
    response = Mock()
    response.headers = {}
    response.iter_content.return_value = [b"data"]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    session = Mock()
    session.get.return_value = response
    module._SESSION = session

    module.download_file(
        "https://cdn.example.com/model.safetensors",
        tmp_path / "model.part",
        Mock(),
    )

    assert session.get.call_args.kwargs["headers"] is None
    assert session.get.call_args.kwargs["allow_redirects"] is True


def test_worker_announces_download_grant_capability(monkeypatch):
    module = load_client_module(monkeypatch)
    module._sock = Mock()
    module._open_evt.set()

    module._send_worker_state(True)

    payload = module.json.loads(module._sock.send.call_args.args[0])
    assert payload == {
        "type": "worker_state",
        "running": True,
        "capabilities": ["link_download_grant_v1"],
    }


def test_grant_is_only_sent_to_the_scoped_arcenciel_route(monkeypatch):
    module = load_downloader_module(monkeypatch)
    job = {"downloadGrant": "token"}

    assert module._grant_headers_for_job(
        job,
        "https://arcenciel.io/api/link/queue/7/download/model.safetensors",
    ) == {"X-ArcEnCiel-Link-Grant": "token"}

    with pytest.raises(RuntimeError, match="not trusted"):
        module._grant_headers_for_job(
            job,
            "https://evil.example/api/link/queue/7/download/model.safetensors",
        )
    with pytest.raises(RuntimeError, match="invalid path"):
        module._grant_headers_for_job(
            job,
            "https://arcenciel.io/api/models/1/versions/2/download",
        )
    with pytest.raises(RuntimeError, match="Invalid Link download grant"):
        module._grant_headers_for_job(
            {"downloadGrant": ""},
            "https://arcenciel.io/api/link/queue/7/download/model.safetensors",
        )


def test_retry_passes_grant_header_to_download_helper(monkeypatch, tmp_path):
    module = load_downloader_module(monkeypatch)
    callback = Mock()
    headers = {"X-ArcEnCiel-Link-Grant": "token"}
    target = tmp_path / "model.part"

    module._download_with_retry(
        "https://arcenciel.io/api/link/queue/7/download/model.safetensors",
        target,
        callback,
        request_headers=headers,
    )

    module.download_file.assert_called_once_with(
        "https://arcenciel.io/api/link/queue/7/download/model.safetensors",
        target,
        callback,
        request_headers=headers,
    )
