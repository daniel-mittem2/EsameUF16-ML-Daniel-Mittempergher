"""Unit tests for :class:`app.backends.sqlite_backend.SqliteEventRepository`.

Covers REQ-EVT-F14 (interchangeable persistence, SQLite branch): CRUD semantics
matching the memory/JSON backends, ``status``/``city`` AND filtering with
``None`` values ignored (REQ-EVT-B06), round-tripping of all thirteen event
fields (including a nullable ``description``), and persistence verified by
reopening the database on a fresh instance (REQ-EVT-F14-AC3). All file-based
tests use ``tmp_path`` so no ``events.db`` leaks into the working tree.
"""
from __future__ import annotations

import threading

import pytest

from app.backends.sqlite_backend import SqliteEventRepository
from app.models import new_event_record, utcnow_iso
from app.repository import AbstractEventRepository, get_repository


def _record(
    *,
    title: str = "PyConf",
    city: str = "Roma",
    status: str = "draft",
    description=None,
    organizer_id: str = "11111111-1111-4111-8111-111111111111",
) -> dict:
    rec = new_event_record(
        {
            "title": title,
            "description": description,
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
def test_get_repository_sqlite_returns_sqlite_backend(tmp_path):
    """REQ-EVT-F14-AC3: the sqlite branch returns a SqliteEventRepository."""
    repo = get_repository("sqlite", data_dir=tmp_path)
    assert isinstance(repo, SqliteEventRepository)
    assert isinstance(repo, AbstractEventRepository)


def test_get_repository_sqlite_creates_data_dir(tmp_path):
    """REQ-EVT-F14: the factory creates the data directory when absent."""
    data_dir = tmp_path / "nested" / "data"
    assert not data_dir.exists()
    get_repository("sqlite", data_dir=data_dir)
    assert data_dir.exists()


def test_db_file_lives_in_data_dir(tmp_path):
    """REQ-EVT-F14-AC3: the sqlite branch stores ``events.db`` in the data dir."""
    get_repository("sqlite", data_dir=tmp_path)
    assert (tmp_path / "events.db").exists()


# --------------------------------------------------------------------------- #
# create / get — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_create_and_get_roundtrip(tmp_path):
    """REQ-EVT-F14: a created event is retrievable by its id."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record()
    created = repo.create(rec)
    assert created["id"] == rec["id"]
    assert repo.get(rec["id"]) == rec


def test_get_missing_returns_none(tmp_path):
    """REQ-EVT-F14: fetching an unknown id returns None."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    assert repo.get("does-not-exist") is None


def test_absent_db_is_empty_collection(tmp_path):
    """REQ-EVT-F14-AC3: opening a fresh database yields an empty repo."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    assert repo.list_all({}) == []


def test_all_thirteen_fields_roundtrip(tmp_path):
    """REQ-EVT-F14: every contract field survives a create/get round-trip."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record(description="A full description", status="published")
    repo.create(rec)
    reloaded = repo.get(rec["id"])
    assert reloaded == rec
    assert set(reloaded.keys()) == set(rec.keys())
    assert len(reloaded) == 13


def test_nullable_description_roundtrips_as_none(tmp_path):
    """REQ-EVT-F14: a ``None`` description is stored and read back as ``None``."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record(description=None)
    repo.create(rec)
    reloaded = repo.get(rec["id"])
    assert reloaded["description"] is None


# --------------------------------------------------------------------------- #
# list_all + filters — REQ-EVT-B06 (memory/JSON-parity)
# --------------------------------------------------------------------------- #
def test_list_all_without_filters_returns_everything(tmp_path):
    """REQ-EVT-B06: an empty filter set returns every stored record."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    repo.create(_record(title="A"))
    repo.create(_record(title="B"))
    assert len(repo.list_all({})) == 2


def test_list_all_filters_by_status(tmp_path):
    """REQ-EVT-B06-AC1: only events with the requested status are returned."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    repo.create(_record(status="draft"))
    repo.create(_record(status="published"))
    repo.create(_record(status="published"))
    result = repo.list_all({"status": "published"})
    assert len(result) == 2
    assert all(r["status"] == "published" for r in result)


def test_list_all_filters_by_city(tmp_path):
    """REQ-EVT-B06-AC3: only events in the requested city are returned."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    repo.create(_record(city="Roma"))
    repo.create(_record(city="Milano"))
    result = repo.list_all({"city": "Roma"})
    assert len(result) == 1
    assert result[0]["city"] == "Roma"


def test_list_all_combines_status_and_city_with_and_logic(tmp_path):
    """REQ-EVT-B06-AC4: status and city filters are combined with AND logic."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    repo.create(_record(status="published", city="Roma"))
    repo.create(_record(status="published", city="Milano"))
    repo.create(_record(status="draft", city="Roma"))
    result = repo.list_all({"status": "published", "city": "Roma"})
    assert len(result) == 1
    assert result[0]["status"] == "published"
    assert result[0]["city"] == "Roma"


def test_list_all_none_filter_values_are_ignored(tmp_path):
    """REQ-EVT-F14 / REQ-EVT-B06: filter keys set to None exclude nothing."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    repo.create(_record(status="draft", city="Roma"))
    assert len(repo.list_all({"status": None, "city": None})) == 1


# --------------------------------------------------------------------------- #
# update / delete — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_update_applies_changes_and_returns_record(tmp_path):
    """REQ-EVT-F14: update mutates only the given fields and returns the record."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record(title="Old")
    repo.create(rec)
    updated = repo.update(rec["id"], {"title": "New", "status": "published"})
    assert updated["title"] == "New"
    assert updated["status"] == "published"
    assert repo.get(rec["id"])["title"] == "New"


def test_update_can_set_description_to_none(tmp_path):
    """REQ-EVT-F14: update may clear the nullable description back to None."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record(description="present")
    repo.create(rec)
    updated = repo.update(rec["id"], {"description": None})
    assert updated["description"] is None


def test_update_missing_returns_none(tmp_path):
    """REQ-EVT-F14: updating an unknown id returns None (no record created)."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    assert repo.update("does-not-exist", {"title": "X"}) is None


def test_update_with_no_known_fields_leaves_record_unchanged(tmp_path):
    """REQ-EVT-F14: an update with no persistable fields returns the record as-is."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record(title="Stable")
    repo.create(rec)
    updated = repo.update(rec["id"], {})
    assert updated["title"] == "Stable"


def test_delete_removes_record_and_reports_true(tmp_path):
    """REQ-EVT-F14: deleting an existing event returns True and removes it."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    rec = _record()
    repo.create(rec)
    assert repo.delete(rec["id"]) is True
    assert repo.get(rec["id"]) is None


def test_delete_missing_reports_false(tmp_path):
    """REQ-EVT-F14: deleting an unknown id returns False."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    assert repo.delete("does-not-exist") is False


# --------------------------------------------------------------------------- #
# Persistence on reopen — REQ-EVT-F14-AC3
# --------------------------------------------------------------------------- #
def test_data_persists_across_reopen(tmp_path):
    """REQ-EVT-F14-AC3: a fresh instance reading the same db sees prior data."""
    path = tmp_path / "events.db"
    first = SqliteEventRepository(path)
    rec = _record(title="Persisted", city="Torino", status="published",
                  description="kept on disk")
    first.create(rec)
    first.close()

    second = SqliteEventRepository(path)
    reloaded = second.get(rec["id"])
    assert reloaded is not None
    assert reloaded == rec
    assert reloaded["description"] == "kept on disk"
    assert len(second.list_all({})) == 1


def test_delete_persists_across_reopen(tmp_path):
    """REQ-EVT-F14-AC3: a delete is durable and visible after reopening."""
    path = tmp_path / "events.db"
    first = SqliteEventRepository(path)
    rec = _record()
    first.create(rec)
    first.delete(rec["id"])
    first.close()

    second = SqliteEventRepository(path)
    assert second.get(rec["id"]) is None
    assert second.list_all({}) == []


def test_update_persists_across_reopen(tmp_path):
    """REQ-EVT-F14-AC3: an update is durable and visible after reopening."""
    path = tmp_path / "events.db"
    first = SqliteEventRepository(path)
    rec = _record(title="Before")
    first.create(rec)
    first.update(rec["id"], {"title": "After", "status": "published"})
    first.close()

    second = SqliteEventRepository(path)
    reloaded = second.get(rec["id"])
    assert reloaded["title"] == "After"
    assert reloaded["status"] == "published"


# --------------------------------------------------------------------------- #
# concurrency — design §10 (RLock per instance)
# --------------------------------------------------------------------------- #
def test_concurrent_creates_are_all_persisted(tmp_path):
    """REQ-EVT-F14 / design §10: concurrent creates under the lock all persist."""
    repo = SqliteEventRepository(tmp_path / "events.db")
    records = [_record(title=f"E{i}") for i in range(50)]

    def worker(record: dict) -> None:
        repo.create(record)

    threads = [threading.Thread(target=worker, args=(r,)) for r in records]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(repo.list_all({})) == 50
