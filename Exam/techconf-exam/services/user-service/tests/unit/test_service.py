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


# --------------------------------------------------------------------------- #
# replace_user — PUT (REQ-USR-F07, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11)
# --------------------------------------------------------------------------- #
def test_replace_user_replaces_all_mutable_fields():
    """REQ-USR-F07-AC1: PUT overwrites every mutable field and returns the record."""
    svc = _service()
    created = svc.create_user(
        {
            "first_name": "Old",
            "last_name": "Name",
            "email": "old@example.com",
            "company": "OldCo",
            "role": "speaker",
        }
    )
    updated = svc.replace_user(
        created["id"],
        {
            "first_name": "New",
            "last_name": "Person",
            "email": "new@example.com",
            "company": "NewCo",
            "role": "organizer",
        },
    )
    assert updated["id"] == created["id"]
    assert updated["first_name"] == "New"
    assert updated["last_name"] == "Person"
    assert updated["email"] == "new@example.com"
    assert updated["company"] == "NewCo"
    assert updated["role"] == "organizer"


def test_replace_user_applies_post_style_defaults_for_optional_fields():
    """REQ-USR-F07-AC2: omitted company/role default to None/attendee on PUT."""
    svc = _service()
    created = svc.create_user(
        {
            "first_name": "Has",
            "last_name": "Company",
            "email": "has@example.com",
            "company": "SomeCo",
            "role": "organizer",
        }
    )
    updated = svc.replace_user(
        created["id"],
        {"first_name": "No", "last_name": "Extras", "email": "no@example.com"},
    )
    assert updated["company"] is None
    assert updated["role"] == "attendee"


def test_replace_user_missing_id_raises_not_found():
    """REQ-USR-F07-AC3: PUT on an unknown id raises UserNotFoundError (404)."""
    svc = _service()
    with pytest.raises(UserNotFoundError):
        svc.replace_user(
            str(uuid.uuid4()),
            {"first_name": "X", "last_name": "Y", "email": "x@example.com"},
        )


def test_replace_user_normalises_email_to_lowercase():
    """REQ-USR-B02-AC2: a PUT email is stored/returned in lower case."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Norm", "last_name": "Alise", "email": "norm@example.com"}
    )
    updated = svc.replace_user(
        created["id"],
        {"first_name": "Norm", "last_name": "Alise", "email": "NORM@Example.COM"},
    )
    assert updated["email"] == "norm@example.com"


def test_replace_user_same_email_does_not_conflict():
    """REQ-USR-B01-AC3: PUT with the user's own email must not raise a conflict."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Same", "last_name": "Email", "email": "same@example.com"}
    )
    updated = svc.replace_user(
        created["id"],
        {"first_name": "Same", "last_name": "Changed", "email": "same@example.com"},
    )
    assert updated["last_name"] == "Changed"
    assert updated["email"] == "same@example.com"


def test_replace_user_same_email_different_case_does_not_conflict():
    """REQ-USR-B01-AC3/B02: PUT reusing own email in different case is not a conflict."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Case", "last_name": "Ins", "email": "case@example.com"}
    )
    updated = svc.replace_user(
        created["id"],
        {"first_name": "Case", "last_name": "Ins", "email": "CASE@Example.com"},
    )
    assert updated["email"] == "case@example.com"


def test_replace_user_email_of_another_user_raises_conflict():
    """REQ-USR-B01-AC2: PUT with another user's email raises EmailConflictError."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "first@example.com"},
            {"email": "second@example.com"},
        ],
    )
    first = svc.list_users({"email": "first@example.com"}, 1, 20)["items"][0]
    with pytest.raises(EmailConflictError):
        svc.replace_user(
            first["id"],
            {"first_name": "First", "last_name": "User", "email": "second@example.com"},
        )


def test_replace_user_preserves_created_at(monkeypatch):
    """REQ-USR-F07-AC3/F11-AC3: created_at is unchanged, updated_at refreshed on PUT."""
    calls = iter(
        ["2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"]
    )
    monkeypatch.setattr("app.service.utcnow_iso", lambda: next(calls))
    svc = _service()
    created = svc.create_user(
        {"first_name": "A", "last_name": "B", "email": "a@b.com"}
    )
    updated = svc.replace_user(
        created["id"], {"first_name": "C", "last_name": "D", "email": "a@b.com"}
    )
    assert updated["created_at"] == "2026-01-01T00:00:00.000000Z"
    assert updated["updated_at"] == "2026-01-02T00:00:00.000000Z"
    assert updated["created_at"] != updated["updated_at"]


def test_replace_user_maps_repository_race_to_conflict(monkeypatch):
    """REQ-USR-B01: a repository EmailAlreadyExistsError becomes EmailConflictError."""
    repo = MemoryUserRepository()
    svc = UserService(repo)
    created = svc.create_user(
        {"first_name": "Race", "last_name": "Put", "email": "race@example.com"}
    )

    def _raise(_user_id, _changes):
        raise EmailAlreadyExistsError()

    monkeypatch.setattr(repo, "update", _raise)
    with pytest.raises(EmailConflictError):
        svc.replace_user(
            created["id"],
            {"first_name": "Race", "last_name": "Put", "email": "other@example.com"},
        )


# --------------------------------------------------------------------------- #
# update_user — PATCH (REQ-USR-F08, REQ-USR-B01, REQ-USR-B02, REQ-USR-F11)
# --------------------------------------------------------------------------- #
def test_update_user_applies_only_present_fields():
    """REQ-USR-F08-AC1/AC3: PATCH updates provided fields, leaves others unchanged."""
    svc = _service()
    created = svc.create_user(
        {
            "first_name": "Keep",
            "last_name": "Last",
            "email": "keep@example.com",
            "company": "KeepCo",
            "role": "speaker",
        }
    )
    updated = svc.update_user(created["id"], {"first_name": "Changed"})
    assert updated["first_name"] == "Changed"
    # untouched fields retain their values
    assert updated["last_name"] == "Last"
    assert updated["email"] == "keep@example.com"
    assert updated["company"] == "KeepCo"
    assert updated["role"] == "speaker"


def test_update_user_can_clear_company_with_null():
    """REQ-USR-F08-AC4: company may be patched to None explicitly."""
    svc = _service()
    created = svc.create_user(
        {
            "first_name": "Has",
            "last_name": "Co",
            "email": "hasco@example.com",
            "company": "SomeCo",
        }
    )
    updated = svc.update_user(created["id"], {"company": None})
    assert updated["company"] is None


def test_update_user_missing_id_raises_not_found():
    """REQ-USR-F08-AC2: PATCH on an unknown id raises UserNotFoundError (404)."""
    svc = _service()
    with pytest.raises(UserNotFoundError):
        svc.update_user(str(uuid.uuid4()), {"first_name": "X"})


def test_update_user_empty_patch_on_missing_id_raises_not_found():
    """REQ-USR-F08-AC2: an empty PATCH on an unknown id is 404, not 200."""
    svc = _service()
    with pytest.raises(UserNotFoundError):
        svc.update_user(str(uuid.uuid4()), {})


def test_update_user_empty_patch_leaves_record_and_timestamp_unchanged(monkeypatch):
    """REQ-USR-F04-AC4/F11-AC2: empty PATCH returns record with updated_at unchanged."""
    calls = iter(["2026-03-01T00:00:00.000000Z"])
    monkeypatch.setattr("app.service.utcnow_iso", lambda: next(calls))
    svc = _service()
    created = svc.create_user(
        {"first_name": "Idem", "last_name": "Potent", "email": "idem@example.com"}
    )
    original_updated_at = created["updated_at"]
    result = svc.update_user(created["id"], {})
    assert result["updated_at"] == original_updated_at
    assert result["created_at"] == created["created_at"]
    # utcnow_iso must not have been consulted a second time (iterator not exhausted)
    assert next(calls, "unused") == "unused"


def test_update_user_normalises_email_to_lowercase():
    """REQ-USR-B02-AC2: a PATCH email is stored/returned in lower case."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Low", "last_name": "Case", "email": "low@example.com"}
    )
    updated = svc.update_user(created["id"], {"email": "LOW2@Example.COM"})
    assert updated["email"] == "low2@example.com"


def test_update_user_same_email_does_not_conflict():
    """REQ-USR-B01-AC3: PATCH with the user's own email must not raise a conflict."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Self", "last_name": "Mail", "email": "self@example.com"}
    )
    updated = svc.update_user(created["id"], {"email": "self@example.com"})
    assert updated["email"] == "self@example.com"


def test_update_user_email_of_another_user_raises_conflict():
    """REQ-USR-B01-AC2: PATCH with another user's email raises EmailConflictError."""
    svc = _service()
    _make_users(
        svc,
        [
            {"email": "one@example.com"},
            {"email": "two@example.com"},
        ],
    )
    one = svc.list_users({"email": "one@example.com"}, 1, 20)["items"][0]
    with pytest.raises(EmailConflictError):
        svc.update_user(one["id"], {"email": "two@example.com"})


def test_update_user_refreshes_updated_at_but_keeps_created_at(monkeypatch):
    """REQ-USR-F11-AC2/AC3: a real PATCH refreshes updated_at, created_at unchanged."""
    calls = iter(
        ["2026-05-01T00:00:00.000000Z", "2026-05-02T00:00:00.000000Z"]
    )
    monkeypatch.setattr("app.service.utcnow_iso", lambda: next(calls))
    svc = _service()
    created = svc.create_user(
        {"first_name": "T", "last_name": "S", "email": "ts@example.com"}
    )
    updated = svc.update_user(created["id"], {"first_name": "Renamed"})
    assert updated["created_at"] == "2026-05-01T00:00:00.000000Z"
    assert updated["updated_at"] == "2026-05-02T00:00:00.000000Z"
    assert updated["created_at"] != updated["updated_at"]


def test_update_user_ignores_unknown_keys_at_service_layer():
    """Defensive: the service persists only mutable contract fields.

    Unknown keys are rejected by the routes-layer validator (REQ-USR-F04-AC3);
    the service additionally never writes a key outside the contract shape.
    """
    svc = _service()
    created = svc.create_user(
        {"first_name": "Guard", "last_name": "Ed", "email": "guard@example.com"}
    )
    updated = svc.update_user(created["id"], {"first_name": "Ok", "id": "spoofed"})
    assert updated["id"] == created["id"]  # server id preserved, not spoofed
    assert updated["first_name"] == "Ok"


def test_update_user_maps_repository_race_to_conflict(monkeypatch):
    """REQ-USR-B01: a repository EmailAlreadyExistsError becomes EmailConflictError."""
    repo = MemoryUserRepository()
    svc = UserService(repo)
    created = svc.create_user(
        {"first_name": "Race", "last_name": "Patch", "email": "racep@example.com"}
    )

    def _raise(_user_id, _changes):
        raise EmailAlreadyExistsError()

    monkeypatch.setattr(repo, "update", _raise)
    with pytest.raises(EmailConflictError):
        svc.update_user(created["id"], {"email": "taken@example.com"})


# --------------------------------------------------------------------------- #
# delete_user (REQ-USR-F09)
# --------------------------------------------------------------------------- #
def test_delete_user_removes_existing_record_and_returns_none():
    """REQ-USR-F09-AC1: delete_user removes the user and returns None."""
    repo = MemoryUserRepository()
    svc = UserService(repo)
    created = svc.create_user(
        {"first_name": "Del", "last_name": "Ete", "email": "del@example.com"}
    )
    assert svc.delete_user(created["id"]) is None
    assert repo.get(created["id"]) is None


def test_delete_user_missing_id_raises_not_found():
    """REQ-USR-F09-AC2: delete_user on an unknown id raises UserNotFoundError (404)."""
    svc = _service()
    with pytest.raises(UserNotFoundError):
        svc.delete_user(str(uuid.uuid4()))


def test_delete_user_then_get_user_raises_not_found():
    """REQ-USR-F09-AC3: after a successful delete, get_user on the same id is 404."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Gone", "last_name": "Soon", "email": "gone@example.com"}
    )
    svc.delete_user(created["id"])
    with pytest.raises(UserNotFoundError):
        svc.get_user(created["id"])


def test_delete_user_second_delete_raises_not_found():
    """REQ-USR-F09-AC4: a second delete on the same id raises UserNotFoundError."""
    svc = _service()
    created = svc.create_user(
        {"first_name": "Twice", "last_name": "Del", "email": "twice@example.com"}
    )
    svc.delete_user(created["id"])
    with pytest.raises(UserNotFoundError):
        svc.delete_user(created["id"])


# --------------------------------------------------------------------------- #
# No mutation on error (REQ-USR-F11-AC4)
# --------------------------------------------------------------------------- #
def test_replace_user_conflict_leaves_stored_record_unchanged():
    """REQ-USR-F11-AC4: a PUT that fails on email conflict mutates nothing.

    The stored record — including its fields and timestamps — must be identical
    to what it was before the rejected replace (no partial mutation on error).
    """
    svc = _service()
    keep = svc.create_user(
        {
            "first_name": "Keep",
            "last_name": "Me",
            "email": "keep@example.com",
            "company": "KeepCo",
            "role": "speaker",
        }
    )
    other = svc.create_user(
        {"first_name": "Other", "last_name": "User", "email": "other@example.com"}
    )
    before = dict(svc.get_user(keep["id"]))

    with pytest.raises(EmailConflictError):
        svc.replace_user(
            keep["id"],
            {
                "first_name": "Should",
                "last_name": "NotApply",
                "email": other["email"],  # already used by another user → 409
            },
        )

    after = svc.get_user(keep["id"])
    assert after == before  # every field and timestamp is unchanged


def test_update_user_conflict_leaves_stored_record_unchanged():
    """REQ-USR-F11-AC4: a PATCH that fails on email conflict mutates nothing."""
    svc = _service()
    keep = svc.create_user(
        {
            "first_name": "Patch",
            "last_name": "Keep",
            "email": "patchkeep@example.com",
            "company": "PatchCo",
        }
    )
    other = svc.create_user(
        {"first_name": "Taken", "last_name": "Email", "email": "taken@example.com"}
    )
    before = dict(svc.get_user(keep["id"]))

    with pytest.raises(EmailConflictError):
        svc.update_user(keep["id"], {"email": other["email"]})

    after = svc.get_user(keep["id"])
    assert after == before


def test_replace_user_repository_error_leaves_record_unchanged(monkeypatch):
    """REQ-USR-F11-AC4: when the repository write fails, the stored record and
    its timestamps stay unchanged (no partial mutation on error)."""
    repo = MemoryUserRepository()
    svc = UserService(repo)
    created = svc.create_user(
        {"first_name": "Race", "last_name": "Guard", "email": "raceguard@example.com"}
    )
    before = dict(repo.get(created["id"]))

    def _raise(_user_id, _changes):
        raise EmailAlreadyExistsError()

    monkeypatch.setattr(repo, "update", _raise)
    with pytest.raises(EmailConflictError):
        svc.replace_user(
            created["id"],
            {"first_name": "New", "last_name": "Vals", "email": "new@example.com"},
        )

    assert repo.get(created["id"]) == before
