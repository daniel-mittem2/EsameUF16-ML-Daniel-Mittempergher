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
from app.service import (
    EmailConflictError,
    InvalidFilterError,
    UserNotFoundError,
    UserService,
)


def _service() -> UserService:
    return UserService(MemoryUserRepository())


def _make_users(svc: UserService, specs: list[dict]) -> list[dict]:
    """Create several users from compact specs; return the created records."""
    created = []
    for i, spec in enumerate(specs):
        created.append(
            svc.create_user(
                {
                    "first_name": spec.get("first_name", f"User{i}"),
                    "last_name": spec.get("last_name", f"Last{i}"),
                    "email": spec["email"],
                    "role": spec.get("role", "attendee"),
                }
            )
        )
    return created


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


# --------------------------------------------------------------------------- #
# get_user (REQ-USR-F05)
# --------------------------------------------------------------------------- #
def test_get_user_returns_stored_record():
    """REQ-USR-F05-AC1: get_user returns the record for an existing id."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Ann", "last_name": "Ives", "email": "ann@example.com"}
    )
    fetched = svc.get_user(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["email"] == "ann@example.com"


def test_get_user_missing_id_raises_not_found():
    """REQ-USR-F05-AC2: an unknown id raises UserNotFoundError (maps to 404)."""
    svc = _service()
    with pytest.raises(UserNotFoundError):
        svc.get_user(str(uuid.uuid4()))


def test_get_user_syntactically_invalid_id_raises_not_found():
    """REQ-USR-F05-AC3: a non-UUID id that is absent yields not-found, not 422."""
    svc = _service()
    with pytest.raises(UserNotFoundError):
        svc.get_user("not-a-uuid")


# --------------------------------------------------------------------------- #
# list_users — filters (REQ-USR-B03)
# --------------------------------------------------------------------------- #
def test_list_users_filters_by_role_exact_match():
    """REQ-USR-B03-AC1: role filter returns only users with that exact role."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "a@example.com", "role": "organizer"},
            {"email": "b@example.com", "role": "attendee"},
            {"email": "c@example.com", "role": "organizer"},
        ],
    )
    page = svc.list_users({"role": "organizer"}, page=1, page_size=20)
    assert page["total"] == 2
    assert {item["email"] for item in page["items"]} == {
        "a@example.com",
        "c@example.com",
    }
    assert all(item["role"] == "organizer" for item in page["items"])


def test_list_users_filters_by_email_case_insensitive():
    """REQ-USR-B03-AC2: email filter matches the stored email case-insensitively."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "alice@example.com"},
            {"email": "bob@example.com"},
        ],
    )
    page = svc.list_users({"email": "ALICE@Example.com"}, page=1, page_size=20)
    assert page["total"] == 1
    assert page["items"][0]["email"] == "alice@example.com"


def test_list_users_combined_filters_use_and_logic():
    """REQ-USR-B03-AC3: role and email filters apply together (AND)."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "match@example.com", "role": "speaker"},
            {"email": "match2@example.com", "role": "attendee"},
            {"email": "other@example.com", "role": "speaker"},
        ],
    )
    page = svc.list_users(
        {"role": "speaker", "email": "match@example.com"}, page=1, page_size=20
    )
    assert page["total"] == 1
    assert page["items"][0]["email"] == "match@example.com"
    assert page["items"][0]["role"] == "speaker"


def test_list_users_total_reflects_filtered_count_not_absolute():
    """REQ-USR-B03-AC4: total counts filtered records, before pagination."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "s1@example.com", "role": "speaker"},
            {"email": "s2@example.com", "role": "speaker"},
            {"email": "s3@example.com", "role": "speaker"},
            {"email": "o1@example.com", "role": "organizer"},
            {"email": "a1@example.com", "role": "attendee"},
        ],
    )
    # 3 speakers exist, but page_size=2 returns only a slice; total must be 3,
    # not the absolute total of 5 and not the page size of 2.
    page = svc.list_users({"role": "speaker"}, page=1, page_size=2)
    assert page["total"] == 3
    assert len(page["items"]) == 2


def test_list_users_no_filters_returns_all():
    """REQ-USR-F06: an empty filter set returns every user."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "x@example.com"},
            {"email": "y@example.com"},
        ],
    )
    page = svc.list_users({}, page=1, page_size=20)
    assert page["total"] == 2


def test_list_users_page_beyond_last_returns_empty_items():
    """REQ-USR-F06-AC7: a page past the end returns empty items with correct total."""
    svc = _service()
    _make_users(svc, [{"email": "only@example.com"}])
    page = svc.list_users({}, page=5, page_size=20)
    assert page["total"] == 1
    assert page["items"] == []
    assert page["page"] == 5
    assert page["page_size"] == 20


def test_list_users_invalid_role_filter_raises_invalid_filter():
    """REQ-USR-B03-AC5: an invalid role filter raises InvalidFilterError (422)."""
    svc = _service()
    _make_users(svc, [{"email": "z@example.com", "role": "attendee"}])
    with pytest.raises(InvalidFilterError):
        svc.list_users({"role": "superadmin"}, page=1, page_size=20)


def test_list_users_items_are_contract_shaped():
    """REQ-USR-F06-AC3: each item exposes exactly the eight contract fields."""
    svc = _service()
    _make_users(svc, [{"email": "shape@example.com"}])
    page = svc.list_users({}, page=1, page_size=20)
    assert set(page["items"][0].keys()) == {
        "id",
        "first_name",
        "last_name",
        "email",
        "company",
        "role",
        "created_at",
        "updated_at",
    }
