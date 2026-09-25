"""Repository abstraction and backend factory for the event-service.

This module defines the storage-agnostic contract every backend must honour
(:class:`AbstractEventRepository`) and the :func:`get_repository` factory that
selects a concrete backend from configuration (REQ-EVT-F14).

The business logic in ``service.py`` depends only on the abstract interface
defined here; it never imports a concrete backend module directly
(REQ-EVT-F14-AC4). Backend classes are imported *locally* inside the factory so
that importing this module does not require every backend's dependencies to be
available.

Unlike the user-service, an event has no uniqueness constraint (no email
equivalent), so there is no ``get_by_email`` counterpart. Filtering by
``status`` and ``city`` is performed inside :meth:`AbstractEventRepository.list_all`
(REQ-EVT-B06); pagination is applied by the caller.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class AbstractEventRepository(ABC):
    """Storage-agnostic contract for persisting event records.

    All record dicts follow the internal shape produced by
    :func:`app.models.new_event_record` (the thirteen contract fields).
    Concrete backends guard read-modify-write sequences with a per-instance
    lock so concurrent updates stay consistent (design §10).
    """

    @abstractmethod
    def create(self, record: dict) -> dict:
        """Persist a new event ``record`` and return it."""

    @abstractmethod
    def get(self, event_id: str) -> Optional[dict]:
        """Return the record with ``event_id`` or ``None`` if it does not exist."""

    @abstractmethod
    def list_all(self, filters: dict) -> list[dict]:
        """Return all records matching ``filters`` (``status`` and/or ``city``).

        ``filters`` may contain ``status`` and/or ``city``; both are matched
        exactly and combined with AND logic (REQ-EVT-B06). An empty ``filters``
        dict (or filter values of ``None``) returns every record. Pagination is
        applied by the caller, not here.
        """

    @abstractmethod
    def update(self, event_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` to the record with ``event_id`` and return it.

        Returns ``None`` when no record with ``event_id`` exists. The lookup and
        the write are performed atomically under the repository lock.
        """

    @abstractmethod
    def delete(self, event_id: str) -> bool:
        """Delete the record with ``event_id``.

        Returns ``True`` when a record was removed, ``False`` when no record with
        ``event_id`` existed.
        """


def get_repository(backend: str, data_dir: Path) -> AbstractEventRepository:
    """Return a concrete repository for the requested ``backend`` (REQ-EVT-F14).

    Backend classes are imported locally so importing this module never pulls in
    a backend that is not needed. In T-05 only the ``memory`` branch is
    implemented; the ``json`` and ``sqlite`` branches are added in T-06/T-07.

    Args:
        backend: One of ``"memory"``, ``"json"`` or ``"sqlite"``.
        data_dir: Directory used by file-based backends for persistence files.

    Raises:
        ValueError: If ``backend`` is not a recognised value.
    """
    if backend == "memory":
        from app.backends.memory import MemoryEventRepository

        return MemoryEventRepository()

    if backend == "json":
        from app.backends.json_backend import JsonEventRepository

        data_dir.mkdir(parents=True, exist_ok=True)
        return JsonEventRepository(data_dir / "events.json")

    if backend == "sqlite":
        from app.backends.sqlite_backend import SqliteEventRepository

        data_dir.mkdir(parents=True, exist_ok=True)
        return SqliteEventRepository(data_dir / "events.db")

    raise ValueError(f"Unknown STORAGE_BACKEND: {backend!r}")
