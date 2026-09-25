"""Unit tests for the repository abstraction and the memory backend.

Covers REQ-USR-F14 (interchangeable persistence, memory branch of the factory)
and REQ-USR-B01 (case-insensitive email uniqueness, including concurrency).
"""
from __future__ import annotations

import threading

import pytest

from app.models import new_user_record, utcnow_iso
from app.backends.memory import MemoryUserRepository
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
