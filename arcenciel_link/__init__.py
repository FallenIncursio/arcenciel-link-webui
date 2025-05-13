from modules import script_callbacks
from .downloader import schedule_inventory_push
from .ui import build_tab
import arcenciel_link.settings

schedule_inventory_push()

def _on_ui_tabs():
    return [(build_tab(), "ArcEnCiel Link", "arcenciel_link")]

script_callbacks.on_ui_tabs(_on_ui_tabs)