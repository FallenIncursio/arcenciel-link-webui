import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from arcenciel_link import job_attempt, utils


@pytest.fixture(autouse=True)
def reset_attempt():
    job_attempt.ACTIVE = None
    yield
    if job_attempt.ACTIVE:
        job_attempt.ACTIVE.finish()
    job_attempt.ACTIVE = None


class Reply:
    def __init__(self, status=200, state="DOWNLOADING"):
        self.status_code = status
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def json(self):
        return {"state": self.state}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("test failure")


def attempt(session=None, token="attempt-123"):
    return job_attempt.JobAttempt(
        {"id": 1, "attemptId": token},
        session or SimpleNamespace(post=Mock(return_value=Reply())),
        "http://localhost/api/link",
        lambda: {},
    )


def test_ack_precedes_work_and_duplicate_active_attempt_is_rejected():
    active = attempt().start()
    assert active.session.post.call_args.kwargs["json"]["action"] == "ack"
    with pytest.raises(job_attempt.AttemptStopped):
        attempt().start()
    active.finish()
    assert job_attempt.ACTIVE is None


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
def test_rejected_ack_never_starts_file_work(status):
    active = attempt(SimpleNamespace(post=Mock(return_value=Reply(status))))
    with pytest.raises(job_attempt.AttemptStopped):
        active.start()
    assert job_attempt.ACTIVE is None


def test_cancel_is_scoped_to_exact_attempt_and_runtime():
    active = attempt().start()
    for values in [
        (2, active.token, job_attempt.RUNTIME_ID),
        (1, "old-attempt", job_attempt.RUNTIME_ID),
        (1, active.token, "old-runtime"),
    ]:
        assert not job_attempt.cancel_attempt(*values)
        assert not active.stopped.is_set()
    assert job_attempt.cancel_attempt(1, active.token, job_attempt.RUNTIME_ID)
    with pytest.raises(job_attempt.AttemptStopped):
        active.check()
    active.finish()
    assert active.session.post.call_args.kwargs["json"]["action"] == "cancel_ack"


def test_deadline_fails_closed_before_server_can_reassign(monkeypatch):
    active = attempt().start()
    active.last_confirmed = time.monotonic() - 41
    with pytest.raises(job_attempt.AttemptStopped):
        active.check()
    active.finish()


def test_hash_and_retry_wait_stop_immediately(tmp_path):
    active = attempt().start()
    target = tmp_path / "partial"
    target.write_bytes(b"a" * 100)
    active.stop()
    with pytest.raises(job_attempt.AttemptStopped):
        utils.sha256_of_file(target)
    started = time.monotonic()
    with pytest.raises(job_attempt.AttemptStopped):
        active.wait(30)
    assert time.monotonic() - started < 1
    active.finish()


def test_legacy_job_can_be_cancelled_without_a_lease_endpoint():
    active = attempt(token=None).start()
    assert not active.session.post.called
    assert job_attempt.cancel_attempt(1)
    active.finish()
    assert not job_attempt.cancel_attempt(1)


@pytest.mark.parametrize("content_length", [True, False])
def test_cancel_interrupts_real_http_stream_before_end(tmp_path, content_length):
    started = threading.Event()
    stopped = threading.Event()
    requests_seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests_seen.append(data["action"])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def do_GET(self):
            self.send_response(200)
            if content_length:
                self.send_header("Content-Length", str(20 * 1024 * 1024))
            self.end_headers()
            started.set()
            try:
                while not stopped.is_set():
                    self.wfile.write(b"x" * 4096)
                    self.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session = requests.Session()
    active = job_attempt.JobAttempt(
        {"id": 1, "attemptId": "attempt-123"}, session, f"http://127.0.0.1:{server.server_port}", lambda: {}
    ).start()
    errors = []
    target = tmp_path / "model.part"

    def download():
        try:
            utils.download_file(f"http://127.0.0.1:{server.server_port}/file", target, lambda fraction: None)
        except Exception as error:
            errors.append(error)

    download_thread = threading.Thread(target=download, daemon=True)
    download_thread.start()
    try:
        assert started.wait(3)
        time.sleep(0.1)
        assert job_attempt.cancel_attempt(1, "attempt-123", job_attempt.RUNTIME_ID)
        download_thread.join(2)
        assert not download_thread.is_alive(), "Cancellation must interrupt a blocked stream read"
        assert errors
        assert target.stat().st_size < 20 * 1024 * 1024
        active.finish()
        assert requests_seen == ["ack", "cancel_ack"]
    finally:
        stopped.set()
        active.finish()
        server.shutdown()
        server.server_close()
        session.close()
