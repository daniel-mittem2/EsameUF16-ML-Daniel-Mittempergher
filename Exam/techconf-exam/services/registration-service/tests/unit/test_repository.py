"""Unit tests for the repository abstraction and the memory backend.

Covers REQ-REG-F13 (interchangeable persistence, memory branch of the factory),
REQ-REG-B04 (no double confirmed registration), REQ-REG-B05 (event capacity),
REQ-REG-B07 (status transition write) and REQ-REG-B08 (confirmed count for
stats). The json/sqlite backends are exercised by their own tasks (T-06/T-07);
here we focus on the ABC contract, the factory ``memory`` branch, and the
atomic ``create_if_allowed`` + CRUD + counting on
:class:`MemoryRegistrationRepository`.
"""
from __future__ import annotations

import threading

import pytest

from app.backends.memory import MemoryRegistrationRepository
from app.models import new_registration_record, utcnow_iso
from app.repository import (
    AbstractRegistrationRepository,
    AlreadyRegisteredError,
    EventFullError,
    get_repository,
)

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
EVENT_X = "33333333-3333-4333-8333-333333333333"
EVENT_Y = "44444444-4444-4444-8444-444444444444"


def _maker(user_id: str, event_id: str, amount=149.0):
    """Return a ``make_record`` callback for ``create_if_allowed``."""

    def _make() -> dict:
        return new_registration_record(user_id, event_id, amount, utcnow_iso())

    return _make


# --------------------------------------------------------------------------- #
# Factory — REQ-REG-F13
# --------------------------------------------------------------------------- #
def test_get_repository_memory_returns_memory_backend():
    """REQ-REG-F13-AC1: the memory branch returns a MemoryRegistrationRepository."""
    repo = get_repository("memory", data_dir=None)
    assert isinstance(repo, MemoryRegistrationRepository)
    assert isinstance(repo, AbstractRegistrationRepository)


def test_get_repository_unknown_backend_raises():
    """REQ-REG-F13: an unrecognised backend name is rejected with ValueError."""
    with pytest.raises(ValueError):
        get_repository("cassandra", data_dir=None)


# --------------------------------------------------------------------------- #
# create_if_allowed — happy path (REQ-REG-B05-AC1)
# --------------------------------------------------------------------------- #
def test_create_if_allowed_creates_and_is_retrievable():
    """REQ-REG-B05-AC1: within capacity, the record is created and retrievable."""
    repo = MemoryRegistrationRepository()
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert record["status"] == "confirmed"
    assert record["user_id"] == USER_A
    assert record["event_id"] == EVENT_X
    assert repo.get(record["id"]) == record


# --------------------------------------------------------------------------- #
# create_if_allowed — duplicate confirmed (REQ-REG-B04)
# --------------------------------------------------------------------------- #
def test_create_if_allowed_duplicate_confirmed_raises_already_registered():
    """REQ-REG-B04-AC1: a second confirmed registration for the pair raises."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    with pytest.raises(AlreadyRegisteredError):
        repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    # only the first record persisted
    assert len(repo.list_all({})) == 1


def test_create_if_allowed_cancelled_does_not_block_new_registration():
    """REQ-REG-B04-AC2: a cancelled registration for the pair does not block a new one."""
    repo = MemoryRegistrationRepository()
    first = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.set_status(first["id"], "cancelled", utcnow_iso())
    second = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert second["status"] == "confirmed"
    assert second["id"] != first["id"]


def test_create_if_allowed_different_user_same_event_is_allowed():
    """REQ-REG-B04: the duplicate check is per (user_id, event_id) pair."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_X, capacity=10, make_record=_maker(USER_B, EVENT_X))
    assert len(repo.list_all({})) == 2


# --------------------------------------------------------------------------- #
# create_if_allowed — capacity (REQ-REG-B05)
# --------------------------------------------------------------------------- #
def test_create_if_allowed_event_full_raises():
    """REQ-REG-B05-AC2: at capacity, a further registration raises EventFullError."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=1, make_record=_maker(USER_A, EVENT_X))
    with pytest.raises(EventFullError):
        repo.create_if_allowed(USER_B, EVENT_X, capacity=1, make_record=_maker(USER_B, EVENT_X))
    assert repo.count_confirmed(EVENT_X) == 1


def test_create_if_allowed_cancelled_frees_a_seat():
    """REQ-REG-B05-AC3/B07-AC4: cancelling a confirmed registration frees a seat."""
    repo = MemoryRegistrationRepository()
    first = repo.create_if_allowed(USER_A, EVENT_X, capacity=1, make_record=_maker(USER_A, EVENT_X))
    # full now — cancel to free the seat
    repo.set_status(first["id"], "cancelled", utcnow_iso())
    second = repo.create_if_allowed(USER_B, EVENT_X, capacity=1, make_record=_maker(USER_B, EVENT_X))
    assert second["status"] == "confirmed"
    assert repo.count_confirmed(EVENT_X) == 1


# --------------------------------------------------------------------------- #
# get — REQ-REG-F13
# --------------------------------------------------------------------------- #
def test_get_missing_returns_none():
    """REQ-REG-F13: fetching an unknown id returns None."""
    repo = MemoryRegistrationRepository()
    assert repo.get("does-not-exist") is None


# --------------------------------------------------------------------------- #
# list_all + filters — REQ-REG-F05
# --------------------------------------------------------------------------- #
def test_list_all_without_filters_returns_everything():
    """REQ-REG-F05: an empty filter set returns every stored record."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_Y, capacity=10, make_record=_maker(USER_B, EVENT_Y))
    assert len(repo.list_all({})) == 2


def test_list_all_filters_by_user_id():
    """REQ-REG-F05-AC4: only records for the requested user_id are returned."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_Y, capacity=10, make_record=_maker(USER_B, EVENT_Y))
    result = repo.list_all({"user_id": USER_A})
    assert len(result) == 1
    assert result[0]["user_id"] == USER_A


def test_list_all_filters_by_event_id():
    """REQ-REG-F05-AC4: only records for the requested event_id are returned."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_Y, capacity=10, make_record=_maker(USER_B, EVENT_Y))
    result = repo.list_all({"event_id": EVENT_Y})
    assert len(result) == 1
    assert result[0]["event_id"] == EVENT_Y


def test_list_all_filters_by_status():
    """REQ-REG-F05-AC4: only records with the requested status are returned."""
    repo = MemoryRegistrationRepository()
    first = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_X, capacity=10, make_record=_maker(USER_B, EVENT_X))
    repo.set_status(first["id"], "cancelled", utcnow_iso())
    result = repo.list_all({"status": "cancelled"})
    assert len(result) == 1
    assert result[0]["id"] == first["id"]


def test_list_all_combines_filters_with_and_logic():
    """REQ-REG-F05-AC4: user_id, event_id and status filters combine with AND."""
    repo = MemoryRegistrationRepository()
    first = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_A, EVENT_Y, capacity=10, make_record=_maker(USER_A, EVENT_Y))
    repo.create_if_allowed(USER_B, EVENT_X, capacity=10, make_record=_maker(USER_B, EVENT_X))
    result = repo.list_all({"user_id": USER_A, "event_id": EVENT_X, "status": "confirmed"})
    assert len(result) == 1
    assert result[0]["id"] == first["id"]


def test_list_all_none_filter_values_are_ignored():
    """REQ-REG-F05: filter keys set to None do not exclude any record."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert len(repo.list_all({"user_id": None, "event_id": None, "status": None})) == 1


# --------------------------------------------------------------------------- #
# set_status — REQ-REG-B07
# --------------------------------------------------------------------------- #
def test_set_status_updates_status_and_updated_at():
    """REQ-REG-B07/F10: set_status writes the new status and refreshes updated_at."""
    repo = MemoryRegistrationRepository()
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    later = "2099-01-01T00:00:00.000000Z"
    updated = repo.set_status(record["id"], "cancelled", later)
    assert updated["status"] == "cancelled"
    assert updated["updated_at"] == later
    assert repo.get(record["id"])["status"] == "cancelled"


def test_set_status_missing_returns_none():
    """REQ-REG-B07: setting the status of an unknown id returns None."""
    repo = MemoryRegistrationRepository()
    assert repo.set_status("does-not-exist", "cancelled", utcnow_iso()) is None


# --------------------------------------------------------------------------- #
# delete — REQ-REG-F07
# --------------------------------------------------------------------------- #
def test_delete_removes_record_and_reports_true():
    """REQ-REG-F07: deleting an existing registration returns True and removes it."""
    repo = MemoryRegistrationRepository()
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert repo.delete(record["id"]) is True
    assert repo.get(record["id"]) is None


def test_delete_missing_reports_false():
    """REQ-REG-F07: deleting an unknown id returns False."""
    repo = MemoryRegistrationRepository()
    assert repo.delete("does-not-exist") is False


# --------------------------------------------------------------------------- #
# count_confirmed — REQ-REG-B08
# --------------------------------------------------------------------------- #
def test_count_confirmed_counts_only_confirmed_for_the_event():
    """REQ-REG-B08: count_confirmed counts only confirmed records for the event."""
    repo = MemoryRegistrationRepository()
    a = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_X, capacity=10, make_record=_maker(USER_B, EVENT_X))
    repo.create_if_allowed(USER_A, EVENT_Y, capacity=10, make_record=_maker(USER_A, EVENT_Y))
    repo.set_status(a["id"], "cancelled", utcnow_iso())
    assert repo.count_confirmed(EVENT_X) == 1
    assert repo.count_confirmed(EVENT_Y) == 1


def test_count_confirmed_unknown_event_is_zero():
    """REQ-REG-B08: an event with no registrations has zero confirmed."""
    repo = MemoryRegistrationRepository()
    assert repo.count_confirmed("no-such-event") == 0


# --------------------------------------------------------------------------- #
# concurrency — design §5 (no overselling under the lock)
# --------------------------------------------------------------------------- #
def test_concurrent_create_capacity_one_admits_exactly_one():
    """REQ-REG-B05-AC5 / design §5: capacity 1, many concurrent creates → one wins."""
    repo = MemoryRegistrationRepository()
    users = [f"{i:08d}-0000-4000-8000-000000000000" for i in range(30)]
    successes: list[dict] = []
    fulls: list[Exception] = []
    lock = threading.Lock()

    def worker(user_id: str) -> None:
        try:
            record = repo.create_if_allowed(
                user_id, EVENT_X, capacity=1, make_record=_maker(user_id, EVENT_X)
            )
            with lock:
                successes.append(record)
        except EventFullError as exc:
            with lock:
                fulls.append(exc)

    threads = [threading.Thread(target=worker, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(fulls) == 29
    assert repo.count_confirmed(EVENT_X) == 1


# --------------------------------------------------------------------------- #
# JsonRegistrationRepository — REQ-REG-F13-AC2 (persistence)
# --------------------------------------------------------------------------- #
from app.backends.json_backend import JsonRegistrationRepository  # noqa: E402


def _json_repo(tmp_path):
    """Return a JsonRegistrationRepository backed by a file under ``tmp_path``."""
    return JsonRegistrationRepository(tmp_path / "registrations.json")


def test_get_repository_json_returns_json_backend(tmp_path):
    """REQ-REG-F13-AC2: the json branch returns a JsonRegistrationRepository."""
    repo = get_repository("json", data_dir=tmp_path)
    assert isinstance(repo, JsonRegistrationRepository)
    assert isinstance(repo, AbstractRegistrationRepository)


def test_json_create_if_allowed_creates_and_is_retrievable(tmp_path):
    """REQ-REG-B05-AC1: within capacity, the record is created and retrievable."""
    repo = _json_repo(tmp_path)
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert record["status"] == "confirmed"
    assert repo.get(record["id"]) == record


def test_json_create_if_allowed_duplicate_confirmed_raises(tmp_path):
    """REQ-REG-B04-AC1: a second confirmed registration for the pair raises."""
    repo = _json_repo(tmp_path)
    repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    with pytest.raises(AlreadyRegisteredError):
        repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert len(repo.list_all({})) == 1


def test_json_create_if_allowed_event_full_raises(tmp_path):
    """REQ-REG-B05-AC2: at capacity, a further registration raises EventFullError."""
    repo = _json_repo(tmp_path)
    repo.create_if_allowed(USER_A, EVENT_X, capacity=1, make_record=_maker(USER_A, EVENT_X))
    with pytest.raises(EventFullError):
        repo.create_if_allowed(USER_B, EVENT_X, capacity=1, make_record=_maker(USER_B, EVENT_X))
    assert repo.count_confirmed(EVENT_X) == 1


def test_json_set_status_updates_and_persists(tmp_path):
    """REQ-REG-B07/F10: set_status writes the new status and refreshes updated_at."""
    repo = _json_repo(tmp_path)
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    later = "2099-01-01T00:00:00.000000Z"
    updated = repo.set_status(record["id"], "cancelled", later)
    assert updated["status"] == "cancelled"
    assert updated["updated_at"] == later


def test_json_set_status_missing_returns_none(tmp_path):
    """REQ-REG-B07: setting the status of an unknown id returns None."""
    repo = _json_repo(tmp_path)
    assert repo.set_status("does-not-exist", "cancelled", utcnow_iso()) is None


def test_json_list_all_combines_filters_with_and_logic(tmp_path):
    """REQ-REG-F05-AC4: user_id, event_id and status filters combine with AND."""
    repo = _json_repo(tmp_path)
    first = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_A, EVENT_Y, capacity=10, make_record=_maker(USER_A, EVENT_Y))
    repo.create_if_allowed(USER_B, EVENT_X, capacity=10, make_record=_maker(USER_B, EVENT_X))
    result = repo.list_all({"user_id": USER_A, "event_id": EVENT_X, "status": "confirmed"})
    assert len(result) == 1
    assert result[0]["id"] == first["id"]


def test_json_delete_removes_record_and_persists(tmp_path):
    """REQ-REG-F07: deleting an existing registration returns True and removes it."""
    repo = _json_repo(tmp_path)
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    assert repo.delete(record["id"]) is True
    assert repo.get(record["id"]) is None


def test_json_delete_missing_reports_false(tmp_path):
    """REQ-REG-F07: deleting an unknown id returns False."""
    repo = _json_repo(tmp_path)
    assert repo.delete("does-not-exist") is False


def test_json_count_confirmed_counts_only_confirmed(tmp_path):
    """REQ-REG-B08: count_confirmed counts only confirmed records for the event."""
    repo = _json_repo(tmp_path)
    a = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.create_if_allowed(USER_B, EVENT_X, capacity=10, make_record=_maker(USER_B, EVENT_X))
    repo.create_if_allowed(USER_A, EVENT_Y, capacity=10, make_record=_maker(USER_A, EVENT_Y))
    repo.set_status(a["id"], "cancelled", utcnow_iso())
    assert repo.count_confirmed(EVENT_X) == 1
    assert repo.count_confirmed(EVENT_Y) == 1


def test_json_data_persists_across_reopen(tmp_path):
    """REQ-REG-F13-AC2: data written by one instance survives reopening the file."""
    path = tmp_path / "registrations.json"
    repo = JsonRegistrationRepository(path)
    created = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.set_status(created["id"], "cancelled", "2099-01-01T00:00:00.000000Z")

    # Reopen a fresh instance against the same file — state must be restored.
    reopened = JsonRegistrationRepository(path)
    restored = reopened.get(created["id"])
    assert restored is not None
    assert restored["id"] == created["id"]
    assert restored["status"] == "cancelled"
    assert restored["updated_at"] == "2099-01-01T00:00:00.000000Z"
    assert len(reopened.list_all({})) == 1


def test_json_no_residual_tmp_file_after_writes(tmp_path):
    """REQ-REG-F13-AC2 / design §6: atomic write leaves no residual .tmp file."""
    path = tmp_path / "registrations.json"
    repo = JsonRegistrationRepository(path)
    record = repo.create_if_allowed(USER_A, EVENT_X, capacity=10, make_record=_maker(USER_A, EVENT_X))
    repo.set_status(record["id"], "cancelled", utcnow_iso())
    repo.delete(record["id"])

    tmp_path_file = path.with_name(path.name + ".tmp")
    assert not tmp_path_file.exists()
    # Only the canonical registrations.json is present in the data dir.
    leftover_tmp = list(tmp_path.glob("*.tmp"))
    assert leftover_tmp == []


def test_json_concurrent_create_capacity_one_admits_exactly_one(tmp_path):
    """REQ-REG-B05-AC5 / design §5: capacity 1, many concurrent creates → one wins."""
    repo = _json_repo(tmp_path)
    users = [f"{i:08d}-0000-4000-8000-000000000000" for i in range(20)]
    successes: list[dict] = []
    fulls: list[Exception] = []
    guard = threading.Lock()

    def worker(user_id: str) -> None:
        try:
            record = repo.create_if_allowed(
                user_id, EVENT_X, capacity=1, make_record=_maker(user_id, EVENT_X)
            )
            with guard:
                successes.append(record)
        except EventFullError as exc:
            with guard:
                fulls.append(exc)

    threads = [threading.Thread(target=worker, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(fulls) == 19
    assert repo.count_confirmed(EVENT_X) == 1
