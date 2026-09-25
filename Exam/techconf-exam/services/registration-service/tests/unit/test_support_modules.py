"""Unit tests for the registration-service support modules.

Covers errors (REQ-REG-F11), models (REQ-REG-F02, REQ-REG-F10), pagination
(REQ-REG-F05), and validators (REQ-REG-F03, REQ-REG-F05, REQ-REG-F06).
"""
import re
import uuid

import pytest
from flask import Flask

from app import errors, models, pagination, validators
from app.pagination import PaginationError


# --------------------------------------------------------------------------- #
# errors.py — REQ-REG-F11
# --------------------------------------------------------------------------- #
@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield app


def test_error_code_constants_are_upper_snake():
    """REQ-REG-F11-AC2: all service error codes are UPPER_SNAKE_CASE strings."""
    codes = (
        errors.VALIDATION_ERROR,
        errors.REFERENCE_NOT_FOUND,
        errors.EVENT_NOT_OPEN,
        errors.ALREADY_REGISTERED,
        errors.EVENT_FULL,
        errors.INVALID_STATUS_TRANSITION,
        errors.NOT_FOUND,
        errors.METHOD_NOT_ALLOWED,
        errors.MALFORMED_JSON,
        errors.DEPENDENCY_UNAVAILABLE,
    )
    for code in codes:
        assert re.fullmatch(r"[A-Z_]+", code)


def test_error_codes_map_to_expected_statuses():
    """REQ-REG-F11-AC3: HTTP status matches the semantics of each code."""
    assert errors.ERROR_CODES[errors.VALIDATION_ERROR] == 422
    assert errors.ERROR_CODES[errors.REFERENCE_NOT_FOUND] == 422
    assert errors.ERROR_CODES[errors.EVENT_NOT_OPEN] == 422
    assert errors.ERROR_CODES[errors.INVALID_STATUS_TRANSITION] == 422
    assert errors.ERROR_CODES[errors.ALREADY_REGISTERED] == 409
    assert errors.ERROR_CODES[errors.EVENT_FULL] == 409
    assert errors.ERROR_CODES[errors.NOT_FOUND] == 404
    assert errors.ERROR_CODES[errors.METHOD_NOT_ALLOWED] == 405
    assert errors.ERROR_CODES[errors.MALFORMED_JSON] == 400
    assert errors.ERROR_CODES[errors.DEPENDENCY_UNAVAILABLE] == 503


def test_make_error_response_details_defaults_to_empty_dict(app_ctx):
    """REQ-REG-F11-AC4: details is always an object, never null."""
    body, status = errors.make_error_response(errors.NOT_FOUND, "missing")
    payload = body.get_json()
    assert status == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["message"] == "missing"
    assert payload["error"]["details"] == {}


def test_make_error_response_derives_status_from_code(app_ctx):
    """REQ-REG-F11-AC3: status derived from ERROR_CODES when not given."""
    _, status = errors.make_error_response(errors.EVENT_FULL, "full")
    assert status == 409


def test_make_error_response_explicit_status_and_details(app_ctx):
    """REQ-REG-F11: explicit status and details are preserved verbatim."""
    body, status = errors.make_error_response(
        errors.VALIDATION_ERROR, "bad", details={"errors": ["x"]}, status=422
    )
    payload = body.get_json()
    assert status == 422
    assert payload["error"]["details"] == {"errors": ["x"]}


# --------------------------------------------------------------------------- #
# models.py — REQ-REG-F02, REQ-REG-F10
# --------------------------------------------------------------------------- #
def test_utcnow_iso_has_microsecond_precision_and_z_suffix():
    """REQ-REG-F10: ISO 8601 UTC with microseconds and Z suffix."""
    ts = models.utcnow_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", ts)


def test_new_registration_record_generates_uuid4_and_confirmed():
    """REQ-REG-F02-AC2/AC3: id is a UUID v4 and status is confirmed."""
    now = "2026-10-15T09:30:00.123456Z"
    rec = models.new_registration_record("u", "e", 149.0, now)
    parsed = uuid.UUID(rec["id"])
    assert parsed.version == 4
    assert rec["status"] == "confirmed"


def test_new_registration_record_copies_amount_and_timestamps():
    """REQ-REG-B06 + REQ-REG-F10-AC2: amount preserved, created==updated."""
    now = "2026-10-15T09:30:00.123456Z"
    rec = models.new_registration_record("user-1", "event-1", 149.0, now)
    assert rec["user_id"] == "user-1"
    assert rec["event_id"] == "event-1"
    assert rec["amount"] == 149.0
    assert rec["created_at"] == now
    assert rec["updated_at"] == now


def test_registration_to_dict_exposes_exactly_seven_contract_fields():
    """REQ-REG-F02-AC7: serialisation exposes the 7 Registration fields only."""
    rec = models.new_registration_record("u", "e", 10, "2026-01-01T00:00:00.000000Z")
    rec["extra"] = "should not leak"
    out = models.registration_to_dict(rec)
    assert set(out.keys()) == {
        "id",
        "user_id",
        "event_id",
        "amount",
        "status",
        "created_at",
        "updated_at",
    }


# --------------------------------------------------------------------------- #
# pagination.py — REQ-REG-F05
# --------------------------------------------------------------------------- #
def test_parse_pagination_defaults_when_absent():
    """REQ-REG-F05-AC1: defaults page=1, page_size=20."""
    page, page_size = pagination.parse_pagination_params({})
    assert (page, page_size) == (1, 20)


def test_parse_pagination_valid_values():
    """REQ-REG-F05-AC2: valid integers are echoed back."""
    page, page_size = pagination.parse_pagination_params({"page": "2", "page_size": "50"})
    assert (page, page_size) == (2, 50)


@pytest.mark.parametrize(
    "args",
    [
        {"page": ""},
        {"page_size": ""},
        {"page": "abc"},
        {"page_size": "1.5"},
        {"page": "0"},
        {"page_size": "0"},
        {"page_size": "101"},
        {"page": "-1"},
    ],
)
def test_parse_pagination_invalid_raises(args):
    """REQ-REG-F05-AC3: empty/non-numeric/non-integer/out-of-range -> error."""
    with pytest.raises(PaginationError):
        pagination.parse_pagination_params(args)


def test_paginate_reports_total_pre_slice():
    """REQ-REG-F05-AC6: total is the pre-slice (post-filter) length."""
    items = list(range(25))
    page = pagination.paginate(items, page=1, page_size=10)
    assert page["total"] == 25
    assert page["items"] == list(range(10))
    assert page["page"] == 1
    assert page["page_size"] == 10


def test_paginate_beyond_last_page_returns_empty_items():
    """REQ-REG-F05: page beyond the last returns empty items, correct total."""
    items = list(range(5))
    page = pagination.paginate(items, page=10, page_size=20)
    assert page["items"] == []
    assert page["total"] == 5
    assert page["page"] == 10


# --------------------------------------------------------------------------- #
# validators.py — REQ-REG-F03, REQ-REG-F05, REQ-REG-F06
# --------------------------------------------------------------------------- #
_UUID_A = str(uuid.uuid4())
_UUID_B = str(uuid.uuid4())


@pytest.mark.parametrize(
    "data,expected",
    [
        ({}, True),          # an empty object is still a valid JSON object
        ([], False),
        (None, False),
        ("x", False),
        (3, False),
        (True, False),
        ({"a": 1}, True),
    ],
)
def test_validate_body_is_object(data, expected):
    """REQ-REG-F03-AC3: only a JSON object counts as a valid body."""
    assert validators.validate_body_is_object(data) is expected


def test_validate_registration_create_ok():
    """REQ-REG-F03: valid user_id/event_id UUIDs pass."""
    assert validators.validate_registration_create(
        {"user_id": _UUID_A, "event_id": _UUID_B}
    ) == []


@pytest.mark.parametrize(
    "data",
    [
        {"event_id": _UUID_B},                         # user_id missing
        {"user_id": _UUID_A},                          # event_id missing
        {"user_id": "not-a-uuid", "event_id": _UUID_B},
        {"user_id": _UUID_A, "event_id": 123},         # non-string, no coercion
        {"user_id": _UUID_A, "event_id": _UUID_B, "amount": 10},  # extra field
        {"user_id": _UUID_A, "event_id": _UUID_B, "status": "confirmed"},  # extra
        {"user_id": _UUID_A, "event_id": _UUID_B, "id": _UUID_A},  # client id
    ],
)
def test_validate_registration_create_rejects(data):
    """REQ-REG-F03-AC1/AC2/AC6 + REQ-REG-F02-AC6: reject invalid create bodies."""
    assert validators.validate_registration_create(data) != []


def test_validate_registration_patch_ok():
    """REQ-REG-F06: a lone valid status passes validation."""
    assert validators.validate_registration_patch({"status": "cancelled"}) == []


@pytest.mark.parametrize(
    "data",
    [
        {},                                        # status missing
        {"status": "unknown"},                     # not in enum
        {"status": 1},                             # non-string
        {"status": "confirmed", "user_id": _UUID_A},  # extra field
    ],
)
def test_validate_registration_patch_rejects(data):
    """REQ-REG-F06-AC2/AC3: reject missing/invalid/extra patch fields."""
    assert validators.validate_registration_patch(data) != []


def test_validate_stats_query_ok():
    """REQ-REG-B08-AC4: a valid event_id passes."""
    assert validators.validate_stats_query({"event_id": _UUID_A}) == []


@pytest.mark.parametrize(
    "args",
    [
        {},                          # event_id absent
        {"event_id": "not-a-uuid"},  # invalid UUID
    ],
)
def test_validate_stats_query_rejects(args):
    """REQ-REG-B08-AC4: event_id is required and must be a UUID."""
    assert validators.validate_stats_query(args) != []


def test_validate_list_filters_empty_is_valid():
    """REQ-REG-F05: no filters is valid."""
    assert validators.validate_list_filters({}) == []


def test_validate_list_filters_all_valid():
    """REQ-REG-F05-AC4: valid status + uuid filters pass."""
    assert validators.validate_list_filters(
        {"status": "confirmed", "user_id": _UUID_A, "event_id": _UUID_B}
    ) == []


@pytest.mark.parametrize(
    "args",
    [
        {"status": "unknown"},        # not in enum
        {"user_id": "not-a-uuid"},    # invalid uuid
        {"event_id": "nope"},         # invalid uuid
    ],
)
def test_validate_list_filters_rejects(args):
    """REQ-REG-F05-AC5: invalid status enum or non-uuid filter -> error."""
    assert validators.validate_list_filters(args) != []
