from __future__ import annotations
import hashlib, json, os, glob, time
from pathlib import Path
from typing import Iterable, List, Dict, Generator

import requests
import tqdm
import logging

log = logging.getLogger("arcenciel_link")
log.setLevel(logging.INFO)

def download_file(url: str, dst: Path, progress_cb):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dst, "wb") as f, tqdm.tqdm(
            total=total, unit="B", unit_scale=True, desc=dst.name
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
                progress_cb(bar.n / total if total else 0)


def sha256_of_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

CACHE_DIR  = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "hashes.json"

MODEL_DIRS = [
    "models",
    "embeddings",
]

MODEL_EXTS = {".safetensors", ".ckpt", ".pt"}


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
    for sub in MODEL_DIRS:
        base = root / sub
        if not base.exists():
            continue
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

    return result


def get_model_path(target: str) -> Path:
    webui_root = Path(os.getenv("SD_WEBUI_ROOT", Path.cwd()))
    return webui_root / target
