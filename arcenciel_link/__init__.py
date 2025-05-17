from modules import script_callbacks
from .downloader import schedule_inventory_push
from .client import check_backend_health
from .server import router as _api_router
from fastapi.middleware.cors import CORSMiddleware

schedule_inventory_push()

check_backend_health()

def _mount_api(_, app): 
    if not any(isinstance(m, CORSMiddleware) for m in app.user_middleware): 
        app.add_middleware( 
            CORSMiddleware, 
            allow_origins=["*"], 
            allow_methods=["*"], 
            allow_headers=["*"], 
        ) 
 
    if not any(r.path.startswith("/arcenciel/") for r in app.router.routes): 
        app.include_router(_api_router)

script_callbacks.on_app_started(_mount_api)