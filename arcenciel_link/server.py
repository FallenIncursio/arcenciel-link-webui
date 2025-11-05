import ipaddress
import threading
import time

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from .downloader import generate_sidecars_for_existing, RUNNING
from .utils import list_subfolders

from . import client
from .config import load as load_config
from .origins import normalize_origin, is_private_host

_CFG = load_config()
_DEV_MODE = bool(_CFG.get("_dev_mode"))


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class ToggleLinkPayload(BaseModel):
    enable: bool
    linkKey: str | None = None
    apiKey: str | None = None


router = APIRouter(prefix="/arcenciel-link")

def _normalize_origin(origin: str) -> str | None:
    return normalize_origin(origin, allow_private=_DEV_MODE)


def _require_allowed_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        normalized = _normalize_origin(origin)
        if normalized:
            return normalized
        raise HTTPException(status_code=403, detail="Origin not allowed")
    client_host = request.client.host if request.client else None
    if client_host:
        if _is_loopback_host(client_host):
            return None
        if _DEV_MODE and is_private_host(client_host):
            return None
    raise HTTPException(status_code=403, detail="Origin not allowed")


def _build_cors_headers(
    origin: str | None, extra: dict[str, str] | None = None
) -> dict[str, str]:
    headers: dict[str, str] = {"Vary": "Origin"}
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    if extra:
        headers.update(extra)
    return headers


@router.get("/ping", response_class=PlainTextResponse)
def ping() -> PlainTextResponse:
    return PlainTextResponse("ok", headers={"Access-Control-Allow-Origin": "*"})


@router.options("/toggle_link")
def toggle_link_options(request: Request) -> PlainTextResponse:
    origin = _require_allowed_origin(request)
    headers = _build_cors_headers(
        origin,
        {
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Max-Age": "600",
        },
    )
    return PlainTextResponse("", status_code=204, headers=headers)


@router.post("/toggle_link")
def toggle_link(payload: ToggleLinkPayload, request: Request):
    """Start/stop the download worker from the browser UI."""
    origin = _require_allowed_origin(request)
    try:
        client.apply_worker_state(
            payload.enable,
            link_key=payload.linkKey,
            api_key=payload.apiKey,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to toggle worker") from exc

    if payload.enable:
        t0 = time.perf_counter()
        while not RUNNING.is_set() and time.perf_counter() - t0 < 3:
            time.sleep(0.05)

    return JSONResponse(
        {"ok": True, "workerOnline": RUNNING.is_set()},
        headers=_build_cors_headers(origin),
    )


@router.get("/folders/{kind}")
def list_folders(kind: str, request: Request):
    origin = _require_allowed_origin(request)
    try:
        folders = list_subfolders(kind)
        return JSONResponse({"folders": folders}, headers=_build_cors_headers(origin))
    except KeyError:
        return JSONResponse(
            {"error": "unknown kind"},
            status_code=400,
            headers=_build_cors_headers(origin),
        )


@router.post("/generate_sidecars")
def generate_sidecars(request: Request):
    origin = _require_allowed_origin(request)
    threading.Thread(target=generate_sidecars_for_existing, daemon=True).start()
    return JSONResponse({"ok": True}, headers=_build_cors_headers(origin))
