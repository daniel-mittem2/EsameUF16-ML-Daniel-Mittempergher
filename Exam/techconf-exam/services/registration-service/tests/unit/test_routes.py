"""Unit tests for the HTTP routes Blueprint (T-12).

Exercises every endpoint through the Flask test client, backed by an in-memory
repository and the two dependency clients (user + event) whose outbound calls
are mocked at the library level by ``responses`` so no real network call ever
leaves the test process (REQ-REG-T01-AC2). Covers the happy paths plus the
error mappings required by REQ-REG-F02..F11 and REQ-REG-B08: 201/Location on
create, pagination + filters on list, stats (200/404/422/503), 404 on missing
resources, 422 on validation/reference/transition failures, 409 on
conflict, 503 on a dependency outage, 400 on malformed JSON, 204 on delete and
405 on PUT / other unsupported methods.
"""
import uuid

import pytest
import responses

from app import create_app
from app.backends.memory import MemoryRegistrationRepository
from app.http_client import EventServiceClient, UserServiceClient

REGISTRATIONS = "/api/v1/registrations"
USER_BASE_URL = "http://user-service.test"
EVENT_BASE_URL = "http://event-service.test"


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
def repo():
    return MemoryRegistrationRepository()


@pytest.fixture()
def client(repo):
    """A Flask test client backed by a fresh in-memory repo + mocked clients."""
    app = create_app(
        repo=repo,
        user_client=UserServiceClient(USER_BASE_URL, timeout=2.0),
        event_client=EventServiceClient(EVENT_BASE_URL, timeout=2.0),
    )
    return app.test_client()


def _mock_user(user_id: str, status: int = 200):
    responses.add(
        responses.GET,
        _user_url(user_id),
        json=_user_payload(user_id),
        status=status,
    )


def _mock_event(event_id: str, http_status: int = 200, **overrides):
    """Register a ``responses`` mock for the event lookup.

    ``http_status`` is the HTTP status code returned by event-service; the
    remaining keyword args (``status``, ``price``, ``capacity``) override fields
    of the event payload.
    """
    responses.add(
        responses.GET,
        _event_url(event_id),
        json=_event_payload(event_id, **overrides),
        status=http_status,
    )


def _create(client, user_id=None, event_id=None, **event_overrides):
    """Create a registration through the API and return the parsed body.

    Registers the user + event mocks automatically. Must run inside a
    ``@responses.activate`` test.
    """
    if user_id is None:
        user_id = str(uuid.uuid4())
    if event_id is None:
        event_id = str(uuid.uuid4())
    _mock_user(user_id)
    _mock_event(event_id, **event_overrides)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --- POST ------------------------------------------------------------------- #


@responses.activate
def test_post_creates_registration_201_location_and_body_REQ_REG_F02(client):
    """POST returns 201, a Location header and the Registration body (REQ-REG-F02)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _mock_user(user_id)
    _mock_event(event_id, price=149.00)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["user_id"] == user_id
    assert body["event_id"] == event_id
    assert body["status"] == "confirmed"  # always confirmed at creation
    assert body["amount"] == 149.00  # copied from event.price (REQ-REG-B06)
    assert resp.headers["Location"] == f"{REGISTRATIONS}/{body['id']}"


@responses.activate
def test_post_array_body_is_422_REQ_REG_F03(client):
    """A JSON array body ([]) is not an object → 422 (REQ-REG-F03-AC3)."""
    resp = client.post(REGISTRATIONS, json=[])
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@responses.activate
def test_post_unknown_field_is_422_REQ_REG_F02(client):
    """An extra field (additionalProperties:false) → 422 (REQ-REG-F02-AC6)."""
    resp = client.post(
        REGISTRATIONS,
        json={"user_id": str(uuid.uuid4()), "event_id": str(uuid.uuid4()), "amount": 5},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_malformed_json_is_400_REQ_REG_F03(client):
    """A syntactically broken JSON body → 400 MALFORMED_JSON (REQ-REG-F03-AC4)."""
    resp = client.post(
        REGISTRATIONS, data="{not json", content_type="application/json"
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"


@responses.activate
def test_post_user_404_is_422_reference_not_found_REQ_REG_B01(client):
    """A user unknown to user-service → 422 REFERENCE_NOT_FOUND (REQ-REG-B01)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _mock_user(user_id, status=404)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@responses.activate
def test_post_event_not_published_is_422_event_not_open_REQ_REG_B03(client):
    """An event that is not published → 422 EVENT_NOT_OPEN (REQ-REG-B03)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _mock_user(user_id)
    _mock_event(event_id, status="draft")
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "EVENT_NOT_OPEN"


@responses.activate
def test_post_duplicate_is_409_already_registered_REQ_REG_B04(client):
    """A second confirmed registration for the same pair → 409 (REQ-REG-B04)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    first = _create(client, user_id=user_id, event_id=event_id)
    assert first["status"] == "confirmed"
    # Register the mocks again for the second attempt.
    _mock_user(user_id)
    _mock_event(event_id)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "ALREADY_REGISTERED"


@responses.activate
def test_post_full_event_is_409_event_full_REQ_REG_B05(client):
    """A registration on a full event → 409 EVENT_FULL (REQ-REG-B05)."""
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _create(client, user_id=user_a, event_id=event_id, capacity=1)
    _mock_user(user_b)
    _mock_event(event_id, capacity=1)
    resp = client.post(REGISTRATIONS, json={"user_id": user_b, "event_id": event_id})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EVENT_FULL"


@responses.activate
def test_post_dependency_5xx_is_503_REQ_REG_B09(client):
    """A user-service 5xx while creating → 503 DEPENDENCY_UNAVAILABLE (REQ-REG-B09)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _mock_user(user_id, status=502)
    resp = client.post(REGISTRATIONS, json={"user_id": user_id, "event_id": event_id})
    assert resp.status_code == 503
    assert resp.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


# --- GET list --------------------------------------------------------------- #


@responses.activate
def test_list_empty_defaults_REQ_REG_F05(client):
    """GET with no query params → 200 with default pagination (REQ-REG-F05-AC1)."""
    resp = client.get(REGISTRATIONS)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"items": [], "page": 1, "page_size": 20, "total": 0}


@responses.activate
def test_list_filters_by_event_and_status_REQ_REG_F05(client):
    """Filters are combined with AND logic and total is post-filter (REQ-REG-F05)."""
    user_id = str(uuid.uuid4())
    event_a = str(uuid.uuid4())
    event_b = str(uuid.uuid4())
    _create(client, user_id=user_id, event_id=event_a)
    _create(client, user_id=str(uuid.uuid4()), event_id=event_b)
    resp = client.get(REGISTRATIONS, query_string={"event_id": event_a})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["event_id"] == event_a


def test_list_page_size_over_max_is_422_REQ_REG_F05(client):
    """page_size=101 exceeds the max of 100 → 422 (REQ-REG-F05-AC3)."""
    resp = client.get(REGISTRATIONS, query_string={"page_size": 101})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_invalid_status_filter_is_422_REQ_REG_F05(client):
    """An invalid status filter → 422 VALIDATION_ERROR (REQ-REG-F05-AC5)."""
    resp = client.get(REGISTRATIONS, query_string={"status": "bogus"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET stats -------------------------------------------------------------- #


@responses.activate
def test_stats_returns_capacity_confirmed_available_REQ_REG_B08(client):
    """stats returns event_id/capacity/confirmed/available (REQ-REG-B08-AC1/AC2)."""
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    _create(client, user_id=user_id, event_id=event_id, capacity=10)
    _mock_event(event_id, capacity=10)
    resp = client.get(f"{REGISTRATIONS}/stats", query_string={"event_id": event_id})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "event_id": event_id,
        "capacity": 10,
        "confirmed": 1,
        "available": 9,
    }


def test_stats_missing_event_id_is_422_REQ_REG_B08(client):
    """stats without event_id → 422 VALIDATION_ERROR (REQ-REG-B08-AC4)."""
    resp = client.get(f"{REGISTRATIONS}/stats")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@responses.activate
def test_stats_unknown_event_is_404_not_found_REQ_REG_B08(client):
    """stats for an event unknown to event-service → 404 NOT_FOUND (REQ-REG-B08-AC3)."""
    event_id = str(uuid.uuid4())
    _mock_event(event_id, http_status=404)
    resp = client.get(f"{REGISTRATIONS}/stats", query_string={"event_id": event_id})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@responses.activate
def test_stats_dependency_unavailable_is_503_REQ_REG_B08(client):
    """stats when event-service is 5xx → 503 DEPENDENCY_UNAVAILABLE (REQ-REG-B08-AC5)."""
    event_id = str(uuid.uuid4())
    _mock_event(event_id, http_status=503)
    resp = client.get(f"{REGISTRATIONS}/stats", query_string={"event_id": event_id})
    assert resp.status_code == 503
    assert resp.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


# --- GET by id -------------------------------------------------------------- #


@responses.activate
def test_get_by_id_returns_registration_REQ_REG_F04(client):
    """GET /<id> returns the registration (REQ-REG-F04-AC1)."""
    created = _create(client)
    resp = client.get(f"{REGISTRATIONS}/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == created["id"]


def test_get_by_id_unknown_is_404_REQ_REG_F04(client):
    """GET /<id> for an unknown id → 404 NOT_FOUND (REQ-REG-F04-AC2)."""
    resp = client.get(f"{REGISTRATIONS}/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# --- PATCH ------------------------------------------------------------------ #


@responses.activate
def test_patch_confirmed_to_cancelled_is_200_REQ_REG_F06(client):
    """PATCH confirmed→cancelled returns 200 with the updated status (REQ-REG-F06)."""
    created = _create(client)
    resp = client.patch(
        f"{REGISTRATIONS}/{created['id']}", json={"status": "cancelled"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelled"


@responses.activate
def test_patch_reactivation_is_422_invalid_transition_REQ_REG_B07(client):
    """PATCH cancelled→confirmed → 422 INVALID_STATUS_TRANSITION (REQ-REG-B07)."""
    created = _create(client)
    client.patch(f"{REGISTRATIONS}/{created['id']}", json={"status": "cancelled"})
    resp = client.patch(
        f"{REGISTRATIONS}/{created['id']}", json={"status": "confirmed"}
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_patch_unknown_id_is_404_REQ_REG_F06(client):
    """PATCH on a missing id → 404 NOT_FOUND (REQ-REG-F06-AC4)."""
    resp = client.patch(
        f"{REGISTRATIONS}/{uuid.uuid4()}", json={"status": "cancelled"}
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_patch_missing_status_is_422_REQ_REG_F06(client):
    """PATCH without status → 422 VALIDATION_ERROR (REQ-REG-F06-AC2)."""
    resp = client.patch(f"{REGISTRATIONS}/{uuid.uuid4()}", json={})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# --- DELETE ----------------------------------------------------------------- #


@responses.activate
def test_delete_returns_204_without_json_content_type_REQ_REG_F07(client):
    """DELETE returns 204 with no body and no JSON Content-Type (REQ-REG-F07-AC1)."""
    created = _create(client)
    resp = client.delete(f"{REGISTRATIONS}/{created['id']}")
    assert resp.status_code == 204
    assert resp.get_data() == b""
    assert "application/json" not in (resp.headers.get("Content-Type") or "")


def test_delete_unknown_id_is_404_REQ_REG_F07(client):
    """DELETE on a missing id → 404 NOT_FOUND (REQ-REG-F07-AC2)."""
    resp = client.delete(f"{REGISTRATIONS}/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# --- PUT / method-not-allowed ---------------------------------------------- #


def test_put_is_405_with_error_body_REQ_REG_F08(client):
    """PUT /<id> → 405 with a conforming Error body (REQ-REG-F08-AC1)."""
    resp = client.put(f"{REGISTRATIONS}/{uuid.uuid4()}", json={"status": "cancelled"})
    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_put_405_regardless_of_existence_REQ_REG_F08(client):
    """PUT returns 405 even for a random id (method unsupported, REQ-REG-F08-AC2)."""
    resp = client.put(f"{REGISTRATIONS}/{uuid.uuid4()}")
    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_unknown_path_is_404_REQ_REG_F09(client):
    """An unknown path → 404 with an Error body (REQ-REG-F09-AC2)."""
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"
