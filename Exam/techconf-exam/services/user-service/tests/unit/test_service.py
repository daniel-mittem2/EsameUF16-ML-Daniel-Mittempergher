"""Unit tests for the UserService business layer.

This module currently covers ``UserService.create_user`` (task T-08):
- email normalisation to lower case (REQ-USR-B02)
- case-insensitive email uniqueness / conflict (REQ-USR-B01)
- identical creation timestamps (REQ-USR-F11)
- server-generated id and defaults (REQ-USR-F02)
"""
from __future__ import annotations

import uuid

import pytest

from app.backends.memory import MemoryUserRepository
from app.repository import EmailAlreadyExistsError
from app.service import EmailConflictError, UserService


def _service() -> UserService:
    return UserService(MemoryUserRepository())


# --------------------------------------------------------------------------- #
# create_user — happy path (REQ-USR-F02, REQ-USR-F11)
# --------------------------------------------------------------------------- #
def test_create_user_returns_record_with_generated_fields():
    """REQ-USR-F02: create_user generates a UUID v4 id and the 8 contract fields."""
    svc = _service()
    record = svc.create_user(
        {"first_name": "Alice", "last_name": "Smith", "email": "alice@example.com"}
    )

    # Server-generated UUID v4 id (REQ-USR-F02-AC2).
    assert uuid.UUID(record["id"]).version == 4
    assert record["first_name"] == "Alice"
    assert record["last_name"] == "Smith"
    assert record["company"] is None
    assert record["role"] == "attendee"  # default (REQ-USR-F02-AC5)


def test_create_user_created_and_updated_at_are_identical():
    """REQ-USR-F11-AC1: created_at and updated_at are the same timestamp at creation."""
    svc = _service()
    record = svc.create_user(
        {"first_name": "Bob", "last_name": "Jones", "email": "bob@example.com"}
    )
    assert record["created_at"] == record["updated_at"]
    assert record["created_at"].endswith("Z")


# --------------------------------------------------------------------------- #
# create_user — email normalisation (REQ-USR-B02)
# --------------------------------------------------------------------------- #
def test_create_user_normalises_uppercase_email_to_lowercase():
    """REQ-USR-B02-AC1: an upper-case email is stored and returned in lower case."""
    svc = _service()
    record = svc.create_user(
        {"first_name": "Carol", "last_name": "Doe", "email": "Carol@Example.COM"}
    )
    assert record["email"] == "carol@example.com"


def test_create_user_persists_lowercase_email_in_repository():
    """REQ-USR-B02: the persisted record carries the lower-case email."""
    repo = MemoryUserRepository()
    svc = UserService(repo)
    record = svc.create_user(
        {"first_name": "Dan", "last_name": "Ray", "email": "DAN@Example.com"}
    )
    stored = repo.get(record["id"])
    assert stored["email"] == "dan@example.com"


# --------------------------------------------------------------------------- #
# create_user — uniqueness (REQ-USR-B01, REQ-USR-B02-AC3)
# --------------------------------------------------------------------------- #
def test_create_user_duplicate_email_same_case_raises_conflict():
    """REQ-USR-B01-AC1: a second create with the same email raises EmailConflictError."""
    svc = _service()
    svc.create_user(
        {"first_name": "Eve", "last_name": "Kay", "email": "eve@example.com"}
    )
    with pytest.raises(EmailConflictError):
        svc.create_user(
            {"first_name": "Eve2", "last_name": "Kay2", "email": "eve@example.com"}
        )


def test_create_user_duplicate_email_different_case_raises_conflict():
    """REQ-USR-B01/B02-AC3: emails differing only by case are detected as duplicates."""
    svc = _service()
    svc.create_user(
        {"first_name": "Frank", "last_name": "Lee", "email": "Frank@Example.com"}
    )
    with pytest.raises(EmailConflictError):
        svc.create_user(
            {"first_name": "Frank2", "last_name": "Lee2", "email": "frank@example.com"}
        )


def test_create_user_conflict_leaves_original_record_only():
    """REQ-USR-B01: a rejected duplicate does not add a second record."""
    repo = MemoryUserRepository()
    svc = UserService(repo)
    svc.create_user(
        {"first_name": "Gina", "last_name": "Moe", "email": "gina@example.com"}
    )
    with pytest.raises(EmailConflictError):
        svc.create_user(
            {"first_name": "Gina", "last_name": "Moe", "email": "GINA@example.com"}
        )
    assert len(repo.list_all({})) == 1


def test_create_user_maps_repository_race_to_conflict(monkeypatch):
    """REQ-USR-B01: a repository EmailAlreadyExistsError becomes EmailConflictError.

    Simulates a concurrent create winning the race after the service pre-check
    passed: the repository raises, and the service re-raises as EmailConflictError.
    """
    repo = MemoryUserRepository()
    svc = UserService(repo)

    def _raise(_record):
        raise EmailAlreadyExistsError()

    monkeypatch.setattr(repo, "create", _raise)
    with pytest.raises(EmailConflictError):
        svc.create_user(
            {"first_name": "Hal", "last_name": "Nix", "email": "hal@example.com"}
        )
