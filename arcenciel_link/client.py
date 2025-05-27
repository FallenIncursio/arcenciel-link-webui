import json, queue, threading, time, requests, websocket
from .config import load
import sys

_cfg = load()
BASE_URL = _cfg["base_url"].rstrip("/")
API_KEY = _cfg["api_key"]
TIMEOUT = 15
HEARTBEAT_INTERVAL = 5

_WS_URL = ( 
     BASE_URL.replace("https://", "wss://") 
             .replace("http://", "ws://") 
             .rstrip("/") + "/ws" 
 )
 
_sock = None
_job_queue = queue.Queue()
_open_evt  = threading.Event() 

def _on_open(ws): 
    _open_evt.set() 
    ws.send('{"type":"poll"}')
 
def _on_close(ws, *_): 
    _open_evt.clear() 
 
def _on_error(ws, err): 
    print("[AEC-LINK] WS error:", err, file=sys.stderr) 
 
def _on_msg(ws, raw): 
    try: 
        msg = json.loads(raw) 
    except Exception: 
        return 
    if msg.get("type") == "job": 
        _job_queue.put(msg["data"]) 

_alive = threading.Event() 
def _on_ping(ws, data): 
    _alive.set()


def _ensure_socket(): 
    global _sock 
    if _sock and _open_evt.is_set(): 
        return 
 
    def _runner(): 
        global _sock
        while True: 
            url = _WS_URL + (f"?key={API_KEY}" if API_KEY else "") 
            try: 
                _sock = websocket.WebSocketApp( 
                    url, 
                    header=[f"x-api-key: {API_KEY}"] if API_KEY else None,
                    on_open=_on_open, 
                    on_close=_on_close, 
                    on_error=_on_error, 
                    on_message=_on_msg,
                    on_ping=_on_ping,
                ) 
                _sock.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as e: 
                print("[AEC-LINK] WS reconnect failed –", e) 
            time.sleep(5)   # reconnect back-off 
 
    threading.Thread(target=_runner, daemon=True).start() 
    time.sleep(0.2) 


def headers():
    return {"x-api-key": API_KEY} if API_KEY else {}


# one-shot health-check so the user sees a console message 
def check_backend_health(): 
    try: 
        r = requests.get(f"{BASE_URL}/health", headers=headers(), timeout=TIMEOUT) 
        r.raise_for_status() 
        print(f"[AEC-LINK] ✅ connected to {BASE_URL}") 
        return True 
    except Exception as e: 
        print(f"[AEC-LINK] ❌ backend not reachable – {e}") 
        return False


def queue_next_job():
    _ensure_socket() 
    try: 
        return _job_queue.get(timeout=HEARTBEAT_INTERVAL + 5) 
    except queue.Empty: 
        if _open_evt.is_set(): 
            try: _sock.send('{"type":"poll"}') 
            except Exception: pass 
        return None


def report_progress(job_id: int, *, progress:int=None, state:str=None, message:str|None=None):
    if _open_evt.is_set(): 
        _sock.send(json.dumps({ 
            "type": "progress", 
            "jobId": job_id, 
            "progress": progress, 
            "state": state, 
            "message": message, 
        })) 
        if state == "DONE": 
            _sock.send('{"type":"poll"}')

    else: 
        payload = {k:v for k,v in 
                   [("progress",progress),("state",state),("message",message)] 
                   if v is not None} 
        requests.patch(f"{BASE_URL}/queue/{job_id}/progress", 
                       json=payload, headers=headers(), timeout=TIMEOUT)


def push_inventory(hashes:list[str]):
    if _open_evt.is_set(): 
        _sock.send(json.dumps({"type":"inventory", "hashes": hashes})) 
    else: 
        requests.post(f"{BASE_URL}/inventory", 
                      json={"hashes":hashes}, headers=headers(), timeout=TIMEOUT)


def cancel_job(job_id: int) -> None:
    r = requests.patch(f"{BASE_URL}/queue/{job_id}/cancel",
                   headers=headers(), timeout=TIMEOUT)
    r.raise_for_status()