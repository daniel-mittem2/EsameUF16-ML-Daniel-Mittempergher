"""Unit tests for the support modules: errors, models, pagination, validators.

Covers REQ-USR-F03 (field validation), REQ-USR-F04 (PATCH validation),
REQ-USR-F06 (pagination), REQ-USR-F12 (error format).
"""
import re

import pytest
from flask import Flask

from app import errors, models, pagination, validators
from app.pagination import PaginationError


# --------------------------------------------------------------------------- #
# errors.py — REQ-USR-F12
# --------------------------------------------------------------------------- #
@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield app


def test_error_code_constants_are_upper_snake():
    """REQ-USR-F12-AC2: error codes are UPPER_SNAKE_CASE strings."""
    for code in (
        errors.VALIDATION_ERROR,
        errors.NOT_FOUND,
        errors.EMAIL_ALREADY_EXISTS,
        errors.MALFORMED_JSON,
        errors.METHOD_NOT_ALLOWED,
    ):
        assert re.fullmatch(r"[A-Z_]+", code)


def test_make_error_response_details_defaults_to_empty_dict(app_ctx):
    """REQ-USR-F12-AC3: details is always an object, never null."""
    body, status = errors.make_error_response(errors.NOT_FOUND, "missing")
    payload = body.get_json()
    assert status == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["message"] == "missing"
    assert payload["error"]["details"] == {}


def test_make_error_response_preserves_details_and_status(app_ctx):
    """REQ-USR-F12: explicit details and status override are respected."""
    body, status = errors.make_error_response(
        errors.VALIDATION_ERROR, "bad", details={"field": "email"}, status=422
    )
    payload = body.get_json()
    assert status == 422
    assert payload["error"]["details"] == {"field": "email"}


def test_make_error_response_derives_status_from_code(app_ctx):
    """REQ-USR-F12: status derived from ERROR_CODES when not provided."""
    _, status = errors.make_error_response(errors.EMAIL_ALREADY_EXISTS, "dup")
    assert status == 409


# --------------------------------------------------------------------------- #
# models.py — REQ-USR-B02, REQ-USR-F02
# --------------------------------------------------------------------------- #
def test_new_user_record_lowercases_email_and_applies_defaults():
    """REQ-USR-B02 + REQ-USR-F02: email lowercased, role/company defaults."""
    rec = models.new_user_record(
        {"first_name": "A", "last_name": "B", "email": "Alice@Example.COM"},
        "2026-01-01T00:00:00.000000Z",
    )
    assert rec["email"] == "alice@example.com"
    assert rec["role"] == "attendee"
    assert rec["company"] is None
    assert rec["created_at"] == rec["updated_at"] == "2026-01-01T00:00:00.000000Z"
    assert re.fullmatch(r"[0-9a-f-]{36}", rec["id"])


def test_new_user_record_keeps_supplied_role_and_company():
    """REQ-USR-F02: explicit role/company are preserved."""
    rec = models.new_user_record(
        {
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.com",
            "role": "speaker",
            "company": "ACME",
        },
        "2026-01-01T00:00:00.000000Z",
    )
    assert rec["role"] == "speaker"
    assert rec["company"] == "ACME"


def test_user_to_dict_returns_only_eight_contract_fields():
    """REQ-USR-F02-AC8: response has exactly the 8 contract fields."""
    record = {f: f for f in models.USER_FIELDS}
    record["secret_internal"] = "should not appear"
    result = models.user_to_dict(record)
    assert set(result.keys()) == set(models.USER_FIELDS)
    assert len(result) == 8


def test_utcnow_iso_format():
    """REQ-USR-F11-AC5: ISO 8601 UTC ending in Z, microsecond precision."""
    ts = models.utcnow_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", ts)


# --------------------------------------------------------------------------- #
# validators.py — REQ-USR-F03, REQ-USR-F04
# --------------------------------------------------------------------------- #
def test_validate_body_is_object():
    """REQ-USR-F03-AC9: only dict bodies are objects."""
    assert validators.validate_body_is_object({}) is True
    for bad in ([], None, "x", 1, True):
        assert validators.validate_body_is_object(bad) is False


@pytest.mark.parametrize(
    "email,expected",
    [
        ("alice@example.com", True),
        ("user+tag@sub.domain.org", True),
        ("notanemail", False),
        ("@domain.com", False),
        ("user@", False),
        ("user@@domain.com", False),
        (123, False),
        (None, False),
    ],
)
def test_validate_email_format(email, expected):
    """REQ-USR-F03-AC3: email format regex accepts/rejects correctly."""
    assert validators.validate_email_format(email) is expected


def test_validate_user_create_valid_minimal():
    """REQ-USR-F03: minimal valid body has no errors."""
    assert validators.validate_user_create(
        {"first_name": "A", "last_name": "B", "email": "a@b.com"}
    ) == []


def test_validate_user_create_missing_required():
    """REQ-USR-F03-AC1/AC2/AC3: missing required fields flagged."""
    errs = validators.validate_user_create({})
    assert any("first_name" in e for e in errs)
    assert any("last_name" in e for e in errs)
    assert any("email" in e for e in errs)


def test_validate_user_create_rejects_unknown_field():
    """REQ-USR-F03-AC4: additionalProperties false — unknown fields rejected."""
    errs = validators.validate_user_create(
        {"first_name": "A", "last_name": "B", "email": "a@b.com", "id": "x"}
    )
    assert any("unknown field" in e for e in errs)


def test_validate_user_create_rejects_wrong_types_no_coercion():
    """REQ-USR-F03-AC10: no implicit type coercion."""
    errs = validators.validate_user_create(
        {"first_name": 123, "last_name": True, "email": 1}
    )
    assert len(errs) >= 3


def test_validate_user_create_length_and_enum():
    """REQ-USR-F03-AC1/AC4/AC5: length and role enum rules."""
    assert validators.validate_user_create(
        {"first_name": "x" * 51, "last_name": "B", "email": "a@b.com"}
    )
    assert validators.validate_user_create(
        {"first_name": "A", "last_name": "B", "email": "a@b.com",
         "company": "x" * 101}
    )
    assert validators.validate_user_create(
        {"first_name": "A", "last_name": "B", "email": "a@b.com",
         "role": "admin"}
    )


def test_validate_user_create_company_null_allowed():
    """REQ-USR-F03-AC4: company may be null."""
    assert validators.validate_user_create(
        {"first_name": "A", "last_name": "B", "email": "a@b.com",
         "company": None}
    ) == []


def test_validate_user_update_all_optional():
    """REQ-USR-F04: empty PATCH body is valid (no required fields)."""
    assert validators.validate_user_update({}) == []


def test_validate_user_update_rejects_unknown_field():
    """REQ-USR-F04-AC3: unknown fields rejected on PATCH."""
    errs = validators.validate_user_update({"created_at": "x"})
    assert any("unknown field" in e for e in errs)


def test_validate_user_update_validates_present_fields():
    """REQ-USR-F04-AC2: present fields are validated individually."""
    assert validators.validate_user_update({"email": "bad"})
    assert validators.validate_user_update({"role": "nope"})


# --------------------------------------------------------------------------- #
# pagination.py — REQ-USR-F06
# --------------------------------------------------------------------------- #
def test_parse_pagination_defaults():
    """REQ-USR-F06-AC1: defaults page=1, page_size=20."""
    assert pagination.parse_pagination_params({}) == (1, 20)


def test_parse_pagination_valid_values():
    """REQ-USR-F06-AC2: supplied integers are parsed."""
    assert pagination.parse_pagination_params(
        {"page": "3", "page_size": "50"}
    ) == (3, 50)


@pytest.mark.parametrize("args", [
    {"page_size": "101"},          # AC4: exceeds max
    {"page": "0"},                 # AC5: page < 1
    {"page_size": "0"},            # AC5: page_size < 1
    {"page": ""},                  # AC6: empty string
    {"page": "abc"},               # AC6: non-numeric
    {"page": "1.5"},               # AC6: non-integer
    {"page_size": "1.5"},          # AC6: non-integer
])
def test_parse_pagination_invalid_raises(args):
    """REQ-USR-F06-AC4/AC5/AC6: invalid pagination raises PaginationError."""
    with pytest.raises(PaginationError):
        pagination.parse_pagination_params(args)


def test_paginate_slices_and_reports_total():
    """REQ-USR-F06-AC2/AC7: slice correct, total is pre-slice length."""
    items = list(range(25))
    result = pagination.paginate(items, page=2, page_size=10)
    assert result["items"] == list(range(10, 20))
    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["total"] == 25


def test_paginate_page_beyond_last_returns_empty():
    """REQ-USR-F06-AC7: page beyond last returns empty items, correct total."""
    items = list(range(5))
    result = pagination.paginate(items, page=10, page_size=20)
    assert result["items"] == []
    assert result["total"] == 5
    assert result["page"] == 10
