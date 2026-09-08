"""Keep the receiving editor inside txt2img; no additional navigation tab."""

import json

import gradio as gr
from modules import scripts, shared

from arcenciel_link import native_fields


class Script(scripts.Script):
    def title(self):
        return "Arc en Ciel Link receiver"

    def show(self, is_img2img):
        return scripts.AlwaysVisible if not is_img2img else False

    def ui(self, is_img2img):
        if is_img2img:
            return []
        if native_fields.ui_id is None:
            native_fields.reset()
        with gr.Accordion("Arc en Ciel Link", open=False, elem_id="aec-link-inbox-accordion"):
            gr.HTML('<div id="aec-link-draft-inbox"></div>')
        native_fields.bridge["root"] = gr.context.Context.root_block
        native_fields.bridge["incoming"] = gr.Textbox(
            elem_id="aec-link-native-input", elem_classes=["aec-link-internal"]
        )
        native_fields.bridge["button"] = gr.Button(
            "Apply Link settings", elem_id="aec-link-native-apply", elem_classes=["aec-link-internal"]
        )
        native_fields.bridge["receipt"] = gr.Textbox(
            value=json.dumps({"uiId": native_fields.ui_id, "protocol": 2}),
            elem_id="aec-link-native-receipt",
            elem_classes=["aec-link-internal"],
        )
        gr.HTML("<style>.aec-link-internal {display:none !important}</style>")
        for key, setting in [("betaAlpha", "beta_dist_alpha"), ("betaBeta", "beta_dist_beta")]:
            if setting in shared.opts.data_labels:
                info = shared.opts.data_labels[setting]
                args = info.component_args if isinstance(info.component_args, dict) else {}
                component = gr.Number(
                    value=getattr(shared.opts, setting),
                    elem_id=native_fields.IDS[key],
                    minimum=args.get("minimum", 0.01),
                    maximum=args.get("maximum", 2.0),
                    elem_classes=["aec-link-internal"],
                )
                native_fields.registered[component.elem_id] = component
        return []
