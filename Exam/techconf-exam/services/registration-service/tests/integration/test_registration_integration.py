"""Own integration tests for the registration-service (REQ-REG-T02).

Unlike the unit tests (which drive the Flask app in-process through the test
client and mock the two dependencies with ``responses``), these tests start the
**real** user-service, event-service *and* registration-service as subprocesses
on free ports, wait for ``GET /health`` on each, then exercise the
registration-service over HTTP with the ``requests`` library. Every subprocess
is always terminated in nested ``try/finally`` blocks, with ``proc.kill()`` as a
fallback if ``terminate()`` does not stop it in time (REQ-REG-T02-AC1).

Because the registration-service depends on **both** user-service (to validate
``user_id``) and event-service (to validate ``event_id`` and to read
``status``/``price``/``capacity``), the live stack starts all three, wiring the
event-service at the live user-service and the registration-service at the live
user- and event-services.

Cases covered:
- positive (REQ-REG-T02-AC2):        create an organizer and an attendee in the
                                     real user-service, create a published event
                                     in the real event-service (the event-service
                                     itself verifies the organizer on the real
                                     user-service), then register the attendee →
                                     201 with ``status="confirmed"`` and
                                     ``amount == event.price``.
- non-existent reference (AC3):      register with a random ``user_id`` unknown
                                     to user-service → 422 ``REFERENCE_NOT_FOUND``;
                                     and, symmetrically, a random ``event_id``
                                     unknown to event-service → 422
                                     ``REFERENCE_NOT_FOUND``.
- dead dependency (AC4):             a registration-service pointed at *closed*
                                     ports for ``USER_SERVICE_URL`` /
                                     ``EVENT_SERVICE_URL`` → POST → 503
                                     ``DEPENDENCY_UNAVAILABLE``.

Run from the service directory::

    py -3.12 -m pytest tests/integration -v
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

# parents[2] resolves .../tests/integration/<file> → .../registration-service
SERVICE_DIR = Path(__file__).resolve().parents[2]
# .../services/registration-service → .../services → sibling service dirs
SERVICES_DIR = SERVICE_DIR.parent
USER_SERVICE_DIR = SERVICES_DIR / "user-service"
EVENT_SERVICE_DIR = SERVICES_DIR / "event-service"

EVENT_PRICE = 149.00
EVENT_CAPACITY = 100


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
    simulate a dead dependency (REQ-REG-T02-AC4).
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
    ``STORAGE_BACKEND`` / ``USER_SERVICE_URL`` / ``EVENT_SERVICE_URL`` are
    controlled per test.
    """
    env = {**os.environ, **env_overrides}
    return subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=str(service_dir),
        env=env,
    )


def _terminate(proc: subprocess.Popen) -> None:
    """Terminate a subprocess, killing it as a fallback (REQ-REG-T02-AC1)."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="module")
def live_stack():
    """Start real user-, event- and registration-services on free ports.

    Starts user-service first (``STORAGE_BACKEND=memory``) and waits for its
    ``/health``; then event-service with ``USER_SERVICE_URL`` pointed at the live
    user-service; then registration-service with both ``USER_SERVICE_URL`` and
    ``EVENT_SERVICE_URL`` pointed at the live user- and event-services. Nested
    ``try/finally`` guarantee every process is terminated (with a ``kill``
    fallback) even if startup or a test fails (REQ-REG-T02-AC1).

    Yields a dict with the three base URLs.
    """
    user_port = find_free_port()
    event_port = find_free_port()
    reg_port = find_free_port()
    user_base = f"http://127.0.0.1:{user_port}"
    event_base = f"http://127.0.0.1:{event_port}"
    reg_base = f"http://127.0.0.1:{reg_port}"

    user_proc = _start_service(
        USER_SERVICE_DIR,
        {"PORT": str(user_port), "STORAGE_BACKEND": "memory"},
    )
    try:
        wait_for_health(user_base)
        event_proc = _start_service(
            EVENT_SERVICE_DIR,
            {
                "PORT": str(event_port),
                "STORAGE_BACKEND": "memory",
                "USER_SERVICE_URL": user_base,
            },
        )
        try:
            wait_for_health(event_base)
            reg_proc = _start_service(
                SERVICE_DIR,
                {
                    "PORT": str(reg_port),
                    "STORAGE_BACKEND": "memory",
                    "USER_SERVICE_URL": user_base,
                    "EVENT_SERVICE_URL": event_base,
                },
            )
            try:
                wait_for_health(reg_base)
                yield {"user": user_base, "event": event_base, "registration": reg_base}
            finally:
                _terminate(reg_proc)
        finally:
            _terminate(event_proc)
    finally:
        _terminate(user_proc)


def _create_user(user_base: str, role: str) -> str:
    """Create a user with the given ``role`` in the real user-service.

    Returns the new user's id. The organizer is used as the event's
    ``organizer_id`` (event-service verifies the role); the attendee is used as
    the registration's ``user_id`` (REQ-REG-B01).
    """
    payload = {
        "first_name": "Test",
        "last_name": role.capitalize(),
        "email": f"{role}.{uuid.uuid4().hex}@example.com",
        "role": role,
    }
    resp = requests.post(f"{user_base}/api/v1/users", json=payload, timeout=5)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_published_event(event_base: str, organizer_id: str) -> dict:
    """Create an event and transition it to ``published`` in the real event-service.

    Follows the event lifecycle: the event is created as ``draft`` (the default)
    referencing a real organizer (verified by the event-service on the real
    user-service), then PATCHed ``draft → published`` so it accepts
    registrations (REQ-REG-B03). Returns the published event object.
    """
    create_payload = {
        "title": "Integration Conf",
        "organizer_id": organizer_id,
        "venue": "Main Hall",
        "city": "Roma",
        "start_date": "2026-10-15",
        "end_date": "2026-10-16",
        "capacity": EVENT_CAPACITY,
        "price": EVENT_PRICE,
    }
    created = requests.post(
        f"{event_base}/api/v1/events", json=create_payload, timeout=5
    )
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    published = requests.patch(
        f"{event_base}/api/v1/events/{event_id}",
        json={"status": "published"},
        timeout=5,
    )
    assert published.status_code == 200, published.text
    event = published.json()
    assert event["status"] == "published", event
    return event


def test_register_attendee_to_published_event_returns_201_confirmed(live_stack):
    """Positive: real attendee + published event → 201 confirmed, amount == price.

    Validates: Requirements REQ-REG-T02 (AC2), REQ-REG-F02, REQ-REG-B06.
    """
    organizer_id = _create_user(live_stack["user"], "organizer")
    attendee_id = _create_user(live_stack["user"], "attendee")
    event = _create_published_event(live_stack["event"], organizer_id)

    resp = requests.post(
        f"{live_stack['registration']}/api/v1/registrations",
        json={"user_id": attendee_id, "event_id": event["id"]},
        timeout=5,
    )

    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["user_id"] == attendee_id
    assert created["event_id"] == event["id"]
    assert created["status"] == "confirmed"
    assert created["amount"] == event["price"] == EVENT_PRICE
    assert resp.headers["Location"] == f"/api/v1/registrations/{created['id']}"


def test_register_with_unknown_user_returns_422_reference_not_found(live_stack):
    """Non-existent user: random user_id → 422 REFERENCE_NOT_FOUND.

    Validates: Requirements REQ-REG-T02 (AC3), REQ-REG-B01.
    """
    organizer_id = _create_user(live_stack["user"], "organizer")
    event = _create_published_event(live_stack["event"], organizer_id)
    unknown_user = str(uuid.uuid4())

    resp = requests.post(
        f"{live_stack['registration']}/api/v1/registrations",
        json={"user_id": unknown_user, "event_id": event["id"]},
        timeout=5,
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_register_with_unknown_event_returns_422_reference_not_found(live_stack):
    """Non-existent event: real user + random event_id → 422 REFERENCE_NOT_FOUND.

    Validates: Requirements REQ-REG-T02 (AC3), REQ-REG-B02.
    """
    attendee_id = _create_user(live_stack["user"], "attendee")
    unknown_event = str(uuid.uuid4())

    resp = requests.post(
        f"{live_stack['registration']}/api/v1/registrations",
        json={"user_id": attendee_id, "event_id": unknown_event},
        timeout=5,
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["error"]["code"] == "REFERENCE_NOT_FOUND"


def test_register_with_dead_dependencies_returns_503(tmp_path):
    """Dead dependency: USER/EVENT_SERVICE_URL at closed ports → 503.

    Starts a standalone registration-service whose ``USER_SERVICE_URL`` and
    ``EVENT_SERVICE_URL`` point at ports that nothing is listening on, so the
    first dependency call (user verification) is refused and maps to
    ``DEPENDENCY_UNAVAILABLE`` (REQ-REG-B09).

    Validates: Requirements REQ-REG-T02 (AC4), REQ-REG-B09.
    """
    reg_port = find_free_port()
    dead_user_port = reserve_closed_port()
    dead_event_port = reserve_closed_port()
    reg_base = f"http://127.0.0.1:{reg_port}"

    reg_proc = _start_service(
        SERVICE_DIR,
        {
            "PORT": str(reg_port),
            "STORAGE_BACKEND": "memory",
            "USER_SERVICE_URL": f"http://127.0.0.1:{dead_user_port}",
            "EVENT_SERVICE_URL": f"http://127.0.0.1:{dead_event_port}",
        },
    )
    try:
        wait_for_health(reg_base)

        resp = requests.post(
            f"{reg_base}/api/v1/registrations",
            json={"user_id": str(uuid.uuid4()), "event_id": str(uuid.uuid4())},
            timeout=5,
        )

        assert resp.status_code == 503, resp.text
        body = resp.json()
        assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    finally:
        _terminate(reg_proc)
