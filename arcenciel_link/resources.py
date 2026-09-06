"""Native model names with cached full-file identities; never load or generate weights."""

import re
import sys
import threading
from pathlib import Path

from . import device_tools, utils

_dirty = threading.Event()
_dirty.set()
KINDS = {"checkpoint": "checkpoints", "lora": "loras", "vae": "vae", "embedding": "embeddings"}


def request_refresh():
    _dirty.set()


def native_catalog(refresh):
    import networks
    from modules import sd_models, sd_vae, shared

    checkpoint_roots = [Path(sd_models.model_path)]
    opts = shared.cmd_opts
    checkpoint_roots.extend(Path(p) for p in (getattr(opts, "ckpt_dirs", None) or []))
    if getattr(opts, "ckpt_dir", None):
        checkpoint_roots.append(Path(opts.ckpt_dir))
    if refresh:
        # Older A1111 list_models can download a default checkpoint when none exists.
        # Register known local checkpoints directly, without that download fallback.
        for root in checkpoint_roots:
            if root.is_dir():
                for path in root.rglob("*"):
                    if (
                        path.is_file()
                        and path.suffix.lower() in {".safetensors", ".ckpt", ".gguf"}
                        and ".vae." not in path.name
                    ):
                        if not any(
                            Path(v.filename).resolve() == path.resolve() for v in sd_models.checkpoints_list.values()
                        ):
                            sd_models.CheckpointInfo(str(path)).register()
        networks.list_available_networks()
        sd_vae.refresh_vae_list()
    catalog = [
        (
            "checkpoint",
            value.short_title if shared.opts.sd_checkpoint_dropdown_use_short else value.name,
            Path(value.filename),
        )
        for value in list(sd_models.checkpoints_list.values())
        if Path(value.filename).is_file()
    ]
    catalog += [
        ("lora", name, Path(value.filename))
        for name, value in list(networks.available_networks.items())
        if Path(value.filename).is_file()
    ]
    catalog += [("vae", name, Path(path)) for name, path in list(sd_vae.vae_dict.items()) if Path(path).is_file()]
    # Forge Neo removed sd_hijack. Read an already initialized native registry;
    # importing the extra-network module here could load embedding weights as a side effect.
    hijack = sys.modules.get("modules.sd_hijack")
    embeddings = getattr(getattr(hijack, "model_hijack", None), "embedding_db", None)
    if embeddings is None:
        embeddings = getattr(sys.modules.get("modules.ui_extra_networks_textual_inversion"), "embedding_db", None)
    catalog += [
        ("embedding", name, Path(value.filename))
        for name, value in getattr(embeddings, "word_embeddings", {}).items()
        if value.filename and Path(value.filename).is_file()
    ]
    roots = [("checkpoint", root) for root in checkpoint_roots]
    for kind in ("lora", "vae", "embedding"):
        roots.append(
            (kind, utils.get_model_path({"lora": "models/Lora", "vae": "models/VAE", "embedding": "embeddings"}[kind]))
        )
    return [(kind, name.replace("\\", "/"), path) for kind, name, path in catalog], roots


def collect():
    refresh = _dirty.is_set()
    _dirty.clear()
    catalog, roots = native_catalog(refresh)
    with utils._CACHE_LOCK:
        cache = dict(utils._ensure_cache())
    maintenance = dict(device_tools._hash_cache)
    known = {(kind, str(path.resolve())): name for kind, name, path in catalog}
    files = {(kind, path.resolve()) for kind, _, path in catalog}
    for kind, root in roots:
        resolved_root = root.resolve()
        for raw in {*cache, *maintenance}:
            path = Path(raw).resolve()
            if path.is_relative_to(resolved_root) and path.is_file():
                files.add((kind, path))
    # A newly installed file may not yet have a hash cache entry or a native loader.
    # Discover its presence without loading weights or hashing the library on every report.
    discovery_complete = True
    for kind, root in roots:
        try:
            if root.is_dir():
                files.update(
                    (kind, path.resolve())
                    for path in root.rglob("*")
                    if path.is_file() and path.suffix.lower() in utils.MODEL_EXTS
                )
        except OSError:
            discovery_complete = False
    entries, complete, used = [], discovery_complete, set()
    for kind, path in sorted(files, key=lambda item: ((item[0], str(item[1])) not in known, item[0], str(item[1]))):
        try:
            stat = path.stat()
            entry = cache.get(str(path), {})
            cached = maintenance.get(str(path))
            digest = (
                entry.get("hash")
                if (entry.get("mtime_ns"), entry.get("size")) == (stat.st_mtime_ns, stat.st_size)
                else None
            )
            if not digest and cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
                digest = cached[2]
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                complete = False
                continue
            name = known.get((kind, str(path)))
            selectable = name is not None
            if name is None:
                root = next(
                    root.resolve()
                    for item_kind, root in roots
                    if item_kind == kind and path.is_relative_to(root.resolve())
                )
                name = path.relative_to(root).as_posix()
            if (kind, name) in used:
                complete = False
                continue
            used.add((kind, name))
            entries.append(
                {
                    "kind": kind,
                    "sha256": digest,
                    "selectionName": name,
                    "sizeBytes": stat.st_size,
                    "selectable": selectable,
                }
            )
        except (OSError, StopIteration):
            complete = False
    if len(entries) > 10000:
        entries, complete = entries[:10000], False
    return {"schemaVersion": 1, "complete": complete, "entries": entries}


def has_verified_file(digest):
    """A historical hash alone cannot prove a file still exists on this device."""
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        return False
    with utils._CACHE_LOCK:
        cache = dict(utils._ensure_cache())
    candidates = [
        (path, entry.get("mtime_ns"), entry.get("size"))
        for path, entry in cache.items()
        if isinstance(entry, dict) and entry.get("hash") == digest
    ]
    candidates.extend(
        (path, entry[0], entry[1]) for path, entry in dict(device_tools._hash_cache).items() if entry[2] == digest
    )
    for path, mtime_ns, size in candidates:
        try:
            stat = Path(path).stat()
            if Path(path).is_file() and (stat.st_mtime_ns, stat.st_size) == (mtime_ns, size):
                return True
        except OSError:
            pass
    return False


def report(client, runtime_id):
    inventory = collect()
    with client.SESSION.post(
        f"{client.BASE_URL}/resources/inventory",
        json={"runtimeId": runtime_id, "inventory": inventory},
        headers=client.headers(),
        timeout=20,
        allow_redirects=False,
    ) as response:
        response.raise_for_status()
