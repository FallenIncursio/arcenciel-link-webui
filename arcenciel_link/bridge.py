from __future__ import annotations

import atexit
import threading

import uvicorn
from fastapi import FastAPI

from .server import router


class BridgeServer:
    """Serve only ArcEnCiel routes outside Forge's global CORS middleware."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    def start(self) -> None:
        if self._thread is not None or self._port <= 0:
            return

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.include_router(router)
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
            access_log=False,
            server_header=False,
            lifespan="off",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run, name="arcenciel-link-bridge", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            assert self._server is not None
            self._server.run()
        except BaseException as exc:  # Uvicorn raises SystemExit when the port is occupied.
            print(f"[AEC-LINK] bridge failed on 127.0.0.1:{self._port}: {exc}", flush=True)
            return
        print(f"[AEC-LINK] bridge stopped on 127.0.0.1:{self._port}", flush=True)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)


_bridge: BridgeServer | None = None


def start_bridge(port: int) -> BridgeServer:
    global _bridge
    if _bridge is None:
        _bridge = BridgeServer(port)
        _bridge.start()
        print(f"[AEC-LINK] browser bridge starting on http://127.0.0.1:{port}", flush=True)
    return _bridge


def stop_bridge() -> None:
    global _bridge
    if _bridge is not None:
        _bridge.stop()
        _bridge = None


atexit.register(stop_bridge)
