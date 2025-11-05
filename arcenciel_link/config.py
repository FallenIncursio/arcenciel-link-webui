import json, os
from pathlib import Path

from .secure_store import (
    get_secret,
    is_secure_storage_available,
    migrate_legacy_secret,
    sanitize_legacy_secret,
    set_secret,
)

_CFG = Path(__file__).parent / "config.json"
_DEFAULT = {
    "base_url": "https://link.arcenciel.io/api/link",
    "api_key": "",
    "link_key": "",
    "min_free_mb": 2048,
    "max_retries": 5,
    "backoff_base": 2,
    "webui_root": "",
    "save_html_preview": False
}

OLD_URLS = {
    "https://arcenciel.io/api/link",
    "https://arcenciel.io/api/link/",
}

_DEV_URL = "http://localhost:3000/api/link"
_SECRET_KEYS = ("api_key", "link_key")

def _detect_dev_mode() -> bool:
    if os.getenv("ARCENCIEL_DEV"):
        return True
    return "--dev" in os.getenv("COMMANDLINE_ARGS", "")

def _apply_env_overrides(cfg: dict) -> None:
    if os.getenv("ARCENCIEL_LINK_URL"):
        cfg["base_url"] = os.getenv("ARCENCIEL_LINK_URL").rstrip("/")
    if os.getenv("ARCENCIEL_API_KEY"):
        cfg["api_key"] = os.getenv("ARCENCIEL_API_KEY").strip()
    if os.getenv("ARCENCIEL_LINK_KEY"):
        cfg["link_key"] = os.getenv("ARCENCIEL_LINK_KEY").strip()


def _load_keyring_secrets(cfg: dict) -> None:
    for key in _SECRET_KEYS:
        provided = sanitize_legacy_secret(cfg.get(key))
        migrate_legacy_secret(key, provided)
        stored = sanitize_legacy_secret(get_secret(key))
        cfg[key] = stored or (provided or "")


def load() -> dict:
    cfg = _DEFAULT.copy()
    dev_mode = _detect_dev_mode()

    if _CFG.exists():
        try:
            cfg.update(json.loads(_CFG.read_text()))
            if cfg["base_url"] in OLD_URLS:
                cfg["base_url"] = _DEFAULT["base_url"]
                try:
                    _CFG.write_text(json.dumps(cfg, indent=2))
                except Exception:
                    pass
        except Exception:
            pass

    # Dev-Override
    if dev_mode and cfg["base_url"] == _DEFAULT["base_url"]:
        cfg["base_url"] = _DEV_URL

    try: 
        from modules import shared 
        cfg["base_url"] = shared.opts.data.get("arcenciel_link_base_url", cfg["base_url"]) 
        cfg["api_key"]  = shared.opts.data.get("arcenciel_link_api_key",  cfg["api_key"]) 
        cfg["link_key"] = shared.opts.data.get("arcenciel_link_access_key", cfg.get("link_key", "")) 
    except Exception: 
        pass

    _apply_env_overrides(cfg)
    _load_keyring_secrets(cfg)

    cfg["_dev_mode"] = dev_mode

    return cfg

def save(cfg: dict):
    for key in _SECRET_KEYS:
        secret = sanitize_legacy_secret(cfg.get(key))
        set_secret(key, secret)

    to_write = {k: v for k, v in cfg.items() if k not in _SECRET_KEYS}

    if not is_secure_storage_available():
        for key in _SECRET_KEYS:
            secret = sanitize_legacy_secret(cfg.get(key))
            to_write[key] = secret or ""

    _CFG.write_text(json.dumps(to_write, indent=2))
