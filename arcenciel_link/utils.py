from __future__ import annotations

import argparse
import glob
import hashlib
import json
import logging
import os
import shlex
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Generator, List, Set

import requests

from . import hash_cache, job_attempt
from .version import VERSION

_DEFAULT_USER_AGENT = f"ArcEnCiel-Link-Forge/{VERSION}"
_SESSION: requests.Session | None = None


def _resolve_user_agent() -> str:
    override = os.getenv("ARCENCIEL_LINK_UA")
    if override:
        trimmed = override.strip()
        if trimmed:
            return trimmed
    return _DEFAULT_USER_AGENT


def get_http_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        session.headers["User-Agent"] = _resolve_user_agent()
        _SESSION = session
    return _SESSION


log = logging.getLogger("arcenciel_link")
log.setLevel(logging.INFO)


def download_file(
    url: str,
    dst: Path,
    progress_cb,
    *,
    request_headers: dict[str, str] | None = None,
    allow_redirects: bool = True,
):
    session = get_http_session()
    with session.get(
        url,
        stream=True,
        timeout=(10, 5),
        headers=request_headers,
        allow_redirects=allow_redirects,
    ) as r:
        active = job_attempt.ACTIVE
        if active:
            active.response = r
            active.check()
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        chunk = 64 * 1024
        with open(dst, "wb") as f:
            done = 0
            for part in r.iter_content(chunk_size=chunk):
                if active:
                    active.check()
                f.write(part)
                done += len(part)
                if active:
                    active.bytes_downloaded = done
                if total:
                    progress_cb(done / total)


def sha256_of_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if job_attempt.ACTIVE:
                job_attempt.ACTIVE.check()
            h.update(chunk)
    return h.hexdigest()


CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "hashes.json"
_CACHE_LOCK = threading.RLock()
_CACHE_DIRTY = False
_MODEL_CATALOG_DIRTY = threading.Event()
_CACHE_LAST_SAVE = 0.0
_CACHE_DATA: Dict[str, Dict] | None = None

MODEL_EXTS = {".safetensors", ".ckpt", ".pt", ".sft", ".gguf"}

KNOWN_HASHES = set()


def list_subfolders(kind: str) -> list[str]:
    base = {
        "checkpoint": "models/Stable-diffusion",
        "lora": "models/Lora",
        "vae": "models/VAE",
        "embedding": "embeddings",
    }[kind.lower()]

    root = Path(get_model_path(base))
    if not root.exists():
        return []

    out: list[str] = []
    for p in root.rglob("*"):
        if p.is_dir() and not p.name.startswith("."):
            rel = p.relative_to(root).as_posix()
            if rel:
                out.append(rel)

    return sorted(out)


def _get_model_dirs(root: Path) -> List[Path]:
    dirs: Set[Path] = set()

    dirs.update(
        {
            root / "models" / "Stable-diffusion",
            root / "models" / "Lora",
            root / "models" / "VAE",
            root / "embeddings",
        }
    )

    try:
        from modules import shared

        co = shared.cmd_opts
        if getattr(co, "ckpt_dir", None):
            dirs.add(Path(co.ckpt_dir))
        for value in getattr(co, "ckpt_dirs", []) or []:
            dirs.add(Path(value))
        if getattr(co, "lora_dir", None):
            dirs.add(Path(co.lora_dir))
        for value in getattr(co, "lora_dirs", []) or []:
            dirs.add(Path(value))
        if getattr(co, "vae_dir", None):
            dirs.add(Path(co.vae_dir))
        for value in getattr(co, "vae_dirs", []) or []:
            dirs.add(Path(value))
        if getattr(co, "embeddings_dir", None):
            dirs.add(Path(co.embeddings_dir))
    except Exception:
        pass

    cla = os.getenv("COMMANDLINE_ARGS", "")
    if cla:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--ckpt-dir")
        parser.add_argument("--ckpt-dirs", action="append")
        parser.add_argument("--lora-dir")
        parser.add_argument("--lora-dirs", action="append")
        parser.add_argument("--vae-dir")
        parser.add_argument("--vae-dirs", action="append")
        parser.add_argument("--embeddings-dir")
        args, _ = parser.parse_known_args(shlex.split(cla))
        for val in vars(args).values():
            if isinstance(val, list):
                dirs.update(Path(item) for item in val if item)
            elif val:
                dirs.add(Path(val))

    return [d for d in dirs if d.exists()]


def _load_cache() -> Dict[str, Dict]:
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            return (
                {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}
                if isinstance(data, dict)
                else {}
            )
        except Exception:
            pass
    return {}


def _save_cache(data: Dict):
    global _CACHE_DATA, _CACHE_DIRTY, _CACHE_LAST_SAVE
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CACHE_DIR, prefix=".hashes-", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CACHE_FILE)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    _CACHE_DATA = data
    _CACHE_DIRTY = False
    _CACHE_LAST_SAVE = time.monotonic()


def flush_hash_cache():
    with _CACHE_LOCK:
        if _CACHE_DIRTY:
            _save_cache(_ensure_cache())


def cached_model_hash(path, check=lambda: None, force=False):
    global _CACHE_DIRTY
    with _CACHE_LOCK:
        digest, changed, source = hash_cache.resolve(path, _ensure_cache(), check, force)
        _CACHE_DIRTY |= changed
        if changed:
            _MODEL_CATALOG_DIRTY.set()
        if _CACHE_DIRTY and time.monotonic() - _CACHE_LAST_SAVE >= 3:
            _save_cache(_ensure_cache())
        if source != "cached":
            import logging

            logging.getLogger("arcenciel_link").info("Model hash: %s (%s)", source, path.name)
        return digest


def _ensure_cache() -> Dict[str, Dict]:
    global _CACHE_DATA
    if _CACHE_DATA is None:
        _CACHE_DATA = _load_cache()
    return _CACHE_DATA


def _iter_model_files(root: Path) -> Generator[Path, None, None]:
    for base in _get_model_dirs(root):
        pattern = str(base / "**" / "*")
        for fp in glob.glob(pattern, recursive=True):
            p = Path(fp)
            if p.suffix.lower() in MODEL_EXTS and p.is_file():
                yield p


def list_model_hashes() -> List[str]:
    from .config import load

    webui_root = Path(os.getenv("SD_WEBUI_ROOT", Path.cwd()))
    cfg = load()
    if cfg.get("webui_root"):
        webui_root = Path(cfg["webui_root"])
    files = _iter_model_files(webui_root)
    result = []
    try:
        for path in dict.fromkeys(files):
            result.append(cached_model_hash(path))
    finally:
        flush_hash_cache()
    KNOWN_HASHES.clear()
    KNOWN_HASHES.update(result)
    return list(dict.fromkeys(result))


def update_cached_hash(path: Path, hash_value: str) -> List[str]:
    resolved = path.resolve()
    try:
        stat = resolved.stat()
        mtime = int(stat.st_mtime)
    except FileNotFoundError:
        return list_model_hashes()
    with _CACHE_LOCK:
        cache = _ensure_cache()
        cache[str(resolved)] = {"mtime": mtime, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "hash": hash_value}
        _save_cache(cache)

        hashes = []
        for cached_path, entry in cache.items():
            try:
                existing = Path(cached_path)
                if existing.is_file() and hash_cache.valid(entry, existing.stat()):
                    hashes.append(entry["hash"])
            except OSError:
                continue

        KNOWN_HASHES.clear()
        KNOWN_HASHES.update(hashes)
        return hashes


def _cmd_opts() -> Dict[str, str | None]:
    opts = {"ckpt_dir": None, "lora_dir": None, "vae_dir": None, "embeddings_dir": None}

    try:
        from modules import shared

        for k in opts:
            val = getattr(shared.cmd_opts, k, None)
            if val:
                opts[k] = val
        if not opts["ckpt_dir"] and getattr(shared.cmd_opts, "ckpt_dirs", None):
            opts["ckpt_dir"] = shared.cmd_opts.ckpt_dirs[0]
        if not opts["lora_dir"] and getattr(shared.cmd_opts, "lora_dirs", None):
            opts["lora_dir"] = shared.cmd_opts.lora_dirs[0]
        if not opts["vae_dir"] and getattr(shared.cmd_opts, "vae_dirs", None):
            opts["vae_dir"] = shared.cmd_opts.vae_dirs[0]
    except Exception:
        pass

    if not any(opts.values()) and (cla := os.getenv("COMMANDLINE_ARGS")):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--ckpt-dir")
        parser.add_argument("--ckpt-dirs", action="append")
        parser.add_argument("--lora-dir")
        parser.add_argument("--lora-dirs", action="append")
        parser.add_argument("--vae-dir")
        parser.add_argument("--vae-dirs", action="append")
        parser.add_argument("--embeddings-dir")
        args, _ = parser.parse_known_args(shlex.split(cla))
        parsed = vars(args)
        for k in opts:
            v = parsed.get(k)
            if v:
                opts[k] = v
        for singular, plural in (
            ("ckpt_dir", "ckpt_dirs"),
            ("lora_dir", "lora_dirs"),
            ("vae_dir", "vae_dirs"),
        ):
            values = parsed.get(plural)
            if not opts[singular] and values:
                opts[singular] = values[0]

    return opts


def get_model_path(target: str) -> Path:
    root = Path(os.getenv("SD_WEBUI_ROOT", Path.cwd()))
    opts = _cmd_opts()

    mapping = {
        "models/Stable-diffusion": Path(opts["ckpt_dir"]) if opts["ckpt_dir"] else root / "models/Stable-diffusion",
        "models/Checkpoint": Path(opts["ckpt_dir"]) if opts["ckpt_dir"] else root / "models/Stable-diffusion",
        "models/Lora": Path(opts["lora_dir"]) if opts["lora_dir"] else root / "models/Lora",
        "models/VAE": Path(opts["vae_dir"]) if opts["vae_dir"] else root / "models/VAE",
        "models/Vae": Path(opts["vae_dir"]) if opts["vae_dir"] else root / "models/VAE",
        "models/Emb": Path(opts["embeddings_dir"]) if opts["embeddings_dir"] else root / "embeddings",
        "embeddings": Path(opts["embeddings_dir"]) if opts["embeddings_dir"] else root / "embeddings",
    }

    normalised = str(target or "").replace("\\", "/").lstrip("/")
    if not normalised:
        raise ValueError("Invalid target path")
    lowered = normalised.lower()

    for prefix, real_dir in mapping.items():
        pref_norm = prefix.replace("\\", "/")
        pref_lower = pref_norm.lower()
        if lowered == pref_lower or lowered.startswith(pref_lower + "/"):
            tail = normalised[len(pref_norm) :].lstrip("/\\")
            base = Path(real_dir).resolve()
            candidate = base if not tail else (base / Path(tail))
            resolved = candidate.resolve()
            try:
                resolved.relative_to(base)
            except ValueError as exc:
                raise ValueError("Target path escapes allowed directories") from exc
            if any(part in ("..", ".") for part in resolved.parts[len(base.parts) :]):
                raise ValueError("Target path contains traversal segments")
            return resolved

    raise ValueError("Unsupported target path")
