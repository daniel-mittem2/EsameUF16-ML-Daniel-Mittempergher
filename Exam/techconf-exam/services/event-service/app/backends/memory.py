"""In-memory event repository backend (REQ-EVT-F14-AC1).

Stores records in a process-local dictionary keyed by event id. Data is lost on
restart. A single :class:`threading.RLock` per instance protects both reads and
writes; the "lookup + write" sequence of :meth:`update` runs entirely inside the
lock so concurrent updates stay consistent (design §10). The lock is re-entrant
so helpers that re-acquire it do not deadlock.
"""
from __future__ import annotations

import threading
from typing import Optional

from app.repository import AbstractEventRepository


class MemoryEventRepository(AbstractEventRepository):
    """Event repository backed by an in-process dictionary.

    The shared :class:`threading.RLock` is created once per instance and reused
    for every operation.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    def create(self, record: dict) -> dict:
        """Persist ``record`` keyed by its ``id`` and return it."""
        with self._lock:
            self._data[record["id"]] = record
            return record

    def get(self, event_id: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(event_id)

    def list_all(self, filters: dict) -> list[dict]:
        """Return records matching ``status`` and/or ``city`` (AND logic, REQ-EVT-B06)."""
        status = filters.get("status")
        city = filters.get("city")
        with self._lock:
            results = []
            for record in self._data.values():
                if status is not None and record["status"] != status:
                    continue
                if city is not None and record["city"] != city:
                    continue
                results.append(record)
            return results

    def update(self, event_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` to the record atomically (REQ-EVT-F14, design §10)."""
        with self._lock:
            record = self._data.get(event_id)
            if record is None:
                return None
            record.update(changes)
            return record

    def delete(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._data:
                del self._data[event_id]
                return True
            return False
