"""ArcEnCiel Link extension package with explicit runtime startup."""

_started = False


def startup() -> None:
    """Register host callbacks and start background Link services once."""

    global _started
    if _started:
        return

    from modules import script_callbacks

    from .client import apply_worker_state, check_backend_health
    from .config import load
    from .downloader import schedule_inventory_push
    from .server import router

    cfg = load()
    bridge_port = int(cfg.get("bridge_port") or 0)

    def mount_api(*args, **_kwargs):
        if not args:
            return
        app = args[-1]
        if not any(route.path.startswith("/arcenciel-link/") for route in app.router.routes):
            app.include_router(router)
            print("[AEC-LINK] API router mounted")

    if bridge_port > 0:
        from .bridge import start_bridge

        start_bridge(bridge_port)
    else:
        if hasattr(script_callbacks, "on_app_created"):
            script_callbacks.on_app_created(mount_api)
        elif hasattr(script_callbacks, "on_server_loaded"):
            script_callbacks.on_server_loaded(mount_api)
        else:
            script_callbacks.on_app_started(mount_api)

    schedule_inventory_push()
    check_backend_health()

    if cfg.get("link_key"):
        apply_worker_state(bool(cfg.get("enabled", False)), link_key=cfg.get("link_key"))
    if cfg.get("save_html_preview", False):
        try:
            import arcenciel_link.extra_preview  # noqa: F401
        except Exception as exc:
            print("[AEC-LINK] extra_preview not loaded", exc)
    else:
        print("[AEC-LINK] HTML preview disabled")

    _started = True
