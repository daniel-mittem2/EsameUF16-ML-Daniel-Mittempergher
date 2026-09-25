"""Repository abstraction and backend factory for the registration-service.

This module defines the storage-agnostic contract every backend must honour
(:class:`AbstractRegistrationRepository`), the two domain exceptions the
repository raises to signal a conflict during creation
(:class:`AlreadyRegisteredError`, :class:`EventFullError`), and the
:func:`get_repository` factory that selects a concrete backend from
configuration (REQ-REG-F13).

The business logic in ``service.py`` depends only on the abstract interface
defined here; it never imports a concrete backend module directly
(REQ-REG-F13-AC4). Backend classes are imported *locally* inside the factory so
that importing this module does not require every backend's dependencies to be
available.

The heart of the design (requirements §"Atomicità", design §5) is
:meth:`AbstractRegistrationRepository.create_if_allowed`: the duplicate-confirmed
check (REQ-REG-B04), the capacity count (REQ-REG-B05) and the record creation
happen together inside the repository's per-instance lock, so there is no window
between check and write under concurrency. The outbound HTTP calls to the
dependencies are performed by the service *before* this critical section — the
lock is never held during network I/O.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


class AlreadyRegisteredError(Exception):
    """A ``confirmed`` registration already exists for ``(user_id, event_id)``.

    Raised by :meth:`AbstractRegistrationRepository.create_if_allowed`; the
    service maps it to 409 ``ALREADY_REGISTERED`` (REQ-REG-B04-AC1).
    """


class EventFullError(Exception):
    """The event already has ``capacity`` confirmed registrations.

    Raised by :meth:`AbstractRegistrationRepository.create_if_allowed`; the
    service maps it to 409 ``EVENT_FULL`` (REQ-REG-B05-AC2).
    """


class AbstractRegistrationRepository(ABC):
    """Storage-agnostic contract for persisting registration records.

    All record dicts follow the internal shape produced by
    :func:`app.models.new_registration_record` (the seven contract fields).
    Concrete backends guard read-modify-write sequences with a per-instance lock
    so concurrent creations and status changes stay consistent (design §5/§10).
    """

    @abstractmethod
    def create_if_allowed(
        self,
        user_id: str,
        event_id: str,
        capacity: int,
        make_record: Callable[[], dict],
    ) -> dict:
        """Atomically check duplicates + capacity, then create the record.

        Performed entirely under the repository lock (design §5):

        1. If a ``confirmed`` registration already exists for
           ``(user_id, event_id)`` → raise :class:`AlreadyRegisteredError`
           (REQ-REG-B04).
        2. Else, if the number of ``confirmed`` registrations for ``event_id`` is
           greater than or equal to ``capacity`` → raise :class:`EventFullError`
           (REQ-REG-B05).
        3. Else, call ``make_record()`` to build the new record (the service has
           already computed ``amount`` and the timestamps), persist it and return
           it.

        ``make_record`` is a callback so the repository never needs to know the
        domain rules — only the atomicity constraint. No record is created when
        step 1 or step 2 raises.
        """

    @abstractmethod
    def get(self, reg_id: str) -> Optional[dict]:
        """Return the record with ``reg_id`` or ``None`` if it does not exist."""

    @abstractmethod
    def list_all(self, filters: dict) -> list[dict]:
        """Return all records matching ``filters`` (``user_id``/``event_id``/``status``).

        ``filters`` may contain ``user_id``, ``event_id`` and/or ``status``; each
        is matched exactly and combined with AND logic (REQ-REG-F05-AC4). Filter
        values of ``None`` are ignored. An empty ``filters`` dict returns every
        record. Pagination is applied by the caller, not here.
        """

    @abstractmethod
    def set_status(self, reg_id: str, new_status: str, now: str) -> Optional[dict]:
        """Set the status of ``reg_id`` to ``new_status`` and refresh ``updated_at``.

        Returns ``None`` when no record with ``reg_id`` exists. The lookup and the
        write are performed atomically under the repository lock. The transition
        rules (REQ-REG-B07) are validated by the service *before* calling this;
        the repository only performs the write. ``updated_at`` is set to ``now``.
        """

    @abstractmethod
    def delete(self, reg_id: str) -> bool:
        """Delete the record with ``reg_id``.

        Returns ``True`` when a record was removed, ``False`` when no record with
        ``reg_id`` existed.
        """

    @abstractmethod
    def count_confirmed(self, event_id: str) -> int:
        """Return the number of ``confirmed`` registrations for ``event_id`` (REQ-REG-B08)."""


def get_repository(backend: str, data_dir: Path) -> AbstractRegistrationRepository:
    """Return a concrete repository for the requested ``backend`` (REQ-REG-F13).

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
        from app.backends.memory import MemoryRegistrationRepository

        return MemoryRegistrationRepository()

    raise ValueError(f"Unknown STORAGE_BACKEND: {backend!r}")
