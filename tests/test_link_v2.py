import json
from pathlib import Path

import pytest

from arcenciel_link import config, downloader, utils


def test_private_download_grant_is_bound_to_configured_origin(monkeypatch):
    monkeypatch.setattr(downloader.client, "BASE_URL", "https://link.arcenciel.io/api/link")
    monkeypatch.setattr(downloader.client, "DEV_MODE", False)
    job = {
        "downloadGrant": "header.payload.signature",
        "downloadGrantHeader": "x-arcenciel-link-grant",
    }

    headers, redirects = downloader._private_download_options(
        job,
        "https://link.arcenciel.io/api/link/queue/7/download/model.safetensors?v=3",
    )

    assert headers == {"X-ArcEnCiel-Link-Grant": "header.payload.signature"}
    assert redirects is False
    with pytest.raises(RuntimeError, match="configured ArcEnCiel host"):
        downloader._private_download_options(
            job,
            "https://evil.example/api/link/queue/7/download/model.safetensors",
        )
    with pytest.raises(RuntimeError, match="forbidden"):
        downloader._private_download_options(
            job,
            "https://user@link.arcenciel.io/api/link/queue/7/download/model.safetensors",
        )


def test_download_retry_forwards_grant_and_disables_redirects(monkeypatch, tmp_path):
    calls = []

    def fake_download(url, target, progress, **options):
        calls.append((url, target, options))

    monkeypatch.setattr(downloader, "download_file", fake_download)
    destination = tmp_path / "model.part"
    downloader._download_with_retry(
        "https://link.arcenciel.io/model",
        destination,
        lambda _fraction: None,
        request_headers={"X-ArcEnCiel-Link-Grant": "grant"},
        allow_redirects=False,
    )

    assert calls[0][2] == {
        "request_headers": {"X-ArcEnCiel-Link-Grant": "grant"},
        "allow_redirects": False,
    }


def test_html_sidecar_escapes_remote_metadata(tmp_path):
    model = tmp_path / "model.safetensors"
    downloader._write_html(
        {
            "modelTitle": "<script>alert(1)</script>",
            "aboutThisVersion": "<img src=x onerror=alert(1)>",
            "activationTags": ["<b>tag</b>"],
            "sha256": "hash",
        },
        'preview" onerror="alert(1).png',
        model,
    )

    rendered = model.with_suffix(".arcenciel.html").read_text()
    assert "<script>" not in rendered
    assert '<img src="preview" onerror=' not in rendered
    assert "&lt;script&gt;" in rendered


def test_hash_cache_update_does_not_reenter_inventory_lock(monkeypatch, tmp_path):
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"tiny model")
    cache_file = tmp_path / "hashes.json"
    monkeypatch.setattr(utils, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(utils, "CACHE_FILE", cache_file)
    monkeypatch.setattr(utils, "_CACHE_DATA", {})

    hashes = utils.update_cached_hash(model, "a" * 64)

    assert hashes == ["a" * 64]
    assert json.loads(cache_file.read_text())[str(model.resolve())]["hash"] == "a" * 64


def test_config_removes_retired_credentials_and_writes_private_file(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "base_url": "https://link.arcenciel.io/api/link",
                "link_key": "lk_" + "a" * 32,
                "api_key": "retired-secret",
            }
        )
    )
    monkeypatch.setattr(config, "_CFG", config_file)
    monkeypatch.setattr(config, "is_secure_storage_available", lambda: False)
    monkeypatch.setattr(config, "get_secret", lambda _key: None)
    monkeypatch.setattr(config, "set_secret", lambda _key, _value: None)
    monkeypatch.setattr(config, "migrate_legacy_secret", lambda _key, _value: None)

    loaded = config.load()
    assert "api_key" not in loaded
    assert "api_key" not in json.loads(config_file.read_text())
    config.save(loaded)
    assert config_file.stat().st_mode & 0o777 == 0o600


def test_plural_forge_directories_are_discovered(monkeypatch, tmp_path):
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    monkeypatch.setenv("COMMANDLINE_ARGS", f"--ckpt-dirs {checkpoint_dir}")

    assert checkpoint_dir in utils._get_model_dirs(Path("/unused"))
