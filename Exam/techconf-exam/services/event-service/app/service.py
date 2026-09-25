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

Responsibilities implemented in T-11:

- ``check_transition`` (T-11): enforces the status-transition state machine
  (REQ-EVT-B04). ``draft->published``, ``draft->cancelled`` and
  ``published->cancelled`` are allowed; an unchanged/absent status is a no-op;
  every other pair raises ``INVALID_STATUS_TRANSITION`` (422).
- ``replace_event`` (PUT, T-11): full replacement of an existing event
  (REQ-EVT-F07). 404 when the id is absent; verifies the organizer when
  ``organizer_id`` is present; enforces the status transition against the stored
  value (REQ-EVT-B04); preserves ``id``/``created_at`` and refreshes
  ``updated_at`` (REQ-EVT-F11); applies POST-style defaults (``status``->``draft``,
  ``description``->``None``) for omitted optionals since a PUT is a full replace.
- ``update_event`` (PATCH, T-11): partial update of an existing event
  (REQ-EVT-F08). Fetches the record **first** so an empty/unknown body on a
  missing id still returns 404; rejects unknown fields; an empty PATCH returns
  the record unchanged and does **not** bump ``updated_at`` (REQ-EVT-F04-AC6);
  re-validates ``end_date`` >= ``start_date`` against the merged (effective)
  record (REQ-EVT-B03); re-verifies the organizer only when ``organizer_id``
  changes; enforces the status transition (REQ-EVT-B04).
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

# Allowed status transitions (REQ-EVT-B04). Any (current, new) pair not in this
# set — with new != current — is rejected as INVALID_STATUS_TRANSITION (422).
# ``draft`` is the only launch state; ``cancelled`` is terminal.
_ALLOWED_TRANSITIONS = {
    ("draft", "published"),
    ("draft", "cancelled"),
    ("published", "cancelled"),
}

# Fields a PATCH body may contain (the EventUpdate schema, additionalProperties
# false). The service rejects anything else defensively even though the routes
# layer validates the body too (REQ-EVT-F04-AC2).
_PATCHABLE_FIELDS = {
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

    def check_transition(self, current: str, new) -> None:
        """Enforce the status-transition state machine (REQ-EVT-B04).

        A status is only ever a *transition* when it differs from the stored
        value. When ``new`` is ``None`` (absent from the request) or equal to
        ``current`` the state is unchanged and this is a no-op — it never raises
        ``INVALID_STATUS_TRANSITION`` (REQ-EVT-B04-AC5). Otherwise the pair must
        be one of the allowed transitions (``draft->published``,
        ``draft->cancelled``, ``published->cancelled``); any other pair (e.g.
        ``published->draft``) is rejected.

        Args:
            current: The currently stored status.
            new: The requested status, or ``None`` when the request omits it.

        Raises:
            ServiceError: ``INVALID_STATUS_TRANSITION`` (422) when ``new`` differs
                from ``current`` and the pair is not an allowed transition.
        """
        if new is None or new == current:
            return  # unchanged state — not a transition (REQ-EVT-B04-AC5)
        if (current, new) not in _ALLOWED_TRANSITIONS:
            raise ServiceError(
                errors.INVALID_STATUS_TRANSITION,
                f"cannot transition status from {current!r} to {new!r}",
                errors.ERROR_CODES[errors.INVALID_STATUS_TRANSITION],
            )

    def replace_event(self, event_id: str, data: dict) -> dict:
        """Fully replace an existing event and return the stored record (REQ-EVT-F07).

        A PUT is a *full replacement*: field-level validation of the
        ``EventCreate`` body (REQ-EVT-F03) is performed upstream by the routes
        layer. The service fetches the stored record first — a missing id is a
        ``NOT_FOUND`` (404) and no outbound call is made. When ``organizer_id`` is
        present it verifies the organizer (existence B01, role B02) mapping
        transport failures to 503 (REQ-EVT-B05). The status transition is checked
        against the *stored* status (REQ-EVT-B04). ``id`` and ``created_at`` are
        preserved; ``updated_at`` is refreshed (REQ-EVT-F11). Because a PUT is a
        full replacement, optionals omitted from the body take their POST-style
        defaults (``status``->``draft``, ``description``->``None``).

        Args:
            event_id: The id of the event to replace.
            data: Validated ``EventCreate`` body.

        Returns:
            The updated event record serialised to the 13 contract fields.

        Raises:
            ServiceError: ``NOT_FOUND`` (404) when the event is absent;
                ``VALIDATION_ERROR`` (422) when ``end_date`` precedes
                ``start_date`` (REQ-EVT-B03); ``REFERENCE_NOT_FOUND`` /
                ``INVALID_ORGANIZER`` (422) or ``DEPENDENCY_UNAVAILABLE`` (503)
                from organizer verification; ``INVALID_STATUS_TRANSITION`` (422)
                for a disallowed status change (REQ-EVT-B04).
        """
        stored = self._repo.get(event_id)
        if stored is None:
            raise ServiceError(
                errors.NOT_FOUND,
                f"event {event_id!r} not found",
                errors.ERROR_CODES[errors.NOT_FOUND],
            )

        # Cross-field date coherence (B03) re-checked before any outbound call so
        # an incoherent pair never triggers a misleading 503 (REQ-EVT-B01-AC4).
        if not validate_dates_coherent(data.get("start_date"), data.get("end_date")):
            raise ServiceError(
                errors.VALIDATION_ERROR,
                "end_date must be greater than or equal to start_date",
                errors.ERROR_CODES[errors.VALIDATION_ERROR],
            )

        # PUT is a full replacement: omitted optionals take POST-style defaults.
        new_status = data.get("status", "draft")
        # Transition is judged against the stored status (REQ-EVT-B04).
        self.check_transition(stored["status"], new_status)

        if "organizer_id" in data:
            self._verify_organizer(data["organizer_id"])

        now = utcnow_iso()
        changes = {
            "title": data["title"],
            "description": data.get("description"),
            "organizer_id": data["organizer_id"],
            "venue": data["venue"],
            "city": data["city"],
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "capacity": data["capacity"],
            "price": data["price"],
            "status": new_status,
            "updated_at": now,
        }
        updated = self._repo.update(event_id, changes)
        return event_to_dict(updated)

    def update_event(self, event_id: str, data: dict) -> dict:
        """Partially update an existing event and return it (REQ-EVT-F08).

        The record is fetched **first**, so a PATCH against a missing id returns
        ``NOT_FOUND`` (404) even for an empty or unknown-field body
        (REQ-EVT-F04-AC5). Unknown fields are rejected explicitly
        (``additionalProperties: false``, REQ-EVT-F04-AC2). An empty PATCH leaves
        the record unchanged and does **not** bump ``updated_at``
        (REQ-EVT-F04-AC6). For a non-empty PATCH the effective (merged) record is
        computed and ``end_date`` >= ``start_date`` re-validated against it
        (REQ-EVT-B03-AC3); the organizer is re-verified only when
        ``organizer_id`` changes; the status transition is enforced against the
        stored value (REQ-EVT-B04); the present fields are applied and
        ``updated_at`` refreshed (REQ-EVT-F11).

        Args:
            event_id: The id of the event to update.
            data: ``EventUpdate`` body (all fields optional).

        Returns:
            The (possibly unchanged) event record serialised to the 13 contract
            fields.

        Raises:
            ServiceError: ``NOT_FOUND`` (404) when the event is absent;
                ``VALIDATION_ERROR`` (422) for an unknown field or an incoherent
                effective date pair (REQ-EVT-B03); ``REFERENCE_NOT_FOUND`` /
                ``INVALID_ORGANIZER`` (422) or ``DEPENDENCY_UNAVAILABLE`` (503)
                from organizer verification; ``INVALID_STATUS_TRANSITION`` (422)
                for a disallowed status change (REQ-EVT-B04).
        """
        # Fetch FIRST: a missing id is 404 regardless of the body (REQ-EVT-F04-AC5).
        stored = self._repo.get(event_id)
        if stored is None:
            raise ServiceError(
                errors.NOT_FOUND,
                f"event {event_id!r} not found",
                errors.ERROR_CODES[errors.NOT_FOUND],
            )

        # additionalProperties:false is not automatic — reject unknown fields.
        unknown = [key for key in data if key not in _PATCHABLE_FIELDS]
        if unknown:
            raise ServiceError(
                errors.VALIDATION_ERROR,
                f"unknown field(s): {', '.join(sorted(unknown))}",
                errors.ERROR_CODES[errors.VALIDATION_ERROR],
            )

        # Empty PATCH: unchanged record, updated_at NOT bumped (REQ-EVT-F04-AC6).
        if not data:
            return event_to_dict(stored)

        # Effective (merged) record: date coherence (B03) is judged on what the
        # record WILL be, not just the fields in the body (REQ-EVT-B03-AC3).
        effective_start = data.get("start_date", stored["start_date"])
        effective_end = data.get("end_date", stored["end_date"])
        if not validate_dates_coherent(effective_start, effective_end):
            raise ServiceError(
                errors.VALIDATION_ERROR,
                "end_date must be greater than or equal to start_date",
                errors.ERROR_CODES[errors.VALIDATION_ERROR],
            )

        # Status transition against the stored value (absent status => no-op, B04).
        self.check_transition(stored["status"], data.get("status"))

        # Re-verify the organizer only when it actually changes (REQ-EVT-F04-AC7).
        if "organizer_id" in data and data["organizer_id"] != stored["organizer_id"]:
            self._verify_organizer(data["organizer_id"])

        changes = dict(data)
        changes["updated_at"] = utcnow_iso()
        updated = self._repo.update(event_id, changes)
        return event_to_dict(updated)

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
