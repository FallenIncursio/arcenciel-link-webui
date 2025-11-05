from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import load as load_config
from .origins import normalize_origin

_DEV_MODE = bool(load_config().get("_dev_mode"))

class PrivateNetworkMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        normalized_origin = normalize_origin(origin, allow_private=_DEV_MODE) if origin else None
        if origin and not normalized_origin:
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
