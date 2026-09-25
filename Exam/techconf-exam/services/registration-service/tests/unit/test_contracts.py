"""Contract-conformance unit tests for the registration-service (T-13, REQ-REG-T01-AC4).

For EACH HTTP operation declared in ``registration-service.yaml`` there is at
least one test that drives the Flask test client and asserts the response
against the OpenAPI contract via ``assert_matches_contract("registration",
method, path, response)`` from ``contracts/validator.py``:

    1. health                    — GET    /health
    2. createRegistration        — POST   /api/v1/registrations
    3. listRegistrations         — GET    /api/v1/registrations
    4. registrationStats         — GET    /api/v1/registrations/stats
    5. getRegistration           — GET    /api/v1/registrations/<id>
    6. updateRegistration        — PATCH  /api/v1/registrations/<id>
    7. deleteRegistration        — DELETE /api/v1/registrations/<id>
    8. putRegistrationNotAllowed — PUT    /api/v1/registrations/<id> (405)

The validator lives in the (non-modifiable) template under
``Exam/techconf-exam/contracts/``; the directory is added to ``sys.path`` the
same way the integration ``conftest.py`` does, resolving the repo root relative
to this file.

Because the registration-service verifies the user against user-service and the
event against event-service, those outbound calls are mocked at the library
level with ``responses`` so no real network call leaves the test process
(REQ-REG-T01-AC2). The contract explicitly declares ``putRegistrationNotAllowed``
returning 405 (with an ``Error`` body), so unlike the purely infrastructural
405s of other services this operation *is* asserted through
``assert_matches_contract`` (design §9, REQ-REG-F08).
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import responses

from app import create_app
from app.backends.memory import MemoryRegistrationRepository
from app.http_client import EventServiceClient, UserServiceClient

# Make contracts/validator.py importable, mirroring tests/integration/conftest.py.
# This file: .../services/registration-service/tests/unit/test_contracts.py
#   parents[0]=unit [1]=tests [2]=registration-service [3]=services [4]=techconf-exam (root)
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "contracts"))

from validator import assert_matches_contract  # noqa: E402

REGISTRATIONS = "/api/v1/registrations"
USER_BASE_URL = "http://user-service.test"
EVENT_BASE_URL = "http://event-service.test"


def flask_to_contract_dict(resp) -> dict:
    """Convert a Flask test response into the dict accepted by the validator.

    The validator's dict branch reads ``response["json"]`` directly (design §9),
    so we build the dict rather than adapting the Flask response object (whose
    ``.json`` is a property, not a callable). ``get_json`` with ``silent=True``
    returns ``None`` for a body-less 204, which the validator treats as
    "no body expected".
    """
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "json": resp.get_json(silent=True),
    }


def _user_url(user_id: str) -> str:
    return f"{USER_BASE_URL}/api/v1/users/{user_id}"


def _event_url(event_id: str) -> str:
    return f"{EVENT_BASE_URL}/api/v1/events/{event_id}"


def _user_payload(user_id: str) -> dict:
    return {
        "id": user_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "company": None,
        "role": "attendee",
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


def _event_payload(
    event_id: str,
    *,
    status: str = "published",
    price: float = 149.00,
    capacity: int = 100,
) -> dict:
    return {
        "id": event_id,
        "title": "TechConf 2026",
        "description": None,
        "organizer_id": str(uuid.uuid4()),
        "venue": "Main Hall",
        "city": "Milano",
        "start_date": "2026-11-01",
        "end_date": "2026-11-02",
        "capacity": capacity,
        "price": price,
        "status": status,
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


@pytest.fixture()
def client():
    """A Flask test client backed by a fresh in-memory repo + mocked clients."""
    app = create_app(
        repo=MemoryRegistrationRepository(),
        user_client=UserServiceClient(USER_BASE_URL, timeout=2.0),
        event_client=EventServiceClient(EVENT_BASE_URL, timeout=2.0),
    )
    return app.test_client()


def _mock_user(user_id: str) -> None:
    responses.add(
        responses.GET, _user_url(user_id), json=_user_payload(user_id), status=200
    )


def _mock_event(event_id: str, **overrides) -> None:
    responses.add(
        responses.GET,
        _event_url(event_id),
        json=_event_payload(event_id, **overrides),
        status=200,
    )


def _create(client, *, event_id=None, **event_overrides) -> dict:
    """Create a registration through the API and return the parsed Registration.

    Registers the user + event mocks automatically; must run inside a
    ``@responses.activate`` test.
    """
    user_id = str(uuid.uuid4())
    if event_id is None:
        event_id = str(uuid.uuid4())
    _mock_user(user_id)
    _mock_event(event_id, **event_overrides)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --------------------------------------------------------------------------- #
# 1/8 — GET /health · health (REQ-REG-F01)
# --------------------------------------------------------------------------- #
def test_health_matches_contract_REQ_REG_F01(client):
    """GET /health 200 conforms to the Health schema (REQ-REG-T01-AC4)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert_matches_contract(
        "registration", "GET", "/health", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 2/8 — POST /api/v1/registrations · createRegistration (REQ-REG-F02)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_registration_matches_contract_REQ_REG_F02(client):
    """POST /api/v1/registrations 201 conforms to the Registration schema."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _mock_user(user_id)
    _mock_event(event_id)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 201
    assert_matches_contract(
        "registration", "POST", REGISTRATIONS, flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 3/8 — GET /api/v1/registrations · listRegistrations (REQ-REG-F05)
# --------------------------------------------------------------------------- #
@responses.activate
def test_list_registrations_matches_contract_REQ_REG_F05(client):
    """GET /api/v1/registrations 200 conforms to the RegistrationPage schema."""
    _create(client)
    resp = client.get(REGISTRATIONS)
    assert resp.status_code == 200
    assert_matches_contract(
        "registration", "GET", REGISTRATIONS, flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 4/8 — GET /api/v1/registrations/stats · registrationStats (REQ-REG-B08)
# --------------------------------------------------------------------------- #
@responses.activate
def test_registration_stats_matches_contract_REQ_REG_B08(client):
    """GET /api/v1/registrations/stats 200 conforms to the RegistrationStats schema."""
    event_id = str(uuid.uuid4())
    _create(client, event_id=event_id, capacity=10)
    _mock_event(event_id, capacity=10)
    resp = client.get(f"{REGISTRATIONS}/stats", query_string={"event_id": event_id})
    assert resp.status_code == 200
    assert_matches_contract(
        "registration",
        "GET",
        f"{REGISTRATIONS}/stats",
        flask_to_contract_dict(resp),
    )


# --------------------------------------------------------------------------- #
# 5/8 — GET /api/v1/registrations/<id> · getRegistration (REQ-REG-F04)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_registration_matches_contract_REQ_REG_F04(client):
    """GET /api/v1/registrations/<id> 200 conforms to the Registration schema."""
    created = _create(client)
    resp = client.get(f"{REGISTRATIONS}/{created['id']}")
    assert resp.status_code == 200
    assert_matches_contract(
        "registration",
        "GET",
        f"{REGISTRATIONS}/{created['id']}",
        flask_to_contract_dict(resp),
    )


# --------------------------------------------------------------------------- #
# 6/8 — PATCH /api/v1/registrations/<id> · updateRegistration (REQ-REG-F06)
# --------------------------------------------------------------------------- #
@responses.activate
def test_update_registration_matches_contract_REQ_REG_F06(client):
    """PATCH /api/v1/registrations/<id> 200 conforms to the Registration schema."""
    created = _create(client)
    resp = client.patch(
        f"{REGISTRATIONS}/{created['id']}", json={"status": "cancelled"}
    )
    assert resp.status_code == 200
    assert_matches_contract(
        "registration",
        "PATCH",
        f"{REGISTRATIONS}/{created['id']}",
        flask_to_contract_dict(resp),
    )


# --------------------------------------------------------------------------- #
# 7/8 — DELETE /api/v1/registrations/<id> · deleteRegistration (REQ-REG-F07)
# --------------------------------------------------------------------------- #
@responses.activate
def test_delete_registration_matches_contract_REQ_REG_F07(client):
    """DELETE /api/v1/registrations/<id> 204 (no body) conforms to the contract.

    The validator returns without error for a 204 because the contract declares
    no response body for that status (design §9).
    """
    created = _create(client)
    resp = client.delete(f"{REGISTRATIONS}/{created['id']}")
    assert resp.status_code == 204
    assert_matches_contract(
        "registration",
        "DELETE",
        f"{REGISTRATIONS}/{created['id']}",
        flask_to_contract_dict(resp),
    )


# --------------------------------------------------------------------------- #
# 8/8 — PUT /api/v1/registrations/<id> · putRegistrationNotAllowed (REQ-REG-F08)
# --------------------------------------------------------------------------- #
def test_put_registration_not_allowed_matches_contract_REQ_REG_F08(client):
    """PUT /api/v1/registrations/<id> 405 conforms to the Error schema.

    The contract explicitly declares ``putRegistrationNotAllowed`` with a 405
    ``Error`` body, so this operation is validated through
    ``assert_matches_contract`` (design §9, REQ-REG-F08-AC1).
    """
    resp = client.put(f"{REGISTRATIONS}/{uuid.uuid4()}", json={"status": "cancelled"})
    assert resp.status_code == 405
    assert_matches_contract(
        "registration",
        "PUT",
        f"{REGISTRATIONS}/{uuid.uuid4()}",
        flask_to_contract_dict(resp),
    )
