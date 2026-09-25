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


# =========================================================================== #
# T-10 — get_event, list_events and filters (B06)
# =========================================================================== #
def _seed_record(status: str, city: str) -> dict:
    """Build a stored event record directly (no HTTP), for list/get tests."""
    event_id = str(uuid.uuid4())
    return {
        "id": event_id,
        "title": "Seeded Event",
        "description": None,
        "organizer_id": str(uuid.uuid4()),
        "venue": "Main Hall",
        "city": city,
        "start_date": "2026-10-15",
        "end_date": "2026-10-17",
        "capacity": 100,
        "price": 49.9,
        "status": status,
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


# --------------------------------------------------------------------------- #
# get_event (REQ-EVT-F05)
# --------------------------------------------------------------------------- #
def test_get_event_returns_contract_shape_when_present(svc, repo):
    """REQ-EVT-F05: get_event returns the stored event as the 13 contract fields."""
    record = _seed_record("draft", "Rome")
    repo.create(record)

    result = svc.get_event(record["id"])

    assert set(result.keys()) == {
        "id", "title", "description", "organizer_id", "venue", "city",
        "start_date", "end_date", "capacity", "price", "status",
        "created_at", "updated_at",
    }
    assert result["id"] == record["id"]
    assert result["status"] == "draft"


def test_get_event_absent_raises_not_found_404(svc):
    """REQ-EVT-F05: an unknown id raises NOT_FOUND (404)."""
    with pytest.raises(ServiceError) as exc_info:
        svc.get_event(str(uuid.uuid4()))

    assert exc_info.value.code == errors.NOT_FOUND
    assert exc_info.value.status == 404


@responses.activate
def test_get_event_makes_no_http_call(svc, repo):
    """REQ-EVT-F05: reading an event never contacts the user-service."""
    record = _seed_record("published", "Milan")
    repo.create(record)

    svc.get_event(record["id"])

    assert len(responses.calls) == 0


# --------------------------------------------------------------------------- #
# list_events — combined filters + correct total (REQ-EVT-F06, REQ-EVT-B06)
# --------------------------------------------------------------------------- #
def test_list_events_combined_status_and_city_filters_and_total(svc, repo):
    """REQ-EVT-B06: status AND city filters combine; total is post-filter count."""
    repo.create(_seed_record("published", "Rome"))
    repo.create(_seed_record("published", "Rome"))
    repo.create(_seed_record("draft", "Rome"))
    repo.create(_seed_record("published", "Milan"))

    result = svc.list_events({"status": "published", "city": "Rome"}, page=1, page_size=20)

    # Only the two published/Rome records match the AND filter.
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert all(item["status"] == "published" and item["city"] == "Rome" for item in result["items"])


def test_list_events_no_filters_returns_all(svc, repo):
    """REQ-EVT-F05: an empty filter dict returns every event."""
    for _ in range(3):
        repo.create(_seed_record("draft", "Rome"))

    result = svc.list_events({}, page=1, page_size=20)

    assert result["total"] == 3
    assert len(result["items"]) == 3
    assert result["page"] == 1
    assert result["page_size"] == 20


def test_list_events_items_have_contract_shape(svc, repo):
    """REQ-EVT-F05: listed items are serialised to the 13 contract fields."""
    repo.create(_seed_record("draft", "Rome"))

    result = svc.list_events({}, page=1, page_size=20)

    assert set(result["items"][0].keys()) == {
        "id", "title", "description", "organizer_id", "venue", "city",
        "start_date", "end_date", "capacity", "price", "status",
        "created_at", "updated_at",
    }


# --------------------------------------------------------------------------- #
# list_events — invalid status filter -> VALIDATION_ERROR (422) (REQ-EVT-B06)
# --------------------------------------------------------------------------- #
def test_list_events_invalid_status_filter_raises_validation_error(svc, repo):
    """REQ-EVT-B06: an unrecognised status filter value maps to VALIDATION_ERROR (422)."""
    repo.create(_seed_record("draft", "Rome"))

    with pytest.raises(ServiceError) as exc_info:
        svc.list_events({"status": "archived"}, page=1, page_size=20)

    assert exc_info.value.code == errors.VALIDATION_ERROR
    assert exc_info.value.status == 422


def test_list_events_none_status_filter_is_not_validated(svc, repo):
    """REQ-EVT-B06: a status filter of None imposes no constraint (returns all)."""
    repo.create(_seed_record("draft", "Rome"))
    repo.create(_seed_record("published", "Rome"))

    result = svc.list_events({"status": None, "city": None}, page=1, page_size=20)

    assert result["total"] == 2


# --------------------------------------------------------------------------- #
# list_events — page beyond the last -> empty items (REQ-EVT-F06)
# --------------------------------------------------------------------------- #
def test_list_events_page_beyond_last_returns_empty_items_with_total(svc, repo):
    """REQ-EVT-F06: a page past the end returns empty items but the correct total."""
    for _ in range(3):
        repo.create(_seed_record("draft", "Rome"))

    result = svc.list_events({}, page=2, page_size=20)

    assert result["items"] == []
    assert result["total"] == 3
    assert result["page"] == 2
    assert result["page_size"] == 20


def test_list_events_pagination_slices_within_total(svc, repo):
    """REQ-EVT-F06: total is pre-pagination; a full page returns page_size items."""
    for _ in range(5):
        repo.create(_seed_record("draft", "Rome"))

    result = svc.list_events({}, page=1, page_size=2)

    assert len(result["items"]) == 2
    assert result["total"] == 5


# =========================================================================== #
# T-11 — replace_event (PUT), update_event (PATCH), check_transition (B04)
# =========================================================================== #
def _put_body(organizer_id: str, **overrides) -> dict:
    """A full EventCreate-shaped PUT body; ``overrides`` tweak individual fields."""
    body = _valid_create_body(organizer_id)
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# check_transition — state machine (REQ-EVT-B04)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "current,new",
    [("draft", "published"), ("draft", "cancelled"), ("published", "cancelled")],
)
def test_check_transition_allows_valid_transitions(svc, current, new):
    """REQ-EVT-B04: the three allowed transitions do not raise."""
    svc.check_transition(current, new)  # must not raise


@pytest.mark.parametrize(
    "current,new",
    [
        ("published", "draft"),
        ("cancelled", "draft"),
        ("cancelled", "published"),
    ],
)
def test_check_transition_rejects_invalid_transitions(svc, current, new):
    """REQ-EVT-B04: a disallowed pair raises INVALID_STATUS_TRANSITION (422)."""
    with pytest.raises(ServiceError) as exc_info:
        svc.check_transition(current, new)
    assert exc_info.value.code == errors.INVALID_STATUS_TRANSITION
    assert exc_info.value.status == 422


@pytest.mark.parametrize("status", ["draft", "published", "cancelled"])
def test_check_transition_unchanged_state_is_noop(svc, status):
    """REQ-EVT-B04-AC5: new == current is a no-op (unchanged state accepted)."""
    svc.check_transition(status, status)  # must not raise


def test_check_transition_absent_status_is_noop(svc):
    """REQ-EVT-B04-AC5: an absent status (None) is a no-op, never a transition."""
    svc.check_transition("published", None)  # must not raise


# --------------------------------------------------------------------------- #
# replace_event — PUT (REQ-EVT-F07)
# --------------------------------------------------------------------------- #
@responses.activate
def test_replace_event_updates_fields_and_preserves_id_created_at(svc, repo, monkeypatch):
    """REQ-EVT-F07/F11: PUT replaces mutable fields, keeps id/created_at, bumps updated_at."""
    created_at = "2026-10-15T09:30:00.000000Z"
    record = _seed_record("draft", "Rome")
    record["created_at"] = created_at
    record["updated_at"] = created_at
    repo.create(record)

    later = "2026-10-16T12:00:00.000000Z"
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: later)

    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"), status=200,
    )

    result = svc.replace_event(record["id"], _put_body(organizer_id, title="Replaced Title"))

    assert result["id"] == record["id"]              # id preserved
    assert result["created_at"] == created_at         # created_at immutable
    assert result["updated_at"] == later              # updated_at refreshed
    assert result["title"] == "Replaced Title"
    assert result["organizer_id"] == organizer_id


@responses.activate
def test_replace_event_applies_post_style_defaults_for_omitted_optionals(svc, repo, monkeypatch):
    """REQ-EVT-F07: PUT is a full replacement — omitted status/description take POST defaults."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("draft", "Rome")
    record["description"] = "old description"
    repo.create(record)

    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"), status=200,
    )
    body = _put_body(organizer_id)  # no status, no description

    result = svc.replace_event(record["id"], body)

    assert result["status"] == "draft"        # default
    assert result["description"] is None       # default (full replacement)


def test_replace_event_absent_raises_not_found_404(svc):
    """REQ-EVT-F07: PUT on an unknown id raises NOT_FOUND (404)."""
    with pytest.raises(ServiceError) as exc_info:
        svc.replace_event(str(uuid.uuid4()), _put_body(str(uuid.uuid4())))
    assert exc_info.value.code == errors.NOT_FOUND
    assert exc_info.value.status == 404


@responses.activate
def test_replace_event_draft_to_published_ok(svc, repo, monkeypatch):
    """REQ-EVT-B04: PUT changing status draft->published is accepted."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("draft", "Rome")
    repo.create(record)
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"), status=200,
    )

    result = svc.replace_event(record["id"], _put_body(organizer_id, status="published"))

    assert result["status"] == "published"


@responses.activate
def test_replace_event_published_to_draft_rejected(svc, repo):
    """REQ-EVT-B04: PUT changing status published->draft is rejected (422)."""
    record = _seed_record("published", "Rome")
    repo.create(record)
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"), status=200,
    )

    with pytest.raises(ServiceError) as exc_info:
        svc.replace_event(record["id"], _put_body(organizer_id, status="draft"))

    assert exc_info.value.code == errors.INVALID_STATUS_TRANSITION
    assert exc_info.value.status == 422


@responses.activate
def test_replace_event_unchanged_state_accepted(svc, repo, monkeypatch):
    """REQ-EVT-B04-AC5: PUT keeping the same status (published) is accepted."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("published", "Rome")
    repo.create(record)
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"), status=200,
    )

    result = svc.replace_event(record["id"], _put_body(organizer_id, status="published"))

    assert result["status"] == "published"


@responses.activate
def test_replace_event_incoherent_dates_raises_before_http_call(svc, repo):
    """REQ-EVT-B03: PUT end<start -> VALIDATION_ERROR (422), no organizer call."""
    record = _seed_record("draft", "Rome")
    repo.create(record)
    organizer_id = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(organizer_id),
        json=_user_payload(organizer_id, "organizer"), status=200,
    )
    body = _put_body(organizer_id, start_date="2026-10-17", end_date="2026-10-15")

    with pytest.raises(ServiceError) as exc_info:
        svc.replace_event(record["id"], body)

    assert exc_info.value.code == errors.VALIDATION_ERROR
    assert len(responses.calls) == 0


# --------------------------------------------------------------------------- #
# update_event — PATCH (REQ-EVT-F08)
# --------------------------------------------------------------------------- #
def test_update_event_absent_raises_not_found_even_for_empty_body(svc):
    """REQ-EVT-F04-AC5: PATCH on a missing id is 404 even for an empty body {}."""
    with pytest.raises(ServiceError) as exc_info:
        svc.update_event(str(uuid.uuid4()), {})
    assert exc_info.value.code == errors.NOT_FOUND
    assert exc_info.value.status == 404


def test_update_event_empty_patch_unchanged_and_updated_at_not_bumped(svc, repo, monkeypatch):
    """REQ-EVT-F04-AC6: empty PATCH returns unchanged record, updated_at NOT bumped."""
    created_at = "2026-10-15T09:30:00.000000Z"
    record = _seed_record("draft", "Rome")
    record["created_at"] = created_at
    record["updated_at"] = created_at
    repo.create(record)

    # Clock would return a different value if the code (wrongly) bumped it.
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2099-01-01T00:00:00.000000Z")

    result = svc.update_event(record["id"], {})

    assert result["updated_at"] == created_at  # NOT bumped
    assert result["title"] == record["title"]


def test_update_event_applies_present_fields_and_bumps_updated_at(svc, repo, monkeypatch):
    """REQ-EVT-F08/F11: PATCH applies only present fields and refreshes updated_at."""
    created_at = "2026-10-15T09:30:00.000000Z"
    record = _seed_record("draft", "Rome")
    record["created_at"] = created_at
    record["updated_at"] = created_at
    repo.create(record)

    later = "2026-10-16T12:00:00.000000Z"
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: later)

    result = svc.update_event(record["id"], {"title": "Patched"})

    assert result["title"] == "Patched"
    assert result["city"] == "Rome"            # untouched
    assert result["created_at"] == created_at   # immutable
    assert result["updated_at"] == later        # bumped


def test_update_event_rejects_unknown_field(svc, repo):
    """REQ-EVT-F04-AC2: PATCH with an unknown field -> VALIDATION_ERROR (422)."""
    record = _seed_record("draft", "Rome")
    repo.create(record)

    with pytest.raises(ServiceError) as exc_info:
        svc.update_event(record["id"], {"bogus": "x"})

    assert exc_info.value.code == errors.VALIDATION_ERROR
    assert exc_info.value.status == 422


def test_update_event_draft_to_published_ok(svc, repo, monkeypatch):
    """REQ-EVT-B04: PATCH status draft->published is accepted."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("draft", "Rome")
    repo.create(record)

    result = svc.update_event(record["id"], {"status": "published"})

    assert result["status"] == "published"


def test_update_event_published_to_draft_rejected(svc, repo):
    """REQ-EVT-B04: PATCH status published->draft is rejected (422)."""
    record = _seed_record("published", "Rome")
    repo.create(record)

    with pytest.raises(ServiceError) as exc_info:
        svc.update_event(record["id"], {"status": "draft"})

    assert exc_info.value.code == errors.INVALID_STATUS_TRANSITION
    assert exc_info.value.status == 422


def test_update_event_same_status_is_noop_transition(svc, repo, monkeypatch):
    """REQ-EVT-B04-AC5: PATCH resending the current status is accepted (no-op transition)."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("published", "Rome")
    repo.create(record)

    result = svc.update_event(record["id"], {"status": "published"})

    assert result["status"] == "published"


def test_update_event_end_before_start_against_effective_record(svc, repo):
    """REQ-EVT-B03-AC3: PATCH re-validates end>=start against the merged record."""
    record = _seed_record("draft", "Rome")  # start 2026-10-15, end 2026-10-17
    repo.create(record)

    # Only end_date changes, to a value earlier than the STORED start_date.
    with pytest.raises(ServiceError) as exc_info:
        svc.update_event(record["id"], {"end_date": "2026-10-14"})

    assert exc_info.value.code == errors.VALIDATION_ERROR
    assert exc_info.value.status == 422


@responses.activate
def test_update_event_reverifies_organizer_only_when_changed(svc, repo, monkeypatch):
    """REQ-EVT-F04-AC7: PATCH re-verifies the organizer only when organizer_id changes."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("draft", "Rome")
    repo.create(record)

    new_organizer = str(uuid.uuid4())
    responses.add(
        responses.GET, _user_url(new_organizer),
        json=_user_payload(new_organizer, "organizer"), status=200,
    )

    result = svc.update_event(record["id"], {"organizer_id": new_organizer})

    assert result["organizer_id"] == new_organizer
    assert len(responses.calls) == 1  # organizer changed -> exactly one call


@responses.activate
def test_update_event_no_organizer_change_makes_no_http_call(svc, repo, monkeypatch):
    """REQ-EVT-F04-AC7: a PATCH not touching organizer_id issues no outbound call."""
    monkeypatch.setattr(service_module, "utcnow_iso", lambda: "2026-10-16T12:00:00.000000Z")
    record = _seed_record("draft", "Rome")
    repo.create(record)

    svc.update_event(record["id"], {"title": "Renamed"})

    assert len(responses.calls) == 0


@responses.activate
def test_update_event_invalid_new_organizer_raises_reference_not_found(svc, repo):
    """REQ-EVT-B01: PATCH to an unknown organizer_id -> REFERENCE_NOT_FOUND (422)."""
    record = _seed_record("draft", "Rome")
    repo.create(record)
    new_organizer = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(new_organizer), status=404)

    with pytest.raises(ServiceError) as exc_info:
        svc.update_event(record["id"], {"organizer_id": new_organizer})

    assert exc_info.value.code == errors.REFERENCE_NOT_FOUND
    assert exc_info.value.status == 422
