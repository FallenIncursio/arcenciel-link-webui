"""Narrow, same-origin native editor transport. Credentials remain in the worker."""


def post(client, runtime_id, action, body):
    if action not in ("inbox", "event") or not isinstance(body, dict):
        return {"code": "INVALID_NATIVE_ACTION"}, 400
    if not client._open_evt.is_set():
        return {"code": "WORKER_OFFLINE"}, 409
    allowed = (
        {"id", "editorId", "action", "fields", "receipt", "resourceSelection", "localPrompts"}
        if action == "event"
        else {"receiveOnly", "id"}
    )
    if set(body) - allowed:
        return {"code": "INVALID_NATIVE_PAYLOAD"}, 400
    try:
        with client.SESSION.post(
            f"{client.BASE_URL}/handoffs/{action}",
            json={**body, "runtimeId": runtime_id},
            headers=client.headers(),
            timeout=20,
            allow_redirects=False,
        ) as response:
            if response.status_code not in (200, 400, 403, 404, 409):
                return {"code": "LINK_INBOX_UNAVAILABLE"}, 503
            result = response.json()
            if response.status_code == 403:
                result = {"code": "DRAFT_PERMISSION_REQUIRED"}
            return result, response.status_code
    except Exception:
        return {"code": "LINK_INBOX_UNAVAILABLE"}, 503
