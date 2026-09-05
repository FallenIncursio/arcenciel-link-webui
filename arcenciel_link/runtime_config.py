"""Runtime configuration contract v1, shared by the Python Link workers."""

import os
import re
import warnings
from urllib.parse import urlsplit

ENV_FIELDS = {
    "ARCENCIEL_LINK_URL": "base_url",
    "ARCENCIEL_LINK_KEY": "link_key",
    "ARCENCIEL_LINK_ENABLED": "enabled",
}
DEFAULT_URL = "https://link.arcenciel.io/api/link"


def apply_environment(cfg: dict, *, dev_mode: bool = False) -> None:
    error = None
    for variable, field in ENV_FIELDS.items():
        if variable in os.environ:
            raw = os.environ[variable].strip()
            if field == "enabled":
                normalized = raw.lower()
                cfg[field] = normalized in {"1", "true", "yes", "on"}
                if normalized not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
                    error = "ARCENCIEL_LINK_ENABLED must be one of 1/0, true/false, yes/no, or on/off"
            else:
                cfg[field] = raw.rstrip("/") if field == "base_url" else raw
    try:
        url = urlsplit(str(cfg.get("base_url", "")).strip())
        valid_url = (
            url.scheme in ({"https", "http"} if dev_mode else {"https"})
            and bool(url.hostname)
            and url.port != 0
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
            and "@" not in url.netloc
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        error = "ARCENCIEL_LINK_URL must be an absolute HTTPS URL without credentials, query, or fragment"
        cfg["base_url"] = DEFAULT_URL
        cfg["link_key"] = ""
    key = str(cfg.get("link_key") or "").strip()
    if key and not re.fullmatch(r"lk_[A-Za-z0-9_-]{32}", key):
        error = error or "ARCENCIEL_LINK_KEY has an invalid format; expected lk_ followed by 32 URL-safe characters"
        key = ""
    cfg["link_key"] = key
    if cfg.get("enabled") and not key:
        error = error or "A Link key is required before enabling the worker (ARCENCIEL_LINK_KEY)"
    cfg["_runtime_error"] = error
    if error:
        cfg["enabled"] = False
        warnings.warn(f"[AEC-LINK] {error}; worker disabled", RuntimeWarning, stacklevel=2)


def validate_worker_change(cfg: dict, enable: bool, link_key: str | None) -> None:
    managed = os.environ.get("ARCENCIEL_LINK_KEY")
    if managed is not None and link_key is not None and link_key != managed.strip():
        raise ValueError("ARCENCIEL_LINK_KEY is managed by the runtime environment; update it and restart")
    if enable:
        error = cfg.get("_runtime_error")
        repairing_desktop_key = (
            managed is None
            and bool(link_key)
            and error
            and error.startswith(("A Link key is required", "ARCENCIEL_LINK_KEY has an invalid format"))
        )
        if error and not repairing_desktop_key:
            raise ValueError(error)
        if not (cfg.get("link_key") if link_key is None else link_key):
            raise ValueError("A Link key is required before enabling the worker (ARCENCIEL_LINK_KEY)")


def persistent_payload(cfg: dict, stored: dict) -> dict:
    """Keep environment values out of disk storage, preserving desktop settings."""
    payload = {k: v for k, v in cfg.items() if not k.startswith("_") and k != "api_key"}
    for variable, field in ENV_FIELDS.items():
        if variable in os.environ:
            if field in stored:
                payload[field] = stored[field]
            else:
                payload.pop(field, None)
    return payload
