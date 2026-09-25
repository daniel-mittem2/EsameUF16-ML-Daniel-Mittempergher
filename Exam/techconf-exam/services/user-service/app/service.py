"""Business logic layer for the user-service (REQ-USR-B*).

:class:`UserService` orchestrates the domain rules on top of an injected
:class:`~app.repository.AbstractUserRepository`. It never imports a concrete
backend and never touches Flask, so it can be unit-tested in isolation with a
:class:`~app.backends.memory.MemoryUserRepository` (REQ-USR-F14-AC4).

Responsibilities implemented in this task (T-08):

- ``create_user``: normalise the email to lower case (REQ-USR-B02), enforce
  case-insensitive email uniqueness (REQ-USR-B01), generate the server-side
  timestamps (REQ-USR-F11) and the UUID via :func:`app.models.new_user_record`
  (REQ-USR-F02).

The service-level :class:`EmailConflictError` is raised on a duplicate email so
the routes layer (T-12) can map it to a 409 ``EMAIL_ALREADY_EXISTS`` response
without depending on the repository's own exception type.
"""
from __future__ import annotations

from app.models import new_user_record, utcnow_iso
from app.repository import AbstractUserRepository, EmailAlreadyExistsError


class EmailConflictError(Exception):
    """Raised when an operation would violate case-insensitive email uniqueness.

    This is the service-layer counterpart of
    :class:`app.repository.EmailAlreadyExistsError`. The routes layer (T-12)
    maps it to HTTP 409 ``EMAIL_ALREADY_EXISTS`` (REQ-USR-B01). Keeping a
    dedicated service exception isolates the HTTP layer from the storage layer.
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
