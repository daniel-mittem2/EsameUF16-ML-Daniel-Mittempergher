"""Business logic layer for the event-service (REQ-EVT-B*).

:class:`EventService` orchestrates the domain rules on top of an injected
:class:`~app.repository.AbstractEventRepository` and an injected
:class:`~app.http_client.UserServiceClient`. It never imports a concrete
backend, never touches Flask, and never issues an outbound request directly
(the HTTP details live in ``http_client.py``), so it can be unit-tested in
isolation with a :class:`~app.backends.memory.MemoryEventRepository` and a
``UserServiceClient`` whose requests are mocked by ``responses``
(REQ-EVT-F14-AC4, REQ-EVT-T01-AC2).

Error-signaling pattern
------------------------
Every domain failure is raised as a :class:`ServiceError` that carries the
uniform error ``code`` (one of the ``errors.py`` constants) and the HTTP
``status`` the routes layer (T-12) will emit via
:func:`app.errors.make_error_response`. Keeping a single service exception with
``code``/``status``/``message`` isolates the HTTP layer from both the storage
layer and the ``http_client`` transport exceptions, and keeps the mapping of
``ReferenceNotFoundError`` / ``InvalidOrganizerError`` /
``DependencyUnavailableError`` -> HTTP in one place.

Responsibilities implemented in T-09:

- ``create_event`` (T-09): re-checks date coherence (REQ-EVT-B03) **before** any
  outbound organizer call, verifies the organizer (REQ-EVT-B01, REQ-EVT-B02),
  maps the dependency's transport failures to 503 (REQ-EVT-B05), applies the
  ``status`` default, generates the UUID and timestamps
  (REQ-EVT-F02, REQ-EVT-F11) and persists the record.

Responsibilities implemented in T-10:

- ``get_event`` (T-10): retrieves a single event by id, raising ``NOT_FOUND``
  (404) when absent (REQ-EVT-F05). No outbound HTTP call is made — reading an
  event does not touch the user-service.
- ``list_events`` (T-10): validates the optional ``status`` filter against the
  contract enum (invalid value -> ``VALIDATION_ERROR`` 422), delegates the
  ``status``/``city`` AND filtering to the repository (REQ-EVT-B06), and applies
  pagination via :func:`app.pagination.paginate` so ``total`` is the post-filter
  pre-pagination count (REQ-EVT-F06).
"""
from __future__ import annotations

from app import errors
from app.http_client import (
    DependencyUnavailableError,
    InvalidOrganizerError,
    ReferenceNotFoundError,
    UserServiceClient,
)
from app.models import event_to_dict, new_event_record, utcnow_iso
from app.pagination import paginate
from app.repository import AbstractEventRepository
from app.validators import VALID_STATUSES, validate_dates_coherent


class ServiceError(Exception):
    """Domain failure carrying an error ``code`` and the HTTP ``status`` to emit.

    The routes layer (T-12) maps this to a response via
    :func:`app.errors.make_error_response`, using ``code`` and ``status``
    directly and ``message`` as the human-readable text (REQ-EVT-F12). Using a
    single exception type keeps the service free of Flask and lets every rule
    signal its outcome uniformly.
    """

    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class EventService:
    """Coordinates event operations and business rules over a repository.

    Both collaborators are injected via the constructor (dependency injection,
    REQ-EVT-F14-AC4): the repository provides storage, the ``user_client``
    performs organizer verification against the user-service. The service holds
    no storage or transport details of its own.
    """

    def __init__(self, repo: AbstractEventRepository, user_client: UserServiceClient) -> None:
        self._repo = repo
        self._user_client = user_client

    def create_event(self, data: dict) -> dict:
        """Create a new event and return the stored record (REQ-EVT-F02).

        Field-level validation (REQ-EVT-F03) is performed upstream by the routes
        layer. The service still re-checks the cross-field date invariant
        ``end_date`` >= ``start_date`` (REQ-EVT-B03) **before** any outbound
        organizer call, so an incoherent date pair never triggers a misleading
        503 (REQ-EVT-F02-AC7, REQ-EVT-B01-AC4). It then verifies the organizer
        (existence B01, role B02), applies the ``status`` default and generates
        the UUID and identical ``created_at``/``updated_at`` timestamps via
        :func:`app.models.new_event_record` (REQ-EVT-F11-AC2), and persists the
        record.

        Args:
            data: Validated ``EventCreate`` body containing at least the required
                fields; ``description`` and ``status`` optional.

        Returns:
            The persisted event record serialised to the contract shape (the 13
            ``Event`` fields).

        Raises:
            ServiceError: ``VALIDATION_ERROR`` (422) when ``end_date`` precedes
                ``start_date`` (REQ-EVT-B03); ``REFERENCE_NOT_FOUND`` (422) when
                the organizer does not exist (REQ-EVT-B01); ``INVALID_ORGANIZER``
                (422) when the referenced user is not an organizer
                (REQ-EVT-B02); ``DEPENDENCY_UNAVAILABLE`` (503) when the
                user-service cannot be reached (REQ-EVT-B05).
        """
        # Date coherence (B03) is a cross-field rule re-checked here BEFORE any
        # HTTP call: an invalid date pair must never reach the dependency
        # (REQ-EVT-F02-AC7, REQ-EVT-B01-AC4, REQ-EVT-B03-AC4).
        if not validate_dates_coherent(data.get("start_date"), data.get("end_date")):
            raise ServiceError(
                errors.VALIDATION_ERROR,
                "end_date must be greater than or equal to start_date",
                errors.ERROR_CODES[errors.VALIDATION_ERROR],
            )

        # Organizer verification (B01 existence + B02 role); transport failures
        # (timeout / refused / 5xx) become 503 DEPENDENCY_UNAVAILABLE (B05).
        self._verify_organizer(data["organizer_id"])

        now = utcnow_iso()
        record = new_event_record(data, now)  # status default + UUID + timestamps
        stored = self._repo.create(record)
        return event_to_dict(stored)

    def get_event(self, event_id: str) -> dict:
        """Return a single event serialised to the contract shape (REQ-EVT-F05).

        Reading an event never contacts the user-service: no outbound HTTP call
        is issued here (REQ-EVT-F05). A missing event is a ``NOT_FOUND`` (404),
        distinct from the reference/validation 422 family used elsewhere.

        Args:
            event_id: The id of the event to retrieve.

        Returns:
            The stored event record serialised to the 13 contract ``Event``
            fields.

        Raises:
            ServiceError: ``NOT_FOUND`` (404) when no event with ``event_id``
                exists (REQ-EVT-F05).
        """
        record = self._repo.get(event_id)
        if record is None:
            raise ServiceError(
                errors.NOT_FOUND,
                f"event {event_id!r} not found",
                errors.ERROR_CODES[errors.NOT_FOUND],
            )
        return event_to_dict(record)

    def list_events(self, filters: dict, page: int, page_size: int) -> dict:
        """Return a paginated ``EventPage`` of events matching ``filters``.

        The optional ``status``/``city`` filters are combined with AND logic by
        the repository (REQ-EVT-B06); ``city`` is a free-string exact match while
        ``status`` must be one of the contract enum values. An unrecognised
        ``status`` filter value is a ``VALIDATION_ERROR`` (422) rather than an
        empty result, so a client typo is surfaced explicitly (REQ-EVT-B06-AC2).

        ``total`` reflects the number of records after filtering but before
        slicing (post-filter, pre-pagination); pagination is applied by
        :func:`app.pagination.paginate`, so a page beyond the last returns an
        empty ``items`` list with the correct ``total`` (REQ-EVT-F06).

        Args:
            filters: Optional filter dict with ``status`` and/or ``city`` keys;
                values of ``None`` (or absent keys) impose no constraint.
            page: 1-based page number (already validated by the routes layer).
            page_size: Page size (already validated by the routes layer).

        Returns:
            An ``EventPage`` dict: ``items`` (each serialised via
            :func:`app.models.event_to_dict`), ``page``, ``page_size`` and
            ``total``.

        Raises:
            ServiceError: ``VALIDATION_ERROR`` (422) when the ``status`` filter
                value is not one of the contract enum values (REQ-EVT-B06-AC2).
        """
        status = filters.get("status")
        if status is not None and status not in VALID_STATUSES:
            raise ServiceError(
                errors.VALIDATION_ERROR,
                "status must be one of draft, published, cancelled",
                errors.ERROR_CODES[errors.VALIDATION_ERROR],
            )

        records = self._repo.list_all(filters)
        items = [event_to_dict(record) for record in records]
        return paginate(items, page, page_size)

    def _verify_organizer(self, organizer_id: str) -> dict:
        """Verify the organizer, translating transport exceptions to ServiceError.

        Maps the ``http_client`` exceptions to the uniform service error:

        * :class:`ReferenceNotFoundError`     -> 422 ``REFERENCE_NOT_FOUND`` (B01)
        * :class:`InvalidOrganizerError`      -> 422 ``INVALID_ORGANIZER``  (B02)
        * :class:`DependencyUnavailableError` -> 503 ``DEPENDENCY_UNAVAILABLE`` (B05)

        A user-service 404 is a *reference* error (422), never *availability*
        (503) — that distinction is enforced by the client and preserved here
        (REQ-EVT-B05-AC5).
        """
        try:
            return self._user_client.verify_organizer(organizer_id)
        except ReferenceNotFoundError as exc:
            raise ServiceError(
                errors.REFERENCE_NOT_FOUND,
                f"organizer_id {organizer_id!r} does not reference an existing user",
                errors.ERROR_CODES[errors.REFERENCE_NOT_FOUND],
            ) from exc
        except InvalidOrganizerError as exc:
            raise ServiceError(
                errors.INVALID_ORGANIZER,
                f"user {organizer_id!r} exists but is not an organizer",
                errors.ERROR_CODES[errors.INVALID_ORGANIZER],
            ) from exc
        except DependencyUnavailableError as exc:
            raise ServiceError(
                errors.DEPENDENCY_UNAVAILABLE,
                "user-service is unavailable",
                errors.ERROR_CODES[errors.DEPENDENCY_UNAVAILABLE],
            ) from exc
