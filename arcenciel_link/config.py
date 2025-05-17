import json, os
from pathlib import Path

_CFG = Path(__file__).parent / "config.json"
_DEFAULT = {
    "base_url": "https://arcenciel.io/api/link",
    "api_key" : "",
    "min_free_mb": 2048,
    "max_retries": 5,
    "backoff_base": 2,
    "webui_root": "",
    "save_html_preview": False
}

_DEV_URL = "http://localhost:3000/api/link"

def _detect_dev_mode() -> bool:
    if os.getenv("ARCENCIEL_DEV"):
        return True
    return "--dev" in os.getenv("COMMANDLINE_ARGS", "")

def _apply_env_overrides(cfg: dict) -> None:
    if os.getenv("ARCENCIEL_LINK_URL"):
        cfg["base_url"] = os.getenv("ARCENCIEL_LINK_URL").rstrip("/")
    if os.getenv("ARCENCIEL_API_KEY"):
        cfg["api_key"]  = os.getenv("ARCENCIEL_API_KEY").strip()


def load() -> dict:
    cfg = _DEFAULT.copy()

    if _CFG.exists():
        try:
            cfg.update(json.loads(_CFG.read_text()))
        except Exception:
            pass

    # Dev-Override
    if _detect_dev_mode() and cfg["base_url"] == _DEFAULT["base_url"]:
        cfg["base_url"] = _DEV_URL

    try: 
        from modules import shared 
        cfg["base_url"] = shared.opts.data.get("arcenciel_link_base_url", cfg["base_url"]) 
        cfg["api_key"]  = shared.opts.data.get("arcenciel_link_api_key",  cfg["api_key"]) 
    except Exception: 
        pass

    return cfg

def save(cfg: dict):
    _CFG.write_text(json.dumps(cfg, indent=2))
