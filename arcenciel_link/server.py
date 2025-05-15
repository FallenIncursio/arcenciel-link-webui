from fastapi import APIRouter, Response, Body
from fastapi.responses import PlainTextResponse, JSONResponse
from .downloader import toggle_worker

router = APIRouter(prefix="/arcenciel")

@router.get("/ping", response_class=PlainTextResponse) 
def ping() -> PlainTextResponse: 
    return PlainTextResponse("ok", headers={"Access-Control-Allow-Origin": "*"}) 

@router.post("/toggle_link") 
def toggle_link(enable: bool = Body(..., embed=True)): 
    """Start/stop the download worker from the browser UI.""" 
    toggle_worker(enable) 
    return JSONResponse({"ok": True}, 
                        headers={"Access-Control-Allow-Origin": "*"})
