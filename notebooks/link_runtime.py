"""Versioned Link setup for existing notebook hosts. No secrets are persisted."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RELEASE = "v2.5.1"
BASE_URL = "https://link.arcenciel.io/api/link"
HOSTS = {
    "webui": ("launch.py", "extensions/arcenciel-link-webui", "arcenciel-link-webui"),
    "comfyui": ("main.py", "custom_nodes/arcenciel-link-comfyui", "arcenciel-link-comfyui"),
    "swarmui": ("src/SwarmUI.csproj", "src/Extensions/ArcEnCielLink", "arcenciel-link-swarmui"),
}


def validate_host(kind: str, root: str | Path) -> Path:
    if kind not in HOSTS:
        raise ValueError("Choose webui, comfyui, or swarmui")
    root = Path(root).expanduser().resolve()
    if not (root / ".git").exists() or not (root / HOSTS[kind][0]).is_file():
        raise RuntimeError(f"Host setup is incomplete: expected a Git checkout and {HOSTS[kind][0]} in {root}")
    try:
        checkout_root = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except subprocess.CalledProcessError:
        raise RuntimeError("Host setup is incomplete: the Git checkout is not readable") from None
    if Path(checkout_root).resolve() != root:
        raise RuntimeError("Host path must point to the root of its Git checkout")
    if (root / "extensions/ArcEnCiel-Extension-for-WebUI").exists():
        raise RuntimeError("Remove or disable the legacy ArcEnCiel-Extension-for-WebUI before installing Link")
    return root


def read_colab_key() -> str:
    try:
        from google.colab import userdata

        key = userdata.get("ARCENCIEL_LINK_KEY")
    except Exception:
        raise RuntimeError("Add ARCENCIEL_LINK_KEY to Colab Secrets and grant this notebook access") from None
    return validate_key(key)


def validate_key(key: str) -> str:
    key = (key or "").strip()
    if not re.fullmatch(r"lk_[A-Za-z0-9_-]{32}", key):
        raise ValueError("ARCENCIEL_LINK_KEY must be lk_ followed by 32 URL-safe characters")
    return key


def install_extension(kind: str, root: str | Path) -> Path:
    root = validate_host(kind, root)
    _, relative, repository = HOSTS[kind]
    extension = root / relative
    if kind == "comfyui":
        candidates = [path for path in (extension, root / "custom_nodes/ArcEnCielLink") if path.exists()]
        if len(candidates) > 1:
            raise RuntimeError("Multiple ComfyUI Link installations found; keep one before updating")
        if candidates:
            extension = candidates[0]
    remote = f"https://github.com/FallenIncursio/{repository}.git"
    if extension.exists():
        if not (extension / ".git").exists():
            raise RuntimeError(f"Existing extension is not a Git checkout: {extension}")
        origin = subprocess.check_output(
            ["git", "-C", str(extension), "remote", "get-url", "origin"], text=True
        ).strip()
        if origin.removesuffix(".git") != remote.removesuffix(".git"):
            raise RuntimeError("Existing extension has a different origin; review it before updating")
        if subprocess.check_output(["git", "-C", str(extension), "status", "--porcelain"], text=True).strip():
            raise RuntimeError("Extension has local changes; preserve them before updating")
        subprocess.run(["git", "-C", str(extension), "fetch", "origin", "tag", RELEASE], check=True)
    else:
        extension.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", RELEASE, remote, str(extension)], check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(extension), "rev-parse", f"{RELEASE}^{{commit}}"], text=True
    ).strip()
    # Forge reads active_branch while loading extension metadata. Keep the pin on a
    # named local branch without overwriting any existing branch or local commit.
    branch = f"arcenciel-link-{RELEASE}"
    existing = subprocess.run(
        ["git", "-C", str(extension), "rev-parse", "--verify", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
    )
    if existing.returncode == 0:
        if existing.stdout.strip() != commit:
            raise RuntimeError("The pinned release branch contains local commits; preserve them before updating")
        subprocess.run(["git", "-C", str(extension), "checkout", branch], check=True)
    else:
        subprocess.run(["git", "-C", str(extension), "checkout", "-b", branch, commit], check=True)
    if kind != "swarmui":
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(extension / "requirements.txt")], check=True)
    print(f"Link {RELEASE} installed for {kind} ({commit[:12]}). Restart the host to load it.")
    return extension


def configure_runtime(kind: str, root: str | Path, key: str, *, enabled: bool = True) -> Path:
    root = validate_host(kind, root)
    key = validate_key(key)
    os.environ["ARCENCIEL_LINK_URL"] = BASE_URL
    os.environ["ARCENCIEL_LINK_KEY"] = key
    os.environ["ARCENCIEL_LINK_ENABLED"] = "1" if enabled else "0"
    print("Link runtime configured. Select Remote / Colab for this key on arcenciel.io.")
    return root


def wait_for_worker(timeout: float = 120) -> dict:
    key = validate_key(os.environ.get("ARCENCIEL_LINK_KEY", ""))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            request = Request(
                BASE_URL + "/health",
                headers={"x-link-key": key, "User-Agent": f"ArcEnCiel-Link-Notebook/{RELEASE.removeprefix('v')}"},
            )
            with urlopen(request, timeout=15) as response:
                health = json.load(response)
            if health.get("disabled"):
                raise RuntimeError("Arc en Ciel Link is temporarily disabled; retry later")
            if health.get("workerOnline") is True and health.get("linkKeyId"):
                print("Authenticated Link worker is online. Queue a small model to verify the complete download path.")
                return {"workerOnline": True, "linkKeyId": health["linkKeyId"]}
        except HTTPError as exc:
            if exc.code in (401, 403):
                if exc.headers.get_content_type() != "application/json":
                    raise RuntimeError(
                        "Link verification was blocked by the HTTP gateway; check runtime network access"
                    ) from None
                raise RuntimeError("Link key rejected; check its validity and jobs/inventory scopes") from None
        except (URLError, TimeoutError):
            pass
        time.sleep(2)
    raise TimeoutError("Worker did not connect. Check the host log and restart it after running the Link setup cell.")
