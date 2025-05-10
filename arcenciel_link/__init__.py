from modules import script_callbacks
from .downloader import schedule_inventory_push
from .ui import settings_panel

schedule_inventory_push()

script_callbacks.on_ui_settings(settings_panel)
