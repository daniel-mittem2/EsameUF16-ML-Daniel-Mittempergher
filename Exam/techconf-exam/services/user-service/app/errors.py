"""Error codes and standard error response builder for the user-service.

All error responses across the service conform to the ``Error`` schema of the
contract: ``{"error": {"code": "UPPER_SNAKE", "message": "...", "details": {}}}``.
The ``details`` field is always a JSON object, never ``null`` (REQ-USR-F12-AC3).

This module is the single place where the ``{"error": ...}`` body is built.
"""
from __future__ import annotations

from typing import Optional

from flask import jsonify

# --- Error code constants (UPPER_SNAKE_CASE, REQ-USR-F12-AC2) ---------------
VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
MALFORMED_JSON = "MALFORMED_JSON"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"

# Mapping error code -> default HTTP status code.
ERROR_CODES = {
    VALIDATION_ERROR: 422,
    NOT_FOUND: 404,
    EMAIL_ALREADY_EXISTS: 409,
    MALFORMED_JSON: 400,
    METHOD_NOT_ALLOWED: 405,
}


def make_error_response(
    code: str,
    message: str,
    details: Optional[dict] = None,
    status: Optional[int] = None,
):
    """Build a standard error response tuple ``(jsonify(body), http_status)``.

    ``details`` is always serialised as a JSON object, never ``null``
    (REQ-USR-F12-AC3). When ``status`` is not provided, it is derived from
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
