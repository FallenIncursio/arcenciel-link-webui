from __future__ import annotations
import json
from textwrap import dedent
import time, random, threading, shutil
from pathlib import Path
import threading
import os, re
import sys
from io import BytesIO

import requests
from .config import load
from .client import queue_next_job, report_progress, push_inventory
from .utils import download_file, sha256_of_file, get_model_path, list_model_hashes

_cfg = load()
MIN_FREE_MB = int(_cfg.get("min_free_mb", 2048))
MAX_RETRIES = int(_cfg.get("max_retries", 5))
BACKOFF_BASE = int(_cfg.get("backoff_base", 2))

SLEEP_AFTER_ERROR = 5
KNOWN_HASHES: set[str] = set()

_backend_ok = False
_user_disabled = False
RUNNING = threading.Event()

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_RND_PREFIX = re.compile(
    r'^(?:\d+_|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_)',
    re.I,
)
def _clean(name: str) -> str:
    return _RND_PREFIX.sub('', name, count=1)

try: 
    from PIL import Image
    _HAS_PIL = True 
except ImportError: 
    _HAS_PIL = False

def _unique_filename(dir_: Path, name: str) -> Path:
    stem, ext = os.path.splitext(name)
    candidate = name
    idx = 1
    while (dir_ / candidate).exists() or (dir_ / (candidate + '.part')).exists():
        candidate = f'{stem}_{idx}{ext}'
        idx += 1
    return dir_ / candidate


def _heartbeat():
    try:
        queue_next_job()
    except:
        pass

HEARTBEAT_INTERVAL = 5

def _enough_free_space(path: Path, min_mb: int = MIN_FREE_MB) -> bool:
    free = shutil.disk_usage(path).free // (1024 * 1024)
    return free >= min_mb


def _print_progress(label: str, pct: int | None = None, last=[-1]):
    if pct is None:
        print(f"[AEC-LINK] ✅ {label} – download finished", file=sys.stderr)
        return
    if pct - last[0] >= 10:
        print(f"[AEC-LINK] …{label} {pct:3d} %", file=sys.stderr, end="\r")
        last[0] = pct


def _already_have(hash_: str | None) -> bool:
    return hash_ in KNOWN_HASHES if hash_ else False


def _download_with_retry(url: str, tmp: Path, progress_cb):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            download_file(url, tmp, progress_cb)
            return
        except Exception:
            tmp.unlink(missing_ok=True)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(BACKOFF_BASE ** attempt + random.uniform(0, 1))


def _save_preview(url: str, model_path: Path) -> str | None:
    if not url:
        return None
    preview_file = model_path.with_suffix(".preview.png") 
    if preview_file.exists(): 
        preview_file = _unique_filename(preview_file.parent, preview_file.stem + ".png")
    
    try: 
        print(f"[AEC-LINK] ↓ preview {url}", flush=True) 
        r = requests.get(url, timeout=20) 
        r.raise_for_status() 
 
        if _HAS_PIL: 
            img = Image.open(BytesIO(r.content)).convert("RGBA") 
            img.save(preview_file, format="PNG") 
        else: 
            with open(preview_file, "wb") as f: 
                f.write(r.content)
        print(f"[AEC-LINK] ✅ preview saved as {preview_file}", flush=True) 
        return preview_file.name 
    except Exception as e: 
        print(f"[AEC-LINK] ⚠️  preview download failed – {e}", flush=True) 
        return None
    

def _write_info_json(meta: dict, sha_local: str, preview_name: str | None,
                     model_path: Path):
    info = {
        "schema": 1,
        "modelId": meta.get("modelId"),
        "versionId": meta.get("versionId"),
        "name": meta.get("modelTitle"),
        "type": meta.get("type"),
        "about": meta.get("aboutThisVersion") or meta.get("about"),
        "description": meta.get("modelDescription") or meta.get("description"),
        "activationTags": meta.get("activationTags"),
        "sha256": sha_local,
        "previewFile":  preview_name,
        "arcencielUrl": f"https://arcenciel.io/models/{meta.get('modelId')}",
    }
    (model_path.parent / (model_path.stem + ".arcenciel.info")).write_text(
        json.dumps(info, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    sd_meta = {
        "description": info["about"],
        "sd version": "unknown",
        "activation text": ", ".join(meta.get("activationTags") or []),
        "preferred weight": 1.0,
        "notes": info["arcencielUrl"],
    }
    sd_file = model_path.parent / (model_path.stem + ".json")
    sd_file.write_text(json.dumps(sd_meta, indent=2, ensure_ascii=False),
                       encoding="utf-8")


def _write_html(meta: dict, preview_name: str | None, model_path: Path):
    html = dedent(f"""
    <!doctype html><html lang="en"><meta charset="utf-8">
    <title>{meta.get('modelTitle','ArcEnCiel Model')}</title>
    <style>
      body{{font-family:system-ui, sans-serif; max-width:720px; margin:2rem auto; line-height:1.5}}
      img{{max-width:100%; border-radius:8px; box-shadow:0 2px 8px #0003}}
      pre{{background:#f8f8f8; padding:0.75rem 1rem; border-radius:6px; overflow:auto}}
      .tag{{display:inline-block; background:#eef; color:#226; padding:2px 6px;
            border-radius:4px; margin:2px; font-size:90%}}
    </style>
    <h1>{meta.get('modelTitle','')}</h1>
    """)
    if preview_name:
        html += f'<img src="{preview_name}" alt="preview">'
    if meta.get("aboutThisVersion"):
        html += f"<h2>About this version</h2><p>{meta['aboutThisVersion']}</p>"
    if (tags := meta.get("activationTags")):
        html += "<h2>Activation Tags</h2>" + \
                "".join(f'<span class="tag">{t}</span>' for t in tags)
    html += f"""
    <hr><p><small>Generated by <b>Arc en Ciel Link</b><br>
    sha256: {meta.get('sha256','')}</small></p></html>
    """
    (model_path.parent / (model_path.stem + ".arcenciel.html")).write_text(
        html,
        encoding="utf-8"
    )


def _worker():
    global _backend_ok

    last_hb = 0 
    while True:
        RUNNING.wait()

        now = time.time()
        if now - last_hb > HEARTBEAT_INTERVAL:
            _heartbeat()
            last_hb = now

        try: 
            job = queue_next_job() 

            if job is None:
                time.sleep(2) 
                continue  

            if not _backend_ok:
                print("[AEC-LINK] 🟢  connected")
            _backend_ok = True 
        except Exception as e: 
            if _backend_ok:
                print("[AEC-LINK] 🔴  disconnected") 
            _backend_ok = False 
            time.sleep(SLEEP_AFTER_ERROR) 
            continue

        try:
            ver = job["version"]
            meta = (ver.get("meta") or {})
            url = ver.get("externalDownloadUrl") or ver.get("filePath")
            if not url:
                raise RuntimeError("No download URL provided by server")

            sha_server = ver.get("sha256")
            dst_path = get_model_path(job["targetPath"]) / Path(url).name

            dst_dir = get_model_path(job["targetPath"]) 
            dst_dir.mkdir(parents=True, exist_ok=True) 
 
            raw_name = Path(url).name          # 6588bcd7_foo.safetensors 
            clean_name  = _clean(raw_name)        # foo.safetensors 
 
            # »foo.safetensors«, »foo_1.safetensors«, »foo_2…« 
            dst_path = _unique_filename(dst_dir, clean_name)

            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # free-space guard
            if not _enough_free_space(dst_path.parent):
                report_progress(job["id"], state="ERROR",
                                message=f"Less than {MIN_FREE_MB} MB free")
                continue

            # already have?
            if sha_server and _already_have(sha_server):
                report_progress(job["id"], state="DONE", progress=100)
                continue

            label = dst_path.name

            # download ↓ tmp
            tmp_path = dst_path.with_suffix(".part")
            report_progress(job["id"], state="DOWNLOADING", progress=0)
            _print_progress(label, 0)

            def _progress_cb(frac: float):
                pct = int(frac * 100)
                report_progress(job["id"], progress=pct)
                _print_progress(label, pct)

            _download_with_retry(url, tmp_path, _progress_cb)

            # hash
            sha_local = sha256_of_file(tmp_path)
            if sha_server and sha_local != sha_server:
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError("SHA-256 mismatch")

            tmp_path.rename(dst_path)

            # side-cars
            preview_name = _save_preview(meta.get("preview"), dst_path)
            _write_info_json(meta, sha_local, preview_name, dst_path)
            if _cfg.get("save_html_preview"):
                _write_html(meta | {"sha256": sha_local}, preview_name, dst_path)

            # done
            hashes = list_model_hashes()
            KNOWN_HASHES.clear(); 
            KNOWN_HASHES.update(hashes) 
            
            push_inventory(hashes)
            report_progress(job["id"], state="DONE", progress=100)
            _print_progress(label)

        except Exception as e: 
            print(f"[AEC-LINK] ❌ worker error – {e}") 
            report_progress(job["id"], state="ERROR", message=str(e)) 
            time.sleep(SLEEP_AFTER_ERROR)


def toggle_worker(enable: bool): 
    global _backend_ok, _user_disabled 
 
    if enable and not RUNNING.is_set():
        _user_disabled = False 
        RUNNING.set() 
        _backend_ok = True
        print("[AEC-LINK] ▶️  worker ENABLED", flush=True) 

    elif not enable and RUNNING.is_set():
        _user_disabled = True 
        RUNNING.clear() 
        _backend_ok = False
        print("[AEC-LINK] ⏹  worker DISABLED by user", flush=True) 


def start_worker():
    threading.Thread(target=_worker, daemon=True).start()


def _inventory_loop():
    while True:
        try:
            hashes = list_model_hashes()
            KNOWN_HASHES.clear()
            KNOWN_HASHES.update(hashes)

            push_inventory(hashes)
        except Exception:
            pass
        time.sleep(3600)


def schedule_inventory_push():
    try:
        hashes = list_model_hashes()
        KNOWN_HASHES.update(hashes)
        push_inventory(hashes)
    except Exception:
        pass

    threading.Thread(target=_inventory_loop, daemon=True).start()


start_worker()

def generate_sidecars_for_existing():
    from .utils import _load_cache 
    cache = _load_cache() 
    model_files = {v["hash"]: Path(k)
                   for k, v in cache.items() 
                   if Path(k).exists()}
    if not model_files:
        return

    try:
        resp = requests.post(
            _cfg["base_url"].rstrip("/") + "/sidecars/meta",
            json={"hashes": list(model_files.keys())},
            headers={"x-api-key": _cfg["api_key"]},
            timeout=30,
        )
        resp.raise_for_status()
        metas = resp.json()
    except Exception as e:
        print("[AEC-LINK] sidecar-meta fetch failed", e)
        return

    for h, path in model_files.items():
        meta = metas.get(h)
        if not meta:
            continue

        dst_path = Path(path)
        if (dst_path.with_suffix(".arcenciel.info")).exists():
            continue

        print(f"[AEC-LINK] ✍  sidecars for {dst_path.name}")
        preview = _save_preview(meta.get("preview"), dst_path)
        _write_info_json(meta, h, preview, dst_path)
        if _cfg.get("save_html_preview"):
            _write_html(meta | {"sha256": h}, preview, dst_path)
