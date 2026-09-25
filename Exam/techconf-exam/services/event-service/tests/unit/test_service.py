"""Unit tests for ``app.service.EventService`` — T-09 (create_event).

Exercise ``create_event`` against a real :class:`MemoryEventRepository` with the
organizer verification mocked at the library level by ``responses`` so no real
network call leaves the test process (REQ-EVT-T01-AC2). The clock
(``utcnow_iso``) is monkeypatched where the exact timestamp is asserted
(REQ-EVT-F11).

Covered outcomes (task completion criteria):

* success                                            (REQ-EVT-F02, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-F11)
* user-service 404   -> REFERENCE_NOT_FOUND (422)    (REQ-EVT-B01)
* wrong role         -> INVALID_ORGANIZER (422)      (REQ-EVT-B02)
* dependency down    -> DEPENDENCY_UNAVAILABLE (503) (REQ-EVT-B05)
* end_date<start_date -> VALIDATION_ERROR (422), no HTTP call (REQ-EVT-B03)
"""
import uuid

import pytest
import requests
import responses

from app import errors, service as service_module
from app.backends.memory import MemoryEventRepository
from app.http_client import UserServiceClient
from app.service import EventService, ServiceError

BASE_URL = "http://user-service.test"


def _user_url(user_id: str) -> str:
    return f"{BASE_URL}/api/v1/users/{user_id}"


def _user_payload(user_id: str, role: str) -> dict:
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


def _valid_create_body(organizer_id: str) -> dict:
    return {
        "title": "PyConf 2026",
        "organizer_id": organizer_id,
        "venue": "Main Hall",
        "city": "Rome",
        "start_date": "2026-10-15",
        "end_date": "2026-10-17",
        "capacity": 100,
        "price": 49.9,
    }


@pytest.fixture
def repo():
    return MemoryEventRepository()


@pytest.fixture
def user_client():
    return UserServiceClient(BASE_URL, timeout=2.0)


@pytest.fixture
def svc(repo, user_client):
    return EventService(repo, user_client)


# --------------------------------------------------------------------------- #
# success (REQ-EVT-F02, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-F11)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_success_persists_and_returns_contract_shape(svc, repo, monkeypatch):
    """REQ-EVT-F02: a valid body + organizer returns the created Event and persists it."""
    fixed_now = "2026-10-15T09:30:00.000000Z"
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: fixed_now)

    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"),
        status=200,
    )

    result = svc.create_event(_valid_create_body(organizer_id))

    # Response has exactly the 13 contract fields.
    assert set(result.keys()) == {
        "id", "title", "description", "organizer_id", "venue", "city",
        "start_date", "end_date", "capacity", "price", "status",
        "created_at", "updated_at",
    }
    # Server-generated id is a valid UUID (REQ-EVT-F02-AC2).
    uuid.UUID(result["id"])
    # The record is persisted and readable via the repository.
    assert repo.get(result["id"]) is not None
    assert result["organizer_id"] == organizer_id


@responses.activate
def test_create_event_defaults_status_draft_and_description_none(svc, monkeypatch):
    """REQ-EVT-F02-AC5/AC6: omitted status defaults to draft, description to None."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-15T09:30:00.000000Z")
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"),
        status=200,
    )

    result = svc.create_event(_valid_create_body(organizer_id))

    assert result["status"] == "draft"
    assert result["description"] is None


@responses.activate
def test_create_event_identical_timestamps_at_creation(svc, monkeypatch):
    """REQ-EVT-F11-AC2: created_at and updated_at are identical at creation."""
    fixed_now = "2026-10-15T09:30:00.123456Z"
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: fixed_now)
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"),
        status=200,
    )

    result = svc.create_event(_valid_create_body(organizer_id))

    assert result["created_at"] == result["updated_at"] == fixed_now


@responses.activate
def test_create_event_keeps_explicit_status(svc, monkeypatch):
    """REQ-EVT-B04-AC3: an explicit valid initial status is preserved (not a transition)."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-15T09:30:00.000000Z")
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"),
        status=200,
    )
    body = _valid_create_body(organizer_id)
    body["status"] = "published"

    result = svc.create_event(body)

    assert result["status"] == "published"


# --------------------------------------------------------------------------- #
# user-service 404 -> REFERENCE_NOT_FOUND (422) (REQ-EVT-B01)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_unknown_organizer_raises_reference_not_found(svc, repo):
    """REQ-EVT-B01: a 404 from user-service maps to REFERENCE_NOT_FOUND (422); no persistence."""
    organizer_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(organizer_id), status=404)

    with pytest.raises(ServiceError) as exc_info:
        svc.create_event(_valid_create_body(organizer_id))

    assert exc_info.value.code == errors.REFERENCE_NOT_FOUND
    assert exc_info.value.status == 422
    # No record was created on error (no repository mutation).
    assert repo.list_all({}) == []


# --------------------------------------------------------------------------- #
# wrong role -> INVALID_ORGANIZER (422) (REQ-EVT-B02)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["attendee", "speaker"])
@responses.activate
def test_create_event_wrong_role_raises_invalid_organizer(svc, repo, role):
    """REQ-EVT-B02: an existing non-organizer user maps to INVALID_ORGANIZER (422); no persistence."""
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, role),
        status=200,
    )

    with pytest.raises(ServiceError) as exc_info:
        svc.create_event(_valid_create_body(organizer_id))

    assert exc_info.value.code == errors.INVALID_ORGANIZER
    assert exc_info.value.status == 422
    assert repo.list_all({}) == []


# --------------------------------------------------------------------------- #
# dependency down -> DEPENDENCY_UNAVAILABLE (503) (REQ-EVT-B05)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_dependency_5xx_raises_dependency_unavailable(svc, repo):
    """REQ-EVT-B05-AC3: a 5xx from user-service maps to DEPENDENCY_UNAVAILABLE (503); no persistence."""
    organizer_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(organizer_id), status=503)

    with pytest.raises(ServiceError) as exc_info:
        svc.create_event(_valid_create_body(organizer_id))

    assert exc_info.value.code == errors.DEPENDENCY_UNAVAILABLE
    assert exc_info.value.status == 503
    assert repo.list_all({}) == []


@responses.activate
def test_create_event_dependency_connection_error_raises_dependency_unavailable(svc, repo):
    """REQ-EVT-B05-AC2: a refused connection maps to DEPENDENCY_UNAVAILABLE (503)."""
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        body=requests.ConnectionError("connection refused"),
    )

    with pytest.raises(ServiceError) as exc_info:
        svc.create_event(_valid_create_body(organizer_id))

    assert exc_info.value.code == errors.DEPENDENCY_UNAVAILABLE
    assert exc_info.value.status == 503
    assert repo.list_all({}) == []


# --------------------------------------------------------------------------- #
# end_date < start_date -> VALIDATION_ERROR (422), no HTTP call (REQ-EVT-B03)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_incoherent_dates_raises_before_http_call(svc, repo):
    """REQ-EVT-B03: end_date<start_date -> VALIDATION_ERROR (422) and no outbound call is made."""
    organizer_id = str(uuid.uuid4())
    # Register the organizer endpoint; if the service (wrongly) called it the
    # request would be recorded. We assert below that it never fired.
    responses.add(
        responses.GET,
        _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"),
        status=200,
    )
    body = _valid_create_body(organizer_id)
    body["start_date"] = "2026-10-17"
    body["end_date"] = "2026-10-15"

    with pytest.raises(ServiceError) as exc_info:
        svc.create_event(body)

    assert exc_info.value.code == errors.VALIDATION_ERROR
    assert exc_info.value.status == 422
    # No HTTP call was made (date check runs before organizer verification).
    assert len(responses.calls) == 0
    # No record was persisted.
    assert repo.list_all({}) == []


def test_service_error_carries_code_status_message():
    """ServiceError exposes code, status and message for the routes layer (REQ-EVT-F12)."""
    err = ServiceError(errors.VALIDATION_ERROR, "bad", 422)
    assert err.code == errors.VALIDATION_ERROR
    assert err.status == 422
    assert err.message == "bad"
    assert str(err) == "bad"
