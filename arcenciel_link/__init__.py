from modules import script_callbacks
from .downloader import schedule_inventory_push
from .client import check_backend_health
from .server import router as _api_router
from fastapi.middleware.cors import CORSMiddleware
from .config import load as _load_cfg

schedule_inventory_push()
check_backend_health()

def _mount_api(*args):
    app = args[-1]

    if not any(isinstance(m, CORSMiddleware) for m in app.user_middleware):
        try:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )
        except RuntimeError as e:
            if "Cannot add middleware" in str(e):
                print("[AEC-LINK] ℹ️  CORS-Middleware skipped  (App already started)")
            else:
                raise

    if not any(r.path.startswith("/arcenciel/") for r in app.router.routes):
        app.include_router(_api_router)

_cfg = _load_cfg()
if _cfg.get("save_html_preview", False):
    try:
        import arcenciel_link.extra_preview  # noqa: F401
    except Exception as e:
        print("[AEC-LINK] ⚠️  extra_preview not loaded –", e)
else:
    print("[AEC-LINK] ℹ️  HTML preview disabled")

if hasattr(script_callbacks, "on_server_loaded"):
    script_callbacks.on_server_loaded(_mount_api)
else:
    script_callbacks.on_app_started(_mount_api)
