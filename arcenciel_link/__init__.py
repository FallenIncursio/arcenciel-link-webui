from modules import script_callbacks
from .ui import on_ui_tabs, add_navbar_icon
from .downloader import schedule_inventory_push; schedule_inventory_push()

script_callbacks.on_ui_tabs(on_ui_tabs)
script_callbacks.on_after_component(add_navbar_icon)
