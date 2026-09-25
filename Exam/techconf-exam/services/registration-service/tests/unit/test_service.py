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


# --------------------------------------------------------------------------- #
# get_registration (REQ-REG-F04)
# --------------------------------------------------------------------------- #
def _seed_confirmed(repo, user_id, event_id, amount=149.00):
    """Insert a confirmed record directly through the repository (no HTTP)."""
    from app.models import new_registration_record, utcnow_iso

    return repo.create_if_allowed(
        user_id,
        event_id,
        capacity=100,
        make_record=lambda: new_registration_record(
            user_id, event_id, amount, utcnow_iso()
        ),
    )


def test_get_registration_returns_contract_fields_REQ_REG_F04(service, repo):
    """get_registration returns the seven contract fields for an existing record."""
    user_id, event_id = _ids()
    record = _seed_confirmed(repo, user_id, event_id)

    result = service.get_registration(record["id"])

    assert set(result) == {
        "id", "user_id", "event_id", "amount", "status", "created_at", "updated_at",
    }
    assert result["id"] == record["id"]
    assert result["user_id"] == user_id
    assert result["event_id"] == event_id
    assert result["status"] == CONFIRMED


def test_get_registration_absent_maps_not_found_REQ_REG_F04(service):
    """A missing id raises ServiceError NOT_FOUND (REQ-REG-F04-AC2)."""
    with pytest.raises(ServiceError) as excinfo:
        service.get_registration(str(uuid.uuid4()))

    assert excinfo.value.code == errors.NOT_FOUND


# --------------------------------------------------------------------------- #
# list_registrations — filters, total, pagination (REQ-REG-F05)
# --------------------------------------------------------------------------- #
def test_list_combined_filters_and_logic_with_total_REQ_REG_F05(service, repo):
    """Combined user_id + event_id + status filters apply with AND logic; total post-filter."""
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    event_x, event_y = str(uuid.uuid4()), str(uuid.uuid4())
    now = "2026-10-15T09:30:00.000000Z"

    # user_a @ event_x confirmed  -> the match we expect
    _seed_confirmed(repo, user_a, event_x)
    # user_a @ event_y confirmed  -> excluded by event_id
    _seed_confirmed(repo, user_a, event_y)
    # user_b @ event_x confirmed  -> excluded by user_id
    _seed_confirmed(repo, user_b, event_x)
    # user_b @ event_y confirmed then cancelled -> a cancelled row excluded by status
    cancelled = _seed_confirmed(repo, user_b, event_y)
    repo.set_status(cancelled["id"], "cancelled", now)

    result = service.list_registrations(
        {"user_id": user_a, "event_id": event_x, "status": CONFIRMED},
        page=1,
        page_size=20,
    )

    assert result["total"] == 1
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["user_id"] == user_a
    assert item["event_id"] == event_x
    assert item["status"] == CONFIRMED


def test_list_total_reflects_filtered_count_before_pagination_REQ_REG_F05(service, repo):
    """total is the filtered count before slicing (REQ-REG-F05-AC6)."""
    event_id = str(uuid.uuid4())
    for _ in range(5):
        _seed_confirmed(repo, str(uuid.uuid4()), event_id)
    # Noise on another event that must not be counted.
    _seed_confirmed(repo, str(uuid.uuid4()), str(uuid.uuid4()))

    result = service.list_registrations(
        {"event_id": event_id}, page=1, page_size=2
    )

    assert result["total"] == 5
    assert len(result["items"]) == 2
    assert result["page"] == 1
    assert result["page_size"] == 2


def test_list_invalid_status_filter_maps_validation_error_REQ_REG_F05(service, repo):
    """An unknown status filter raises ServiceError VALIDATION_ERROR (422) (REQ-REG-F05-AC5)."""
    with pytest.raises(ServiceError) as excinfo:
        service.list_registrations(
            {"status": "pending"}, page=1, page_size=20
        )

    assert excinfo.value.code == errors.VALIDATION_ERROR


def test_list_page_beyond_last_returns_empty_items_REQ_REG_F05(service, repo):
    """A page beyond the last returns empty items with the correct total."""
    event_id = str(uuid.uuid4())
    for _ in range(3):
        _seed_confirmed(repo, str(uuid.uuid4()), event_id)

    result = service.list_registrations(
        {"event_id": event_id}, page=99, page_size=20
    )

    assert result["items"] == []
    assert result["total"] == 3
    assert result["page"] == 99
    assert result["page_size"] == 20


def test_list_no_filters_returns_all_REQ_REG_F05(service, repo):
    """No filters returns every record; None-valued filters are ignored."""
    for _ in range(4):
        _seed_confirmed(repo, str(uuid.uuid4()), str(uuid.uuid4()))

    result = service.list_registrations(
        {"user_id": None, "event_id": None, "status": None}, page=1, page_size=20
    )

    assert result["total"] == 4
    assert len(result["items"]) == 4


# --------------------------------------------------------------------------- #
# patch_status — transitions and seat freeing (REQ-REG-F06, REQ-REG-B07, F10)
# --------------------------------------------------------------------------- #
def test_patch_status_absent_maps_not_found_REQ_REG_F06(service):
    """PATCH on a missing id raises ServiceError NOT_FOUND (REQ-REG-F06-AC4)."""
    with pytest.raises(ServiceError) as excinfo:
        service.patch_status(str(uuid.uuid4()), "cancelled")

    assert excinfo.value.code == errors.NOT_FOUND


@responses.activate
def test_patch_status_confirmed_to_cancelled_ok_and_frees_seat_REQ_REG_B07(service, repo):
    """confirmed -> cancelled succeeds and frees a seat (REQ-REG-B07-AC1/AC4).

    With capacity 1, cancelling the only confirmed registration must let a fresh
    registration for the same event succeed (the seat is freed).
    """
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    # Capacity 1: seed a confirmed registration directly through the repository.
    record = _seed_confirmed(repo, user_a, event_id)
    assert repo.count_confirmed(event_id) == 1

    result = service.patch_status(record["id"], "cancelled")

    assert result["status"] == "cancelled"
    # The seat is freed: the confirmed count for the event drops to zero.
    assert repo.count_confirmed(event_id) == 0

    # A new registration for the same capacity-1 event now succeeds.
    _mock_user_ok(user_b)
    _mock_event_ok(event_id, capacity=1)

    new_record = service.create_registration(
        {"user_id": user_b, "event_id": event_id}
    )

    assert new_record["status"] == CONFIRMED
    assert repo.count_confirmed(event_id) == 1


def test_patch_status_cancelled_to_confirmed_maps_invalid_transition_REQ_REG_B07(service, repo):
    """cancelled -> confirmed (reactivation) raises INVALID_STATUS_TRANSITION (REQ-REG-B07-AC2)."""
    user_id, event_id = _ids()
    record = _seed_confirmed(repo, user_id, event_id)
    # Move it to cancelled first.
    service.patch_status(record["id"], "cancelled")

    with pytest.raises(ServiceError) as excinfo:
        service.patch_status(record["id"], "confirmed")

    assert excinfo.value.code == errors.INVALID_STATUS_TRANSITION
    # The record stays cancelled: no reactivation happened (REQ-REG-B07-AC5).
    assert repo.get(record["id"])["status"] == "cancelled"


@pytest.mark.parametrize("status", ["confirmed", "cancelled"])
def test_patch_status_same_status_is_noop_updated_at_unchanged_REQ_REG_B07(
    service, repo, status
):
    """Same-status PATCH is a no-op: updated_at is left unchanged (REQ-REG-B07-AC3)."""
    user_id, event_id = _ids()
    record = _seed_confirmed(repo, user_id, event_id)
    if status == "cancelled":
        service.patch_status(record["id"], "cancelled")

    before = repo.get(record["id"])
    updated_at_before = before["updated_at"]

    result = service.patch_status(record["id"], status)

    assert result["status"] == status
    # No-op must not refresh updated_at (REQ-REG-B07-AC3).
    assert repo.get(record["id"])["updated_at"] == updated_at_before
    assert result["updated_at"] == updated_at_before


def test_patch_status_transition_refreshes_updated_at_REQ_REG_F10(service, repo, monkeypatch):
    """A real confirmed -> cancelled transition refreshes updated_at (REQ-REG-F10-AC4)."""
    user_id, event_id = _ids()
    record = _seed_confirmed(repo, user_id, event_id)
    created_updated_at = repo.get(record["id"])["updated_at"]

    # Monkeypatch utcnow_iso used by the service so the new timestamp is distinct
    # and deterministic.
    new_ts = "2099-01-01T00:00:00.000000Z"
    monkeypatch.setattr("app.service.utcnow_iso", lambda: new_ts)

    result = service.patch_status(record["id"], "cancelled")

    assert result["updated_at"] == new_ts
    assert result["updated_at"] != created_updated_at
    assert repo.get(record["id"])["updated_at"] == new_ts
