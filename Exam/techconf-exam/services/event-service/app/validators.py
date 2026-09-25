"""Pure input-validation functions for the event-service.

These functions have no state, no Flask context, and no repository access, so
they can be unit-tested in isolation. They return lists of human-readable error
strings (empty list == valid), except for the boolean/date helpers.

Validation covers the contract schemas ``EventCreate`` and ``EventUpdate``, both
declared with ``additionalProperties: false`` — unknown fields are rejected
here since JSON Schema's ``additionalProperties`` is not enforced automatically
(REQ-EVT-F03-AC10/AC11, REQ-EVT-F04-AC2). No implicit type coercion is performed
(REQ-EVT-F03-AC11): the string ``"100"`` is not accepted for the integer
``capacity``. ``description`` is the only field that accepts ``null``.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

# Fields allowed by EventCreate / EventUpdate (contract schemas).
_ALLOWED_FIELDS = {
    "title",
    "description",
    "organizer_id",
    "venue",
    "city",
    "start_date",
    "end_date",
    "capacity",
    "price",
    "status",
}
_REQUIRED_CREATE_FIELDS = (
    "title",
    "organizer_id",
    "venue",
    "city",
    "start_date",
    "end_date",
    "capacity",
    "price",
)

# Public: the status enum from the contract, shared with the service layer's
# list filter validation (REQ-EVT-B06-AC2).
VALID_STATUSES = {"draft", "published", "cancelled"}

_TITLE_MIN_LEN = 3
_TITLE_MAX_LEN = 120
_VENUE_MAX_LEN = 100
_CITY_MAX_LEN = 60
_DESCRIPTION_MAX_LEN = 2000
_CAPACITY_MIN = 1
_CAPACITY_MAX = 10000

# UUID length when formatted with hyphens (8-4-4-4-12).
_UUID_LEN = 36


def validate_body_is_object(data) -> bool:
    """Return True only if the body is a JSON object (dict).

    A JSON array, ``null``, or a scalar (string, number, boolean) is not an
    object (REQ-EVT-F03-AC10).
    """
    return isinstance(data, dict)


def validate_date(value) -> bool:
    """Return True if ``value`` is a valid ``YYYY-MM-DD`` date string.

    Rejects non-strings, wrong formats, and impossible calendar dates
    (e.g. ``2026-02-30``) (REQ-EVT-F03-AC5).
    """
    if not _is_str(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    # ``date.fromisoformat`` accepts exactly ``YYYY-MM-DD`` for date objects;
    # guard the length to reject any surprising accepted extended forms.
    return len(value) == 10


def validate_dates_coherent(start, end) -> bool:
    """Return True if ``end`` >= ``start`` (both valid ``YYYY-MM-DD`` strings).

    Returns False if either date is invalid or if ``end`` precedes ``start``
    (REQ-EVT-B03).
    """
    if not (validate_date(start) and validate_date(end)):
        return False
    return date.fromisoformat(end) >= date.fromisoformat(start)


def _is_str(value) -> bool:
    """True if value is a string (bool is explicitly excluded, no coercion)."""
    return isinstance(value, str) and not isinstance(value, bool)


def _is_int(value) -> bool:
    """True if value is an int (bool excluded — no coercion, REQ-EVT-F03-AC11)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    """True if value is a number (int or float; bool excluded, no coercion)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_uuid(value) -> bool:
    """True if ``value`` is a syntactically valid UUID string."""
    if not _is_str(value):
        return False
    import uuid

    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return len(value) == _UUID_LEN


def _validate_title(value) -> List[str]:
    if not _is_str(value):
        return ["title must be a string"]
    if len(value) < _TITLE_MIN_LEN or len(value) > _TITLE_MAX_LEN:
        return [f"title must be between {_TITLE_MIN_LEN} and {_TITLE_MAX_LEN} characters"]
    return []


def _validate_organizer_id(value) -> List[str]:
    if not _is_str(value):
        return ["organizer_id must be a string"]
    if not _is_uuid(value):
        return ["organizer_id must be a valid UUID"]
    return []


def _validate_venue(value) -> List[str]:
    if not _is_str(value):
        return ["venue must be a string"]
    if len(value) > _VENUE_MAX_LEN:
        return [f"venue must be at most {_VENUE_MAX_LEN} characters"]
    return []


def _validate_city(value) -> List[str]:
    if not _is_str(value):
        return ["city must be a string"]
    if len(value) > _CITY_MAX_LEN:
        return [f"city must be at most {_CITY_MAX_LEN} characters"]
    return []


def _validate_date_field(field: str, value) -> List[str]:
    if not validate_date(value):
        return [f"{field} must be a valid YYYY-MM-DD date"]
    return []


def _validate_capacity(value) -> List[str]:
    if not _is_int(value):
        return ["capacity must be an integer"]
    if value < _CAPACITY_MIN or value > _CAPACITY_MAX:
        return [f"capacity must be between {_CAPACITY_MIN} and {_CAPACITY_MAX}"]
    return []


def _validate_price(value) -> List[str]:
    if not _is_number(value):
        return ["price must be a number"]
    if value < 0:
        return ["price must be >= 0"]
    return []


def _validate_description(value) -> List[str]:
    """description is the only field that accepts null (REQ-EVT-F03-AC8)."""
    if value is None:
        return []
    if not _is_str(value):
        return ["description must be a string or null"]
    if len(value) > _DESCRIPTION_MAX_LEN:
        return [f"description must be at most {_DESCRIPTION_MAX_LEN} characters"]
    return []


def _validate_status(value) -> List[str]:
    if not _is_str(value):
        return ["status must be a string"]
    if value not in VALID_STATUSES:
        return ["status must be one of draft, published, cancelled"]
    return []


# Map of field name -> per-field validator, used by both create and update.
_FIELD_VALIDATORS = {
    "title": _validate_title,
    "organizer_id": _validate_organizer_id,
    "venue": _validate_venue,
    "city": _validate_city,
    "start_date": lambda v: _validate_date_field("start_date", v),
    "end_date": lambda v: _validate_date_field("end_date", v),
    "capacity": _validate_capacity,
    "price": _validate_price,
    "description": _validate_description,
    "status": _validate_status,
}


def _unknown_field_errors(data: dict) -> List[str]:
    """Return errors for any key not defined in the contract schema."""
    return [f"unknown field: {key}" for key in data if key not in _ALLOWED_FIELDS]


def _validate_present_fields(data: dict) -> List[str]:
    """Validate every present field against its per-field validator."""
    errors: List[str] = []
    for field, validator in _FIELD_VALIDATORS.items():
        if field in data:
            errors.extend(validator(data[field]))
    return errors


def _date_coherence_errors(start, end) -> List[str]:
    """Return the date-coherence error when both dates are valid but end<start.

    Type/format errors for the individual dates are reported by the per-field
    validators; this only adds the cross-field ``end >= start`` rule when both
    values are individually valid (REQ-EVT-B03).
    """
    if validate_date(start) and validate_date(end):
        if not validate_dates_coherent(start, end):
            return ["end_date must be greater than or equal to start_date"]
    return []


def validate_event_create(data: dict) -> List[str]:
    """Validate an EventCreate body (used by POST and PUT).

    Required fields must be present; unknown fields are rejected
    (``additionalProperties: false``); present fields must match their declared
    type/range/enum with no coercion; ``end_date`` must be >= ``start_date``.
    Returns a list of error strings; empty list means valid
    (REQ-EVT-F03, REQ-EVT-B03).
    """
    errors: List[str] = []
    errors.extend(_unknown_field_errors(data))

    for field in _REQUIRED_CREATE_FIELDS:
        if field not in data:
            errors.append(f"{field} is required")

    errors.extend(_validate_present_fields(data))
    errors.extend(_date_coherence_errors(data.get("start_date"), data.get("end_date")))

    return errors


def validate_event_update(data: dict) -> List[str]:
    """Validate an EventUpdate body (used by PATCH).

    All fields are optional; only the fields present are validated. Unknown
    fields are rejected (``additionalProperties: false``). The cross-field
    ``end_date`` >= ``start_date`` rule is applied only when both dates are
    present in the body; a PATCH that changes a single date is re-validated
    against the stored value by the service layer (REQ-EVT-F04, REQ-EVT-B03-AC3).
    Returns a list of error strings; empty list means valid.
    """
    errors: List[str] = []
    errors.extend(_unknown_field_errors(data))
    errors.extend(_validate_present_fields(data))

    if "start_date" in data and "end_date" in data:
        errors.extend(_date_coherence_errors(data.get("start_date"), data.get("end_date")))

    return errors
