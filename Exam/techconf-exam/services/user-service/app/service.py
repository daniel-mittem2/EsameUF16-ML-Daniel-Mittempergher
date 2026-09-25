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

from app.models import DEFAULT_ROLE, new_user_record, user_to_dict, utcnow_iso
from app.pagination import paginate
from app.repository import AbstractUserRepository, EmailAlreadyExistsError
from app.validators import VALID_ROLES

# Mutable fields replaced wholesale by a PUT (REQ-USR-F07). ``id``,
# ``created_at`` and ``updated_at`` are server-managed and never taken from the
# client body.
_MUTABLE_FIELDS = ("first_name", "last_name", "email", "company", "role")


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

    def replace_user(self, user_id: str, data: dict) -> dict:
        """Replace every mutable field of an existing user (PUT, REQ-USR-F07).

        PUT uses the ``UserCreate`` schema (already validated by the routes
        layer): ``first_name``, ``last_name`` and ``email`` are required;
        ``company`` and ``role`` are optional with the same defaults as POST
        (``company`` -> ``None``, ``role`` -> ``"attendee"``). All mutable
        fields are overwritten from ``data``; ``id`` and ``created_at`` are kept
        from the stored record (REQ-USR-F07-AC5) and ``updated_at`` is refreshed
        to the current timestamp (REQ-USR-F11-AC2).

        The email is normalised to lower case (REQ-USR-B02) *before* the
        uniqueness check. Updating a user's email to the value it already holds
        does not raise a conflict (REQ-USR-B01-AC3); a value already used by a
        *different* user does (REQ-USR-B01-AC2).

        Args:
            user_id: The UUID of the user to replace.
            data: Validated ``UserCreate`` body (required fields present).

        Returns:
            The updated user record (the eight contract fields).

        Raises:
            UserNotFoundError: If no user with ``user_id`` exists
                (REQ-USR-F07-AC3). The routes layer maps this to 404.
            EmailConflictError: If the new email is already used by a different
                user (REQ-USR-B01-AC2). The routes layer maps this to 409.
        """
        # Resource lookup first: a missing user is a 404 regardless of the body
        # (REQ-USR-F07-AC3).
        if self._repo.get(user_id) is None:
            raise UserNotFoundError(f"No user with id {user_id!r}")

        # Full replacement of every mutable field, applying POST-style defaults
        # for the optional ones (REQ-USR-F07-AC2). Email normalised before the
        # uniqueness comparison (REQ-USR-B02-AC3).
        changes = {
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "email": data["email"].lower(),
            "company": data.get("company"),
            "role": data.get("role", DEFAULT_ROLE),
            "updated_at": utcnow_iso(),
        }

        return self._apply_update(user_id, changes)

    def update_user(self, user_id: str, data: dict) -> dict:
        """Partially update an existing user (PATCH, REQ-USR-F08).

        The stored record is looked up **first**, so a missing user yields a 404
        even when the body is empty (REQ-USR-F08-AC2). Only the fields present in
        ``data`` are applied; absent fields keep their current values
        (REQ-USR-F08-AC3). ``company`` may be patched to ``None`` explicitly to
        clear it (REQ-USR-F08-AC4).

        An empty body (``{}``) is idempotent: the record is returned unchanged
        and ``updated_at`` is **not** refreshed (REQ-USR-F04-AC4,
        REQ-USR-F11-AC2). Any non-empty change refreshes ``updated_at``.

        A supplied ``email`` is normalised to lower case (REQ-USR-B02) before the
        uniqueness check; reusing the user's own email is not a conflict
        (REQ-USR-B01-AC3).

        Args:
            user_id: The UUID of the user to update.
            data: Validated ``UserUpdate`` body (all fields optional).

        Returns:
            The (possibly unchanged) user record (the eight contract fields).

        Raises:
            UserNotFoundError: If no user with ``user_id`` exists
                (REQ-USR-F08-AC2). The routes layer maps this to 404.
            EmailConflictError: If a supplied email is already used by a
                different user (REQ-USR-B01-AC2). The routes layer maps to 409.
        """
        # Resource lookup first: a missing user is a 404 even for an empty body
        # (REQ-USR-F08-AC2).
        record = self._repo.get(user_id)
        if record is None:
            raise UserNotFoundError(f"No user with id {user_id!r}")

        # Apply only the mutable fields actually present in the body. Unknown
        # keys have already been rejected by the routes-layer validator
        # (REQ-USR-F04-AC3); guard here too so the service never persists a key
        # outside the contract shape.
        changes = {
            field: data[field] for field in _MUTABLE_FIELDS if field in data
        }

        # Empty PATCH: nothing to change, updated_at left untouched
        # (REQ-USR-F04-AC4, REQ-USR-F11-AC2).
        if not changes:
            return record

        if "email" in changes:
            changes["email"] = changes["email"].lower()  # REQ-USR-B02-AC2

        changes["updated_at"] = utcnow_iso()  # REQ-USR-F11-AC2

        return self._apply_update(user_id, changes)

    def delete_user(self, user_id: str) -> None:
        """Delete the user with ``user_id`` (REQ-USR-F09).

        The delete is delegated to the repository, which reports whether a
        record was actually removed. A missing user is a 404
        (REQ-USR-F09-AC2). Because the repository returns ``False`` rather than
        removing anything when the id is absent, a second delete of the same id
        also raises :class:`UserNotFoundError` — the operation is not silently
        idempotent at 204 (REQ-USR-F09-AC4). After a successful delete a later
        :meth:`get_user` on the same id likewise raises ``UserNotFoundError``
        (REQ-USR-F09-AC3).

        Args:
            user_id: The UUID of the user to delete. Treated as an opaque key;
                an absent id (including a syntactically invalid one) is a 404.

        Returns:
            ``None``. The routes layer maps a successful delete to HTTP 204 with
            no body (REQ-USR-F09-AC1).

        Raises:
            UserNotFoundError: If no user with ``user_id`` exists
                (REQ-USR-F09-AC2). The routes layer maps this to 404.
        """
        if not self._repo.delete(user_id):
            raise UserNotFoundError(f"No user with id {user_id!r}")

    def _apply_update(self, user_id: str, changes: dict) -> dict:
        """Delegate the atomic write to the repository, mapping its exceptions.

        The repository performs the "check email uniqueness (excluding self) +
        write" sequence atomically under its lock (REQ-USR-B01, design §10) and
        raises :class:`EmailAlreadyExistsError` on a cross-user collision, which
        we translate into the service-level :class:`EmailConflictError`.

        A ``None`` return from the repository means the record vanished between
        our lookup and the write (a concurrent delete); treat it as not-found.
        """
        try:
            updated = self._repo.update(user_id, changes)
        except EmailAlreadyExistsError as exc:
            raise EmailConflictError(
                f"A user with email {changes.get('email')!r} already exists"
            ) from exc

        if updated is None:
            raise UserNotFoundError(f"No user with id {user_id!r}")
        return updated
