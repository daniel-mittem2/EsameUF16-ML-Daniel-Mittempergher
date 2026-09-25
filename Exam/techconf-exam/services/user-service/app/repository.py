"""Repository abstraction and backend factory for the user-service.

This module defines the storage-agnostic contract every backend must honour
(:class:`AbstractUserRepository`), the domain exception raised on a duplicate
email (:class:`EmailAlreadyExistsError`), and the :func:`get_repository`
factory that selects a concrete backend from configuration (REQ-USR-F14).

The business logic in ``service.py`` depends only on the abstract interface
defined here; it never imports a concrete backend module directly
(REQ-USR-F14-AC4). Backend classes are imported *locally* inside the factory so
that importing this module does not require every backend's dependencies to be
available.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class EmailAlreadyExistsError(Exception):
    """Raised by a repository when a create/update would violate email uniqueness.

    Email comparison is case-insensitive (REQ-USR-B01). The service layer
    catches this exception and converts it into a 409 ``EMAIL_ALREADY_EXISTS``
    response. The uniqueness check and the write happen atomically inside the
    repository lock (see the backend implementations and design §10).
    """


class AbstractUserRepository(ABC):
    """Storage-agnostic contract for persisting user records.

    All record dicts follow the internal shape produced by
    :func:`app.models.new_user_record` (the eight contract fields). Email values
    stored in records are already normalised to lower case by the service layer
    (REQ-USR-B02); backends compare emails case-insensitively for uniqueness and
    for :meth:`get_by_email`.
    """

    @abstractmethod
    def create(self, record: dict) -> dict:
        """Persist a new user record and return it.

        Raises:
            EmailAlreadyExistsError: If another record already uses the same
                email (compared case-insensitively). The check and the write
                are performed atomically under the repository lock.
        """

    @abstractmethod
    def get(self, user_id: str) -> Optional[dict]:
        """Return the record with ``user_id`` or ``None`` if it does not exist."""

    @abstractmethod
    def list_all(self, filters: dict) -> list[dict]:
        """Return all records matching ``filters`` (``role`` and/or ``email``).

        ``filters`` may contain ``role`` (exact match) and ``email`` (matched
        case-insensitively). An empty ``filters`` dict returns every record.
        Pagination is applied by the caller, not here.
        """

    @abstractmethod
    def update(self, user_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` to the record with ``user_id`` and return it.

        Returns ``None`` when no record with ``user_id`` exists. When
        ``changes`` contains an ``email`` that collides with a *different*
        record, raises :class:`EmailAlreadyExistsError` (REQ-USR-B01). The
        uniqueness check and the write are atomic under the repository lock.
        """

    @abstractmethod
    def delete(self, user_id: str) -> bool:
        """Delete the record with ``user_id``.

        Returns ``True`` when a record was removed, ``False`` when no record
        with ``user_id`` existed.
        """

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[dict]:
        """Return the record whose email matches ``email`` case-insensitively.

        Returns ``None`` when no record matches.
        """


def get_repository(backend: str, data_dir: Path) -> AbstractUserRepository:
    """Return a concrete repository for the requested ``backend`` (REQ-USR-F14).

    Backend classes are imported locally so importing this module never pulls in
    a backend that is not needed. All three branches (``memory``, ``json``,
    ``sqlite``) are implemented.

    Args:
        backend: One of ``"memory"``, ``"json"`` or ``"sqlite"``.
        data_dir: Directory used by file-based backends for persistence files.

    Raises:
        ValueError: If ``backend`` is not a recognised value.
    """
    if backend == "memory":
        from app.backends.memory import MemoryUserRepository

        return MemoryUserRepository()

    if backend == "json":
        from app.backends.json_backend import JsonUserRepository

        data_dir.mkdir(parents=True, exist_ok=True)
        return JsonUserRepository(data_dir / "users.json")

    if backend == "sqlite":
        from app.backends.sqlite_backend import SqliteUserRepository

        data_dir.mkdir(parents=True, exist_ok=True)
        return SqliteUserRepository(data_dir / "users.db")

    raise ValueError(f"Unknown STORAGE_BACKEND: {backend!r}")
