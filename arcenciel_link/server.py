from fastapi import APIRouter, Body
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from .downloader import toggle_worker, generate_sidecars_for_existing, RUNNING
from .utils import list_subfolders 
import threading
import time

router = APIRouter(prefix="/arcenciel-link")

@router.get("/ping", response_class=PlainTextResponse) 
def ping() -> PlainTextResponse: 
    return PlainTextResponse("ok", headers={"Access-Control-Allow-Origin": "*"}) 

@router.post("/toggle_link") 
def toggle_link(enable: bool = Body(..., embed=True)): 
    """Start/stop the download worker from the browser UI.""" 
    toggle_worker(enable) 
    if enable:
        t0 = time.perf_counter() 
        while not RUNNING.is_set() and time.perf_counter() - t0 < 3: 
            time.sleep(0.05) 
 
    return JSONResponse( 
        {"ok": True, "workerOnline": RUNNING.is_set()}, 
        headers={"Access-Control-Allow-Origin": "*"}, 
    )

@router.get("/folders/{kind}") 
def list_folders(kind: str): 
    try: 
        folders = list_subfolders(kind) 
        return JSONResponse({"folders": folders}, 
                            headers={"Access-Control-Allow-Origin": "*"}) 
    except KeyError: 
        return JSONResponse({"error": "unknown kind"}, status_code=400, 
                            headers={"Access-Control-Allow-Origin": "*"})
    
@router.post("/generate_sidecars")
def generate_sidecars():
    threading.Thread( 
        target=generate_sidecars_for_existing, 
        daemon=True 
    ).start() 
    return JSONResponse({"ok": True}, 
                        headers={"Access-Control-Allow-Origin": "*"})