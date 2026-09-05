"""Device-scoped maintenance. Progress contains counts and stable codes, never paths or keys."""

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

CAPABILITY = "device_tools_v1"
MODEL_EXTS = {".safetensors", ".ckpt", ".pt", ".sft", ".gguf"}
_lock = threading.Lock()
_active = None
_last = None
_hash_cache = {}


class ToolStopped(Exception):
    pass


class ToolFailure(Exception):
    pass


def status():
    return dict(_active.state if _active else _last) if (_active or _last) else None


def cancel(message, runtime_id):
    if _active and message.get("runtimeId") == runtime_id and message.get("taskId") == _active.task_id:
        _active.stopped.set()
        return True
    return False


def scan(roots, check, progress):
    files = set()
    for root in roots:
        root = Path(root).resolve()
        if not root.exists():
            continue
        if not root.is_dir():
            raise ToolFailure("SCAN_FAILED")

        def failed(_error):
            raise ToolFailure("SCAN_FAILED")

        for parent, dirs, names in os.walk(root, followlinks=False, onerror=failed):
            check()
            dirs[:] = [d for d in dirs if not d.startswith(".") and not (Path(parent) / d).is_symlink()]
            for name in names:
                p = Path(parent) / name
                if not p.is_symlink() and p.suffix.lower() in MODEL_EXTS and p.is_file():
                    files.add(p)
                    if len(files) > 10000:
                        raise ToolFailure("SCAN_FAILED")
    result = []
    progress(0, len(files))
    for i, path in enumerate(sorted(files)):
        check()
        before = path.stat()
        stamp = (before.st_mtime_ns, before.st_size)
        cached = _hash_cache.get(str(path))
        if cached and cached[:2] == stamp:
            digest = cached[2]
        else:
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    check()
                    h.update(chunk)
            after = path.stat()
            if (after.st_mtime_ns, after.st_size) != stamp:
                raise ToolFailure("SCAN_FAILED")
            digest = h.hexdigest()
            _hash_cache[str(path)] = (*stamp, digest)
        result.append((digest, path))
        progress(i + 1, len(files))
    for key in list(_hash_cache):
        if Path(key) not in files:
            del _hash_cache[key]
    return result


def write_missing(path, text):
    """Exclusive create preserves user-authored files even if one appears during repair."""
    import tempfile

    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".aec-sidecar-", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not path.is_file():
                raise ToolFailure("WRITE_FAILED")
            return False
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ToolRun:
    def __init__(self, message, runtime_id, session, base_url, headers):
        self.task_id = message["taskId"]
        self.action = message["action"]
        self.runtime_id = runtime_id
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.stopped = threading.Event()
        self.done = threading.Event()
        self.last_ack = time.monotonic()
        self.state = dict(
            taskId=self.task_id,
            runtimeId=runtime_id,
            action=self.action,
            state="RUNNING",
            phase="starting",
            processed=0,
            total=0,
            repaired=0,
            skipped=0,
            warnings=0,
        )
        self.report_lock = threading.Lock()

    def check(self):
        if self.stopped.is_set() or time.monotonic() - self.last_ack > 45:
            raise ToolStopped()

    def post(self, suffix, body):
        self.check()
        r = self.session.post(
            self.base_url + suffix, json=body, headers=self.headers, timeout=(5, 10), allow_redirects=False
        )
        if r.status_code in (401, 403, 409):
            self.stopped.set()
            raise ToolStopped()
        if not 200 <= r.status_code < 300:
            raise ToolFailure("TOOL_FAILED")
        return r.json()

    def report(self, heartbeat=False):
        with self.report_lock:
            if heartbeat and self.done.is_set():
                return False
            try:
                self.post("/tools/progress", dict(self.state))
                self.last_ack = time.monotonic()
                return True
            except ToolStopped:
                raise
            except Exception:
                return False

    def heartbeat(self):
        while not self.done.wait(10):
            try:
                self.check()
                self.report(heartbeat=True)
            except ToolStopped:
                self.stopped.set()
                return

    def execute(self, roots, repair, sync_local):
        if not self.report():
            raise ToolFailure("TOOL_FAILED")
        heartbeat = threading.Thread(target=self.heartbeat, name="aec-link-tool-heartbeat", daemon=True)
        heartbeat.start()
        self.state["phase"] = "scanning"

        def progress(n, total):
            self.state.update(processed=n, total=total)

        try:
            files = scan(roots(), self.check, progress)
        except (ToolStopped, ToolFailure):
            raise
        except Exception as e:
            raise ToolFailure("SCAN_FAILED") from e
        hashes = list(dict.fromkeys(h for h, _ in files))
        self.state["phase"] = "syncing"
        try:
            self.post("/inventory", {"hashes": hashes, "runtimeId": self.runtime_id})
            sync_local(hashes)
        except ToolStopped:
            raise
        except Exception as e:
            raise ToolFailure("INVENTORY_FAILED") from e
        if self.action == "repair_sidecars":
            self.state.update(phase="repairing", total=len(files) * 2)
            for offset in range(0, len(files), 100):
                batch = files[offset : offset + 100]
                try:
                    metas = self.post("/sidecars/meta", {"hashes": list(dict.fromkeys(h for h, _ in batch))})
                    if not isinstance(metas, dict):
                        raise ValueError("Metadata response")
                except ToolStopped:
                    raise
                except Exception as e:
                    raise ToolFailure("METADATA_FAILED") from e
                for digest, path in batch:
                    self.check()
                    meta = metas.get(digest)
                    if not isinstance(meta, dict):
                        self.state["skipped"] += 1
                    else:
                        try:
                            changed, warning = repair(path, digest, meta, self.check)
                            self.state["repaired" if changed else "skipped"] += 1
                            self.state["warnings"] += int(bool(warning))
                        except ToolStopped:
                            raise
                        except Exception:
                            self.state["warnings"] += 1
                    self.state["processed"] += 1
        self.done.set()
        self.state.update(state="DONE", phase="complete")
        if not self.report():
            raise ToolFailure("TOOL_FAILED")


def start(message, *, runtime_id, session, base_url, headers, roots, repair, sync_local, busy=False):
    global _active
    if (
        message.get("runtimeId") != runtime_id
        or message.get("action") not in ("rescan", "repair_sidecars")
        or not re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", str(message.get("taskId", "")))
    ):
        return False
    if not _lock.acquire(blocking=False):
        return False
    run = ToolRun(message, runtime_id, session, base_url, headers)
    _active = run

    def execute():
        global _active, _last
        try:
            if busy:
                raise ToolFailure("BUSY")
            run.execute(roots, repair, sync_local)
        except ToolStopped:
            run.state.update(state="CANCELLED")
        except Exception as e:
            run.state.update(state="ERROR", code=str(e) if isinstance(e, ToolFailure) else "TOOL_FAILED")
            try:
                run.report()
            except ToolStopped:
                pass
        finally:
            run.done.set()
            _last = dict(run.state)
            _active = None
            _lock.release()

    threading.Thread(target=execute, name="aec-link-device-tool", daemon=True).start()
    return True


def repair_missing(path, digest, meta, check, session, save_html=False):
    """Fill gaps only. Custom sidecars and model bytes are never overwritten."""
    import tempfile
    from html import escape
    from io import BytesIO
    from urllib.parse import urlparse

    path = Path(path)
    before = {
        suffix: path.with_suffix(suffix).exists()
        for suffix in (".arcenciel.info", ".json", ".preview.png", ".arcenciel.html")
    }
    warning = False
    preview = path.with_suffix(".preview.png")
    if meta.get("preview") and not before[".preview.png"]:
        temporary = None
        try:
            url = str(meta["preview"])
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.username or parsed.password:
                raise ValueError("Invalid preview URL")
            with session.get(url, stream=True, timeout=(5, 10), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError("Preview unavailable")
                data = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    check()
                    data.extend(chunk)
                    if len(data) > 20 * 1024 * 1024:
                        raise ValueError("Preview too large")
            from PIL import Image

            with tempfile.NamedTemporaryFile(
                prefix=".aec-sidecar-", suffix=".tmp", dir=path.parent, delete=False
            ) as output:
                temporary = Path(output.name)
                with Image.open(BytesIO(data)) as picture:
                    picture.convert("RGBA").save(output, format="PNG")
            check()
            try:
                os.link(temporary, preview)
            except FileExistsError:
                pass
        except ToolStopped:
            raise
        except Exception:
            warning = True
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    check()
    info = dict(
        schema=1,
        modelId=meta.get("modelId"),
        versionId=meta.get("versionId"),
        name=meta.get("modelTitle"),
        type=meta.get("type"),
        about=meta.get("aboutThisVersion") or meta.get("about"),
        sha256=digest,
        previewFile=preview.name if preview.exists() else None,
        arcencielUrl=f"https://arcenciel.io/models/{meta.get('modelId')}",
    )
    tags = " || ".join(str(t) for t in meta.get("activationTags", []) if isinstance(t, str))
    write_missing(path.with_suffix(".arcenciel.info"), json.dumps(info, indent=2, ensure_ascii=False))
    write_missing(
        path.with_suffix(".json"),
        json.dumps(
            {
                "description": info["about"],
                "sd version": "unknown",
                "activation text": tags,
                "modelspec.trigger_phrase": tags,
                "preferred weight": 1.0,
                "notes": info["arcencielUrl"],
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
    if save_html:
        check()
        text = (
            '<!doctype html><meta charset="utf-8"><title>'
            + escape(str(meta.get("modelTitle", "Arc en Ciel")))
            + "</title><h1>"
            + escape(str(meta.get("modelTitle", "")))
            + "</h1><p>"
            + escape(str(info["about"] or ""))
            + "</p><p>"
            + escape(tags)
            + "</p><small>SHA-256: "
            + digest
            + "</small>"
        )
        write_missing(path.with_suffix(".arcenciel.html"), text)
    return any(not existed and path.with_suffix(suffix).is_file() for suffix, existed in before.items()), warning
