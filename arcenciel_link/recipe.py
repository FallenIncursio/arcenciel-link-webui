"""Native recipe capabilities. Draft actions never trigger a generation."""

import threading
import time

from . import drafts, native_fields, resources


def build_profile():
    from modules import sd_samplers

    try:
        from modules import sd_schedulers

        schedulers = [s.label for s in sd_schedulers.schedulers]
    except ImportError:
        schedulers = []
    result = {
        "schemaVersion": 1,
        "draftSelection": 1,
        "host": "forge",
        "fields": list(native_fields.components),
        "samplers": [s.name for s in sd_samplers.all_samplers],
        "schedulers": schedulers,
        "maxSeed": "9007199254740991",
        "templates": ["basic_checkpoint_v1"],
    }
    if "modules" in result["fields"]:
        from modules_forge import main_entry

        result["options"] = {"modules": sorted(main_entry.module_list)[:256]}
    return result


_report_started = False
_report_lock = threading.Lock()
REPORT_STATE = "Waiting for the host"


def start_reporting(client, runtime_id):
    """Read native options without generating, hashing libraries or changing the editor."""
    global _report_started
    with _report_lock:
        if _report_started:
            return
        _report_started = True

    def run():
        global REPORT_STATE
        while True:
            if client._open_evt.is_set():
                try:
                    profile = build_profile()
                    with client.SESSION.post(
                        f"{client.BASE_URL}/recipe/profile",
                        json={"runtimeId": runtime_id, "profile": profile},
                        headers=client.headers(),
                        timeout=15,
                    ) as response:
                        response.raise_for_status()
                    REPORT_STATE = (
                        "Host fields available; editor checked in browser"
                        if profile["fields"]
                        else "Waiting for editor setup"
                    )
                    try:
                        resources.report(client, runtime_id)
                    except Exception:
                        REPORT_STATE = "Recipe ready; resource inventory needs a refresh"
                    drafts.post(client, runtime_id, "inbox", {"receiveOnly": True})
                except Exception:
                    # Never include requests, prompts, keys or provider errors in logs.
                    REPORT_STATE = "Recipe check unavailable; refresh after reconnecting"
            else:
                REPORT_STATE = "Waiting for connection"
            time.sleep(30)

    threading.Thread(target=run, name="aec-link-recipes", daemon=True).start()
