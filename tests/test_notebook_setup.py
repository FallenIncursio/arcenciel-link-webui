import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("notebook_link", Path(__file__).parents[1] / "notebooks/link_runtime.py")
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


@pytest.mark.parametrize("kind", link.HOSTS)
def test_incomplete_host_cannot_install_or_configure(kind, tmp_path, monkeypatch):
    monkeypatch.delenv("ARCENCIEL_LINK_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Host setup is incomplete"):
        link.configure_runtime(kind, tmp_path, "lk_" + "a" * 32)
    with pytest.raises(RuntimeError, match="Host setup is incomplete"):
        link.install_extension(kind, tmp_path)
    assert "ARCENCIEL_LINK_KEY" not in link.os.environ


@pytest.mark.parametrize("kind", link.HOSTS)
def test_all_hosts_configure_the_same_runtime_contract(kind, tmp_path, monkeypatch):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    launcher = tmp_path / link.HOSTS[kind][0]
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.touch()
    for variable in ["ARCENCIEL_LINK_KEY", "ARCENCIEL_LINK_URL", "ARCENCIEL_LINK_ENABLED"]:
        monkeypatch.delenv(variable, raising=False)
    link.configure_runtime(kind, tmp_path, "lk_" + "a" * 32)
    assert link.os.environ["ARCENCIEL_LINK_ENABLED"] == "1"
    assert link.os.environ["ARCENCIEL_LINK_URL"] == link.BASE_URL
    assert list(tmp_path.glob("**/config.json")) == []


def test_missing_colab_secret_reports_no_values(monkeypatch):
    def denied(_name):
        raise ValueError("sensitive provider details")

    monkeypatch.setitem(sys.modules, "google.colab", SimpleNamespace(userdata=SimpleNamespace(get=denied)))
    with pytest.raises(RuntimeError, match="Add ARCENCIEL_LINK_KEY to Colab Secrets") as error:
        link.read_colab_key()
    assert "sensitive" not in str(error.value)


def test_worker_verification_requires_authenticated_key_identity(monkeypatch):
    monkeypatch.setenv("ARCENCIEL_LINK_KEY", "lk_" + "a" * 32)
    replies = iter([{"status": "ok", "workerOnline": False}, {"status": "ok", "workerOnline": True, "linkKeyId": 7}])
    monkeypatch.setattr(link, "urlopen", lambda *_args, **_kwargs: io.BytesIO(json.dumps(next(replies)).encode()))
    monkeypatch.setattr(link.time, "sleep", lambda _seconds: None)
    assert link.wait_for_worker() == {"workerOnline": True, "linkKeyId": 7}
