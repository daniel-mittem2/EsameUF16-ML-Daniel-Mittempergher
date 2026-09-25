"""Unit tests for the repository abstraction and the memory backend.

Covers REQ-USR-F14 (interchangeable persistence, memory branch of the factory)
and REQ-USR-B01 (case-insensitive email uniqueness, including concurrency).
"""
from __future__ import annotations

import threading

import pytest

from app.models import new_user_record, utcnow_iso
from app.backends.memory import MemoryUserRepository
from app.backends.json_backend import JsonUserRepository
from app.backends.sqlite_backend import SqliteUserRepository
from app.repository import (
    AbstractUserRepository,
    EmailAlreadyExistsError,
    get_repository,
)


def _record(email: str, role: str = "attendee", first: str = "A", last: str = "B") -> dict:
    return new_user_record(
        {"first_name": first, "last_name": last, "email": email, "role": role},
        utcnow_iso(),
    )


# --------------------------------------------------------------------------- #
# Factory — REQ-USR-F14
# --------------------------------------------------------------------------- #
def test_get_repository_memory_returns_memory_backend():
    """REQ-USR-F14-AC1: the memory branch returns a MemoryUserRepository."""
    repo = get_repository("memory", data_dir=None)
    assert isinstance(repo, MemoryUserRepository)
    assert isinstance(repo, AbstractUserRepository)


def test_get_repository_unknown_backend_raises():
    """REQ-USR-F14: an unrecognised backend name is rejected."""
    with pytest.raises(ValueError):
        get_repository("cassandra", data_dir=None)


# --------------------------------------------------------------------------- #
# CRUD on the memory backend
# --------------------------------------------------------------------------- #
def test_create_and_get_roundtrip():
    repo = MemoryUserRepository()
    rec = _record("alice@example.com")
    created = repo.create(rec)
    assert created["id"] == rec["id"]
    assert repo.get(rec["id"]) == rec


def test_get_missing_returns_none():
    repo = MemoryUserRepository()
    assert repo.get("does-not-exist") is None


def test_get_by_email_is_case_insensitive():
    """REQ-USR-B01: email lookup ignores capitalisation."""
    repo = MemoryUserRepository()
    rec = _record("alice@example.com")
    repo.create(rec)
    assert repo.get_by_email("ALICE@EXAMPLE.COM")["id"] == rec["id"]
    assert repo.get_by_email("nobody@example.com") is None


def test_create_duplicate_email_case_insensitive_raises():
    """REQ-USR-B01: differing case is still a duplicate."""
    repo = MemoryUserRepository()
    repo.create(_record("alice@example.com"))
    dup = new_user_record(
        {"first_name": "C", "last_name": "D", "email": "ALICE@example.com"},
        utcnow_iso(),
    )
    with pytest.raises(EmailAlreadyExistsError):
        repo.create(dup)


def test_list_all_filters_by_role_and_email():
    repo = MemoryUserRepository()
    repo.create(_record("a@example.com", role="organizer"))
    repo.create(_record("b@example.com", role="attendee"))
    repo.create(_record("c@example.com", role="organizer"))

    assert len(repo.list_all({})) == 3
    assert len(repo.list_all({"role": "organizer"})) == 2
    matched = repo.list_all({"email": "B@EXAMPLE.COM"})
    assert len(matched) == 1 and matched[0]["email"] == "b@example.com"
    assert repo.list_all({"role": "organizer", "email": "b@example.com"}) == []


def test_update_applies_changes():
    repo = MemoryUserRepository()
    rec = _record("alice@example.com")
    repo.create(rec)
    updated = repo.update(rec["id"], {"first_name": "Alicia"})
    assert updated["first_name"] == "Alicia"
    assert repo.get(rec["id"])["first_name"] == "Alicia"


def test_update_missing_returns_none():
    repo = MemoryUserRepository()
    assert repo.update("nope", {"first_name": "X"}) is None


def test_update_same_user_same_email_allowed():
    """REQ-USR-B01-AC3: updating your own email to the same value is not a conflict."""
    repo = MemoryUserRepository()
    rec = _record("alice@example.com")
    repo.create(rec)
    updated = repo.update(rec["id"], {"email": "alice@example.com", "first_name": "Al"})
    assert updated["first_name"] == "Al"


def test_update_to_other_users_email_raises():
    """REQ-USR-B01-AC2: taking a different user's email is a conflict."""
    repo = MemoryUserRepository()
    a = _record("alice@example.com")
    b = _record("bob@example.com")
    repo.create(a)
    repo.create(b)
    with pytest.raises(EmailAlreadyExistsError):
        repo.update(b["id"], {"email": "ALICE@example.com"})


def test_delete_removes_record_and_is_reported():
    repo = MemoryUserRepository()
    rec = _record("alice@example.com")
    repo.create(rec)
    assert repo.delete(rec["id"]) is True
    assert repo.get(rec["id"]) is None
    assert repo.delete(rec["id"]) is False


# --------------------------------------------------------------------------- #
# Concurrency — REQ-USR-B01 (design §10)
# --------------------------------------------------------------------------- #
def test_concurrent_create_same_email_exactly_one_success():
    """REQ-USR-B01: two concurrent creates with the same email yield exactly one
    success and one EmailAlreadyExistsError.

    The check-uniqueness + write sequence runs inside the shared RLock, so the
    duplicate can never slip through even under thread interleaving.
    """
    repo = MemoryUserRepository()
    start = threading.Barrier(2)
    successes: list[dict] = []
    conflicts: list[EmailAlreadyExistsError] = []
    lock = threading.Lock()

    def attempt():
        rec = new_user_record(
            {"first_name": "A", "last_name": "B", "email": "dup@example.com"},
            utcnow_iso(),
        )
        start.wait()  # maximise the chance of a real race
        try:
            created = repo.create(rec)
            with lock:
                successes.append(created)
        except EmailAlreadyExistsError as exc:
            with lock:
                conflicts.append(exc)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(conflicts) == 1
    # Exactly one record persisted, and it is the successful one.
    stored = repo.list_all({})
    assert len(stored) == 1
    assert stored[0]["id"] == successes[0]["id"]


# --------------------------------------------------------------------------- #
# JSON backend — REQ-USR-F14 (json branch) + REQ-USR-B01
# --------------------------------------------------------------------------- #
def test_get_repository_json_returns_json_backend(tmp_path):
    """REQ-USR-F14-AC2: the json branch returns a JsonUserRepository."""
    repo = get_repository("json", data_dir=tmp_path)
    assert isinstance(repo, JsonUserRepository)
    assert isinstance(repo, AbstractUserRepository)
    assert (tmp_path / "users.json").parent.exists()


def test_json_create_and_get_roundtrip(tmp_path):
    repo = JsonUserRepository(tmp_path / "users.json")
    rec = _record("alice@example.com")
    created = repo.create(rec)
    assert created["id"] == rec["id"]
    assert repo.get(rec["id"])["email"] == "alice@example.com"


def test_json_missing_file_starts_empty(tmp_path):
    """A JsonUserRepository over a non-existent file behaves as an empty store."""
    repo = JsonUserRepository(tmp_path / "does-not-exist.json")
    assert repo.list_all({}) == []
    assert repo.get("anything") is None


def test_json_get_by_email_is_case_insensitive(tmp_path):
    """REQ-USR-B01: email lookup ignores capitalisation."""
    repo = JsonUserRepository(tmp_path / "users.json")
    rec = _record("alice@example.com")
    repo.create(rec)
    assert repo.get_by_email("ALICE@EXAMPLE.COM")["id"] == rec["id"]
    assert repo.get_by_email("nobody@example.com") is None


def test_json_create_duplicate_email_case_insensitive_raises(tmp_path):
    """REQ-USR-B01: differing case is still a duplicate."""
    repo = JsonUserRepository(tmp_path / "users.json")
    repo.create(_record("alice@example.com"))
    dup = new_user_record(
        {"first_name": "C", "last_name": "D", "email": "ALICE@example.com"},
        utcnow_iso(),
    )
    with pytest.raises(EmailAlreadyExistsError):
        repo.create(dup)


def test_json_persists_across_reopen(tmp_path):
    """REQ-USR-F14-AC2: data written by one instance is visible to a fresh
    instance opened on the same file (reopening restores persisted state)."""
    path = tmp_path / "users.json"
    repo = JsonUserRepository(path)
    rec = _record("alice@example.com", role="organizer")
    repo.create(rec)

    # Brand new instance over the same file — must load the existing record.
    reopened = JsonUserRepository(path)
    loaded = reopened.get(rec["id"])
    assert loaded is not None
    assert loaded["id"] == rec["id"]
    assert loaded["email"] == "alice@example.com"
    assert loaded["role"] == "organizer"
    assert reopened.get_by_email("alice@example.com")["id"] == rec["id"]
    assert len(reopened.list_all({})) == 1


def test_json_update_and_delete_persist_across_reopen(tmp_path):
    """Updates and deletes are flushed to disk and survive a reopen."""
    path = tmp_path / "users.json"
    repo = JsonUserRepository(path)
    rec = _record("alice@example.com")
    repo.create(rec)
    repo.update(rec["id"], {"first_name": "Alicia"})

    assert JsonUserRepository(path).get(rec["id"])["first_name"] == "Alicia"

    repo.delete(rec["id"])
    assert JsonUserRepository(path).get(rec["id"]) is None


def test_json_uses_atomic_replace_no_tmp_left_behind(tmp_path):
    """The temporary write file is renamed away, never left behind."""
    path = tmp_path / "users.json"
    repo = JsonUserRepository(path)
    repo.create(_record("alice@example.com"))
    assert path.exists()
    assert not (tmp_path / "users.json.tmp").exists()


def test_json_get_returns_independent_copy(tmp_path):
    """Mutating a returned record must not corrupt the in-memory/on-disk store."""
    path = tmp_path / "users.json"
    repo = JsonUserRepository(path)
    rec = _record("alice@example.com")
    repo.create(rec)
    fetched = repo.get(rec["id"])
    fetched["first_name"] = "MUTATED"
    assert repo.get(rec["id"])["first_name"] != "MUTATED"


# --------------------------------------------------------------------------- #
# SQLite backend — REQ-USR-F14 (sqlite branch) + REQ-USR-B01 (IntegrityError)
# --------------------------------------------------------------------------- #
def test_get_repository_sqlite_returns_sqlite_backend(tmp_path):
    """REQ-USR-F14-AC3: the sqlite branch returns a SqliteUserRepository."""
    repo = get_repository("sqlite", data_dir=tmp_path)
    assert isinstance(repo, SqliteUserRepository)
    assert isinstance(repo, AbstractUserRepository)
    assert (tmp_path / "users.db").exists()
    repo.close()


def test_sqlite_create_and_get_roundtrip(tmp_path):
    repo = SqliteUserRepository(tmp_path / "users.db")
    rec = _record("alice@example.com")
    created = repo.create(rec)
    assert created["id"] == rec["id"]
    assert repo.get(rec["id"])["email"] == "alice@example.com"
    repo.close()


def test_sqlite_missing_returns_none(tmp_path):
    repo = SqliteUserRepository(tmp_path / "users.db")
    assert repo.get("does-not-exist") is None
    assert repo.get_by_email("nobody@example.com") is None
    repo.close()


def test_sqlite_company_null_roundtrips(tmp_path):
    """company defaults to NULL and round-trips as None, not ""."""
    repo = SqliteUserRepository(tmp_path / "users.db")
    rec = _record("alice@example.com")
    assert rec["company"] is None
    repo.create(rec)
    assert repo.get(rec["id"])["company"] is None
    repo.close()


def test_sqlite_get_by_email_is_case_insensitive(tmp_path):
    """REQ-USR-B01: email lookup ignores capitalisation."""
    repo = SqliteUserRepository(tmp_path / "users.db")
    rec = _record("alice@example.com")
    repo.create(rec)
    assert repo.get_by_email("ALICE@EXAMPLE.COM")["id"] == rec["id"]
    assert repo.get_by_email("nobody@example.com") is None
    repo.close()


def test_sqlite_create_duplicate_email_case_insensitive_raises(tmp_path):
    """REQ-USR-B01: differing case is still a duplicate (caught by the check)."""
    repo = SqliteUserRepository(tmp_path / "users.db")
    repo.create(_record("alice@example.com"))
    dup = new_user_record(
        {"first_name": "C", "last_name": "D", "email": "ALICE@example.com"},
        utcnow_iso(),
    )
    with pytest.raises(EmailAlreadyExistsError):
        repo.create(dup)
    repo.close()


def test_sqlite_integrity_error_maps_to_email_exists_on_create(tmp_path, monkeypatch):
    """REQ-USR-B01: a duplicate that slips past the in-process check and reaches
    the UNIQUE INDEX surfaces as EmailAlreadyExistsError, not sqlite3.IntegrityError.

    We neutralise the Python-level check so the INSERT hits the DB constraint,
    exercising the ``sqlite3.IntegrityError`` -> ``EmailAlreadyExistsError``
    mapping directly (design §9, §10).
    """
    repo = SqliteUserRepository(tmp_path / "users.db")
    repo.create(_record("alice@example.com"))
    # Force the DB path: pretend no matching email exists in-process.
    monkeypatch.setattr(repo, "_find_by_email_unlocked", lambda email: None)
    dup = new_user_record(
        {"first_name": "C", "last_name": "D", "email": "ALICE@example.com"},
        utcnow_iso(),
    )
    with pytest.raises(EmailAlreadyExistsError):
        repo.create(dup)
    repo.close()


def test_sqlite_integrity_error_maps_to_email_exists_on_update(tmp_path, monkeypatch):
    """REQ-USR-B01: the same IntegrityError mapping guards the UPDATE path."""
    repo = SqliteUserRepository(tmp_path / "users.db")
    repo.create(_record("alice@example.com"))
    bob = _record("bob@example.com")
    repo.create(bob)
    # Force the DB path so the UNIQUE INDEX is what rejects the collision.
    monkeypatch.setattr(repo, "_find_by_email_unlocked", lambda email: None)
    with pytest.raises(EmailAlreadyExistsError):
        repo.update(bob["id"], {"email": "ALICE@example.com"})
    repo.close()


def test_sqlite_list_all_filters_by_role_and_email(tmp_path):
    repo = SqliteUserRepository(tmp_path / "users.db")
    repo.create(_record("a@example.com", role="organizer"))
    repo.create(_record("b@example.com", role="attendee"))
    repo.create(_record("c@example.com", role="organizer"))

    assert len(repo.list_all({})) == 3
    assert len(repo.list_all({"role": "organizer"})) == 2
    matched = repo.list_all({"email": "B@EXAMPLE.COM"})
    assert len(matched) == 1 and matched[0]["email"] == "b@example.com"
    assert repo.list_all({"role": "organizer", "email": "b@example.com"}) == []
    repo.close()


def test_sqlite_update_applies_changes(tmp_path):
    repo = SqliteUserRepository(tmp_path / "users.db")
    rec = _record("alice@example.com")
    repo.create(rec)
    updated = repo.update(rec["id"], {"first_name": "Alicia"})
    assert updated["first_name"] == "Alicia"
    assert repo.get(rec["id"])["first_name"] == "Alicia"
    repo.close()


def test_sqlite_update_missing_returns_none(tmp_path):
    repo = SqliteUserRepository(tmp_path / "users.db")
    assert repo.update("nope", {"first_name": "X"}) is None
    repo.close()


def test_sqlite_update_same_user_same_email_allowed(tmp_path):
    """REQ-USR-B01-AC3: updating your own email to the same value is not a conflict."""
    repo = SqliteUserRepository(tmp_path / "users.db")
    rec = _record("alice@example.com")
    repo.create(rec)
    updated = repo.update(rec["id"], {"email": "alice@example.com", "first_name": "Al"})
    assert updated["first_name"] == "Al"
    repo.close()


def test_sqlite_update_to_other_users_email_raises(tmp_path):
    """REQ-USR-B01-AC2: taking a different user's email is a conflict."""
    repo = SqliteUserRepository(tmp_path / "users.db")
    a = _record("alice@example.com")
    b = _record("bob@example.com")
    repo.create(a)
    repo.create(b)
    with pytest.raises(EmailAlreadyExistsError):
        repo.update(b["id"], {"email": "ALICE@example.com"})
    repo.close()


def test_sqlite_delete_removes_record_and_is_reported(tmp_path):
    repo = SqliteUserRepository(tmp_path / "users.db")
    rec = _record("alice@example.com")
    repo.create(rec)
    assert repo.delete(rec["id"]) is True
    assert repo.get(rec["id"]) is None
    assert repo.delete(rec["id"]) is False
    repo.close()


def test_sqlite_persists_across_reopen(tmp_path):
    """REQ-USR-F14-AC3: data written by one instance is visible to a fresh
    instance opened on the same file (reopening restores persisted state)."""
    path = tmp_path / "users.db"
    repo = SqliteUserRepository(path)
    rec = _record("alice@example.com", role="organizer")
    repo.create(rec)
    repo.close()

    reopened = SqliteUserRepository(path)
    loaded = reopened.get(rec["id"])
    assert loaded is not None
    assert loaded["id"] == rec["id"]
    assert loaded["email"] == "alice@example.com"
    assert loaded["role"] == "organizer"
    assert reopened.get_by_email("alice@example.com")["id"] == rec["id"]
    assert len(reopened.list_all({})) == 1
    reopened.close()


def test_sqlite_update_and_delete_persist_across_reopen(tmp_path):
    """Updates and deletes are committed and survive a reopen."""
    path = tmp_path / "users.db"
    repo = SqliteUserRepository(path)
    rec = _record("alice@example.com")
    repo.create(rec)
    repo.update(rec["id"], {"first_name": "Alicia"})
    repo.close()

    r2 = SqliteUserRepository(path)
    assert r2.get(rec["id"])["first_name"] == "Alicia"
    r2.close()

    r3 = SqliteUserRepository(path)
    r3.delete(rec["id"])
    r3.close()
    assert SqliteUserRepository(path).get(rec["id"]) is None


def test_sqlite_concurrent_create_same_email_exactly_one_success(tmp_path):
    """REQ-USR-B01: two concurrent creates with the same email yield exactly one
    success and one EmailAlreadyExistsError.

    The check-uniqueness + write sequence runs inside the shared RLock, so the
    duplicate can never slip through even under thread interleaving.
    """
    repo = SqliteUserRepository(tmp_path / "users.db")
    start = threading.Barrier(2)
    successes: list[dict] = []
    conflicts: list[EmailAlreadyExistsError] = []
    lock = threading.Lock()

    def attempt():
        rec = new_user_record(
            {"first_name": "A", "last_name": "B", "email": "dup@example.com"},
            utcnow_iso(),
        )
        start.wait()
        try:
            created = repo.create(rec)
            with lock:
                successes.append(created)
        except EmailAlreadyExistsError as exc:
            with lock:
                conflicts.append(exc)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(conflicts) == 1
    stored = repo.list_all({})
    assert len(stored) == 1
    assert stored[0]["id"] == successes[0]["id"]
    repo.close()
