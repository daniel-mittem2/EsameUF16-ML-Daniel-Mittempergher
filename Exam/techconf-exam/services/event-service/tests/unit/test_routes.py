"""Unit tests for the HTTP routes Blueprint (T-12).

Exercises every endpoint through the Flask test client, backed by an in-memory
repository and a :class:`UserServiceClient` whose outbound calls are mocked at
the library level by ``responses`` so no real network call ever leaves the test
process (REQ-EVT-T01-AC2). Covers the happy paths plus the error mappings
required by REQ-EVT-F02..F12: 201/Location on create, pagination + filters on
list, 404 on missing resources, 422 on validation/reference/transition
failures, 503 on a user-service outage, 400 on malformed JSON, 204 on delete
and 405 on unsupported methods.
"""
import uuid

import pytest
import responses

from app import create_app
from app.backends.memory import MemoryEventRepository
from app.http_client import UserServiceClient

EVENTS = "/api/v1/events"
BASE_URL = "http://user-service.test"


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


def _mock_organizer(organizer_id: str, role: str = "organizer", status: int = 200):
    """Register a ``responses`` mock for the organizer lookup."""
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, role),
        status=status,
    )


def _create(client, organizer_id=None, **overrides):
    """Create an event through the API and return the parsed response body.

    Registers the organizer mock automatically. Must run inside a
    ``@responses.activate`` test.
    """
    if organizer_id is None:
        organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id)
    resp = client.post(EVENTS, json=_valid_payload(organizer_id, **overrides))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --- POST ------------------------------------------------------------------- #

@responses.activate
def test_post_creates_event_201_location_and_body_REQ_EVT_F02(client):
    """POST returns 201, a Location header and the Event body (REQ-EVT-F02-AC1)."""
    organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id)
    resp = client.post(EVENTS, json=_valid_payload(organizer_id))
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["title"] == "PyConf 2026"
    assert body["organizer_id"] == organizer_id
    assert body["status"] == "draft"  # default (REQ-EVT-B04-AC3)
    assert body["description"] is None  # default null (REQ-EVT-F02-AC6)
    assert resp.headers["Location"] == f"{EVENTS}/{body['id']}"


@responses.activate
def test_post_missing_required_field_422_REQ_EVT_F03(client):
    """POST without a required field is 422 VALIDATION_ERROR (REQ-EVT-F03)."""
    resp = client.post(EVENTS, json={"title": "Only a title"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@responses.activate
def test_post_array_body_is_422_REQ_EVT_F03(client):
    """A JSON array body ([]) is not an object → 422 (REQ-EVT-F03-AC10)."""
    resp = client.post(EVENTS, json=[])
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@responses.activate
def test_post_wrong_field_type_is_422_REQ_EVT_F03(client):
    """A wrong field type (capacity as string, no coercion) → 422 (REQ-EVT-F03-AC11)."""
    organizer_id = str(uuid.uuid4())
    resp = client.post(EVENTS, json=_valid_payload(organizer_id, capacity="100"))
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_malformed_json_is_400_REQ_EVT_F12(client):
    """A syntactically broken body → 400 MALFORMED_JSON (REQ-EVT-F12)."""
    resp = client.post(
        EVENTS, data="{not json", content_type="application/json"
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"


@responses.activate
def test_post_incoherent_dates_is_422_REQ_EVT_B03(client):
    """end_date before start_date → 422 VALIDATION_ERROR (REQ-EVT-B03)."""
    organizer_id = str(uuid.uuid4())
    resp = client.post(
        EVENTS,
        json=_valid_payload(
            organizer_id, start_date="2026-10-17", end_date="2026-10-15"
        ),
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


@responses.activate
def test_post_unknown_organizer_is_422_reference_not_found_REQ_EVT_B01(client):
    """A user-service 404 for the organizer → 422 REFERENCE_NOT_FOUND (REQ-EVT-B01)."""
    organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id, status=404)
    resp = client.post(EVENTS, json=_valid_payload(organizer_id))
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "REFERENCE_NOT_FOUND"


@responses.activate
def test_post_non_organizer_role_is_422_invalid_organizer_REQ_EVT_B02(client):
    """A user whose role != organizer → 422 INVALID_ORGANIZER (REQ-EVT-B02)."""
    organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id, role="attendee")
    resp = client.post(EVENTS, json=_valid_payload(organizer_id))
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "INVALID_ORGANIZER"


@responses.activate
def test_post_dependency_down_is_503_REQ_EVT_B05(client):
    """A user-service 5xx → 503 DEPENDENCY_UNAVAILABLE (REQ-EVT-B05)."""
    organizer_id = str(uuid.uuid4())
    _mock_organizer(organizer_id, status=500)
    resp = client.post(EVENTS, json=_valid_payload(organizer_id))
    assert resp.status_code == 503
    assert resp.get_json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


# --- GET list --------------------------------------------------------------- #

@responses.activate
def test_list_returns_paginated_page_REQ_EVT_F06(client):
    """GET list returns an EventPage with items/page/page_size/total (REQ-EVT-F06)."""
    _create(client)
    _create(client)
    resp = client.get(EVENTS)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 2


@responses.activate
def test_list_filters_by_city_REQ_EVT_B06(client):
    """The city filter narrows the result set (REQ-EVT-B06)."""
    _create(client, city="Rome")
    _create(client, city="Milan")
    resp = client.get(EVENTS, query_string={"city": "Rome"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["city"] == "Rome"


def test_list_page_size_over_max_is_422_REQ_EVT_F06(client):
    """page_size=101 (over the max of 100) → 422 VALIDATION_ERROR (REQ-EVT-F06-AC3)."""
    resp = client.get(EVENTS, query_string={"page_size": "101"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_non_integer_page_is_422_REQ_EVT_F06(client):
    """page=abc (non-integer) → 422 VALIDATION_ERROR (REQ-EVT-F06-AC3)."""
    resp = client.get(EVENTS, query_string={"page": "abc"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_invalid_status_filter_is_422_REQ_EVT_B06(client):
    """An unrecognised status filter value → 422 VALIDATION_ERROR (REQ-EVT-B06-AC2)."""
    resp = client.get(EVENTS, query_string={"status": "archived"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET by id -------------------------------------------------------------- #

@responses.activate
def test_get_existing_event_200_REQ_EVT_F05(client):
    """GET /events/<id> returns 200 with the Event (REQ-EVT-F05)."""
    created = _create(client)
    resp = client.get(f"{EVENTS}/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == created["id"]


def test_get_unknown_event_404_REQ_EVT_F05(client):
    """GET /events/<unknown id> → 404 NOT_FOUND (REQ-EVT-F05)."""
    resp = client.get(f"{EVENTS}/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# --- PUT -------------------------------------------------------------------- #

@responses.activate
def test_put_replaces_event_200_REQ_EVT_F07(client):
    """PUT fully replaces an existing event and returns 200 (REQ-EVT-F07)."""
    created = _create(client)
    organizer_id = created["organizer_id"]
    _mock_organizer(organizer_id)
    resp = client.put(
        f"{EVENTS}/{created['id']}",
        json=_valid_payload(organizer_id, title="Renamed Conf", city="Turin"),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "Renamed Conf"
    assert body["city"] == "Turin"
    assert body["id"] == created["id"]
    assert body["created_at"] == created["created_at"]


@responses.activate
def test_put_unknown_event_404_REQ_EVT_F07(client):
    """PUT on a missing id → 404 NOT_FOUND (REQ-EVT-F07)."""
    organizer_id = str(uuid.uuid4())
    resp = client.put(
        f"{EVENTS}/{uuid.uuid4()}", json=_valid_payload(organizer_id)
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@responses.activate
def test_put_invalid_body_422_REQ_EVT_F03(client):
    """PUT with a missing required field → 422 VALIDATION_ERROR (REQ-EVT-F03)."""
    created = _create(client)
    resp = client.put(f"{EVENTS}/{created['id']}", json={"title": "x"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# --- PATCH ------------------------------------------------------------------ #

@responses.activate
def test_patch_updates_single_field_200_REQ_EVT_F08(client):
    """PATCH applies only the present fields and returns 200 (REQ-EVT-F08)."""
    created = _create(client)
    resp = client.patch(f"{EVENTS}/{created['id']}", json={"venue": "Aula Magna"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["venue"] == "Aula Magna"
    assert body["title"] == created["title"]  # untouched


@responses.activate
def test_patch_empty_body_returns_unchanged_REQ_EVT_F04(client):
    """An empty PATCH {} returns the record unchanged, updated_at intact (REQ-EVT-F04-AC6)."""
    created = _create(client)
    resp = client.patch(f"{EVENTS}/{created['id']}", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["updated_at"] == created["updated_at"]


@responses.activate
def test_patch_status_transition_published_ok_REQ_EVT_B04(client):
    """PATCH draft→published is an allowed transition → 200 (REQ-EVT-B04)."""
    created = _create(client)
    resp = client.patch(
        f"{EVENTS}/{created['id']}", json={"status": "published"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "published"


@responses.activate
def test_patch_invalid_status_transition_422_REQ_EVT_B04(client):
    """PATCH published→draft is disallowed → 422 INVALID_STATUS_TRANSITION (REQ-EVT-B04)."""
    created = _create(client)
    client.patch(f"{EVENTS}/{created['id']}", json={"status": "published"})
    resp = client.patch(f"{EVENTS}/{created['id']}", json={"status": "draft"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_patch_unknown_event_404_REQ_EVT_F04(client):
    """PATCH on a missing id → 404 even with an empty body (REQ-EVT-F04-AC5)."""
    resp = client.patch(f"{EVENTS}/{uuid.uuid4()}", json={})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@responses.activate
def test_patch_unknown_field_422_REQ_EVT_F04(client):
    """PATCH with an unknown field → 422 VALIDATION_ERROR (REQ-EVT-F04-AC2)."""
    created = _create(client)
    resp = client.patch(f"{EVENTS}/{created['id']}", json={"nope": 1})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# --- DELETE ----------------------------------------------------------------- #

@responses.activate
def test_delete_existing_event_204_no_body_REQ_EVT_F09(client):
    """DELETE returns 204 with an empty body and no JSON Content-Type (REQ-EVT-F09-AC1)."""
    created = _create(client)
    resp = client.delete(f"{EVENTS}/{created['id']}")
    assert resp.status_code == 204
    assert resp.get_data(as_text=True) == ""
    assert "application/json" not in resp.headers.get("Content-Type", "")


def test_delete_unknown_event_404_REQ_EVT_F09(client):
    """DELETE on a missing id → 404 NOT_FOUND (REQ-EVT-F09-AC2)."""
    resp = client.delete(f"{EVENTS}/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


@responses.activate
def test_delete_twice_second_is_404_REQ_EVT_F09(client):
    """A second delete of the same id → 404 NOT_FOUND (REQ-EVT-F09-AC2)."""
    created = _create(client)
    assert client.delete(f"{EVENTS}/{created['id']}").status_code == 204
    resp = client.delete(f"{EVENTS}/{created['id']}")
    assert resp.status_code == 404


# --- 405 / method not allowed ----------------------------------------------- #

def test_post_on_item_path_is_405_REQ_EVT_F10(client):
    """POST /events/<id> is not a defined operation → 405 (REQ-EVT-F10)."""
    resp = client.post(f"{EVENTS}/{uuid.uuid4()}", json={})
    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"
