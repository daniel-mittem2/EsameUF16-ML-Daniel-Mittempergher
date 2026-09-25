"""Business logic layer for the user-service (REQ-USR-B*).

:class:`UserService` orchestrates the domain rules on top of an injected
:class:`~app.repository.AbstractUserRepository`. It never imports a concrete
backend and never touches Flask, so it can be unit-tested in isolation with a
:class:`~app.backends.memory.MemoryUserRepository` (REQ-USR-F14-AC4).

Responsibilities implemented so far:

- ``create_user`` (T-08): normalise the email to lower case (REQ-USR-B02),
  enforce case-insensitive email uniqueness (REQ-USR-B01), generate the
  server-side timestamps (REQ-USR-F11) and the UUID via
  :func:`app.models.new_user_record` (REQ-USR-F02).
- ``get_user`` (T-09): fetch a single user by id, raising
  :class:`UserNotFoundError` when absent (REQ-USR-F05).
- ``list_users`` (T-09): apply the ``role``/``email`` filters (REQ-USR-B03) and
  paginate the filtered result set (REQ-USR-F06). An invalid ``role`` filter
  raises :class:`InvalidFilterError` for the routes layer to map to 422.

The service-level :class:`EmailConflictError` is raised on a duplicate email so
the routes layer (T-12) can map it to a 409 ``EMAIL_ALREADY_EXISTS`` response
without depending on the repository's own exception type.
"""
from __future__ import annotations

from app.models import new_user_record, user_to_dict, utcnow_iso
from app.pagination import paginate
from app.repository import AbstractUserRepository, EmailAlreadyExistsError
from app.validators import VALID_ROLES


class EmailConflictError(Exception):
    """Raised when an operation would violate case-insensitive email uniqueness.

    This is the service-layer counterpart of
    :class:`app.repository.EmailAlreadyExistsError`. The routes layer (T-12)
    maps it to HTTP 409 ``EMAIL_ALREADY_EXISTS`` (REQ-USR-B01). Keeping a
    dedicated service exception isolates the HTTP layer from the storage layer.
    """


class UserNotFoundError(Exception):
    """Raised when an operation targets a user id that does not exist.

    The routes layer (T-12) maps it to HTTP 404 ``NOT_FOUND`` (REQ-USR-F05-AC2).
    Keeping a dedicated service exception isolates the HTTP layer from the
    storage layer, which merely returns ``None`` for a missing record.
    """


class InvalidFilterError(ValueError):
    """Raised when a list filter carries an invalid value (maps to 422).

    Currently raised only for a ``role`` filter whose value is not one of
    ``attendee``, ``speaker`` or ``organizer`` (REQ-USR-B03-AC5). The routes
    layer maps it to HTTP 422 ``VALIDATION_ERROR``.
    """


class UserService:
    """Coordinates user operations and business rules over a repository.

    The repository is injected via the constructor (dependency injection,
    REQ-USR-F14-AC4); the service holds no storage details of its own.
    """

    def __init__(self, repo: AbstractUserRepository) -> None:
        self._repo = repo

    def create_user(self, data: dict) -> dict:
        """Create a new user and return the stored record.

        The email is normalised to lower case (REQ-USR-B02) *before* the
        uniqueness check, so ``Alice@Example.com`` and ``alice@example.com`` are
        detected as duplicates (REQ-USR-B01, REQ-USR-B02-AC3). ``created_at`` and
        ``updated_at`` are set to the same server-generated timestamp
        (REQ-USR-F11-AC1). The record's ``id`` and defaults come from
        :func:`app.models.new_user_record` (REQ-USR-F02).

        Args:
            data: Validated request body containing at least ``first_name``,
                ``last_name`` and ``email``; ``company`` and ``role`` optional.

        Returns:
            The persisted user record (the eight contract fields).

        Raises:
            EmailConflictError: If a user with the same email (compared
                case-insensitively) already exists (REQ-USR-B01).
        """
        normalised_email = data["email"].lower()

        # Pre-check for a friendly, deterministic conflict (REQ-USR-B01). The
        # repository re-checks and writes atomically under its own lock, so the
        # authoritative guard against a concurrent duplicate remains there.
        if self._repo.get_by_email(normalised_email) is not None:
            raise EmailConflictError(
                f"A user with email {normalised_email!r} already exists"
            )

        now = utcnow_iso()
        record = new_user_record(data, now)

        try:
            return self._repo.create(record)
        except EmailAlreadyExistsError as exc:
            # A concurrent create won the race after our pre-check succeeded.
            raise EmailConflictError(
                f"A user with email {normalised_email!r} already exists"
            ) from exc

    def get_user(self, user_id: str) -> dict:
        """Return the user record with ``user_id`` (REQ-USR-F05).

        Args:
            user_id: The user's UUID string. Treated as an opaque key; a
                syntactically invalid UUID that is simply absent yields the same
                not-found result (REQ-USR-F05-AC3).

        Returns:
            The stored user record (the eight contract fields).

        Raises:
            UserNotFoundError: If no user with ``user_id`` exists
                (REQ-USR-F05-AC2). The routes layer maps this to 404.
        """
        record = self._repo.get(user_id)
        if record is None:
            raise UserNotFoundError(f"No user with id {user_id!r}")
        return record

    def list_users(self, filters: dict, page: int, page_size: int) -> dict:
        """Return a paginated, filtered page of users (REQ-USR-F06, REQ-USR-B03).

        Filters are applied before pagination so that ``total`` reflects the
        count of matching records, not the size of the current page
        (REQ-USR-B03-AC4, REQ-USR-F06-AC7). Supported filters:

        - ``role``: exact match against the user's role (REQ-USR-B03-AC1). Must
          be one of the contract roles; any other value raises
          :class:`InvalidFilterError` (REQ-USR-B03-AC5).
        - ``email``: case-insensitive match against the stored (lower-case)
          email (REQ-USR-B03-AC2).

        When both are supplied they combine with AND logic (REQ-USR-B03-AC3).

        Args:
            filters: A mapping that may contain ``role`` and/or ``email``. Keys
                mapping to ``None`` are ignored (no filter applied).
            page: 1-based page number (already validated by the caller).
            page_size: Page size (already validated by the caller).

        Returns:
            A ``UserPage`` dict: ``{"items": [...], "page": int,
            "page_size": int, "total": int}`` where each item is serialised via
            :func:`app.models.user_to_dict`.

        Raises:
            InvalidFilterError: If a ``role`` filter value is not a valid role
                (REQ-USR-B03-AC5). The routes layer maps this to 422.
        """
        active_filters: dict = {}

        role = filters.get("role")
        if role is not None:
            if role not in VALID_ROLES:
                raise InvalidFilterError(
                    "role must be one of attendee, speaker, organizer"
                )
            active_filters["role"] = role

        email = filters.get("email")
        if email is not None:
            # Email is matched case-insensitively against the stored (already
            # normalised) email; lower-case it here so the backend comparison is
            # consistent with the normalised persisted value (REQ-USR-B03-AC2).
            active_filters["email"] = email.lower()

        records = self._repo.list_all(active_filters)
        items = [user_to_dict(record) for record in records]
        return paginate(items, page, page_size)
