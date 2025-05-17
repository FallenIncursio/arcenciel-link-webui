from pathlib import Path
from modules import script_callbacks

try:
    from modules import extra_networks
except Exception:        # pragma: no cover
    extra_networks = None        # type: ignore

ICON  = "🔍"
STYLE = (
    "position:absolute;top:4px;right:4px;"
    "background:#fff;border-radius:50%;padding:2px 6px;"
    "box-shadow:0 0 4px #0006"
)

def _inject(html_snippet: str, model_path: str) -> str:
    """hängt den Button an, falls *.html existiert"""
    html_path = Path(model_path).with_suffix(".html")
    if not html_path.exists():
        return html_snippet

    btn = (f'<a class="aec-preview" style="{STYLE}" '
           f'href="file://{html_path}" target="_blank">{ICON}</a>')
    return html_snippet + btn

if extra_networks and hasattr(extra_networks, "ExtraNetworksDataProcessor"):

    class AECPreview(extra_networks.ExtraNetworksDataProcessor):   # type: ignore
        def __init__(self):
            super().__init__("aec_preview")

        def process_thumbnail(self, thumb_html, card):
            # card.name == voller Dateipfad
            return _inject(thumb_html, card.name)

    def _register_new(_demo, _app):
        extra_networks.register_extra_networks_data_processor(AECPreview())  # type: ignore

    script_callbacks.on_app_started(_register_new)
    print("[AEC-LINK] 🔍 extra_preview: using new ExtraNetworksDataProcessor")

elif extra_networks:

    def _patch_old_api():
        pages = (
            getattr(extra_networks, "extra_pages", None)
            or getattr(extra_networks, "pages", None)
        )
        if not pages:
            print("[AEC-LINK] ⚠️  extra_preview: no pages list found – skipping")
            return

        patched = 0
        for _tab, data in pages:
            if not hasattr(data, "create_thumbnail_html"):
                continue

            orig = data.create_thumbnail_html

            def wrapper(item, *a, _orig=orig, **k):
                try:
                    snippet = _orig(item, *a, **k)
                    return _inject(snippet, getattr(item, "filename", ""))
                except Exception:
                    return _orig(item, *a, **k)

            data.create_thumbnail_html = wrapper     # type: ignore
            patched += 1

        print(f"[AEC-LINK] 🔍 extra_preview: patched {patched} old pages")

    script_callbacks.on_app_started(lambda *_: _patch_old_api())

else:
    print("[AEC-LINK] ⚠️  extra_preview: no compatible ExtraNetworks API – button disabled")
