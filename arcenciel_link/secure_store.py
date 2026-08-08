from __future__ import annotations

SERVICE_NAME = "arcenciel-link-forge"


def sanitize_legacy_secret(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _keyring():
    try:
        import keyring

        backend = keyring.get_keyring()
        if float(getattr(backend, "priority", 0) or 0) <= 0:
            return None
        return keyring
    except Exception:
        return None


def is_secure_storage_available() -> bool:
    return _keyring() is not None


def get_secret(key: str) -> str | None:
    backend = _keyring()
    if backend is None:
        return None
    try:
        return sanitize_legacy_secret(backend.get_password(SERVICE_NAME, key))
    except Exception:
        return None


def set_secret(key: str, value: str | None) -> None:
    backend = _keyring()
    if backend is None:
        return
    normalized = sanitize_legacy_secret(value)
    try:
        if normalized:
            backend.set_password(SERVICE_NAME, key, normalized)
        else:
            backend.delete_password(SERVICE_NAME, key)
    except Exception:
        return


def migrate_legacy_secret(key: str, value: str | None) -> None:
    normalized = sanitize_legacy_secret(value)
    if normalized and is_secure_storage_available() and not get_secret(key):
        set_secret(key, normalized)
