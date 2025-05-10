import gradio as gr
from modules import script_callbacks
from arcenciel_link.ui import on_ui_tabs

def on_ui_settings():
    with gr.Blocks(analytics_enabled=False) as aec_settings:
        tab_root, *_ = on_ui_tabs()[0]
        aec_settings.children.extend(tab_root.children)
    return aec_settings

script_callbacks.on_ui_settings(on_ui_settings)
