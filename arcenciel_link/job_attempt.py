"""Fenced job execution shared with the ComfyUI extension. No persisted credentials."""

import socket
import threading
import time
import uuid

RUNTIME_ID = str(uuid.uuid4())
ACTIVE = None


class AttemptStopped(Exception):
    pass


class JobAttempt:
    def __init__(self, job, session, base_url, headers):
        self.job = job
        self.session = session
        self.url = f"{base_url}/queue/{job['id']}/lease"
        self.headers = headers
        self.token = job.get("attemptId")
        self.stopped = threading.Event()
        self.finished = threading.Event()
        self.response = None
        self.cancelled = False
        self.cancel_acknowledged = False
        self.last_confirmed = time.monotonic()
        self.bytes_downloaded = 0

    def fields(self):
        return {"attemptId": self.token, "runtimeId": RUNTIME_ID, "bytesDownloaded": self.bytes_downloaded}

    def renew(self, action="heartbeat"):
        if not self.token:
            return
        with self.session.post(
            self.url,
            headers=self.headers(),
            json={**self.fields(), "action": action},
            timeout=5 if action == "cancel_ack" else 10,
        ) as reply:
            if reply.status_code in (400, 401, 403, 404, 409):
                try:
                    if reply.json().get("state") == "CANCELLED":
                        self.cancelled = True
                except ValueError:
                    pass
                self.stop()
                raise AttemptStopped("Download attempt ended; reconnect or retry from ArcEnCiel")
            reply.raise_for_status()
        self.last_confirmed = time.monotonic()

    def start(self):
        global ACTIVE
        if ACTIVE is not None:
            raise AttemptStopped("Worker already has an active attempt")
        ACTIVE = self
        try:
            self.renew("ack")
        except Exception:
            ACTIVE = None
            raise
        if self.token:
            threading.Thread(target=self._heartbeat, daemon=True).start()
        return self

    def _heartbeat(self):
        while not self.finished.wait(10) and not self.stopped.is_set():
            try:
                self.renew()
            except AttemptStopped:
                return
            except Exception:
                if time.monotonic() - self.last_confirmed >= 40:
                    self.stop()
                    return

    def check(self):
        if self.token and time.monotonic() - self.last_confirmed >= 40:
            self.stop()
        if self.stopped.is_set():
            raise AttemptStopped("Download cancelled or lease lost")

    def stop(self):
        self.stopped.set()
        # Interrupt requests' blocking read, including servers sending no further chunks.
        response = self.response
        if response is not None:
            try:
                response.raw._fp.fp.raw._sock.shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError):
                pass

    def wait(self, seconds):
        self.stopped.wait(seconds)
        self.check()

    def finish(self):
        global ACTIVE
        self.finished.set()
        if self.cancelled and self.token and not self.cancel_acknowledged:
            for retry in range(3):
                try:
                    self.renew("cancel_ack")
                    self.cancel_acknowledged = True
                    break
                except AttemptStopped:
                    # Revoked credentials or a stale token cannot acknowledge another attempt.
                    break
                except Exception:
                    if retry < 2:
                        time.sleep(retry + 1)
        if ACTIVE is self:
            ACTIVE = None


def cancel_attempt(job_id, attempt_id=None, runtime_id=None):
    active = ACTIVE
    if active is None or active.job["id"] != job_id:
        return False
    if active.token and (active.token != attempt_id or runtime_id != RUNTIME_ID):
        return False
    active.cancelled = True
    active.stop()
    return True
