import requests
from .config import load

_cfg = load()
BASE_URL = _cfg["base_url"].rstrip("/")
API_KEY = _cfg["api_key"]
TIMEOUT = 15

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
    r = requests.get(f"{BASE_URL}/queue", headers=headers(), timeout=TIMEOUT)
    if r.status_code == 204:
        return None
    r.raise_for_status()
    return r.json()


def report_progress(job_id: int, *, progress:int=None, state:str=None, message:str|None=None):
    payload = {k:v for k,v in [("progress",progress),("state",state),("message",message)] if v is not None}
    requests.patch(f"{BASE_URL}/queue/{job_id}/progress", json=payload, headers=headers(), timeout=TIMEOUT)


def push_inventory(hashes:list[str]):
    requests.post(f"{BASE_URL}/inventory", json={"hashes":hashes}, headers=headers(), timeout=TIMEOUT)


def cancel_job(job_id: int) -> None:
    r = requests.patch(f"{BASE_URL}/queue/{job_id}/cancel",
                   headers=headers(), timeout=TIMEOUT)
    r.raise_for_status()