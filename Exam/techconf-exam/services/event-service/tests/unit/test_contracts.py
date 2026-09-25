"""Contract-conformance unit tests for the event-service (T-13, REQ-EVT-T01-AC4).

For EACH of the seven HTTP operations declared in ``event-service.yaml`` there
is at least one test that drives the Flask test client and asserts the response
against the OpenAPI contract via ``assert_matches_contract("event", method,
path, response)`` from ``contracts/validator.py``:

    1. health       — GET  /health
    2. createEvent  — POST /api/v1/events
    3. listEvents   — GET  /api/v1/events
    4. getEvent     — GET  /api/v1/events/<id>
    5. replaceEvent — PUT  /api/v1/events/<id>
    6. updateEvent  — PATCH /api/v1/events/<id>
    7. deleteEvent  — DELETE /api/v1/events/<id>

The validator lives in the (non-modifiable) template under
``Exam/techconf-exam/contracts/``; we add that directory to ``sys.path`` the
same way the integration ``conftest.py`` does, resolving the repo root relative
to this file.

Because event-service verifies the organizer against user-service on
create/replace/update, those outbound calls are mocked at the library level
with ``responses`` so no real network call leaves the test process
(REQ-EVT-T01-AC2). Per design.md §11/§12 the validator is used ONLY for
responses the contract actually declares; infrastructure-only codes (400/405)
are asserted manually in ``test_routes.py``/``test_app_factory.py``, never
through ``assert_matches_contract``.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import responses

from app import create_app
from app.backends.memory import MemoryEventRepository
from app.http_client import UserServiceClient

# Make contracts/validator.py importable, mirroring tests/integration/conftest.py.
# This file: .../services/event-service/tests/unit/test_contracts.py
#   parents[0]=unit [1]=tests [2]=event-service [3]=services [4]=techconf-exam (root)
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "contracts"))

from validator import assert_matches_contract  # noqa: E402

EVENTS = "/api/v1/events"
BASE_URL = "http://user-service.test"


def flask_to_contract_dict(resp) -> dict:
    """Convert a Flask test response into the dict accepted by the validator.

    Design.md §11: the validator's dict branch reads ``response["json"]``
    directly, so we build the dict rather than adapting the Flask response
    object (whose ``.json`` is a property, not a callable). ``get_json`` with
    ``silent=True`` returns ``None`` for a body-less 204, which the validator
    treats as "no body expected".
    """
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "json": resp.get_json(silent=True),
    }


def _user_url(user_id: str) -> str:
    return f"{BASE_URL}/api/v1/users/{user_id}"


def _user_payload(user_id: str, role: str = "organizer") -> dict:
    return {
        "id": user_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "company": None,
        "role": role,
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


def _mock_organizer(organizer_id: str) -> None:
    """Register a ``responses`` mock for a valid organizer lookup (200 + role)."""
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"),
        status=200,
    )


def _valid_payload(organizer_id: str, **overrides) -> dict:
    """A valid EventCreate body; keyword args override individual fields."""
    payload = {
        "title": "PyConf 2026",
        "organizer_id": organizer_id,
        "venue": "Main Hall",
        "city": "Rome",
        "start_date": "2026-10-15",
        "end_date": "2026-10-17",
        "capacity": 100,
        "price": 49.9,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def client():
    """A Flask test client backed by a fresh in-memory repo + mocked user client."""
    app = create_app(
        repo=MemoryEventRepository(),
        user_client=UserServiceClient(BASE_URL, timeout=2.0),
    )
    return app.test_client()


def _create_event(client, **overrides) -> dict:
    """Create an event through the API and return the parsed Event body.

    Registers the organizer mock automatically; must run inside a
    ``@responses.activate`` test.
    """
    organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id)
    resp = client.post(EVENTS, json=_valid_payload(organizer_id, **overrides))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --------------------------------------------------------------------------- #
# 1/7 — GET /health (REQ-EVT-F01)
# --------------------------------------------------------------------------- #
def test_health_matches_contract_REQ_EVT_F01(client):
    """GET /health 200 conforms to the Health schema (REQ-EVT-T01-AC4)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert_matches_contract("event", "GET", "/health", flask_to_contract_dict(resp))


# --------------------------------------------------------------------------- #
# 2/7 — POST /api/v1/events (REQ-EVT-F02)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_matches_contract_REQ_EVT_F02(client):
    """POST /api/v1/events 201 conforms to the Event schema (REQ-EVT-T01-AC4)."""
    organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id)
    resp = client.post(EVENTS, json=_valid_payload(organizer_id))
    assert resp.status_code == 201
    assert_matches_contract("event", "POST", EVENTS, flask_to_contract_dict(resp))


# --------------------------------------------------------------------------- #
# 3/7 — GET /api/v1/events (REQ-EVT-F06)
# --------------------------------------------------------------------------- #
@responses.activate
def test_list_events_matches_contract_REQ_EVT_F06(client):
    """GET /api/v1/events 200 conforms to the EventPage schema (REQ-EVT-T01-AC4)."""
    _create_event(client)
    resp = client.get(EVENTS)
    assert resp.status_code == 200
    assert_matches_contract("event", "GET", EVENTS, flask_to_contract_dict(resp))


# --------------------------------------------------------------------------- #
# 4/7 — GET /api/v1/events/<id> (REQ-EVT-F05)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_event_matches_contract_REQ_EVT_F05(client):
    """GET /api/v1/events/<id> 200 conforms to the Event schema (REQ-EVT-T01-AC4)."""
    created = _create_event(client)
    resp = client.get(f"{EVENTS}/{created['id']}")
    assert resp.status_code == 200
    assert_matches_contract(
        "event", "GET", f"{EVENTS}/{created['id']}", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 5/7 — PUT /api/v1/events/<id> (REQ-EVT-F07)
# --------------------------------------------------------------------------- #
@responses.activate
def test_replace_event_matches_contract_REQ_EVT_F07(client):
    """PUT /api/v1/events/<id> 200 conforms to the Event schema (REQ-EVT-T01-AC4)."""
    created = _create_event(client)
    organizer_id = created["organizer_id"]
    _mock_organizer(organizer_id)
    resp = client.put(
        f"{EVENTS}/{created['id']}",
        json=_valid_payload(organizer_id, title="Renamed Conf", city="Turin"),
    )
    assert resp.status_code == 200
    assert_matches_contract(
        "event", "PUT", f"{EVENTS}/{created['id']}", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 6/7 — PATCH /api/v1/events/<id> (REQ-EVT-F08)
# --------------------------------------------------------------------------- #
@responses.activate
def test_update_event_matches_contract_REQ_EVT_F08(client):
    """PATCH /api/v1/events/<id> 200 conforms to the Event schema (REQ-EVT-T01-AC4)."""
    created = _create_event(client)
    resp = client.patch(f"{EVENTS}/{created['id']}", json={"venue": "Aula Magna"})
    assert resp.status_code == 200
    assert_matches_contract(
        "event", "PATCH", f"{EVENTS}/{created['id']}", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 7/7 — DELETE /api/v1/events/<id> (REQ-EVT-F09)
# --------------------------------------------------------------------------- #
@responses.activate
def test_delete_event_matches_contract_REQ_EVT_F09(client):
    """DELETE /api/v1/events/<id> 204 (no body) conforms to the contract.

    REQ-EVT-T01-AC4: the validator returns without error for a 204 because the
    contract declares no response body for that status (design.md §11).
    """
    created = _create_event(client)
    resp = client.delete(f"{EVENTS}/{created['id']}")
    assert resp.status_code == 204
    assert_matches_contract(
        "event", "DELETE", f"{EVENTS}/{created['id']}", flask_to_contract_dict(resp)
    )
