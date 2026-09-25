"""Unit tests for the repository abstraction and the memory backend.

Covers REQ-EVT-F14 (interchangeable persistence, memory branch of the factory)
and REQ-EVT-B06 (list filtering by ``status`` and ``city`` with AND logic).
The json/sqlite backends are exercised by their own tasks (T-06/T-07); here we
focus on the ABC contract, the factory ``memory`` branch, and CRUD + filtering
on :class:`MemoryEventRepository`.
"""
from __future__ import annotations

import threading

import pytest

from app.backends.memory import MemoryEventRepository
from app.models import new_event_record, utcnow_iso
from app.repository import AbstractEventRepository, get_repository


def _record(
    *,
    title: str = "PyConf",
    city: str = "Roma",
    status: str = "draft",
    organizer_id: str = "11111111-1111-4111-8111-111111111111",
) -> dict:
    rec = new_event_record(
        {
            "title": title,
            "organizer_id": organizer_id,
            "venue": "Auditorium",
            "city": city,
            "start_date": "2026-10-15",
            "end_date": "2026-10-16",
            "capacity": 100,
            "price": 0,
        },
        utcnow_iso(),
    )
    rec["status"] = status
    return rec


# --------------------------------------------------------------------------- #
# Factory — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_get_repository_memory_returns_memory_backend():
    """REQ-EVT-F14-AC1: the memory branch returns a MemoryEventRepository."""
    repo = get_repository("memory", data_dir=None)
    assert isinstance(repo, MemoryEventRepository)
    assert isinstance(repo, AbstractEventRepository)


def test_get_repository_unknown_backend_raises():
    """REQ-EVT-F14: an unrecognised backend name is rejected with ValueError."""
    with pytest.raises(ValueError):
        get_repository("cassandra", data_dir=None)


# --------------------------------------------------------------------------- #
# create / get — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_create_and_get_roundtrip():
    """REQ-EVT-F14: a created event is retrievable by its id."""
    repo = MemoryEventRepository()
    rec = _record()
    created = repo.create(rec)
    assert created["id"] == rec["id"]
    assert repo.get(rec["id"]) == rec


def test_get_missing_returns_none():
    """REQ-EVT-F14: fetching an unknown id returns None."""
    repo = MemoryEventRepository()
    assert repo.get("does-not-exist") is None


# --------------------------------------------------------------------------- #
# list_all + filters — REQ-EVT-B06
# --------------------------------------------------------------------------- #
def test_list_all_without_filters_returns_everything():
    """REQ-EVT-B06: an empty filter set returns every stored record."""
    repo = MemoryEventRepository()
    repo.create(_record(title="A"))
    repo.create(_record(title="B"))
    assert len(repo.list_all({})) == 2


def test_list_all_filters_by_status():
    """REQ-EVT-B06-AC1: only events with the requested status are returned."""
    repo = MemoryEventRepository()
    repo.create(_record(status="draft"))
    repo.create(_record(status="published"))
    repo.create(_record(status="published"))
    result = repo.list_all({"status": "published"})
    assert len(result) == 2
    assert all(r["status"] == "published" for r in result)


def test_list_all_filters_by_city():
    """REQ-EVT-B06-AC3: only events in the requested city are returned."""
    repo = MemoryEventRepository()
    repo.create(_record(city="Roma"))
    repo.create(_record(city="Milano"))
    result = repo.list_all({"city": "Roma"})
    assert len(result) == 1
    assert result[0]["city"] == "Roma"


def test_list_all_combines_status_and_city_with_and_logic():
    """REQ-EVT-B06-AC4: status and city filters are combined with AND logic."""
    repo = MemoryEventRepository()
    repo.create(_record(status="published", city="Roma"))
    repo.create(_record(status="published", city="Milano"))
    repo.create(_record(status="draft", city="Roma"))
    result = repo.list_all({"status": "published", "city": "Roma"})
    assert len(result) == 1
    assert result[0]["status"] == "published"
    assert result[0]["city"] == "Roma"


def test_list_all_none_filter_values_are_ignored():
    """REQ-EVT-B06: filter keys set to None do not exclude any record."""
    repo = MemoryEventRepository()
    repo.create(_record(status="draft", city="Roma"))
    assert len(repo.list_all({"status": None, "city": None})) == 1


# --------------------------------------------------------------------------- #
# update — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_update_applies_changes_and_returns_record():
    """REQ-EVT-F14: update mutates only the given fields and returns the record."""
    repo = MemoryEventRepository()
    rec = _record(title="Old")
    repo.create(rec)
    updated = repo.update(rec["id"], {"title": "New", "status": "published"})
    assert updated["title"] == "New"
    assert updated["status"] == "published"
    assert repo.get(rec["id"])["title"] == "New"


def test_update_missing_returns_none():
    """REQ-EVT-F14: updating an unknown id returns None (no record created)."""
    repo = MemoryEventRepository()
    assert repo.update("does-not-exist", {"title": "X"}) is None


# --------------------------------------------------------------------------- #
# delete — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_delete_removes_record_and_reports_true():
    """REQ-EVT-F14: deleting an existing event returns True and removes it."""
    repo = MemoryEventRepository()
    rec = _record()
    repo.create(rec)
    assert repo.delete(rec["id"]) is True
    assert repo.get(rec["id"]) is None


def test_delete_missing_reports_false():
    """REQ-EVT-F14: deleting an unknown id returns False."""
    repo = MemoryEventRepository()
    assert repo.delete("does-not-exist") is False


# --------------------------------------------------------------------------- #
# concurrency — design §10 (RLock per instance)
# --------------------------------------------------------------------------- #
def test_concurrent_creates_are_all_persisted():
    """REQ-EVT-F14 / design §10: concurrent creates under the lock all persist."""
    repo = MemoryEventRepository()
    records = [_record(title=f"E{i}") for i in range(50)]

    def worker(record: dict) -> None:
        repo.create(record)

    threads = [threading.Thread(target=worker, args=(r,)) for r in records]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(repo.list_all({})) == 50
