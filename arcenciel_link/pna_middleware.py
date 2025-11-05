from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import load as load_config
from .origins import normalize_origin, is_same_origin

_DEV_MODE = bool(load_config().get("_dev_mode"))

class PrivateNetworkMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        normalized_origin = None
        if origin:
            if is_same_origin(
                origin,
                request.url.scheme,
                request.url.hostname,
                request.url.port,
            ):
                normalized_origin = f"{request.url.scheme}://{request.url.netloc}"
            else:
                normalized_origin = normalize_origin(origin, allow_private=_DEV_MODE)
            if not normalized_origin:
                return Response(status_code=403)

        if request.method == "OPTIONS":
            resp = Response(status_code=204)
        else:
            resp = await call_next(request)

        if normalized_origin:
            resp.headers["Access-Control-Allow-Origin"] = normalized_origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Credentials"] = "true"

        resp.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        resp.headers.setdefault("Access-Control-Allow-Headers", "*")
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
        resp.headers.setdefault("Access-Control-Max-Age", "600")

        return resp
