import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

# Resolved in each public extension, with no dependency on the private monorepo.
root = Path(__file__).parents[1]
source = root / "aec_link_drafts.py"
if not source.exists():
    source = root / "arcenciel_link" / "drafts.py"
spec = importlib.util.spec_from_file_location("tested_native_drafts", source)
drafts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drafts)


def client(status=200, data=None):
    response = Mock(status_code=status)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    response.json.return_value = data if data is not None else {"items": []}
    c = SimpleNamespace(
        _open_evt=Mock(),
        SESSION=Mock(),
        BASE_URL="https://example.test/api/link",
        headers=lambda: {"x-link-key": "private-test-key"},
    )
    c._open_evt.is_set.return_value = True
    c.SESSION.post.return_value = response
    return c


def test_native_inbox_fences_runtime_and_never_exposes_credentials():
    c = client()
    assert drafts.post(c, "runtime-own", "inbox", {}) == ({"items": []}, 200)
    args, kw = c.SESSION.post.call_args
    assert args == ("https://example.test/api/link/handoffs/inbox",)
    assert kw["json"] == {"runtimeId": "runtime-own"}
    assert kw["headers"] == {"x-link-key": "private-test-key"}
    assert kw["allow_redirects"] is False


@pytest.mark.parametrize(
    "action,body",
    [("generate", {}), ("inbox", []), ("event", {"runtimeId": "foreign"}), ("inbox", {"url": "https://external.test"})],
)
def test_only_narrow_inbox_and_event_actions_are_accepted(action, body):
    c = client()
    assert drafts.post(c, "runtime-own", action, body)[1] == 400
    c.SESSION.post.assert_not_called()


def test_offline_refuses_delivery_and_scope_failure_explains_opt_in():
    c = client(403)
    assert drafts.post(c, "runtime-own", "inbox", {}) == ({"code": "DRAFT_PERMISSION_REQUIRED"}, 403)
    c._open_evt.is_set.return_value = False
    assert drafts.post(c, "runtime-own", "inbox", {})[1] == 409


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_backend_failures_do_not_echo_private_provider_errors(status):
    c = client(status, {"error": "private provider internals"})
    assert drafts.post(c, "runtime-own", "inbox", {}) == ({"code": "LINK_INBOX_UNAVAILABLE"}, 503)


def test_transport_failure_is_retryable_without_automatic_replay():
    c = client()
    c.SESSION.post.side_effect = RuntimeError("private request details")
    assert drafts.post(
        c,
        "runtime-own",
        "event",
        {"id": "draft", "action": "applied", "editorId": "editor", "receipt": {"fields": {"prompt": "private prompt"}}},
    ) == ({"code": "LINK_INBOX_UNAVAILABLE"}, 503)
    assert c.SESSION.post.call_count == 1
