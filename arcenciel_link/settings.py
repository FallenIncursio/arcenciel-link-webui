from modules import script_callbacks, shared

from .config import _detect_dev_mode, load, save

_cfg = load()


def _apply_opts():
    _cfg.update(
        base_url=shared.opts.data.get("arcenciel_link_base_url", _cfg["base_url"]).rstrip("/"),
        link_key=shared.opts.data.get("arcenciel_link_access_key", _cfg.get("link_key", "")).strip(),
        enabled=bool(shared.opts.data.get("arcenciel_link_enabled", _cfg.get("enabled", False))),
    )
    save(_cfg)

    import arcenciel_link.client as client

    client.update_credentials(
        base_url=_cfg["base_url"],
        link_key=_cfg.get("link_key", ""),
    )
    client.apply_worker_state(_cfg["enabled"], link_key=_cfg.get("link_key", ""))


def on_ui_settings():
    section = ("arcenciel_link", "ArcEnCiel")
    if _detect_dev_mode():
        shared.opts.add_option(
            "arcenciel_link_base_url",
            shared.OptionInfo(
                _cfg["base_url"],
                "Backend URL (dev only)",
                section=section,
                onchange=_apply_opts,
            ),
        )
    shared.opts.add_option(
        "arcenciel_link_access_key",
        shared.OptionInfo(
            _cfg.get("link_key", ""),
            "Link Key (lk_...)",
            section=section,
            onchange=_apply_opts,
        ),
    )
    shared.opts.add_option(
        "arcenciel_link_enabled",
        shared.OptionInfo(
            bool(_cfg.get("enabled", False)),
            "Enable ArcEnCiel Link worker",
            section=section,
            onchange=_apply_opts,
        ),
    )


script_callbacks.on_ui_settings(on_ui_settings)
