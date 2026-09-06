"""Native components shared by the capability report and txt2img paste callback."""

IDS = {
    "prompt": "txt2img_prompt",
    "negativePrompt": "txt2img_neg_prompt",
    "seed": "txt2img_seed",
    "steps": "txt2img_steps",
    "cfg": "txt2img_cfg_scale",
    "width": "txt2img_width",
    "height": "txt2img_height",
    "sampler": "txt2img_sampling",
    "scheduler": "txt2img_scheduler",
    "shift": "txt2img_distilled_cfg_scale",
    "checkpoint": "setting_sd_model_checkpoint",
    "modules": "setting_sd_modules",
    "vae": "setting_sd_vae",
    "betaAlpha": "aec-link-beta-alpha",
    "betaBeta": "aec-link-beta-beta",
    "clipSkip": "setting_CLIP_stop_at_last_layers",
}
registered = {}
components = {}
bridge = {}


def record(component, **_kwargs):
    if getattr(component, "elem_id", None) in IDS.values():
        registered[component.elem_id] = component
