from __future__ import annotations
import hashlib, json, os, glob
from pathlib import Path
from typing import List, Dict, Generator, Set
import shlex, argparse

import requests
import logging

log = logging.getLogger("arcenciel_link")
log.setLevel(logging.INFO)

def download_file(url: str, dst: Path, progress_cb):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        chunk = 1024 * 1024
        with open(dst, "wb") as f:
            done = 0
            for part in r.iter_content(chunk_size=chunk):
                f.write(part)
                done += len(part)
                if total:
                    progress_cb(done / total)


def sha256_of_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

CACHE_DIR  = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "hashes.json"

MODEL_EXTS = {".safetensors", ".ckpt", ".pt"}

KNOWN_HASHES = set()


def _get_model_dirs(root: Path) -> List[Path]:
    dirs: Set[Path] = set()

    dirs.update({
        root / "models" / "Stable-diffusion",
        root / "models" / "Lora",
        root / "models" / "VAE",
        root / "embeddings",
    })

    try:
        from modules import shared
        co = shared.cmd_opts
        if getattr(co, "ckpt_dir", None): dirs.add(Path(co.ckpt_dir))
        if getattr(co, "lora_dir", None): dirs.add(Path(co.lora_dir))
        if getattr(co, "vae_dir", None): dirs.add(Path(co.vae_dir))
        if getattr(co, "embeddings_dir", None): dirs.add(Path(co.embeddings_dir))
    except Exception:
        pass

    cla = os.getenv("COMMANDLINE_ARGS", "")
    if cla:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--ckpt-dir")
        parser.add_argument("--lora-dir")
        parser.add_argument("--vae-dir")
        parser.add_argument("--embeddings-dir")
        args, _ = parser.parse_known_args(shlex.split(cla))
        for val in vars(args).values():
            if val: dirs.add(Path(val))

    return [d for d in dirs if d.exists()]


def _load_cache() -> Dict[str, Dict]:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_cache(data: Dict):
    CACHE_DIR.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2))


def _iter_model_files(root: Path) -> Generator[Path, None, None]:
    for base in _get_model_dirs(root):
        pattern = str(base / "**" / "*")
        for fp in glob.glob(pattern, recursive=True):
            p = Path(fp)
            if p.suffix.lower() in MODEL_EXTS and p.is_file():
                yield p


def list_model_hashes() -> List[str]:
    KNOWN_HASHES.clear()
    from .config import load
    webui_root = Path(os.getenv("SD_WEBUI_ROOT", Path.cwd()))
    cfg = load()
    if cfg.get("webui_root"):
        webui_root = Path(cfg["webui_root"])

    cache = _load_cache()
    updated = False
    result = []

    for p in _iter_model_files(webui_root):
        mtime = int(p.stat().st_mtime)
        key = str(p)
        entry = cache.get(key)

        if entry and entry["mtime"] == mtime:
            h = entry["hash"]
        else:
            log.info("hashing %s", p)
            h = sha256_of_file(p)
            cache[key] = {"mtime": mtime, "hash": h}
            updated = True

        result.append(h)

    orphan_keys = [k for k in cache if not Path(k).exists()]
    for k in orphan_keys:
        del cache[k]
        updated = True

    if updated:
        _save_cache(cache)

    KNOWN_HASHES.update(result)

    return result


def _cmd_opts() -> Dict[str, str | None]:
    opts = {"ckpt_dir": None, "lora_dir": None, "vae_dir": None,
            "embeddings_dir": None}

    try:
        from modules import shared
        for k in opts:
            val = getattr(shared.cmd_opts, k, None)
            if val: opts[k] = val
    except Exception:
        pass

    if not any(opts.values()) and (cla := os.getenv("COMMANDLINE_ARGS")):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--ckpt-dir")
        parser.add_argument("--lora-dir")
        parser.add_argument("--vae-dir")
        parser.add_argument("--embeddings-dir")
        args, _ = parser.parse_known_args(shlex.split(cla))
        for k, v in vars(args).items():
            if v:
                opts[k] = v

    return opts


def get_model_path(target: str) -> Path:
    root = Path(os.getenv("SD_WEBUI_ROOT", Path.cwd()))
    opts = _cmd_opts()

    mapping = {
        "models/Stable-diffusion": opts["ckpt_dir"] or root / "models/Stable-diffusion",
        "models/Lora": opts["lora_dir"] or root / "models/Lora",
        "models/VAE": opts["vae_dir"] or root / "models/VAE",
        "embeddings": opts["embeddings_dir"] or root / "embeddings",
    }

    for prefix, real_dir in mapping.items():
        if target.startswith(prefix):
            tail = target[len(prefix):].lstrip("/\\")
            return Path(real_dir) / tail if tail else Path(real_dir)

    return root / target
