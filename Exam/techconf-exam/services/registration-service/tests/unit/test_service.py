"""Unit tests for ``app.service.RegistrationService`` create flow (T-09).

Exercises ``create_registration`` with a real
:class:`app.backends.memory.MemoryRegistrationRepository` and the two dependency
clients whose outbound HTTP is mocked at the library level with ``responses`` —
no real network call leaves the test process (REQ-REG-T01-AC2).

Branch matrix (design §4):

* success                 -> record confirmed, ``amount == event.price`` (REQ-REG-F02, B06)
* user 404                -> ServiceError REFERENCE_NOT_FOUND               (REQ-REG-B01)
* event 404               -> ServiceError REFERENCE_NOT_FOUND               (REQ-REG-B02)
* event not published     -> ServiceError EVENT_NOT_OPEN                    (REQ-REG-B03)
* duplicate confirmed     -> ServiceError ALREADY_REGISTERED                (REQ-REG-B04)
* event full              -> ServiceError EVENT_FULL                        (REQ-REG-B05)
* dependency unavailable  -> ServiceError DEPENDENCY_UNAVAILABLE (user/event) (REQ-REG-B09)
* no mutation on error    -> repository unchanged after any failure          (design §4)
"""
import uuid

import pytest
import responses

from app import errors
from app.backends.memory import MemoryRegistrationRepository
from app.http_client import EventServiceClient, UserServiceClient
from app.models import CONFIRMED
from app.service import RegistrationService, ServiceError

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


@pytest.fixture
def repo():
    return MemoryRegistrationRepository()


@pytest.fixture
def service(repo):
    return RegistrationService(
        repo,
        UserServiceClient(USER_BASE_URL, timeout=2.0),
        EventServiceClient(EVENT_BASE_URL, timeout=2.0),
    )


def _ids():
    return str(uuid.uuid4()), str(uuid.uuid4())


def _mock_user_ok(user_id: str):
    responses.add(responses.GET, _user_url(user_id),
                  json=_user_payload(user_id), status=200)


def _mock_event_ok(event_id: str, **kwargs):
    responses.add(responses.GET, _event_url(event_id),
                  json=_event_payload(event_id, **kwargs), status=200)


# --------------------------------------------------------------------------- #
# Success (REQ-REG-F02, REQ-REG-B06, REQ-REG-F10)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_success_confirmed_and_amount_from_price_REQ_REG_F02_B06(service, repo):
    """A valid create yields a confirmed record with amount = event.price."""
    user_id, event_id = _ids()
    _mock_user_ok(user_id)
    _mock_event_ok(event_id, price=149.00, capacity=100)

    record = service.create_registration({"user_id": user_id, "event_id": event_id})

    assert record["user_id"] == user_id
    assert record["event_id"] == event_id
    assert record["status"] == CONFIRMED
    assert record["amount"] == 149.00
    # Timestamps identical at creation (REQ-REG-F10-AC2).
    assert record["created_at"] == record["updated_at"]
    # The record was actually persisted.
    assert repo.get(record["id"]) is not None
    assert repo.count_confirmed(event_id) == 1


# --------------------------------------------------------------------------- #
# REFERENCE_NOT_FOUND — user 404 (REQ-REG-B01)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_user_not_found_maps_reference_not_found_REQ_REG_B01(service, repo):
    """A 404 from user-service maps to REFERENCE_NOT_FOUND and mutates nothing."""
    user_id, event_id = _ids()
    responses.add(responses.GET, _user_url(user_id), status=404)

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.REFERENCE_NOT_FOUND
    assert repo.list_all({}) == []
    # The event was never queried because the user check failed first.
    assert len(responses.calls) == 1


# --------------------------------------------------------------------------- #
# REFERENCE_NOT_FOUND — event 404 (REQ-REG-B02)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_not_found_maps_reference_not_found_REQ_REG_B02(service, repo):
    """A 404 from event-service maps to REFERENCE_NOT_FOUND and mutates nothing."""
    user_id, event_id = _ids()
    _mock_user_ok(user_id)
    responses.add(responses.GET, _event_url(event_id), status=404)

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.REFERENCE_NOT_FOUND
    assert repo.list_all({}) == []


# --------------------------------------------------------------------------- #
# EVENT_NOT_OPEN (REQ-REG-B03)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", ["draft", "cancelled"])
@responses.activate
def test_create_event_not_published_maps_event_not_open_REQ_REG_B03(service, repo, status):
    """An event whose status is not published maps to EVENT_NOT_OPEN, no mutation."""
    user_id, event_id = _ids()
    _mock_user_ok(user_id)
    _mock_event_ok(event_id, status=status)

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.EVENT_NOT_OPEN
    assert repo.list_all({}) == []


# --------------------------------------------------------------------------- #
# ALREADY_REGISTERED (REQ-REG-B04)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_duplicate_confirmed_maps_already_registered_REQ_REG_B04(service, repo):
    """A second confirmed registration for the same pair maps to ALREADY_REGISTERED."""
    user_id, event_id = _ids()
    # Two lookups happen (one per create attempt); register both responses.
    for _ in range(2):
        _mock_user_ok(user_id)
        _mock_event_ok(event_id, capacity=100)

    first = service.create_registration({"user_id": user_id, "event_id": event_id})

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.ALREADY_REGISTERED
    # Only the first record exists; the duplicate did not mutate the store.
    assert [r["id"] for r in repo.list_all({})] == [first["id"]]


# --------------------------------------------------------------------------- #
# EVENT_FULL (REQ-REG-B05)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_event_full_maps_event_full_REQ_REG_B05(service, repo):
    """When capacity is reached a new registration maps to EVENT_FULL, no mutation."""
    event_id = str(uuid.uuid4())
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    # Capacity 1: first user succeeds, second user is rejected.
    _mock_user_ok(user_a)
    _mock_event_ok(event_id, capacity=1)
    _mock_user_ok(user_b)
    _mock_event_ok(event_id, capacity=1)

    service.create_registration({"user_id": user_a, "event_id": event_id})

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_b, "event_id": event_id})

    assert excinfo.value.code == errors.EVENT_FULL
    assert repo.count_confirmed(event_id) == 1


# --------------------------------------------------------------------------- #
# DEPENDENCY_UNAVAILABLE (REQ-REG-B09)
# --------------------------------------------------------------------------- #
@responses.activate
def test_create_user_dependency_unavailable_maps_503_REQ_REG_B09(service, repo):
    """A 5xx from user-service maps to DEPENDENCY_UNAVAILABLE, no mutation."""
    user_id, event_id = _ids()
    responses.add(responses.GET, _user_url(user_id), status=503)

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.DEPENDENCY_UNAVAILABLE
    assert repo.list_all({}) == []


@responses.activate
def test_create_event_dependency_unavailable_maps_503_REQ_REG_B09(service, repo):
    """A 5xx from event-service maps to DEPENDENCY_UNAVAILABLE, no mutation."""
    user_id, event_id = _ids()
    _mock_user_ok(user_id)
    responses.add(responses.GET, _event_url(event_id), status=500)

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.DEPENDENCY_UNAVAILABLE
    assert repo.list_all({}) == []


@responses.activate
def test_create_event_timeout_maps_503_REQ_REG_B09(service, repo):
    """A timeout from event-service maps to DEPENDENCY_UNAVAILABLE, no mutation."""
    import requests

    user_id, event_id = _ids()
    _mock_user_ok(user_id)
    responses.add(responses.GET, _event_url(event_id),
                  body=requests.Timeout("timed out"))

    with pytest.raises(ServiceError) as excinfo:
        service.create_registration({"user_id": user_id, "event_id": event_id})

    assert excinfo.value.code == errors.DEPENDENCY_UNAVAILABLE
    assert repo.list_all({}) == []
