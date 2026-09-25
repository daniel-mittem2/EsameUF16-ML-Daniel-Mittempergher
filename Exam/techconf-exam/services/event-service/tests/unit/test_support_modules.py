"""Unit tests for the event-service support modules.

Covers errors (REQ-EVT-F12), models (REQ-EVT-F02, REQ-EVT-F11), pagination
(REQ-EVT-F06), and validators (REQ-EVT-F03, REQ-EVT-F04, REQ-EVT-B03).
"""
import re

import pytest
from flask import Flask

from app import errors, models, pagination, validators
from app.pagination import PaginationError


# --------------------------------------------------------------------------- #
# errors.py — REQ-EVT-F12
# --------------------------------------------------------------------------- #
@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield app


def test_error_code_constants_are_upper_snake():
    """REQ-EVT-F12-AC2: all service error codes are UPPER_SNAKE_CASE strings."""
    codes = (
        errors.VALIDATION_ERROR,
        errors.REFERENCE_NOT_FOUND,
        errors.INVALID_ORGANIZER,
        errors.INVALID_STATUS_TRANSITION,
        errors.NOT_FOUND,
        errors.METHOD_NOT_ALLOWED,
        errors.MALFORMED_JSON,
        errors.DEPENDENCY_UNAVAILABLE,
    )
    for code in codes:
        assert re.fullmatch(r"[A-Z_]+", code)


def test_error_codes_map_to_expected_statuses():
    """REQ-EVT-F12-AC3: HTTP status matches the semantics of each code."""
    assert errors.ERROR_CODES[errors.VALIDATION_ERROR] == 422
    assert errors.ERROR_CODES[errors.REFERENCE_NOT_FOUND] == 422
    assert errors.ERROR_CODES[errors.INVALID_ORGANIZER] == 422
    assert errors.ERROR_CODES[errors.INVALID_STATUS_TRANSITION] == 422
    assert errors.ERROR_CODES[errors.NOT_FOUND] == 404
    assert errors.ERROR_CODES[errors.METHOD_NOT_ALLOWED] == 405
    assert errors.ERROR_CODES[errors.MALFORMED_JSON] == 400
    assert errors.ERROR_CODES[errors.DEPENDENCY_UNAVAILABLE] == 503


def test_make_error_response_details_defaults_to_empty_dict(app_ctx):
    """REQ-EVT-F12-AC4: details is always an object, never null."""
    body, status = errors.make_error_response(errors.NOT_FOUND, "missing")
    payload = body.get_json()
    assert status == 404
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["message"] == "missing"
    assert payload["error"]["details"] == {}


def test_make_error_response_preserves_details_and_status(app_ctx):
    """REQ-EVT-F12-AC1: explicit details and status override are respected."""
    body, status = errors.make_error_response(
        errors.VALIDATION_ERROR, "bad", details={"field": "title"}, status=422
    )
    payload = body.get_json()
    assert status == 422
    assert payload["error"]["details"] == {"field": "title"}


def test_make_error_response_derives_status_from_code(app_ctx):
    """REQ-EVT-F12-AC3: status derived from ERROR_CODES when not provided."""
    _, status = errors.make_error_response(errors.DEPENDENCY_UNAVAILABLE, "down")
    assert status == 503


# --------------------------------------------------------------------------- #
# models.py — REQ-EVT-F02, REQ-EVT-F11
# --------------------------------------------------------------------------- #
def _valid_create_data():
    return {
        "title": "PyConf",
        "organizer_id": "11111111-1111-4111-8111-111111111111",
        "venue": "Main Hall",
        "city": "Rome",
        "start_date": "2026-10-15",
        "end_date": "2026-10-17",
        "capacity": 100,
        "price": 0,
    }


def test_new_event_record_applies_defaults():
    """REQ-EVT-F02-AC5/AC6 + REQ-EVT-B04-AC3: status->draft, description->None."""
    rec = models.new_event_record(_valid_create_data(), "2026-01-01T00:00:00.000000Z")
    assert rec["status"] == "draft"
    assert rec["description"] is None
    assert rec["created_at"] == rec["updated_at"] == "2026-01-01T00:00:00.000000Z"
    assert re.fullmatch(r"[0-9a-f-]{36}", rec["id"])


def test_new_event_record_keeps_supplied_status_and_description():
    """REQ-EVT-F02: explicit status/description are preserved."""
    data = _valid_create_data()
    data["status"] = "published"
    data["description"] = "A great conference"
    rec = models.new_event_record(data, "2026-01-01T00:00:00.000000Z")
    assert rec["status"] == "published"
    assert rec["description"] == "A great conference"


def test_new_event_record_explicit_null_description_preserved():
    """REQ-EVT-F02-AC6: explicit null description is stored as None."""
    data = _valid_create_data()
    data["description"] = None
    rec = models.new_event_record(data, "2026-01-01T00:00:00.000000Z")
    assert rec["description"] is None


def test_event_to_dict_returns_only_thirteen_contract_fields():
    """REQ-EVT-F02-AC8: response has exactly the 13 contract fields."""
    record = {f: f for f in models.EVENT_FIELDS}
    record["secret_internal"] = "should not appear"
    result = models.event_to_dict(record)
    assert set(result.keys()) == set(models.EVENT_FIELDS)
    assert len(result) == 13


def test_utcnow_iso_format():
    """REQ-EVT-F11-AC1: ISO 8601 UTC ending in Z, microsecond precision."""
    ts = models.utcnow_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", ts)


# --------------------------------------------------------------------------- #
# validators.py — REQ-EVT-F03, REQ-EVT-F04, REQ-EVT-B03
# --------------------------------------------------------------------------- #
def test_validate_body_is_object():
    """REQ-EVT-F03-AC10: only dict bodies are objects."""
    assert validators.validate_body_is_object({}) is True
    for bad in ([], None, "x", 1, True):
        assert validators.validate_body_is_object(bad) is False


def test_validate_event_create_valid_minimal():
    """REQ-EVT-F03: a minimal valid body has no errors."""
    assert validators.validate_event_create(_valid_create_data()) == []


def test_validate_event_create_missing_required():
    """REQ-EVT-F03-AC1..AC7: all missing required fields are flagged."""
    errs = validators.validate_event_create({})
    for field in (
        "title",
        "organizer_id",
        "venue",
        "city",
        "start_date",
        "end_date",
        "capacity",
        "price",
    ):
        assert any(field in e for e in errs)


def test_validate_event_create_rejects_unknown_field():
    """REQ-EVT-F03-AC11 / additionalProperties false: unknown fields rejected."""
    data = _valid_create_data()
    data["id"] = "x"
    errs = validators.validate_event_create(data)
    assert any("unknown field" in e for e in errs)


def test_validate_event_create_read_only_fields_rejected():
    """REQ-EVT-F11-AC6: id, created_at, updated_at are rejected in a create body."""
    for ro in ("id", "created_at", "updated_at"):
        data = _valid_create_data()
        data[ro] = "x"
        errs = validators.validate_event_create(data)
        assert any("unknown field" in e for e in errs)


def test_validate_title_length_bounds():
    """REQ-EVT-F03-AC1: title must be 3..120 characters."""
    short = _valid_create_data()
    short["title"] = "ab"
    assert validators.validate_event_create(short)
    long = _valid_create_data()
    long["title"] = "x" * 121
    assert validators.validate_event_create(long)


def test_validate_venue_and_city_length():
    """REQ-EVT-F03-AC3/AC4: venue<=100, city<=60."""
    v = _valid_create_data()
    v["venue"] = "x" * 101
    assert validators.validate_event_create(v)
    c = _valid_create_data()
    c["city"] = "x" * 61
    assert validators.validate_event_create(c)


def test_validate_capacity_range_and_type():
    """REQ-EVT-F03-AC6/AC11: capacity integer 1..10000, no coercion."""
    for bad_cap in (0, 10001, "100", 1.5, True):
        data = _valid_create_data()
        data["capacity"] = bad_cap
        assert validators.validate_event_create(data), f"expected error for {bad_cap!r}"
    ok = _valid_create_data()
    ok["capacity"] = 10000
    assert validators.validate_event_create(ok) == []


def test_validate_price_range_and_type():
    """REQ-EVT-F03-AC7/AC11: price number >= 0, no coercion of strings."""
    neg = _valid_create_data()
    neg["price"] = -1
    assert validators.validate_event_create(neg)
    bad_type = _valid_create_data()
    bad_type["price"] = "10"
    assert validators.validate_event_create(bad_type)
    ok = _valid_create_data()
    ok["price"] = 12.5
    assert validators.validate_event_create(ok) == []


def test_validate_description_nullable_and_length():
    """REQ-EVT-F03-AC8: description nullable, max 2000 chars."""
    null_desc = _valid_create_data()
    null_desc["description"] = None
    assert validators.validate_event_create(null_desc) == []
    long_desc = _valid_create_data()
    long_desc["description"] = "x" * 2001
    assert validators.validate_event_create(long_desc)


def test_validate_status_enum():
    """REQ-EVT-F03-AC9: status must be one of the contract enum values."""
    bad = _valid_create_data()
    bad["status"] = "archived"
    assert validators.validate_event_create(bad)
    for good in ("draft", "published", "cancelled"):
        ok = _valid_create_data()
        ok["status"] = good
        assert validators.validate_event_create(ok) == []


def test_validate_organizer_id_must_be_uuid():
    """REQ-EVT-F03-AC2: organizer_id must be a syntactically valid UUID."""
    bad = _valid_create_data()
    bad["organizer_id"] = "not-a-uuid"
    assert validators.validate_event_create(bad)
    wrong_type = _valid_create_data()
    wrong_type["organizer_id"] = 123
    assert validators.validate_event_create(wrong_type)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-10-15", True),
        ("2026-02-30", False),   # impossible calendar date
        ("2026-13-01", False),   # invalid month
        ("15-10-2026", False),   # wrong format
        ("2026/10/15", False),   # wrong separator
        ("", False),
        (None, False),
        (20261015, False),       # not a string, no coercion
    ],
)
def test_validate_date(value, expected):
    """REQ-EVT-F03-AC5: only well-formed YYYY-MM-DD strings are valid dates."""
    assert validators.validate_date(value) is expected


def test_validate_dates_coherent():
    """REQ-EVT-B03: end_date must be >= start_date."""
    assert validators.validate_dates_coherent("2026-10-15", "2026-10-17") is True
    assert validators.validate_dates_coherent("2026-10-15", "2026-10-15") is True
    assert validators.validate_dates_coherent("2026-10-17", "2026-10-15") is False
    assert validators.validate_dates_coherent("bad", "2026-10-15") is False


def test_validate_event_create_end_before_start_flagged():
    """REQ-EVT-B03-AC2: create with end_date < start_date yields an error."""
    data = _valid_create_data()
    data["start_date"] = "2026-10-17"
    data["end_date"] = "2026-10-15"
    errs = validators.validate_event_create(data)
    assert any("end_date" in e for e in errs)


def test_validate_event_update_all_optional():
    """REQ-EVT-F04-AC1: an empty PATCH body is valid (no required fields)."""
    assert validators.validate_event_update({}) == []


def test_validate_event_update_rejects_unknown_field():
    """REQ-EVT-F04-AC2: unknown fields rejected on PATCH."""
    errs = validators.validate_event_update({"created_at": "x"})
    assert any("unknown field" in e for e in errs)


def test_validate_event_update_validates_present_fields():
    """REQ-EVT-F04-AC3: present fields obey the same constraints as create."""
    assert validators.validate_event_update({"capacity": "100"})
    assert validators.validate_event_update({"status": "nope"})
    assert validators.validate_event_update({"title": "ab"})


def test_validate_event_update_date_coherence_when_both_present():
    """REQ-EVT-B03-AC3: PATCH with both dates re-checks end>=start."""
    assert validators.validate_event_update(
        {"start_date": "2026-10-17", "end_date": "2026-10-15"}
    )
    assert validators.validate_event_update(
        {"start_date": "2026-10-15", "end_date": "2026-10-17"}
    ) == []


def test_validate_event_update_single_date_not_cross_checked():
    """REQ-EVT-B03-AC3: a single-date PATCH is not cross-checked in the validator."""
    # Only one date present — the service layer re-validates against the stored
    # value; the pure validator does not flag a coherence error here.
    assert validators.validate_event_update({"end_date": "2026-10-15"}) == []


# --------------------------------------------------------------------------- #
# pagination.py — REQ-EVT-F06
# --------------------------------------------------------------------------- #
def test_parse_pagination_defaults():
    """REQ-EVT-F06-AC1: defaults page=1, page_size=20."""
    assert pagination.parse_pagination_params({}) == (1, 20)


def test_parse_pagination_valid_values():
    """REQ-EVT-F06-AC2: supplied integers are parsed."""
    assert pagination.parse_pagination_params({"page": "3", "page_size": "50"}) == (3, 50)


@pytest.mark.parametrize(
    "args",
    [
        {"page_size": "101"},   # AC3: exceeds max
        {"page": "0"},          # AC3: page < 1
        {"page_size": "0"},     # AC3: page_size < 1
        {"page": ""},           # AC3: empty string
        {"page": "abc"},        # AC3: non-numeric
        {"page": "1.5"},        # AC3: non-integer
        {"page_size": "1.5"},   # AC3: non-integer
    ],
)
def test_parse_pagination_invalid_raises(args):
    """REQ-EVT-F06-AC3: invalid pagination raises PaginationError."""
    with pytest.raises(PaginationError):
        pagination.parse_pagination_params(args)


def test_paginate_slices_and_reports_total():
    """REQ-EVT-F06-AC2/AC5: slice correct, total is pre-slice length."""
    items = list(range(25))
    result = pagination.paginate(items, page=2, page_size=10)
    assert result["items"] == list(range(10, 20))
    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["total"] == 25


def test_paginate_page_beyond_last_returns_empty():
    """REQ-EVT-F06-AC6: page beyond last returns empty items, correct total."""
    items = list(range(5))
    result = pagination.paginate(items, page=10, page_size=20)
    assert result["items"] == []
    assert result["total"] == 5
    assert result["page"] == 10
