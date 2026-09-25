"""Business logic layer for the registration-service (REQ-REG-B01..B09).

:class:`RegistrationService` orchestrates the two dependencies (user-service and
event-service) and the repository, enforcing the domain rules of §5.3 of the
track. The HTTP layer (``routes.py``) is a thin adapter: it validates input,
calls a service method and maps the raised :class:`ServiceError` to an HTTP
status via ``errors.py`` (mapping consumed in T-12).

The service never imports Flask, ``requests`` or a concrete repository backend:
it depends only on the injected ``repo`` (an
:class:`app.repository.AbstractRegistrationRepository`), ``user_client`` and
``event_client`` (the dependency clients from ``app.http_client``). This keeps
the rules unit-testable with a memory repository and ``responses``-mocked
clients (design §3, REQ-REG-T01).

**Service-level exception scheme.** Every rule violation is raised as a
:class:`ServiceError` carrying the ``errors.py`` error ``code`` (and an optional
``message``/``details``). The routes layer maps the code to the HTTP status via
``errors.ERROR_CODES``, so the service stays free of HTTP concerns while still
driving a contract-conformant response.

**Creation flow (this task, T-09, design §4).** ``create_registration``:

1. field validation has already run in the routes layer *before* any dependency
   call (REQ-REG-F03-AC5); the service re-reads the validated ids;
2. ``user_client.get_user`` — 404 → 422 ``REFERENCE_NOT_FOUND`` (B01),
   unavailable → 503 ``DEPENDENCY_UNAVAILABLE`` (B09);
3. ``event_client.get_event`` — 404 → 422 ``REFERENCE_NOT_FOUND`` (B02),
   unavailable → 503 (B09);
4. ``event.status == "published"`` else 422 ``EVENT_NOT_OPEN`` (B03);
5. ``amount = event.price`` (B06), ``capacity = event.capacity`` (for B05);
6. ``repo.create_if_allowed(...)`` runs the duplicate + capacity + create
   atomically under the repository lock — ``AlreadyRegisteredError`` → 409
   ``ALREADY_REGISTERED`` (B04), ``EventFullError`` → 409 ``EVENT_FULL`` (B05).

The outbound HTTP calls (steps 2-3) happen **outside** the repository lock: the
lock is never held during network I/O (design §4/§5). No record is created when
any check fails (no mutation on error).
"""
from __future__ import annotations

from typing import Optional

from app import errors
from app.http_client import DependencyUnavailableError, ReferenceNotFoundError
from app.models import new_registration_record, utcnow_iso
from app.repository import AlreadyRegisteredError, EventFullError

# The only event status that accepts registrations (REQ-REG-B03).
PUBLISHED = "published"


class ServiceError(Exception):
    """A domain-rule violation carrying an ``errors.py`` error code.

    The routes layer maps :attr:`code` to an HTTP status via
    ``errors.ERROR_CODES`` and builds the ``Error`` body with
    ``errors.make_error_response`` (REQ-REG-F11). ``details`` is always a dict so
    the response body never carries ``null`` details (REQ-REG-F11-AC4).
    """

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details if details is not None else {}


class RegistrationService:
    """Orchestrates dependencies and repository to enforce REQ-REG-B01..B09.

    Injecting ``repo``, ``user_client`` and ``event_client`` lets tests supply a
    :class:`app.backends.memory.MemoryRegistrationRepository` and
    ``responses``-mocked clients without touching the network (design §3).
    """

    def __init__(self, repo, user_client, event_client) -> None:
        self._repo = repo
        self._user_client = user_client
        self._event_client = event_client

    def create_registration(self, data: dict) -> dict:
        """Create a confirmed registration for ``data`` (REQ-REG-F02, design §4).

        ``data`` is a body already validated by the routes layer
        (``user_id``/``event_id`` present and syntactically valid UUIDs, no other
        field — REQ-REG-F03/REQ-REG-F02-AC6). Returns the created record dict (the
        seven contract fields). Raises :class:`ServiceError` for every rule
        violation; no record is created when a check fails (no mutation on error).
        """
        user_id = data["user_id"]
        event_id = data["event_id"]

        # Step 2 — user existence (B01) / dependency availability (B09).
        self._verify_user(user_id)

        # Step 3 — event existence (B02) / dependency availability (B09).
        event = self._fetch_event(event_id)

        # Step 4 — event must be published (B03).
        if event.get("status") != PUBLISHED:
            raise ServiceError(
                errors.EVENT_NOT_OPEN,
                "event is not open for registration",
                {"event_id": event_id, "status": event.get("status")},
            )

        # Step 5 — amount copied from the event price (B06); capacity for B05.
        amount = event.get("price")
        capacity = event.get("capacity")

        # Step 6 — duplicate + capacity + create, atomic under the repo lock.
        # The HTTP calls above happened outside the lock (design §4/§5).
        now = utcnow_iso()
        try:
            record = self._repo.create_if_allowed(
                user_id,
                event_id,
                capacity,
                lambda: new_registration_record(user_id, event_id, amount, now),
            )
        except AlreadyRegisteredError as exc:
            raise ServiceError(
                errors.ALREADY_REGISTERED,
                "a confirmed registration already exists for this user and event",
                {"user_id": user_id, "event_id": event_id},
            ) from exc
        except EventFullError as exc:
            raise ServiceError(
                errors.EVENT_FULL,
                "the event has reached its capacity",
                {"event_id": event_id, "capacity": capacity},
            ) from exc

        return record

    def _verify_user(self, user_id: str) -> None:
        """Verify the user exists via user-service (B01); map failures (B09)."""
        try:
            self._user_client.get_user(user_id)
        except ReferenceNotFoundError as exc:
            raise ServiceError(
                errors.REFERENCE_NOT_FOUND,
                "user_id does not reference an existing user",
                {"user_id": user_id},
            ) from exc
        except DependencyUnavailableError as exc:
            raise ServiceError(
                errors.DEPENDENCY_UNAVAILABLE,
                "user-service is unavailable",
                {"dependency": "user-service"},
            ) from exc

    def _fetch_event(self, event_id: str) -> dict:
        """Fetch the event via event-service (B02); map failures (B09)."""
        try:
            return self._event_client.get_event(event_id)
        except ReferenceNotFoundError as exc:
            raise ServiceError(
                errors.REFERENCE_NOT_FOUND,
                "event_id does not reference an existing event",
                {"event_id": event_id},
            ) from exc
        except DependencyUnavailableError as exc:
            raise ServiceError(
                errors.DEPENDENCY_UNAVAILABLE,
                "event-service is unavailable",
                {"dependency": "event-service"},
            ) from exc
