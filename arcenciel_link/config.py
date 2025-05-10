import json, os
from pathlib import Path

_CFG = Path(__file__).parent / "config.json"
_DEFAULT  = {
    "base_url": "https://arcenciel.io/api/link",
    "api_key": "",
    "min_free_mb": 2048,
    "max_retries": 5,
    "backoff_base" : 2,
    "webui_root": ""
}

def load() -> dict:
    if _CFG.exists():
        try:
            return {**_DEFAULT, **json.loads(_CFG.read_text())}
        except Exception:
            pass
    return _DEFAULT.copy()

def save(cfg: dict):
    _CFG.write_text(json.dumps(cfg, indent=2))
