from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class PrivateNetworkMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            resp = Response(status_code=204)
        else:
            resp = await call_next(request)

        origin = request.headers.get("origin")
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            resp.headers.setdefault("Access-Control-Allow-Origin", "*")

        resp.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        resp.headers.setdefault("Access-Control-Allow-Headers", "*")
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
        resp.headers.setdefault("Access-Control-Max-Age", "600")

        return resp
