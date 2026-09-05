"""Small native status panel. Device actions remain authenticated in the Link Hub."""

from . import client, device_tools
from .downloader import RUNNING
from .version import VERSION


def summary():
    tool = device_tools.status()
    state = "Connected" if client._open_evt.is_set() else "Disconnected"
    text = f"Link {VERSION} · {state} · Downloads {'enabled' if RUNNING.is_set() else 'paused'}"
    if tool:
        text += (
            f"\n{tool['action']}: {tool['state']} · {tool['processed']}/{tool['total']} · {tool['warnings']} warnings"
        )
    return text


def register():
    import gradio as gr
    from modules import script_callbacks

    def ui_tabs():
        with gr.Blocks() as panel:
            gr.Markdown("## Arc en Ciel Link\n[Open device tools and your library](https://arcenciel.io/link)")
            status = gr.Textbox(value=summary(), label="This host", interactive=False)
            refresh = gr.Button("Refresh Link status")
            refresh.click(fn=summary, inputs=[], outputs=[status])
        return [(panel, "Arc en Ciel Link", "arcenciel_link_tools")]

    script_callbacks.on_ui_tabs(ui_tabs)
