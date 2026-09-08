"""Local, metadata-validated SHA cache. Cached values are not a fresh integrity check.

Move reuse requires a local filesystem identity including creation time, unchanged
size/mtime and a matching sample. A sample alone NEVER establishes file identity.
Unsupported/network filesystems use the ordinary path cache and full hashing on moves.
"""

import ctypes
import hashlib
import os
import re
import struct
import sys
import time
from pathlib import Path


def identity(stream, path, stat):
    try:
        if sys.platform == "win32":
            import msvcrt
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
            # UNC, mapped network drives and unknown providers have no move shortcut.
            if str(path).startswith("\\\\") or kernel.GetDriveTypeW(Path(path).anchor) != 3:
                return None
            kernel.GetFileInformationByHandleEx.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            file_id, basic = ctypes.create_string_buffer(24), ctypes.create_string_buffer(40)
            handle = msvcrt.get_osfhandle(stream.fileno())
            if not kernel.GetFileInformationByHandleEx(handle, 18, file_id, 24):
                return None
            if not kernel.GetFileInformationByHandleEx(handle, 0, basic, 40):
                return None
            birth = struct.unpack_from("<q", basic.raw)[0]
            if birth <= 0 or file_id.raw[8:] == bytes(16):
                return None
            return f"windows:{file_id.raw.hex()}:{birth}"
        if sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            fs, data = ctypes.create_string_buffer(256), ctypes.create_string_buffer(256)
            # ext*, XFS and Btrfs. In particular, exclude SMB/NFS/FUSE/overlay.
            if libc.fstatfs(stream.fileno(), fs) or ctypes.c_long.from_buffer(fs).value not in (
                0xEF53,
                0x58465342,
                0x9123683E,
            ):
                return None
            if libc.statx(stream.fileno(), b"", 0x1000, 0xFFF, data):
                return None
            mask = struct.unpack_from("=I", data.raw)[0]
            birth_s, birth_ns = struct.unpack_from("=qI", data.raw, 80)
            if not mask & 0x800 or not birth_s or not stat.st_ino:
                return None
            return f"linux:{stat.st_dev}:{stat.st_ino}:{birth_s}:{birth_ns}"
    except (OSError, AttributeError, ValueError):
        pass
    return None


def change_token(stream):
    if sys.platform != "win32":
        return str(os.fstat(stream.fileno()).st_ctime_ns)
    try:
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        basic = ctypes.create_string_buffer(40)
        if kernel.GetFileInformationByHandleEx(msvcrt.get_osfhandle(stream.fileno()), 0, basic, 40):
            return str(struct.unpack_from("<q", basic.raw, 24)[0])
    except (OSError, AttributeError, ValueError):
        pass
    return None


def fingerprint(stream, size, check):
    digest = hashlib.sha256()
    for offset in sorted({0, max(0, size // 2 - 32768), max(0, size - 65536)}):
        check()
        stream.seek(offset)
        digest.update(stream.read(65536))
    stream.seek(0)
    return digest.hexdigest()


def stamp(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def valid(entry, stat):
    return (
        isinstance(entry, dict)
        and re.fullmatch(r"[a-f0-9]{64}", str(entry.get("hash", ""))) is not None
        and (entry.get("size"), entry.get("mtime_ns")) == (stat.st_size, stat.st_mtime_ns)
    )


def resolve(path, cache, check=lambda: None, force=False):
    """Caller owns the shared cache lock. Inspect and hash through the same open handle."""
    path = Path(path).resolve()
    key = str(path)
    check()
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        file_id = identity(stream, path, before)
        change = change_token(stream)
        entry = cache.get(key)
        source, digest, sample = "hashed", None, None
        if not force and valid(entry, before):
            if entry.get("schema") != 2:
                # Preserve old cache hits, but don't invent a historical file identity.
                digest, source = entry["hash"], "cached"
            if (
                entry.get("identity") == file_id
                and entry.get("ctime_ns") == before.st_ctime_ns
                and entry.get("change") == change
            ):
                digest, sample, source = entry["hash"], entry.get("sample"), "cached"
        if not force and digest is None and file_id:
            candidates = [
                (old, value)
                for old, value in cache.items()
                if old != key
                and valid(value, before)
                and value.get("identity") == file_id
                and value.get("schema") == 2
                and not Path(old).exists()
            ]
            # A unique historical record, never a filename/size or sample-only match.
            if len(candidates) == 1:
                _, previous = candidates[0]
                sample = fingerprint(stream, before.st_size, check)
                if sample == previous.get("sample"):
                    digest, source = previous["hash"], "moved"
        if digest is None:
            import logging

            logging.getLogger("arcenciel_link").info("Hashing model content (%s)", path.name)
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                check()
                hasher.update(chunk)
            digest = hasher.hexdigest()
            sample = fingerprint(stream, before.st_size, check)
        check()
        if (
            change_token(stream) != change
            or stamp(os.fstat(stream.fileno())) != stamp(before)
            or stamp(path.stat()) != stamp(before)
        ):
            raise OSError("Model changed during inventory scan")
        if source == "cached":
            return digest, False, source
        cache[key] = {
            "schema": 2,
            "mtime": int(before.st_mtime),
            "mtime_ns": before.st_mtime_ns,
            "ctime_ns": before.st_ctime_ns,
            "size": before.st_size,
            "hash": digest,
            "identity": file_id,
            "change": change,
            "sample": sample,
            "seen": int(time.time()),
        }
        if source == "moved":
            del cache[candidates[0][0]]
        return digest, True, source
