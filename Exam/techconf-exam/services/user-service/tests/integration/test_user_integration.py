"""Own integration tests for the user-service (REQ-USR-T01-AC6).

Unlike the unit tests (which drive the Flask app in-process through the test
client), these tests start the service as a **real subprocess** on a free port,
wait for ``GET /health`` to return 200, then exercise it over HTTP with the
``requests`` library. The subprocess is always terminated in a ``finally``
block, with ``proc.kill()`` as a fallback if ``terminate()`` does not stop the
process in time (REQ-USR-T01-AC6).

Cases covered:
- positive:            POST a user then GET it by id → 200 with matching data
- non-existent ref:    GET /api/v1/users/<fake-uuid> → 404
- duplicate email:     two POSTs with the same email → second returns 409

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

# parents[2] resolves .../tests/integration/<file> → .../user-service
SERVICE_DIR = Path(__file__).resolve().parents[2]


def find_free_port() -> int:
    """Return a currently-free TCP port.

    Binds a socket to port 0 (the OS assigns a free port), reads the assigned
    port, then releases the socket so the service can bind it moments later.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base_url: str, timeout: float = 10.0) -> None:
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
        f"service did not become healthy within {timeout}s "
        f"(last error: {last_err!r})"
    )


@pytest.fixture(scope="module")
def live_server():
    """Start the user-service as a real subprocess on a free port.

    Launches ``py -3.12 -m app`` with ``PORT`` injected and
    ``STORAGE_BACKEND=memory`` (a copy of the current environment, overridden),
    running from the service directory. Waits for ``/health`` to return 200
    (10s timeout), then yields the base URL. The ``try/finally`` guarantees the
    process is terminated even if startup or a test fails; ``proc.kill()`` is
    the fallback if ``terminate()`` does not stop it within 5s (REQ-USR-T01-AC6).
    """
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PORT": str(port), "STORAGE_BACKEND": "memory"}

    proc = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=str(SERVICE_DIR),
        env=env,
    )
    try:
        wait_for_health(base_url, timeout=10)
        yield base_url
    finally:
        # Cleanup guaranteed even if wait_for_health raises or a test throws.
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_create_then_get_by_id_returns_created_user(live_server):
    """Positive path: POST a user then GET it by id → 200 (REQ-USR-F02, REQ-USR-F05)."""
    payload = {
        "first_name": "Alice",
        "last_name": "Rossi",
        "email": "alice.integration@example.com",
        "role": "speaker",
    }

    create_resp = requests.post(
        f"{live_server}/api/v1/users", json=payload, timeout=5
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]
    assert created["first_name"] == "Alice"
    assert created["last_name"] == "Rossi"
    assert created["email"] == "alice.integration@example.com"
    assert created["role"] == "speaker"

    get_resp = requests.get(
        f"{live_server}/api/v1/users/{user_id}", timeout=5
    )
    assert get_resp.status_code == 200, get_resp.text
    fetched = get_resp.json()
    assert fetched["id"] == user_id
    assert fetched["email"] == "alice.integration@example.com"
    assert fetched["first_name"] == "Alice"
    assert fetched["last_name"] == "Rossi"


def test_get_nonexistent_user_returns_404(live_server):
    """Non-existent reference: GET /api/v1/users/<fake-uuid> → 404 (REQ-USR-F05)."""
    fake_id = str(uuid.uuid4())
    resp = requests.get(
        f"{live_server}/api/v1/users/{fake_id}", timeout=5
    )
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"


def test_duplicate_email_returns_409(live_server):
    """Duplicate email: two POSTs with the same email → second 409 (REQ-USR-B01)."""
    payload = {
        "first_name": "Bob",
        "last_name": "Bianchi",
        "email": "duplicate.integration@example.com",
    }

    first = requests.post(
        f"{live_server}/api/v1/users", json=payload, timeout=5
    )
    assert first.status_code == 201, first.text

    second = requests.post(
        f"{live_server}/api/v1/users", json=payload, timeout=5
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"]["code"] == "EMAIL_ALREADY_EXISTS"
