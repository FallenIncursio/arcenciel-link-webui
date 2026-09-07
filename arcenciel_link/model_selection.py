"""Keep Forge's selected options and the next generation's loading plan together."""


class ModelSelection:
    def __init__(self):
        self.forge = None
        try:
            from backend.args import dynamic_args
            from modules import processing, sd_models
            from modules_forge import main_entry
        except ImportError:
            return  # A1111 uses its own option callbacks.
        self.forge = main_entry
        self.data = sd_models.model_data
        self.processing = processing
        self.dynamic = dynamic_args
        self.previous = dict(self.data.forge_loading_parameters)
        self.unload = processing.need_global_unload
        self.online_lora = dynamic_args.online_lora

    def refresh(self):
        if self.forge is None:
            return
        from modules import sd_models, shared

        selected = sd_models.get_closet_checkpoint_match(shared.opts.sd_model_checkpoint)
        if selected is None:
            raise ValueError("No native checkpoint selected")
        self.forge.refresh_model_loading_parameters()
        actual = self.data.forge_loading_parameters
        if actual.get("checkpoint_info") != selected or sorted(actual.get("additional_modules", [])) != sorted(
            shared.opts.forge_additional_modules
        ):
            raise ValueError("Native model loading plan did not accept the selection")

    def restore(self):
        if self.forge is not None:
            self.data.forge_loading_parameters = self.previous
            self.processing.need_global_unload = self.unload
            self.dynamic.online_lora = self.online_lora
