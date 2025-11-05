from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlparse

_DEFAULT_PORTS = {"http": 80, "https": 443}

_ALLOWED_DOMAIN_SUFFIXES = (".arcenciel.io",)
_ALLOWED_DOMAIN_NAMES = {"arcenciel.io"}
_LOCAL_HOSTNAMES = {"localhost"}
_LOCAL_TLDS = (".local", ".lan")


def _is_arcenciel_host(host: str) -> bool:
    return host in _ALLOWED_DOMAIN_NAMES or any(
        host.endswith(suffix) for suffix in _ALLOWED_DOMAIN_SUFFIXES
    )


@lru_cache(maxsize=1024)
def _is_private_host(host: str) -> bool:
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        lowered = host.lower()
        if lowered in _LOCAL_HOSTNAMES:
            return True
        if lowered.endswith(_LOCAL_TLDS):
            return True
        return "." not in lowered


def is_private_host(host: str | None) -> bool:
    if host is None:
        return False
    return _is_private_host(host)


def _port_or_default(scheme: str | None, port: int | None) -> int | None:
    if port is not None:
        return port
    if not scheme:
        return None
    return _DEFAULT_PORTS.get(scheme.lower())


def is_same_origin(
    origin: str | None,
    request_scheme: str | None,
    request_host: str | None,
    request_port: int | None,
) -> bool:
    if not origin or not request_scheme or not request_host:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    origin_host = (parsed.hostname or "").strip().lower()
    request_host_norm = request_host.strip().lower()
    if not origin_host or origin_host != request_host_norm:
        return False
    origin_scheme = (parsed.scheme or "").lower()
    request_scheme_norm = request_scheme.lower()
    if origin_scheme != request_scheme_norm:
        return False
    origin_port = _port_or_default(origin_scheme, parsed.port)
    request_port_norm = _port_or_default(request_scheme_norm, request_port)
    return origin_port == request_port_norm


def normalize_origin(origin: str | None, *, allow_private: bool = False) -> str | None:
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").strip()
    if not host:
        return None
    if allow_private and _is_private_host(host):
        return f"{parsed.scheme}://{parsed.netloc}"
    if _is_arcenciel_host(host):
        if parsed.scheme != "https":
            return None
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


__all__ = ["normalize_origin", "is_private_host", "is_same_origin"]
