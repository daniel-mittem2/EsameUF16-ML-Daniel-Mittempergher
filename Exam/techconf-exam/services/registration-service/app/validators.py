"""Pure input-validation functions for the registration-service.

These functions have no state, no Flask context, and no repository access, so
they can be unit-tested in isolation. They return lists of human-readable error
strings (empty list == valid), except for ``validate_body_is_object`` which
returns a boolean.

Validation covers the contract schemas ``RegistrationCreate`` and
``RegistrationPatch`` (both ``additionalProperties: false`` — unknown fields are
rejected here since JSON Schema's ``additionalProperties`` is not enforced
automatically), the ``stats`` required ``event_id`` query parameter, and the
optional list filters. No implicit type coercion is performed (a non-string
``user_id`` is a validation error, not coerced) (REQ-REG-F03, REQ-REG-F05,
REQ-REG-F06).
"""
from __future__ import annotations

import uuid
from typing import List

# Fields allowed by RegistrationCreate (contract schema).
_ALLOWED_CREATE_FIELDS = {"user_id", "event_id"}
_REQUIRED_CREATE_FIELDS = ("user_id", "event_id")

# Fields allowed by RegistrationPatch (contract schema): only ``status``.
_ALLOWED_PATCH_FIELDS = {"status"}

# The RegistrationStatus enum from the contract.
VALID_STATUSES = {"confirmed", "cancelled"}

# UUID length when formatted with hyphens (8-4-4-4-12).
_UUID_LEN = 36


def _is_str(value) -> bool:
    """True if value is a string (bool is explicitly excluded, no coercion)."""
    return isinstance(value, str) and not isinstance(value, bool)


def _is_uuid(value) -> bool:
    """True if ``value`` is a syntactically valid UUID string."""
    if not _is_str(value):
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return len(value) == _UUID_LEN


def validate_body_is_object(data) -> bool:
    """Return True only if the body is a JSON object (dict).

    A JSON array, ``null``, or a scalar (string, number, boolean) is not an
    object (REQ-REG-F03-AC3).
    """
    return isinstance(data, dict)


def _validate_uuid_field(field: str, value) -> List[str]:
    """Validate a required UUID field with no coercion."""
    if not _is_str(value):
        return [f"{field} must be a string"]
    if not _is_uuid(value):
        return [f"{field} must be a valid UUID"]
    return []


def validate_registration_create(data: dict) -> List[str]:
    """Validate a RegistrationCreate body (used by POST).

    Both ``user_id`` and ``event_id`` are required and must be syntactically
    valid UUID strings; no other field is allowed (``additionalProperties:
    false``); no coercion. Returns a list of error strings; empty list means
    valid (REQ-REG-F03).
    """
    errors: List[str] = []
    errors.extend(
        f"unknown field: {key}" for key in data if key not in _ALLOWED_CREATE_FIELDS
    )
    for field in _REQUIRED_CREATE_FIELDS:
        if field not in data:
            errors.append(f"{field} is required")
        else:
            errors.extend(_validate_uuid_field(field, data[field]))
    return errors


def validate_registration_patch(data: dict) -> List[str]:
    """Validate a RegistrationPatch body (used by PATCH).

    ``status`` is required and must be one of the contract enum values; no other
    field is allowed (``additionalProperties: false``). The transition rules
    (REQ-REG-B07) are enforced by the service layer, not here. Returns a list of
    error strings; empty list means valid (REQ-REG-F06).
    """
    errors: List[str] = []
    errors.extend(
        f"unknown field: {key}" for key in data if key not in _ALLOWED_PATCH_FIELDS
    )
    if "status" not in data:
        errors.append("status is required")
    else:
        value = data["status"]
        if not _is_str(value):
            errors.append("status must be a string")
        elif value not in VALID_STATUSES:
            errors.append("status must be one of confirmed, cancelled")
    return errors


def validate_stats_query(args) -> List[str]:
    """Validate the ``stats`` query parameters.

    ``event_id`` is a required query parameter and must be a syntactically valid
    UUID; when absent or invalid the routes layer responds 422 (REQ-REG-B08-AC4,
    REQ-REG-F03). Returns a list of error strings; empty list means valid.
    """
    errors: List[str] = []
    event_id = args.get("event_id")
    if event_id is None:
        errors.append("event_id is required")
    else:
        errors.extend(_validate_uuid_field("event_id", event_id))
    return errors


def validate_list_filters(args) -> List[str]:
    """Validate the optional list filters.

    ``status`` (when present) must be one of the contract enum values;
    ``user_id`` and ``event_id`` (when present) must be syntactically valid
    UUIDs. An unrecognised filter value is a validation error rather than an
    empty result, so a client typo is surfaced explicitly (REQ-REG-F05-AC4/AC5).
    Returns a list of error strings; empty list means valid.
    """
    errors: List[str] = []

    status = args.get("status")
    if status is not None:
        if not _is_str(status):
            errors.append("status must be a string")
        elif status not in VALID_STATUSES:
            errors.append("status must be one of confirmed, cancelled")

    for field in ("user_id", "event_id"):
        value = args.get(field)
        if value is not None:
            errors.extend(_validate_uuid_field(field, value))

    return errors
