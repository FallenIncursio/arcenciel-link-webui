import base64, json, queue, threading, time, websocket, re
from .config import load, save
from .utils import list_subfolders, get_http_session
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import atexit
import signal
import logging
from logging.handlers import RotatingFileHandler

_LOG_FILE = Path(__file__).with_name("client-debug.log")

_LOGGER: logging.Logger | None = None

_LINK_KEY_REGEX = re.compile(r"^lk_[A-Za-z0-9_-]{32}$")


def _get_logger() -> logging.Logger | None:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    try:
        handler = RotatingFileHandler(
            _LOG_FILE, maxBytes=262_144, backupCount=1, encoding="utf-8"
        )
        formatter = logging.Formatter("%(asctime)s %(message)s")
        handler.setFormatter(formatter)
        logger = logging.getLogger("arcenciel_link.client")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        _LOGGER = logger
    except Exception:
        _LOGGER = None
    return _LOGGER


def _debug(msg: str):
    logger = _get_logger()
    if logger is not None:
        logger.info(msg)


_cfg = load()
DEV_MODE = bool(_cfg.get("_dev_mode"))
SESSION = get_http_session()


def _normalise_base_url(raw: str, *, allow_insecure: bool) -> str:
    trimmed = (raw or "").strip()
    if not trimmed:
        raise ValueError("base_url cannot be empty")
    if trimmed.startswith(("ws://", "wss://")):
        parsed = urlparse(trimmed.replace("wss://", "https://").replace("ws://", "http://"))
    else:
        parsed = urlparse(trimmed)
    if parsed.scheme not in ("https", "http"):
        raise ValueError("base_url must start with https://")
    if parsed.scheme == "http" and not allow_insecure:
        secure = parsed._replace(scheme="https")
        secure_url = urlunparse(secure)
        print(
            "[AEC-LINK] insecure base_url overridden to HTTPS; enable ARCENCIEL_DEV for http:// usage.",
            file=sys.stderr,
        )
        trimmed = secure_url
    return trimmed.rstrip("/")


BASE_URL = _normalise_base_url(_cfg["base_url"], allow_insecure=DEV_MODE)
LINK_KEY = _cfg.get("link_key", "")
API_KEY = _cfg.get("api_key", "")
TIMEOUT = 15
HEARTBEAT_INTERVAL = 5
_socket_enabled = False
_runner_started = False
_credentials_dirty = False
_reconnect_attempts = 0
_last_connected_at = 0.0
_RECONNECT_BASE_DELAY = 1
_RECONNECT_MAX_DELAY = 10

_runner_lock = threading.Lock()
_PUBLIC_LABEL = "arcenciel.io"


def _encode_protocol_value(value: str) -> str:
    if not value:
        return ""
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _ws_subprotocols() -> list[str] | None:
    if LINK_KEY.strip():
        return [f"aec-link.link-key.{_encode_protocol_value(LINK_KEY)}"]
    if API_KEY.strip():
        return [f"aec-link.api-key.{_encode_protocol_value(API_KEY)}"]
    return None


def _display_target() -> str:
    if DEV_MODE:
        return BASE_URL
    parsed = urlparse(BASE_URL)
    host = parsed.netloc or ""
    if not host or host.endswith("arcenciel.io"):
        return _PUBLIC_LABEL
    return host


def _refresh_ws_url():
    global _WS_URL
    _WS_URL = (
        BASE_URL.replace("https://", "wss://").replace("http://", "ws://").rstrip("/")
        + "/ws"
    )


def update_credentials(
    *,
    base_url: str | None = None,
    link_key: str | None = None,
    api_key: str | None = None,
):
    global \
        BASE_URL, \
        LINK_KEY, \
        API_KEY, \
        _credentials_dirty, \
        _suspend_until, \
        _suspend_notice_logged
    ws_needs_refresh = False
    credentials_changed = False

    if base_url is not None:
        try:
            normalized = _normalise_base_url(base_url, allow_insecure=DEV_MODE)
        except ValueError as exc:
            print(f"[AEC-LINK] base_url rejected: {exc}", file=sys.stderr)
        else:
            if normalized != BASE_URL:
                BASE_URL = normalized
                ws_needs_refresh = True
                _credentials_dirty = True
                credentials_changed = True

    if link_key is not None:
        stripped = link_key.strip()
        if stripped != LINK_KEY:
            LINK_KEY = stripped
            _credentials_dirty = True
            credentials_changed = True

    if api_key is not None:
        stripped = api_key.strip()
        if stripped != API_KEY:
            API_KEY = stripped
            _credentials_dirty = True
            credentials_changed = True

    if ws_needs_refresh:
        _refresh_ws_url()

    if credentials_changed:
        _suspend_until = 0.0
        _suspend_notice_logged = False


_refresh_ws_url()

_sock = None
_job_queue = queue.Queue()
_open_evt = threading.Event()


def _sanitize_link_key(value):
    if value is None:
        return None
    key = str(value).strip()
    if not key:
        return ""
    if not _LINK_KEY_REGEX.fullmatch(key):
        raise ValueError("Invalid link key format")
    return key


def _is_worker_running() -> bool:
    try:
        from .downloader import RUNNING

        return RUNNING.is_set()
    except Exception:
        return False


def _send_ws_payload(payload: dict, *, default_type: str | None = None):
    if not isinstance(payload, dict):
        return
    if default_type and "type" not in payload:
        payload["type"] = default_type
    if not _open_evt.is_set():
        return
    try:
        if _sock is not None:
            _sock.send(json.dumps(payload))
    except Exception as exc:
        _debug(f"failed to send payload: {exc}")


def _send_worker_state(running: bool | None = None):
    if running is None:
        running = _is_worker_running()
    _send_ws_payload({"type": "worker_state", "running": bool(running)})


def _send_control_ack(payload: dict):
    _send_ws_payload(payload, default_type="control_ack")


def _apply_worker_state(enable: bool, *, link_key=None, api_key=None) -> bool:
    cfg = load()
    changed = False

    sanitized_link = _sanitize_link_key(link_key)
    if sanitized_link is not None and sanitized_link != cfg.get("link_key", ""):
        cfg["link_key"] = sanitized_link
        changed = True

    if api_key is not None:
        stripped_api = api_key.strip() if isinstance(api_key, str) else ""
        if stripped_api != cfg.get("api_key", ""):
            cfg["api_key"] = stripped_api
            changed = True

    if changed:
        save(cfg)
        update_credentials(
            base_url=cfg.get("base_url", BASE_URL),
            link_key=cfg.get("link_key", ""),
            api_key=cfg.get("api_key", ""),
        )

    from .downloader import toggle_worker

    if enable:
        set_connection_enabled(True, silent=True)
        toggle_worker(True)
        force_reconnect()
        _send_worker_state(True)
    else:
        toggle_worker(False)
        set_connection_enabled(True, silent=True)
        _send_worker_state(False)

    return _is_worker_running()


def apply_worker_state(
    enable: bool, *, link_key: str | None = None, api_key: str | None = None
) -> bool:
    return _apply_worker_state(enable, link_key=link_key, api_key=api_key)


_connection_state = "idle"
_health_state: str | None = None
_last_error: str | None = None
_suspend_until = 0.0
_suspend_notice_logged = False

WS_CLOSE_CODE_UNAUTHORIZED = 4401
WS_CLOSE_CODE_RATE_LIMITED = 4429
WS_CLOSE_CODE_SERVICE_DISABLED = 1013
_DEFAULT_RATE_LIMIT_WAIT = 900.0


def _set_connection_state(state: str, message: str):
    global _connection_state
    if state != _connection_state:
        print(message, flush=True)
        _connection_state = state
        _debug(message)


def _on_open(ws):
    global \
        _reconnect_attempts, \
        _credentials_dirty, \
        _last_connected_at, \
        _suspend_until, \
        _suspend_notice_logged
    _open_evt.set()
    _reconnect_attempts = 0
    _credentials_dirty = False
    _last_connected_at = time.monotonic()
    _suspend_until = 0.0
    _suspend_notice_logged = False
    _set_connection_state("connected", f"[AEC-LINK] connected to {_display_target()}")
    _send_worker_state()
    ws.send('{"type":"poll"}')


def _parse_retry_after(reason: str | None) -> float:
    if not reason:
        return 0.0
    if reason.startswith("RATE_LIMITED:"):
        try:
            return float(reason.split(":", 1)[1])
        except ValueError:
            return 0.0
    return 0.0


def _on_close(ws, code=None, msg=None):
    global _suspend_until, _suspend_notice_logged
    _open_evt.clear()
    reason = msg
    if isinstance(reason, bytes):
        try:
            reason_text = reason.decode("utf-8", "ignore")
        except Exception:
            reason_text = ""
    elif isinstance(reason, str):
        reason_text = reason
    else:
        reason_text = ""
    _debug(f"close event code={code} msg={reason_text!r}")

    if code is not None:
        detail = f" reason={reason_text}" if reason_text else ""
        print(f"[AEC-LINK] websocket closed (code={code}{detail})")

    if reason_text.startswith("LINK_SCOPE_MISSING"):
        _set_connection_state(
            "blocked",
            "[AEC-LINK] access key missing required permissions; update scopes in dashboard.",
        )
        set_connection_enabled(False, silent=True)
        return

    if code == WS_CLOSE_CODE_UNAUTHORIZED:
        _set_connection_state(
            "blocked",
            "[AEC-LINK] authentication failed; update API key or link key and re-enable the worker.",
        )
        set_connection_enabled(False, silent=True)
        return

    if code == WS_CLOSE_CODE_RATE_LIMITED:
        wait_seconds = _parse_retry_after(reason_text) or _DEFAULT_RATE_LIMIT_WAIT
        _suspend_until = time.monotonic() + wait_seconds
        _suspend_notice_logged = False
        _set_connection_state(
            "blocked", f"[AEC-LINK] rate limited; retrying in {int(wait_seconds)}s."
        )
        return

    if code == WS_CLOSE_CODE_SERVICE_DISABLED:
        # Pause retries briefly; admin toggled the service off.
        wait_seconds = max(30.0, _RECONNECT_BASE_DELAY)
        _suspend_until = time.monotonic() + wait_seconds
        _suspend_notice_logged = False
        _set_connection_state(
            "blocked",
            "[AEC-LINK] link service temporarily disabled by server; retrying shortly.",
        )
        return

    _set_connection_state("disconnected", "[AEC-LINK] disconnected; retrying...")


def _on_error(ws, err):
    global _last_error
    if hasattr(err, "__class__"):
        err_type = err.__class__.__name__
    else:
        err_type = type(err).__name__
    msg = f"{err_type}: {err}"
    if msg != _last_error:
        print("[AEC-LINK] websocket error:", msg, file=sys.stderr)
        _last_error = msg
        _debug(f"[AEC-LINK] websocket error: {msg}")
    _set_connection_state("error", "[AEC-LINK] websocket error")


def _on_msg(ws, raw):
    try:
        msg = json.loads(raw)
    except Exception:
        return
    if msg.get("type") == "job":
        _job_queue.put(msg["data"])
    elif msg.get("type") == "control":
        _handle_control(msg)


def _handle_control(msg: dict):
    command = msg.get("command")
    request_id = msg.get("requestId")
    response = {"command": command}
    if request_id is not None:
        response["requestId"] = request_id
    if command == "set_worker_state":
        raw_enable = msg.get("enable")
        enable = not (raw_enable in (False, "false", 0))
        response["enable"] = enable
        try:
            running = _apply_worker_state(
                enable,
                link_key=msg.get("linkKey"),
                api_key=msg.get("apiKey"),
            )
            response.update({"ok": True, "running": running})
        except Exception as exc:
            response.update({"ok": False, "message": str(exc)})
        _send_control_ack(response)
    elif command == "list_subfolders":
        kind = str(msg.get("kind") or "").lower().strip()
        allowed = {"checkpoint", "lora", "vae", "embedding"}
        if kind not in allowed:
            _send_ws_payload(
                {
                    "type": "folders_result",
                    "requestId": request_id,
                    "ok": False,
                    "error": f"Unsupported kind '{kind}'",
                }
            )
            return
        try:
            folders = list_subfolders(kind)
            _send_ws_payload(
                {
                    "type": "folders_result",
                    "requestId": request_id,
                    "ok": True,
                    "kind": kind,
                    "folders": folders,
                }
            )
        except Exception as exc:
            _send_ws_payload(
                {
                    "type": "folders_result",
                    "requestId": request_id,
                    "ok": False,
                    "error": str(exc),
                    "kind": kind,
                }
            )
    else:
        response.update({"ok": False, "message": "unknown command"})
        _send_control_ack(response)


_alive = threading.Event()


def _on_ping(ws, data):
    _alive.set()
    try:
        sock = getattr(ws, "sock", None)
        if sock and getattr(sock, "connected", False):
            sock.pong(data)
        else:
            ws.send(data, opcode=websocket.ABNF.OPCODE_PONG)
        _debug("sent pong frame")
    except Exception as exc:
        _debug(f"failed to send pong: {exc}")


def _ensure_socket():
    global _sock, _reconnect_attempts
    if not _socket_enabled:
        _debug("ensure_socket skipped: disabled")
        return
    if _sock and _open_evt.is_set():
        return

    def _runner():
        global _sock, _reconnect_attempts, _suspend_until, _suspend_notice_logged
        while True:
            if not _socket_enabled:
                if _sock is not None:
                    try:
                        _sock.close()
                    except Exception:
                        pass
                    _sock = None
                _open_evt.clear()
                _debug("runner sleeping - disabled")
                time.sleep(1)
                continue

            if _suspend_until:
                remaining = _suspend_until - time.monotonic()
                if remaining > 0:
                    if not _suspend_notice_logged:
                        print(
                            f"[AEC-LINK] waiting {int(remaining)}s before reconnect..."
                        )
                        _debug(f"suspend_until active, {remaining:.1f}s remaining")
                        _suspend_notice_logged = True
                    time.sleep(min(remaining, 5))
                    continue
                _suspend_until = 0.0
                _suspend_notice_logged = False

            params: list[str] = ["mode=worker"]
            headers: list[str] = []
            if LINK_KEY:
                headers.append(f"x-link-key: {LINK_KEY}")
            elif API_KEY:
                headers.append(f"x-api-key: {API_KEY}")
            query = "?" + "&".join(params)
            url = _WS_URL + query
            protocols = _ws_subprotocols()
            try:
                _set_connection_state(
                    "connecting", f"[AEC-LINK] connecting to {_display_target()}"
                )
                _debug(f"connecting via {url}")
                _sock = websocket.WebSocketApp(
                    url,
                    header=headers or None,
                    subprotocols=protocols,
                    on_open=_on_open,
                    on_close=_on_close,
                    on_error=_on_error,
                    on_message=_on_msg,
                    on_ping=_on_ping,
                )
                _sock.run_forever(ping_interval=0, ping_timeout=None)
            except Exception as e:
                global _last_error
                _set_connection_state("error", "[AEC-LINK] connection error")
                msg = str(e)
                if msg != _last_error:
                    print(
                        "[AEC-LINK] websocket reconnect failed:", msg, file=sys.stderr
                    )
                    _last_error = msg
                    _debug(f"websocket reconnect failed: {msg}")
            finally:
                _open_evt.clear()
                _sock = None
            delay = min(
                _RECONNECT_MAX_DELAY, _RECONNECT_BASE_DELAY * (2**_reconnect_attempts)
            )
            _reconnect_attempts = min(_reconnect_attempts + 1, 6)
            _debug(f"reconnect back-off: {delay:.1f}s")
            time.sleep(delay)

    global _runner_started
    if not _runner_started:
        with _runner_lock:
            if not _runner_started:
                threading.Thread(target=_runner, daemon=True).start()
                _runner_started = True
                _debug("runner started")
    time.sleep(0.2)


def headers():
    if LINK_KEY:
        return {"x-link-key": LINK_KEY}
    if API_KEY:
        return {"x-api-key": API_KEY}
    return {}


# one-shot health-check so the user sees a console message


def check_backend_health():
    global _health_state
    try:
        r = SESSION.get(f"{BASE_URL}/health", headers=headers(), timeout=TIMEOUT)
        r.raise_for_status()
        if _health_state != "up":
            target = _display_target()
            if DEV_MODE:
                print(f"[AEC-LINK] connected to {BASE_URL}")
            else:
                print(f"[AEC-LINK] connected to {target}")
            _debug(f"connected to {BASE_URL}")
        _health_state = "up"
        return True
    except Exception as e:
        if _health_state != "down":
            if DEV_MODE:
                print(f"[AEC-LINK] backend not reachable: {e}", file=sys.stderr)
            else:
                print("[AEC-LINK] backend not reachable; retrying...", file=sys.stderr)
            _debug(f"backend not reachable: {e}")
        _health_state = "down"
        return False


def queue_next_job():
    _ensure_socket()
    try:
        return _job_queue.get(timeout=HEARTBEAT_INTERVAL + 5)
    except queue.Empty:
        if _open_evt.is_set():
            try:
                _sock.send('{"type":"poll"}')
            except Exception:
                pass
        return None


def report_progress(
    job_id: int, *, progress: int = None, state: str = None, message: str | None = None
):
    if _open_evt.is_set():
        _sock.send(
            json.dumps(
                {
                    "type": "progress",
                    "jobId": job_id,
                    "progress": progress,
                    "state": state,
                    "message": message,
                }
            )
        )
        if state == "DONE":
            _sock.send('{"type":"poll"}')

    else:
        payload = {
            k: v
            for k, v in [("progress", progress), ("state", state), ("message", message)]
            if v is not None
        }
        SESSION.patch(
            f"{BASE_URL}/queue/{job_id}/progress",
            json=payload,
            headers=headers(),
            timeout=TIMEOUT,
        )


def push_inventory(hashes: list[str]):
    if _open_evt.is_set():
        _sock.send(json.dumps({"type": "inventory", "hashes": hashes}))
    else:
        SESSION.post(
            f"{BASE_URL}/inventory",
            json={"hashes": hashes},
            headers=headers(),
            timeout=TIMEOUT,
        )


def set_connection_enabled(enabled: bool, *, silent: bool = False):
    global _socket_enabled, _sock
    _socket_enabled = enabled
    _debug(f"set_connection_enabled({enabled}, silent={silent})")
    if not enabled:
        if _sock is not None:
            try:
                _sock.close()
            except Exception:
                pass
            _sock = None
        _open_evt.clear()
        if not silent:
            _set_connection_state("disconnected", "[AEC-LINK] worker offline")
    else:
        _ensure_socket()


def _shutdown(*_args):
    try:
        set_connection_enabled(False, silent=True)
    except Exception:
        pass


atexit.register(_shutdown)

for _sig_name in ("SIGINT", "SIGTERM", "SIGHUP"):
    _sig = getattr(signal, _sig_name, None)
    if _sig is not None:
        try:
            signal.signal(_sig, _shutdown)
        except (ValueError, OSError):
            pass


def force_reconnect():
    global \
        _reconnect_attempts, \
        _last_connected_at, \
        _suspend_until, \
        _suspend_notice_logged
    _debug("force_reconnect() invoked")
    if _suspend_until and time.monotonic() < _suspend_until:
        remaining = _suspend_until - time.monotonic()
        print(
            f"[AEC-LINK] reconnect paused for {int(remaining)}s due to previous error."
        )
        _debug(f"force_reconnect blocked by suspend_until ({remaining:.1f}s)")
        return
    if not _socket_enabled:
        set_connection_enabled(True, silent=True)
        return
    if not _open_evt.is_set():
        _debug("force_reconnect: socket not open, ensuring connection")
        _ensure_socket()
        return
    if _credentials_dirty or _sock is None:
        _debug("force_reconnect: credentials changed, closing socket")
        _reconnect_attempts = 0
        try:
            if _sock is not None:
                _sock.close()
        except Exception:
            pass
        return
    if time.monotonic() - _last_connected_at < 5:
        _debug("force_reconnect: recent connection, sending poll instead of reconnect")
        try:
            _sock.send('{"type":"poll"}')
        except Exception as exc:
            _debug(f"force_reconnect poll failed: {exc}")
        return
    _debug("force_reconnect: refreshing socket connection")
    _reconnect_attempts = 0
    try:
        _sock.close()
    except Exception:
        pass


def cancel_job(job_id: int) -> None:
    r = SESSION.patch(
        f"{BASE_URL}/queue/{job_id}/cancel", headers=headers(), timeout=TIMEOUT
    )
    r.raise_for_status()
