"""HTTP layer for the event-service — a Flask Blueprint (T-12).

The Blueprint owns *only* the HTTP concerns: parsing and validating the request
body/query params, delegating to :class:`~app.service.EventService`, serialising
the result, choosing the status code and setting the ``Location`` header on a
201. It holds **no** business logic (design §3) — every domain rule (organizer
verification B01/B02/B05, date coherence B03, status transitions B04, list
filters B06) lives in the service layer.

Responsibilities per operation:

- ``POST   /api/v1/events``       → 201 + ``Location`` + ``Event`` body (REQ-EVT-F02)
- ``GET    /api/v1/events``       → 200 paginated + filters (REQ-EVT-F06, B06)
- ``GET    /api/v1/events/<id>``  → 200 or 404 (REQ-EVT-F05)
- ``PUT    /api/v1/events/<id>``  → 200 or 404/422/503 (REQ-EVT-F07)
- ``PATCH  /api/v1/events/<id>``  → 200 or 404/422/503 (REQ-EVT-F08)
- ``DELETE /api/v1/events/<id>``  → 204 no body, or 404 (REQ-EVT-F09)

Error mapping (REQ-EVT-F12):

- :class:`~app.service.ServiceError` → its own ``code``/``status`` (422/404/503),
  built by :func:`app.errors.make_error_response`. This funnels
  ``REFERENCE_NOT_FOUND`` / ``INVALID_ORGANIZER`` / ``INVALID_STATUS_TRANSITION``
  (422), ``NOT_FOUND`` (404) and ``DEPENDENCY_UNAVAILABLE`` (503) through a
  single translation point.
- field validation errors                    → 422 ``VALIDATION_ERROR``
- :class:`~app.pagination.PaginationError`   → 422 ``VALIDATION_ERROR``
- a non-object body (``[]``, scalar, null)   → 422 ``VALIDATION_ERROR``
- malformed JSON body                         → 400 ``MALFORMED_JSON`` (Flask 400 handler)

The repository and user-service client live in ``current_app.config["REPO"]``
and ``current_app.config["USER_CLIENT"]`` (injected by :func:`app.create_app`);
an :class:`EventService` is constructed per request from them, so the routes
stay stateless and the backend/dependency remain swappable (design §3).
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app import errors
from app.pagination import PaginationError, parse_pagination_params
from app.service import EventService, ServiceError
from app.validators import (
    validate_body_is_object,
    validate_event_create,
    validate_event_update,
)

events_bp = Blueprint("events", __name__)

_EVENTS_PATH = "/api/v1/events"


def _service() -> EventService:
    """Build an :class:`EventService` from the request-scoped collaborators.

    The repository and user-service client live in ``current_app.config``
    (injected by :func:`app.create_app`). A fresh service wrapper is cheap and
    keeps the routes free of any backend/transport detail (design §3).
    """
    return EventService(
        current_app.config["REPO"], current_app.config["USER_CLIENT"]
    )


def _parse_json_body():
    """Parse the request body as JSON, mapping a broken body to 400.

    Returns the decoded JSON value (which may be a dict, list, scalar or
    ``None``). Raises :class:`werkzeug.exceptions.BadRequest` when the body is
    not syntactically valid JSON, so Flask's 400 handler produces the standard
    ``MALFORMED_JSON`` error (REQ-EVT-F12). Structural validation (must be an
    object) and value validation happen later in the caller, so a valid-but-
    wrong-shape body yields 422, not 400.
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


def _service_error(exc: ServiceError):
    """Translate a :class:`ServiceError` into the standard error response."""
    return errors.make_error_response(exc.code, exc.message, status=exc.status)


@events_bp.post(_EVENTS_PATH)
def create_event():
    """POST /api/v1/events → 201 with the created Event and a Location header.

    Validates the body against the ``EventCreate`` rules (REQ-EVT-F03),
    delegates creation to the service (organizer verification B01/B02/B05, date
    coherence B03, UUID/timestamps and status default live there) and returns
    the serialised event with a ``Location`` header pointing at
    ``/api/v1/events/<id>`` (REQ-EVT-F02-AC1).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_event_create(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().create_event(data)
    except ServiceError as exc:
        return _service_error(exc)

    response = jsonify(record)
    response.status_code = 201
    response.headers["Location"] = f"{_EVENTS_PATH}/{record['id']}"
    return response


@events_bp.get(_EVENTS_PATH)
def list_events():
    """GET /api/v1/events → 200 with a paginated, filtered EventPage.

    Parses and validates ``page``/``page_size`` (REQ-EVT-F06) and the optional
    ``status``/``city`` filters (REQ-EVT-B06). Invalid pagination or an invalid
    ``status`` filter both map to 422 ``VALIDATION_ERROR``. This endpoint never
    contacts the user-service (REQ-EVT-F06-AC7).
    """
    try:
        page, page_size = parse_pagination_params(request.args)
    except PaginationError as exc:
        return _validation_error([str(exc)])

    filters = {
        "status": request.args.get("status"),
        "city": request.args.get("city"),
    }

    try:
        page_result = _service().list_events(filters, page, page_size)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(page_result), 200


@events_bp.get(f"{_EVENTS_PATH}/<id>")
def get_event(id: str):
    """GET /api/v1/events/<id> → 200 with the Event, or 404 if absent.

    A syntactically invalid or simply unknown id yields 404 ``NOT_FOUND``
    (REQ-EVT-F05). No outbound HTTP call is made (REQ-EVT-F05-AC4).
    """
    try:
        record = _service().get_event(id)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(record), 200


@events_bp.put(f"{_EVENTS_PATH}/<id>")
def replace_event(id: str):
    """PUT /api/v1/events/<id> → 200 with the replaced Event.

    Uses the ``EventCreate`` rules (all required fields, REQ-EVT-F07). Maps a
    missing event to 404, an incoherent date pair / disallowed status
    transition / reference error to 422, and a user-service outage to 503.
    ``created_at`` is preserved and ``updated_at`` refreshed by the service
    (REQ-EVT-F07-AC5, REQ-EVT-F11).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_event_create(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().replace_event(id, data)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(record), 200


@events_bp.patch(f"{_EVENTS_PATH}/<id>")
def update_event(id: str):
    """PATCH /api/v1/events/<id> → 200 with the (partially) updated Event.

    Uses the ``EventUpdate`` rules (all fields optional, REQ-EVT-F04/F08). An
    empty body ``{}`` returns the resource unchanged with ``updated_at`` intact
    (REQ-EVT-F04-AC6). Maps a missing event to 404, any validation / transition
    / reference failure to 422, and a user-service outage to 503. The record is
    fetched first by the service, so a PATCH against a missing id is 404 even
    for an empty or unknown-field body (REQ-EVT-F04-AC5).
    """
    data = _parse_json_body()

    if not validate_body_is_object(data):
        return _validation_error(["request body must be a JSON object"])

    field_errors = validate_event_update(data)
    if field_errors:
        return _validation_error(field_errors)

    try:
        record = _service().update_event(id, data)
    except ServiceError as exc:
        return _service_error(exc)

    return jsonify(record), 200


@events_bp.delete(f"{_EVENTS_PATH}/<id>")
def delete_event(id: str):
    """DELETE /api/v1/events/<id> → 204 with no body, or 404 if absent.

    A successful delete returns 204 with an empty body and no JSON
    Content-Type (REQ-EVT-F09-AC1, REQ-EVT-F12). A missing event (including a
    second delete of the same id) yields 404 (REQ-EVT-F09-AC2). No outbound
    HTTP call is made (REQ-EVT-F09-AC4).
    """
    try:
        _service().delete_event(id)
    except ServiceError as exc:
        return _service_error(exc)

    return "", 204
