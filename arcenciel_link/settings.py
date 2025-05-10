from modules import shared, script_callbacks
from .config import load, save

_cfg = load()

def _after_save():
    _cfg.update(
        base_url = shared.opts.data.get("arcenciel_link_base_url", _cfg["base_url"]).rstrip("/"),
        api_key  = shared.opts.data.get("arcenciel_link_api_key",  _cfg["api_key"]).strip(),
    )
    save(_cfg)

    import arcenciel_link.client as client
    client.BASE_URL = _cfg["base_url"]
    client.API_KEY  = _cfg["api_key"]

def on_ui_settings():
    section = ("arcenciel_link", "ArcEnCiel")
    shared.opts.add_option(
        "arcenciel_link_base_url",
        shared.OptionInfo(_cfg["base_url"], "Backend URL",  section=section)
    )
    shared.opts.add_option(
        "arcenciel_link_api_key",
        shared.OptionInfo(_cfg["api_key"],  "API Key",      section=section, password=True)
    )

script_callbacks.on_ui_settings(on_ui_settings)
script_callbacks.on_reload(_after_save)
