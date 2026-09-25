"""HTTP layer for the registration-service — a Flask Blueprint (T-12).

The Blueprint owns *only* the HTTP concerns: parsing and validating the request
body/query params, delegating to :class:`~app.service.RegistrationService`,
serialising the result, choosing the status code and setting the ``Location``
header on a 201. It holds **no** business logic (design §3) — every domain rule
(user/event verification B01/B02, published check B03, capacity/duplicate
B04/B05, amount copy B06, status transitions B07, stats B08, dependency mapping
B09) lives in the service layer.

Responsibilities per operation (design §3, contract
``registration-service.yaml``):

- ``POST   /api/v1/registrations``          → 201 + ``Location`` + ``Registration`` (REQ-REG-F02)
- ``GET    /api/v1/registrations``          → 200 paginated + filters (REQ-REG-F05)
- ``GET    /api/v1/registrations/stats``    → 200 ``RegistrationStats`` (REQ-REG-B08)
- ``GET    /api/v1/registrations/<id>``     → 200 or 404 (REQ-REG-F04)
- ``PATCH  /api/v1/registrations/<id>``     → 200 or 404/422 (REQ-REG-F06)
- ``DELETE /api/v1/registrations/<id>``     → 204 no body, or 404 (REQ-REG-F07)
- ``PUT    /api/v1/registrations/<id>``     → 405 with ``Error`` body (REQ-REG-F08)

**Route ordering (design §3).** The static ``/stats`` route is declared *before*
the ``/<id>`` route so that ``GET /api/v1/registrations/stats`` is never
interpreted as ``GET /api/v1/registrations/{id=stats}``. Flask gives priority to
static rules over variable rules, but the explicit ordering makes the intent
clear.

Error mapping (REQ-REG-F11):

- :class:`~app.service.ServiceError` → its ``code`` mapped to the HTTP status via
  ``errors.ERROR_CODES``, built by :func:`app.errors.make_error_response`. This
  funnels ``REFERENCE_NOT_FOUND`` / ``EVENT_NOT_OPEN`` /
  ``INVALID_STATUS_TRANSITION`` (422), ``NOT_FOUND`` (404),
  ``ALREADY_REGISTERED`` / ``EVENT_FULL`` (409) and ``DEPENDENCY_UNAVAILABLE``
  (503) through a single translation point.
- field validation errors                    → 422 ``VALIDATION_ERROR``
- :class:`~app.pagination.PaginationError`   → 422 ``VALIDATION_ERROR``
- a non-object body (``[]``, scalar, null)   → 422 ``VALIDATION_ERROR``
- malformed JSON body                         → 400 ``MALFORMED_JSON`` (Flask 400 handler)

The repository and the two dependency clients live in
``current_app.config["REPO"]`` / ``["USER_CLIENT"]`` / ``["EVENT_CLIENT"]``
(injected by :func:`app.create_app`); a :class:`RegistrationService` is
constructed per request from them, so the routes stay stateless and the
backend/dependencies remain swappable (design §3).
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app import errors
from app.pagination import PaginationError, parse_pagination_params
from app.service import RegistrationService, ServiceError
from app.validators import (
    validate_body_is_object,
    validate_registration_create,
    validate_registration_patch,
    validate_stats_query,
    validate_list_filters,
)

registrations_bp = Blueprint("registrations", __name__)

_REGISTRATIONS_PATH = "/api/v1/registrations"


def _service() -> RegistrationService:
    """Build a :class:`RegistrationService` from request-scoped collaborators.

    The repository and the two dependency clients live in
    ``current_app.config`` (injected by :func:`app.create_app`). A fresh service
    wrapper is cheap and keeps the routes free of any backend/transport detail
    (design §3).
    """
    return RegistrationService(
        current_app.config["REPO"],
        current_app.config["USER_CLIENT"],
        current_app.config["EVENT_CLIENT"],
    )


def _parse_json_body():
    """Parse the request body as JSON, mapping a broken body to 400.

    Returns the decoded JSON value (dict, list, scalar or ``None``). Raises
    :class:`werkzeug.exceptions.BadRequest` when the body is not syntactically
    valid JSON, so Flask's 400 handler produces the standard ``MALFORMED_JSON``
    error (REQ-REG-F03-AC4). Structural validation (must be an object) and value
    validation happen later, so a valid-but-wrong-shape body yields 422, not 400.
    """
    return request.get_json(force=True, silent=False)


def _validation_error(messages):
    """Build a 422 VALIDATION_ERROR response from a list of field errors."""
    return errors.make_error_response(
        errors.VALIDATION_ERROR,
        "Request validation failed",
        details={"errors": list(messages)},
        status=422,
    )


def _service_error(exc: ServiceError):
    """Translate a :class:`ServiceError` into the standard error response.

    The HTTP status is derived from the error ``code`` via ``errors.ERROR_CODES``
    (REQ-REG-F11-AC3), the single mapping point for the service.
    """
    return errors.make_error_response(exc.code, exc.message, details=exc.details)


@registrations_bp.post(_REGISTRATIONS_PATH)
def create_registration():
    """POST /api/v1/registrations → 201 with the created Registration + Location.

    Validates the body against the ``RegistrationCreate`` rules
    (``user_id``/``event_id`` present, valid UUIDs, no other field —
    REQ-REG-F02-AC6, REQ-REG-F03) *before* any dependency call
    (REQ-REG-F03-AC5), delegates creation to the service (user/event checks,
    published check, amount copy, atomic duplicate + capacity + create) and
    returns the serialised registration with a ``Location`` header pointing at
    ``/api/v1/registrations/<id>`` (REQ-REG-F02-AC1).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_registration_create(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().create_registration(data)
    except ServiceError as exc:
        return _service_error(exc)

    response = jsonify(record)
    response.status_code = 201
    response.headers["Location"] = f"{_REGISTRATIONS_PATH}/{record['id']}"
    return response


@registrations_bp.get(_REGISTRATIONS_PATH)
def list_registrations():
    """GET /api/v1/registrations → 200 with a paginated, filtered RegistrationPage.

    Parses and validates ``page``/``page_size`` (REQ-REG-F05-AC2/AC3) and the
    optional ``user_id``/``event_id``/``status`` filters, applied with AND logic
    (REQ-REG-F05-AC4). Invalid pagination, an invalid ``status`` filter or an
    invalid filter UUID all map to 422 ``VALIDATION_ERROR``. This endpoint never
    contacts a dependency (REQ-REG-F05-AC7).
    """
    try:
        page, page_size = parse_pagination_params(request.args)
    except PaginationError as exc:
        return _validation_error([str(exc)])

    filter_errors = validate_list_filters(request.args)
    if filter_errors:
        return _validation_error(filter_errors)

    filters = {
        "user_id": request.args.get("user_id"),
        "event_id": request.args.get("event_id"),
        "status": request.args.get("status"),
    }

    try:
        page_result = _service().list_registrations(filters, page, page_size)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(page_result), 200


@registrations_bp.get(f"{_REGISTRATIONS_PATH}/stats")
def registration_stats():
    """GET /api/v1/registrations/stats → 200 with RegistrationStats (REQ-REG-B08).

    Declared **before** the ``/<id>`` route so ``stats`` is not captured as an
    id (design §3). ``event_id`` is a required query parameter: when absent or
    not a valid UUID the response is 422 ``VALIDATION_ERROR`` (REQ-REG-B08-AC4).
    The service fetches the event from event-service (a 404 → 404 ``NOT_FOUND``
    per REQ-REG-B08-AC3, an outage → 503 ``DEPENDENCY_UNAVAILABLE`` per
    REQ-REG-B08-AC5), counts ``confirmed`` locally and computes
    ``available = capacity - confirmed``.
    """
    query_errors = validate_stats_query(request.args)
    if query_errors:
        return _validation_error(query_errors)

    event_id = request.args.get("event_id")

    try:
        result = _service().stats(event_id)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(result), 200


@registrations_bp.get(f"{_REGISTRATIONS_PATH}/<id>")
def get_registration(id: str):
    """GET /api/v1/registrations/<id> → 200 with the Registration, or 404.

    A syntactically invalid or simply unknown id yields 404 ``NOT_FOUND``
    (REQ-REG-F04-AC2). No outbound HTTP call is made (REQ-REG-F04-AC4).
    """
    try:
        record = _service().get_registration(id)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(record), 200


@registrations_bp.patch(f"{_REGISTRATIONS_PATH}/<id>")
def update_registration(id: str):
    """PATCH /api/v1/registrations/<id> → 200 with the updated Registration.

    The ``RegistrationPatch`` body must contain only ``status`` (a valid enum
    value); a missing ``status`` or any other field is 422 ``VALIDATION_ERROR``
    (REQ-REG-F06-AC2/AC3). The service locates the resource first (missing id →
    404, REQ-REG-F06-AC4) and applies the transition rules of REQ-REG-B07
    (``confirmed → cancelled`` ok, reactivation → 422
    ``INVALID_STATUS_TRANSITION``, same status → no-op). Only ``status`` is
    mutated (REQ-REG-F06-AC6).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_registration_patch(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().patch_status(id, data["status"])
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(record), 200


@registrations_bp.delete(f"{_REGISTRATIONS_PATH}/<id>")
def delete_registration(id: str):
    """DELETE /api/v1/registrations/<id> → 204 with no body, or 404 if absent.

    A successful delete returns 204 with an empty body and no JSON
    Content-Type (REQ-REG-F07-AC1). A missing registration (including a second
    delete of the same id) yields 404 ``NOT_FOUND`` (REQ-REG-F07-AC2). No
    outbound HTTP call is made (REQ-REG-F07-AC3).
    """
    try:
        _service().delete_registration(id)
    except ServiceError as exc:
        return _service_error(exc)

    return "", 204


@registrations_bp.put(f"{_REGISTRATIONS_PATH}/<id>")
def put_registration_not_allowed(id: str):
    """PUT /api/v1/registrations/<id> → 405 with an Error body (REQ-REG-F08).

    The contract explicitly declares ``putRegistrationNotAllowed`` returning 405.
    An explicit route returns the standard ``Error`` body with code
    ``METHOD_NOT_ALLOWED`` so the response conforms to the contract regardless of
    whether ``id`` exists (REQ-REG-F08-AC1/AC2).
    """
    return errors.make_error_response(
        errors.METHOD_NOT_ALLOWED,
        "PUT is not allowed on a registration",
        status=405,
    )
