"""Unit tests for :class:`app.backends.json_backend.JsonEventRepository`.

Covers REQ-EVT-F14 (interchangeable persistence, JSON branch): CRUD semantics
matching the memory backend, ``status``/``city`` AND filtering with ``None``
values ignored (REQ-EVT-B06), atomic writes that leave no ``.tmp`` residue, and
persistence verified by reopening the file on a fresh instance (REQ-EVT-F14-AC2).
"""
from __future__ import annotations

import json

import pytest

from app.backends.json_backend import JsonEventRepository
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
def test_get_repository_json_returns_json_backend(tmp_path):
    """REQ-EVT-F14-AC2: the json branch returns a JsonEventRepository."""
    repo = get_repository("json", data_dir=tmp_path)
    assert isinstance(repo, JsonEventRepository)
    assert isinstance(repo, AbstractEventRepository)


def test_get_repository_json_creates_data_dir(tmp_path):
    """REQ-EVT-F14: the factory creates the data directory when absent."""
    data_dir = tmp_path / "nested" / "data"
    assert not data_dir.exists()
    get_repository("json", data_dir=data_dir)
    assert data_dir.exists()


# --------------------------------------------------------------------------- #
# create / get — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_create_and_get_roundtrip(tmp_path):
    """REQ-EVT-F14: a created event is retrievable by its id."""
    repo = JsonEventRepository(tmp_path / "events.json")
    rec = _record()
    created = repo.create(rec)
    assert created["id"] == rec["id"]
    assert repo.get(rec["id"]) == rec


def test_get_missing_returns_none(tmp_path):
    """REQ-EVT-F14: fetching an unknown id returns None."""
    repo = JsonEventRepository(tmp_path / "events.json")
    assert repo.get("does-not-exist") is None


def test_absent_file_is_empty_collection(tmp_path):
    """REQ-EVT-F14-AC2: opening against a missing file yields an empty repo."""
    repo = JsonEventRepository(tmp_path / "events.json")
    assert repo.list_all({}) == []


# --------------------------------------------------------------------------- #
# list_all + filters — REQ-EVT-B06 (memory-parity)
# --------------------------------------------------------------------------- #
def test_list_all_filters_by_status(tmp_path):
    """REQ-EVT-B06-AC1: only events with the requested status are returned."""
    repo = JsonEventRepository(tmp_path / "events.json")
    repo.create(_record(status="draft"))
    repo.create(_record(status="published"))
    repo.create(_record(status="published"))
    result = repo.list_all({"status": "published"})
    assert len(result) == 2
    assert all(r["status"] == "published" for r in result)


def test_list_all_combines_status_and_city_with_and_logic(tmp_path):
    """REQ-EVT-B06-AC4: status and city filters are combined with AND logic."""
    repo = JsonEventRepository(tmp_path / "events.json")
    repo.create(_record(status="published", city="Roma"))
    repo.create(_record(status="published", city="Milano"))
    repo.create(_record(status="draft", city="Roma"))
    result = repo.list_all({"status": "published", "city": "Roma"})
    assert len(result) == 1
    assert result[0]["status"] == "published"
    assert result[0]["city"] == "Roma"


def test_list_all_none_filter_values_are_ignored(tmp_path):
    """REQ-EVT-F14 / REQ-EVT-B06: filter keys set to None exclude nothing."""
    repo = JsonEventRepository(tmp_path / "events.json")
    repo.create(_record(status="draft", city="Roma"))
    assert len(repo.list_all({"status": None, "city": None})) == 1


# --------------------------------------------------------------------------- #
# update / delete — REQ-EVT-F14
# --------------------------------------------------------------------------- #
def test_update_applies_changes_and_returns_record(tmp_path):
    """REQ-EVT-F14: update mutates only the given fields and returns the record."""
    repo = JsonEventRepository(tmp_path / "events.json")
    rec = _record(title="Old")
    repo.create(rec)
    updated = repo.update(rec["id"], {"title": "New", "status": "published"})
    assert updated["title"] == "New"
    assert updated["status"] == "published"
    assert repo.get(rec["id"])["title"] == "New"


def test_update_missing_returns_none(tmp_path):
    """REQ-EVT-F14: updating an unknown id returns None (no record created)."""
    repo = JsonEventRepository(tmp_path / "events.json")
    assert repo.update("does-not-exist", {"title": "X"}) is None


def test_delete_removes_record_and_reports_true(tmp_path):
    """REQ-EVT-F14: deleting an existing event returns True and removes it."""
    repo = JsonEventRepository(tmp_path / "events.json")
    rec = _record()
    repo.create(rec)
    assert repo.delete(rec["id"]) is True
    assert repo.get(rec["id"]) is None


def test_delete_missing_reports_false(tmp_path):
    """REQ-EVT-F14: deleting an unknown id returns False."""
    repo = JsonEventRepository(tmp_path / "events.json")
    assert repo.delete("does-not-exist") is False


# --------------------------------------------------------------------------- #
# Persistence on reopen — REQ-EVT-F14-AC2
# --------------------------------------------------------------------------- #
def test_data_persists_across_reopen(tmp_path):
    """REQ-EVT-F14-AC2: a fresh instance reading the same file sees prior data."""
    path = tmp_path / "events.json"
    first = JsonEventRepository(path)
    rec = _record(title="Persisted", city="Torino", status="published")
    first.create(rec)

    second = JsonEventRepository(path)
    reloaded = second.get(rec["id"])
    assert reloaded is not None
    assert reloaded["title"] == "Persisted"
    assert reloaded["city"] == "Torino"
    assert reloaded["status"] == "published"
    assert len(second.list_all({})) == 1


def test_delete_persists_across_reopen(tmp_path):
    """REQ-EVT-F14-AC2: a delete is durable and visible after reopening."""
    path = tmp_path / "events.json"
    first = JsonEventRepository(path)
    rec = _record()
    first.create(rec)
    first.delete(rec["id"])

    second = JsonEventRepository(path)
    assert second.get(rec["id"]) is None
    assert second.list_all({}) == []


# --------------------------------------------------------------------------- #
# Atomic write — no leftover .tmp file (design §9)
# --------------------------------------------------------------------------- #
def test_no_leftover_tmp_file_after_writes(tmp_path):
    """REQ-EVT-F14: os.replace leaves no ``.tmp`` residue after mutations."""
    path = tmp_path / "events.json"
    repo = JsonEventRepository(path)
    rec = _record()
    repo.create(rec)
    repo.update(rec["id"], {"title": "Renamed"})
    repo.delete(rec["id"])

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []
    assert path.exists()


def test_file_contains_valid_json_array(tmp_path):
    """REQ-EVT-F14: the persisted file is a JSON array of records."""
    path = tmp_path / "events.json"
    repo = JsonEventRepository(path)
    repo.create(_record(title="A"))
    repo.create(_record(title="B"))

    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, list)
    assert len(data) == 2
    assert {r["title"] for r in data} == {"A", "B"}


def test_non_array_file_raises_on_open(tmp_path):
    """REQ-EVT-F14: a malformed (non-array) file is rejected on open."""
    path = tmp_path / "events.json"
    path.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        JsonEventRepository(path)
