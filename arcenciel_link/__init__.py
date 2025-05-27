from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
from modules import script_callbacks

from .client import check_backend_health
from .config import load as _load_cfg
from .downloader import schedule_inventory_push
from .server import router as _api_router
from .pna_middleware import PrivateNetworkMiddleware

schedule_inventory_push()
check_backend_health()

def _mount_api(*args, **kwargs):
    if not args:
        return
    app = args[-1]

    if not any(m.cls is PrivateNetworkMiddleware for m in app.user_middleware): 
        try: 
            app.add_middleware(PrivateNetworkMiddleware) 
            print("[AEC-LINK] ✅ PNA middleware added") 
        except RuntimeError: 
            try: 
                app.user_middleware.insert( 
                    0, 
                    Middleware(PrivateNetworkMiddleware), 
                ) 
                app.middleware_stack = app.build_middleware_stack() 
                print("[AEC-LINK] ✅ PNA middleware injected late") 
            except Exception as e: 
                print("[AEC-LINK] ❌ late PNA injection failed –", e)

    if not any(isinstance(m, CORSMiddleware) for m in app.user_middleware):
        try:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )
            print("[AEC-LINK] ✅ CORS middleware added")
        except RuntimeError:
            print("[AEC-LINK] ⚠️  CORS middleware could not be added "
                  "– FastAPI already running, trying late injection …")
            try:
                app.user_middleware.insert(
                    0,
                    Middleware(
                        CORSMiddleware,
                        allow_origins=["*"],
                        allow_methods=["*"],
                        allow_headers=["*"],
                    ),
                )
                app.middleware_stack = app.build_middleware_stack()
                print("[AEC-LINK] ✅ CORS middleware injected late")
            except Exception as e:
                print("[AEC-LINK] ❌ late CORS injection failed –", e)

    if not any(r.path.startswith("/arcenciel-link/") for r in app.router.routes):
        app.include_router(_api_router)
        print("[AEC-LINK] ✅ API router mounted")


if hasattr(script_callbacks, "on_app_created"):
    script_callbacks.on_app_created(_mount_api)
elif hasattr(script_callbacks, "on_server_loaded"):
    script_callbacks.on_server_loaded(_mount_api)
else:
    script_callbacks.on_app_started(_mount_api)

_cfg = _load_cfg()
if _cfg.get("save_html_preview", False):
    try:
        import arcenciel_link.extra_preview  # noqa: F401
    except Exception as e:
        print("[AEC-LINK] ⚠️  extra_preview not loaded –", e)
else:
    print("[AEC-LINK] ℹ️  HTML preview disabled")
