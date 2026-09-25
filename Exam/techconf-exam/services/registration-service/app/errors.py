"""Error codes and standard error response builder for the registration-service.

All error responses across the service conform to the ``Error`` schema of the
contract: ``{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {}}}``.
The ``details`` field is always a JSON object, never ``null`` (REQ-REG-F11-AC4).

This module is the single place where the ``{"error": ...}`` body is built
(REQ-REG-F11).
"""
from __future__ import annotations

from typing import Optional

from flask import jsonify

# --- Error code constants (UPPER_SNAKE_CASE, REQ-REG-F11-AC2) ---------------
VALIDATION_ERROR = "VALIDATION_ERROR"
REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
EVENT_NOT_OPEN = "EVENT_NOT_OPEN"
ALREADY_REGISTERED = "ALREADY_REGISTERED"
EVENT_FULL = "EVENT_FULL"
INVALID_STATUS_TRANSITION = "INVALID_STATUS_TRANSITION"
NOT_FOUND = "NOT_FOUND"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
MALFORMED_JSON = "MALFORMED_JSON"
DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"

# Mapping error code -> default HTTP status code (REQ-REG-F11-AC3).
#   400 malformed JSON, 404 not found, 405 method not allowed,
#   409 conflict (ALREADY_REGISTERED, EVENT_FULL),
#   422 validation / reference / business rule, 503 dependency unavailable.
ERROR_CODES = {
    VALIDATION_ERROR: 422,
    REFERENCE_NOT_FOUND: 422,
    EVENT_NOT_OPEN: 422,
    INVALID_STATUS_TRANSITION: 422,
    ALREADY_REGISTERED: 409,
    EVENT_FULL: 409,
    NOT_FOUND: 404,
    METHOD_NOT_ALLOWED: 405,
    MALFORMED_JSON: 400,
    DEPENDENCY_UNAVAILABLE: 503,
}


def make_error_response(
    code: str,
    message: str,
    details: Optional[dict] = None,
    status: Optional[int] = None,
):
    """Build a standard error response tuple ``(jsonify(body), http_status)``.

    ``details`` is always serialised as a JSON object, never ``null``
    (REQ-REG-F11-AC4). When ``status`` is not provided, it is derived from
    ``ERROR_CODES`` for the given ``code``, defaulting to 422.
    """
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        }
    }
    http_status = status if status is not None else ERROR_CODES.get(code, 422)
    return jsonify(body), http_status
