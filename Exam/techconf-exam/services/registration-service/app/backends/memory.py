"""In-memory registration repository backend (REQ-REG-F13-AC1).

Stores records in a process-local dictionary keyed by registration id. Data is
lost on restart. A single :class:`threading.RLock` per instance protects both
reads and writes.

The critical sequences run entirely inside the lock so concurrent requests never
oversell an event or create a duplicate confirmed registration (design §5):

- :meth:`create_if_allowed` performs the duplicate-confirmed check
  (REQ-REG-B04), the capacity count (REQ-REG-B05) and the record creation under
  the same lock — no window between check and write.
- :meth:`set_status` reads the current record and writes the new status under the
  lock (REQ-REG-B07).
- :meth:`count_confirmed` counts under the lock for a consistent snapshot
  (REQ-REG-B08).

The lock is re-entrant so helpers that re-acquire it do not deadlock.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from app.models import CONFIRMED
from app.repository import (
    AbstractRegistrationRepository,
    AlreadyRegisteredError,
    EventFullError,
)


class MemoryRegistrationRepository(AbstractRegistrationRepository):
    """Registration repository backed by an in-process dictionary.

    The shared :class:`threading.RLock` is created once per instance and reused
    for every operation.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    def create_if_allowed(
        self,
        user_id: str,
        event_id: str,
        capacity: int,
        make_record: Callable[[], dict],
    ) -> dict:
        """Atomically check duplicate + capacity, then create (design §5)."""
        with self._lock:
            for record in self._data.values():
                if (
                    record["user_id"] == user_id
                    and record["event_id"] == event_id
                    and record["status"] == CONFIRMED
                ):
                    raise AlreadyRegisteredError(
                        f"user {user_id} already confirmed for event {event_id}"
                    )
            confirmed = self._count_confirmed_locked(event_id)
            if confirmed >= capacity:
                raise EventFullError(
                    f"event {event_id} is full ({confirmed}/{capacity})"
                )
            record = make_record()
            self._data[record["id"]] = record
            return record

    def get(self, reg_id: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(reg_id)

    def list_all(self, filters: dict) -> list[dict]:
        """Return records matching ``user_id``/``event_id``/``status`` (AND logic)."""
        user_id = filters.get("user_id")
        event_id = filters.get("event_id")
        status = filters.get("status")
        with self._lock:
            results = []
            for record in self._data.values():
                if user_id is not None and record["user_id"] != user_id:
                    continue
                if event_id is not None and record["event_id"] != event_id:
                    continue
                if status is not None and record["status"] != status:
                    continue
                results.append(record)
            return results

    def set_status(self, reg_id: str, new_status: str, now: str) -> Optional[dict]:
        """Apply ``new_status`` atomically and refresh ``updated_at`` (REQ-REG-B07)."""
        with self._lock:
            record = self._data.get(reg_id)
            if record is None:
                return None
            record["status"] = new_status
            record["updated_at"] = now
            return record

    def delete(self, reg_id: str) -> bool:
        with self._lock:
            if reg_id in self._data:
                del self._data[reg_id]
                return True
            return False

    def count_confirmed(self, event_id: str) -> int:
        with self._lock:
            return self._count_confirmed_locked(event_id)

    def _count_confirmed_locked(self, event_id: str) -> int:
        """Count confirmed registrations for ``event_id``; caller holds the lock."""
        return sum(
            1
            for record in self._data.values()
            if record["event_id"] == event_id and record["status"] == CONFIRMED
        )
