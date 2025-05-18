from fastapi import APIRouter, Body
from fastapi.responses import PlainTextResponse, JSONResponse
from .downloader import toggle_worker, generate_sidecars_for_existing
from .utils import list_subfolders 
import threading

router = APIRouter(prefix="/arcenciel-link")

@router.get("/ping", response_class=PlainTextResponse) 
def ping() -> PlainTextResponse: 
    return PlainTextResponse("ok", headers={"Access-Control-Allow-Origin": "*"}) 

@router.post("/toggle_link") 
def toggle_link(enable: bool = Body(..., embed=True)): 
    """Start/stop the download worker from the browser UI.""" 
    toggle_worker(enable) 
    return JSONResponse({"ok": True}, 
                        headers={"Access-Control-Allow-Origin": "*"})

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