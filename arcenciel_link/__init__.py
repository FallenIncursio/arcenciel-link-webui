from modules import script_callbacks
from .downloader import schedule_inventory_push
from .ui import build_tab
from .settings import on_ui_settings

schedule_inventory_push()

script_callbacks.on_ui_settings(on_ui_settings)

def _on_ui_tabs():
    return [(build_tab(), "ArcEnCiel Link", "arcenciel_link")]

script_callbacks.on_ui_tabs(_on_ui_tabs)