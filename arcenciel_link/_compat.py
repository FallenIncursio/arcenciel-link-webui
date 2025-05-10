import gradio as gr
from pathlib import Path
from contextlib import contextmanager

GR_MAJOR = int(gr.__version__.split(".")[0])
IS_GR4   = GR_MAJOR >= 4

@contextmanager
def blocks_with_assets(js: Path, css: Path):
    if IS_GR4:
        with gr.Blocks(js=str(js), css=str(css)) as blk:
            yield blk
    else:
        with gr.Blocks() as blk:
            if js.exists():
                gr.HTML(f"<script>{js.read_text()}</script>")
            if css.exists():
                gr.HTML(f"<style>{css.read_text()}</style>")
            yield blk

def register_load_event(container, fn, outputs, every=5):
    if IS_GR4:
        gr.on(triggers="load", fn=fn, inputs=None, outputs=outputs,
              every=every)
    else:
        container.load(fn, None, outputs, every=every)
