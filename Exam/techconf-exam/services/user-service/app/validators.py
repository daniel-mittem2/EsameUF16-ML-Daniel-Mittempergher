"""Pure input-validation functions for the user-service.

These functions have no state, no Flask context, and no repository access, so
they can be unit-tested in isolation. They return lists of human-readable error
strings (empty list == valid), except for the boolean helpers.

Validation covers the contract schemas ``UserCreate`` and ``UserUpdate``, both
declared with ``additionalProperties: false`` — unknown fields are rejected
here since JSON Schema's ``additionalProperties`` is not enforced automatically
(REQ-USR-F03-AC4, REQ-USR-F04-AC3).
"""
from __future__ import annotations

import re
from typing import List

# Minimal email regex: form local@domain.tld (design §4).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Fields allowed by UserCreate / UserUpdate (contract schemas).
_ALLOWED_FIELDS = {"first_name", "last_name", "email", "company", "role"}
_REQUIRED_CREATE_FIELDS = ("first_name", "last_name", "email")
# Public: the role enum from the contract, shared with the service layer's
# list filter validation (REQ-USR-B03-AC5).
VALID_ROLES = {"attendee", "speaker", "organizer"}
_VALID_ROLES = VALID_ROLES  # backward-compatible alias for internal callers

_MAX_NAME_LEN = 50
_MAX_COMPANY_LEN = 100


def validate_body_is_object(data) -> bool:
    """Return True only if the body is a JSON object (dict).

    A JSON array, ``null``, or a scalar (string, number, boolean) is not an
    object (REQ-USR-F03-AC9, REQ-USR-F04-AC6).
    """
    return isinstance(data, dict)


def validate_email_format(email) -> bool:
    """Return True if ``email`` is a syntactically valid email address.

    Accepts ``alice@example.com`` / ``user+tag@sub.domain.org``; rejects
    ``notanemail``, ``@domain.com``, ``user@``, ``user@@domain.com``.
    """
    return bool(_EMAIL_RE.match(email)) if isinstance(email, str) else False


def _is_str(value) -> bool:
    """True if value is a string (bool is explicitly excluded, no coercion)."""
    return isinstance(value, str) and not isinstance(value, bool)


def _validate_name(field: str, value) -> List[str]:
    """Validate a required name field (first_name / last_name)."""
    if not _is_str(value):
        return [f"{field} must be a string"]
    if len(value) < 1 or len(value) > _MAX_NAME_LEN:
        return [f"{field} must be between 1 and {_MAX_NAME_LEN} characters"]
    return []


def _validate_email_field(value) -> List[str]:
    """Validate the email field type and format."""
    if not _is_str(value):
        return ["email must be a string"]
    if not validate_email_format(value):
        return ["email is not a valid email address"]
    return []


def _validate_company(value) -> List[str]:
    """Validate the company field. company is the only field that accepts null."""
    if value is None:
        return []
    if not _is_str(value):
        return ["company must be a string or null"]
    if len(value) > _MAX_COMPANY_LEN:
        return [f"company must be at most {_MAX_COMPANY_LEN} characters"]
    return []


def _validate_role(value) -> List[str]:
    """Validate the role field against the allowed enum."""
    if not _is_str(value):
        return ["role must be a string"]
    if value not in _VALID_ROLES:
        return ["role must be one of attendee, speaker, organizer"]
    return []


def _unknown_field_errors(data: dict) -> List[str]:
    """Return errors for any key not defined in the contract schema."""
    return [
        f"unknown field: {key}"
        for key in data
        if key not in _ALLOWED_FIELDS
    ]


def validate_user_create(data: dict) -> List[str]:
    """Validate a UserCreate body (used by POST and PUT).

    Required fields must be present; unknown fields are rejected
    (``additionalProperties: false``). Returns a list of error strings; empty
    list means valid.
    """
    errors: List[str] = []
    errors.extend(_unknown_field_errors(data))

    # Required field presence.
    for field in _REQUIRED_CREATE_FIELDS:
        if field not in data:
            errors.append(f"{field} is required")

    if "first_name" in data:
        errors.extend(_validate_name("first_name", data["first_name"]))
    if "last_name" in data:
        errors.extend(_validate_name("last_name", data["last_name"]))
    if "email" in data:
        errors.extend(_validate_email_field(data["email"]))
    if "company" in data:
        errors.extend(_validate_company(data["company"]))
    if "role" in data:
        errors.extend(_validate_role(data["role"]))

    return errors


def validate_user_update(data: dict) -> List[str]:
    """Validate a UserUpdate body (used by PATCH).

    All fields are optional; only the fields present are validated. Unknown
    fields are rejected (``additionalProperties: false``). Returns a list of
    error strings; empty list means valid.
    """
    errors: List[str] = []
    errors.extend(_unknown_field_errors(data))

    if "first_name" in data:
        errors.extend(_validate_name("first_name", data["first_name"]))
    if "last_name" in data:
        errors.extend(_validate_name("last_name", data["last_name"]))
    if "email" in data:
        errors.extend(_validate_email_field(data["email"]))
    if "company" in data:
        errors.extend(_validate_company(data["company"]))
    if "role" in data:
        errors.extend(_validate_role(data["role"]))

    return errors
