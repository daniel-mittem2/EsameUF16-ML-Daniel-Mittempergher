"""HTTP layer for the user-service — a Flask Blueprint (T-12).

The Blueprint owns *only* the HTTP concerns: parsing and validating the request
body/query params, delegating to :class:`~app.service.UserService`, serialising
the result with :func:`~app.models.user_to_dict`, choosing the status code and
setting the ``Location`` header on a 201. It holds **no** business logic
(REQ-USR-F14-AC5) — every domain rule lives in the service layer.

Responsibilities per operation:

- ``POST   /api/v1/users``       → 201 + ``Location`` + ``User`` body (REQ-USR-F02)
- ``GET    /api/v1/users``       → 200 paginated + filters (REQ-USR-F06, B03)
- ``GET    /api/v1/users/<id>``  → 200 or 404 (REQ-USR-F05)
- ``PUT    /api/v1/users/<id>``  → 200 or 404/409/422 (REQ-USR-F07)
- ``PATCH  /api/v1/users/<id>``  → 200 or 404/409/422 (REQ-USR-F08)
- ``DELETE /api/v1/users/<id>``  → 204 no body (REQ-USR-F09)

Error mapping (REQ-USR-F12):

- :class:`~app.service.EmailConflictError`  → 409 ``EMAIL_ALREADY_EXISTS``
- :class:`~app.service.UserNotFoundError`   → 404 ``NOT_FOUND``
- :class:`~app.service.InvalidFilterError`  → 422 ``VALIDATION_ERROR``
- field validation errors                   → 422 ``VALIDATION_ERROR``
- :class:`~app.pagination.PaginationError`  → 422 ``VALIDATION_ERROR``
- malformed JSON body                        → 400 ``MALFORMED_JSON``

The repository instance is stored in ``current_app.config["REPO"]``; a
:class:`UserService` is constructed per request from it, so the routes stay
stateless and the backend remains swappable (REQ-USR-F14).
"""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import BadRequest

from app import errors
from app.models import user_to_dict
from app.pagination import PaginationError, parse_pagination_params
from app.service import (
    EmailConflictError,
    InvalidFilterError,
    UserNotFoundError,
    UserService,
)
from app.validators import (
    validate_body_is_object,
    validate_user_create,
    validate_user_update,
)

users_bp = Blueprint("users", __name__)

_USERS_PATH = "/api/v1/users"


def _service() -> UserService:
    """Build a :class:`UserService` from the request-scoped repository.

    The repository lives in ``current_app.config["REPO"]`` (injected by
    :func:`app.create_app`). A fresh service wrapper is cheap and keeps the
    routes free of any backend detail (REQ-USR-F14).
    """
    return UserService(current_app.config["REPO"])


def _parse_json_body():
    """Parse the request body as JSON, mapping a broken body to 400.

    Returns the decoded JSON value (which may be a dict, list, scalar or
    ``None``). Raises :class:`werkzeug.exceptions.BadRequest` when the body is
    not syntactically valid JSON, so Flask's 400 handler produces the standard
    ``MALFORMED_JSON`` error (REQ-USR-F03-AC7/AC8, REQ-USR-F04-AC5).

    Structural validation (must be an object) and value validation happen later
    in the caller, so a valid-but-wrong-shape body yields 422, not 400.
    """
    # force=True: parse regardless of Content-Type. silent=False: raise
    # BadRequest on malformed JSON so the 400 handler fires. An empty body is
    # treated as malformed for POST/PUT/PATCH (the schemas require content).
    return request.get_json(force=True, silent=False)


def _validation_error(messages):
    """Build a 422 VALIDATION_ERROR response from a list of field errors."""
    return errors.make_error_response(
        errors.VALIDATION_ERROR,
        "Request validation failed",
        details={"errors": list(messages)},
        status=422,
    )


@users_bp.post(_USERS_PATH)
def create_user():
    """POST /api/v1/users → 201 with the created User and a Location header.

    Validates the body against the ``UserCreate`` rules (REQ-USR-F02, F03),
    delegates creation to the service (email normalisation + uniqueness live
    there, REQ-USR-B01/B02) and returns the serialised user with a ``Location``
    header pointing at ``/api/v1/users/<id>`` (REQ-USR-F02-AC1).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_user_create(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().create_user(data)
    except EmailConflictError as exc:
        return errors.make_error_response(
            errors.EMAIL_ALREADY_EXISTS, str(exc), status=409
        )

    body = user_to_dict(record)
    response = jsonify(body)
    response.status_code = 201
    response.headers["Location"] = f"{_USERS_PATH}/{record['id']}"
    return response


@users_bp.get(_USERS_PATH)
def list_users():
    """GET /api/v1/users → 200 with a paginated, filtered UserPage.

    Parses and validates ``page``/``page_size`` (REQ-USR-F06) and the optional
    ``role``/``email`` filters (REQ-USR-B03). Invalid pagination or an invalid
    ``role`` filter both map to 422 ``VALIDATION_ERROR``.
    """
    try:
        page, page_size = parse_pagination_params(request.args)
    except PaginationError as exc:
        return _validation_error([str(exc)])

    filters = {
        "role": request.args.get("role"),
        "email": request.args.get("email"),
    }

    try:
        page_result = _service().list_users(filters, page, page_size)
    except InvalidFilterError as exc:
        return _validation_error([str(exc)])

    return jsonify(page_result), 200


@users_bp.get(f"{_USERS_PATH}/<id>")
def get_user(id: str):
    """GET /api/v1/users/<id> → 200 with the User, or 404 if absent.

    A syntactically invalid or simply unknown id yields 404 ``NOT_FOUND``
    (REQ-USR-F05-AC2/AC3).
    """
    try:
        record = _service().get_user(id)
    except UserNotFoundError as exc:
        return errors.make_error_response(errors.NOT_FOUND, str(exc), status=404)

    return jsonify(user_to_dict(record)), 200


@users_bp.put(f"{_USERS_PATH}/<id>")
def replace_user(id: str):
    """PUT /api/v1/users/<id> → 200 with the replaced User.

    Uses the ``UserCreate`` rules (required fields, REQ-USR-F07-AC2). Maps a
    missing user to 404, a cross-user email collision to 409 and any validation
    failure to 422. ``created_at`` is preserved and ``updated_at`` refreshed by
    the service (REQ-USR-F07-AC5, REQ-USR-F11).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_user_create(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().replace_user(id, data)
    except UserNotFoundError as exc:
        return errors.make_error_response(errors.NOT_FOUND, str(exc), status=404)
    except EmailConflictError as exc:
        return errors.make_error_response(
            errors.EMAIL_ALREADY_EXISTS, str(exc), status=409
        )

    return jsonify(user_to_dict(record)), 200


@users_bp.patch(f"{_USERS_PATH}/<id>")
def update_user(id: str):
    """PATCH /api/v1/users/<id> → 200 with the (partially) updated User.

    Uses the ``UserUpdate`` rules (all fields optional, REQ-USR-F04/F08). An
    empty body ``{}`` returns the resource unchanged with timestamps intact
    (REQ-USR-F04-AC4). Maps a missing user to 404, a cross-user email collision
    to 409 and any validation failure to 422.
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_user_update(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().update_user(id, data)
    except UserNotFoundError as exc:
        return errors.make_error_response(errors.NOT_FOUND, str(exc), status=404)
    except EmailConflictError as exc:
        return errors.make_error_response(
            errors.EMAIL_ALREADY_EXISTS, str(exc), status=409
        )

    return jsonify(user_to_dict(record)), 200


@users_bp.delete(f"{_USERS_PATH}/<id>")
def delete_user(id: str):
    """DELETE /api/v1/users/<id> → 204 with no body, or 404 if absent.

    A successful delete returns 204 with an empty body and no JSON
    Content-Type (REQ-USR-F09-AC1, REQ-USR-F12-AC6). A missing user (including
    a second delete of the same id) yields 404 (REQ-USR-F09-AC2/AC4).
    """
    try:
        _service().delete_user(id)
    except UserNotFoundError as exc:
        return errors.make_error_response(errors.NOT_FOUND, str(exc), status=404)

    return "", 204
