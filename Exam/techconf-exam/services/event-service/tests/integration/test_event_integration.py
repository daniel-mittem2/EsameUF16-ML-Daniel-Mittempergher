"""Own integration tests for the event-service (REQ-EVT-T02).

Unlike the unit tests (which drive the Flask app in-process through the test
client and mock user-service with ``responses``), these tests start the
**real** event-service *and* its **real** user-service dependency as
subprocesses on free ports, wait for ``GET /health`` on both, then exercise the
event-service over HTTP with the ``requests`` library. Every subprocess is
always terminated in a ``try/finally`` block, with ``proc.kill()`` as a
fallback if ``terminate()`` does not stop it in time (REQ-EVT-T02-AC1).

Cases covered:
- positive (REQ-EVT-T02-AC2):        create an organizer in the real user-service,
                                     then POST an event referencing it → 201 with
                                     ``status="draft"``.
- non-existent reference (AC3):      POST an event with a random ``organizer_id``
                                     unknown to user-service → 422
                                     ``REFERENCE_NOT_FOUND``.
- dead dependency (AC4):             an event-service pointed at a *closed* port for
                                     ``USER_SERVICE_URL`` → POST → 503
                                     ``DEPENDENCY_UNAVAILABLE``.

Run from the service directory::

    py -3.12 -m pytest tests/integration -v
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

# parents[2] resolves .../tests/integration/<file> → .../event-service
SERVICE_DIR = Path(__file__).resolve().parents[2]
# .../services/event-service → .../services → user-service sibling
USER_SERVICE_DIR = SERVICE_DIR.parent / "user-service"


def find_free_port() -> int:
    """Return a currently-free TCP port.

    Binds a socket to port 0 (the OS assigns a free port), reads the assigned
    port, then releases the socket so a service can bind it moments later.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def reserve_closed_port() -> int:
    """Return a port number that is (very likely) not accepting connections.

    Binds and immediately releases a socket to obtain a free port. Because
    nothing rebinds it, a connection attempt to that port is refused — used to
    simulate a dead user-service dependency (REQ-EVT-T02-AC4).
    """
    return find_free_port()


def wait_for_health(base_url: str, timeout: float = 15.0) -> None:
    """Poll ``GET <base_url>/health`` until it returns 200 or the timeout hits.

    Raises ``RuntimeError`` if the service does not become healthy within
    ``timeout`` seconds.
    """
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"{base_url}/health", timeout=1)
            if resp.status_code == 200:
                return
        except requests.RequestException as exc:  # not up yet
            last_err = exc
        time.sleep(0.1)
    raise RuntimeError(
        f"service at {base_url} did not become healthy within {timeout}s "
        f"(last error: {last_err!r})"
    )


def _start_service(service_dir: Path, env_overrides: dict) -> subprocess.Popen:
    """Launch ``py -3.12 -m app`` from ``service_dir`` with env overrides.

    Uses a copy of the current environment overridden with the given values so
    the child inherits the interpreter path etc. while ``PORT`` /
    ``STORAGE_BACKEND`` / ``USER_SERVICE_URL`` are controlled per test.
    """
    env = {**os.environ, **env_overrides}
    return subprocess.Popen(
        ["py", "-3.12", "-m", "app"],
        cwd=str(service_dir),
        env=env,
    )


def _terminate(proc: subprocess.Popen) -> None:
    """Terminate a subprocess, killing it as a fallback (REQ-EVT-T02-AC1)."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _event_payload(organizer_id: str) -> dict:
    """Return a minimal valid EventCreate body for the given organizer."""
    return {
        "title": "Integration Conf",
        "organizer_id": organizer_id,
        "venue": "Main Hall",
        "city": "Roma",
        "start_date": "2026-10-15",
        "end_date": "2026-10-16",
        "capacity": 100,
        "price": 0,
    }


@pytest.fixture(scope="module")
def live_stack():
    """Start real user-service and event-service subprocesses on free ports.

    Starts user-service first (``STORAGE_BACKEND=memory``), waits for its
    ``/health``, then starts event-service with ``USER_SERVICE_URL`` pointed at
    the live user-service and waits for *its* ``/health``. Nested ``try/finally``
    guarantee both processes are terminated (with a ``kill`` fallback) even if
    startup or a test fails (REQ-EVT-T02-AC1).

    Yields a dict with the two base URLs.
    """
    user_port = find_free_port()
    event_port = find_free_port()
    user_base = f"http://127.0.0.1:{user_port}"
    event_base = f"http://127.0.0.1:{event_port}"

    user_proc = _start_service(
        USER_SERVICE_DIR,
        {"PORT": str(user_port), "STORAGE_BACKEND": "memory"},
    )
    try:
        wait_for_health(user_base)
        event_proc = _start_service(
            SERVICE_DIR,
            {
                "PORT": str(event_port),
                "STORAGE_BACKEND": "memory",
                "USER_SERVICE_URL": user_base,
            },
        )
        try:
            wait_for_health(event_base)
            yield {"user": user_base, "event": event_base}
        finally:
            _terminate(event_proc)
    finally:
        _terminate(user_proc)


def _create_organizer(user_base: str) -> str:
    """Create a user with role ``organizer`` in the real user-service.

    Returns the new user's id. Used by the positive path so the event's
    ``organizer_id`` references a real organizer (REQ-EVT-B01/B02).
    """
    payload = {
        "first_name": "Olga",
        "last_name": "Organizer",
        "email": f"organizer.{uuid.uuid4().hex}@example.com",
        "role": "organizer",
    }
    resp = requests.post(f"{user_base}/api/v1/users", json=payload, timeout=5)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_create_event_with_real_organizer_returns_201_draft(live_stack):
    """Positive: real organizer → POST event → 201 status=draft (REQ-EVT-T02-AC2)."""
    organizer_id = _create_organizer(live_stack["user"])

    resp = requests.post(
        f"{live_stack['event']}/api/v1/events",
        json=_event_payload(organizer_id),
        timeout=5,
    )

    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["organizer_id"] == organizer_id
    assert created["status"] == "draft"
    assert created["title"] == "Integration Conf"
    assert resp.headers["Location"] == f"/api/v1/events/{created['id']}"


def test_create_event_with_unknown_organizer_returns_422_reference_not_found(
    live_stack,
):
    """Non-existent reference: unknown organizer_id → 422 REFERENCE_NOT_FOUND (REQ-EVT-T02-AC3)."""
    unknown_organizer = str(uuid.uuid4())

    resp = requests.post(
        f"{live_stack['event']}/api/v1/events",
        json=_event_payload(unknown_organizer),
        timeout=5,
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_create_event_with_dead_dependency_returns_503(tmp_path):
    """Dead dependency: USER_SERVICE_URL at a closed port → 503 (REQ-EVT-T02-AC4).

    Starts a standalone event-service whose ``USER_SERVICE_URL`` points at a
    port that nothing is listening on, so the organizer-verification call is
    refused and maps to ``DEPENDENCY_UNAVAILABLE`` (REQ-EVT-B05).
    """
    event_port = find_free_port()
    dead_port = reserve_closed_port()
    event_base = f"http://127.0.0.1:{event_port}"

    event_proc = _start_service(
        SERVICE_DIR,
        {
            "PORT": str(event_port),
            "STORAGE_BACKEND": "memory",
            "USER_SERVICE_URL": f"http://127.0.0.1:{dead_port}",
        },
    )
    try:
        wait_for_health(event_base)

        resp = requests.post(
            f"{event_base}/api/v1/events",
            json=_event_payload(str(uuid.uuid4())),
            timeout=5,
        )

        assert resp.status_code == 503, resp.text
        body = resp.json()
        assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    finally:
        _terminate(event_proc)
