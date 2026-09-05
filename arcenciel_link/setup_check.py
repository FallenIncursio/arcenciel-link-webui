"""Bounded setup probe shared by the Python hosts. Never installs a model."""

import hashlib
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

CAPABILITY = "setup_check_v1"
SIZE = 4096
SHA256 = "d956b3266db2e34aebd97935fc60086319e2b35f028b78feab2b98bdf5e88b47"
TARGETS = {"checkpoint": "models/Checkpoint", "lora": "models/Lora", "vae": "models/VAE", "embedding": "embeddings"}
_lock = threading.Lock()


def probe(root, session, url, headers):
    result = {"ok": False, "code": "TARGET_UNAVAILABLE"}
    temporary = None
    try:
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(root).free
        if free < 1024 * 1024:
            result["code"] = "LOW_DISK_SPACE"
            return result
        result["code"] = "WRITE_FAILED"
        with tempfile.NamedTemporaryFile(prefix=".aec-link-check-", suffix=".tmp", dir=root, delete=False) as output:
            temporary = Path(output.name)
            result["code"] = "TRANSFER_FAILED"
            with session.get(url, headers=headers, stream=True, timeout=(5, 10), allow_redirects=False) as response:
                if response.status_code != 200:
                    return result
                size = 0
                for chunk in response.iter_content(chunk_size=4096):
                    size += len(chunk)
                    if size > SIZE:
                        result["code"] = "HASH_MISMATCH"
                        return result
                    result["code"] = "WRITE_FAILED"
                    output.write(chunk)
                    result["code"] = "TRANSFER_FAILED"
            result["code"] = "WRITE_FAILED"
            output.flush()
            os.fsync(output.fileno())
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if size != SIZE or digest != SHA256:
            result["code"] = "HASH_MISMATCH"
            return result
        result.update(ok=True, code="VERIFIED", bytes=size, sha256=digest, target=str(root), freeBytes=free)
    except Exception:
        # Stable codes only: HTTP errors can contain credentials or private paths.
        result["ok"] = False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
                result["cleaned"] = True
            except OSError:
                result.update(ok=False, code="CLEANUP_FAILED", cleaned=False)
    return result


def start_check(message, *, runtime_id, root_for, session, base_url, headers, reply, busy=False):
    request_id = message.get("requestId")
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", request_id):
        return False
    if message.get("runtimeId") != runtime_id or message.get("kind") not in TARGETS:
        return False
    envelope = {"type": "setup_check_result", "requestId": request_id, "runtimeId": runtime_id}
    if busy or not _lock.acquire(blocking=False):
        reply({**envelope, "ok": False, "code": "BUSY"})
        return False

    def run():
        try:
            try:
                root = root_for(TARGETS[message["kind"]])
            except Exception:
                result = {"ok": False, "code": "TARGET_UNAVAILABLE"}
            else:
                result = probe(root, session, f"{base_url}/setup/file/{request_id}", headers)
            reply({**envelope, **result})
        finally:
            _lock.release()

    threading.Thread(target=run, name="aec-link-setup-check", daemon=True).start()
    return True
