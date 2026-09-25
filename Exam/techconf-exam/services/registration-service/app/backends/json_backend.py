"""JSON-file registration repository backend (REQ-REG-F13-AC2).

Persists records as a JSON array in ``registrations.json`` inside the configured
data directory. The whole file is read on open (an empty list is assumed when the
file does not yet exist) and rewritten on every mutation. Writes are made durable
and crash-safe by writing to a temporary file in the same directory and then
performing an atomic :func:`os.replace` (design §6); no ``.tmp`` file is ever left
behind on a successful write.

A single :class:`threading.RLock` per instance protects both reads and writes. The
critical sequences run entirely inside the lock so concurrent requests never
oversell an event or create a duplicate confirmed registration (design §5):

- :meth:`create_if_allowed` performs the duplicate-confirmed check (REQ-REG-B04),
  the capacity count (REQ-REG-B05), the record creation and the persistence under
  the same lock — no window between check and write.
- :meth:`set_status` reads the current record and writes the new status under the
  lock (REQ-REG-B07).
- :meth:`count_confirmed` counts under the lock for a consistent snapshot
  (REQ-REG-B08).

``os.replace`` guarantees the file is never left half-written, but it is the
in-process lock that makes each read-modify-write atomic within a single process.
The lock is re-entrant so helpers that re-acquire it do not deadlock.

The business rules (transition validation, dependency checks) live in the service;
this backend mirrors :class:`app.backends.memory.MemoryRegistrationRepository`
semantics with disk persistence added.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from app.models import CONFIRMED
from app.repository import (
    AbstractRegistrationRepository,
    AlreadyRegisteredError,
    EventFullError,
)


class JsonRegistrationRepository(AbstractRegistrationRepository):
    """Registration repository backed by a JSON file on disk.

    Args:
        path: Path to the ``registrations.json`` file. The parent directory is
            created if it does not exist. When the file is absent it is treated as
            an empty collection; it is created lazily on the first write.

    The shared :class:`threading.RLock` is created once per instance and reused for
    every operation. Because it is re-entrant, helper methods that acquire it while
    an outer method already holds it do not deadlock.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._tmp_path = self._path.with_name(self._path.name + ".tmp")
        self._lock = threading.RLock()
        # Ensure the containing directory exists so the first write succeeds.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Load existing data on open (reopening an existing file restores state).
        self._data: dict[str, dict] = {}
        with self._lock:
            for record in self._read_file():
                self._data[record["id"]] = record

    # ------------------------------------------------------------------ #
    # File I/O helpers (call sites already hold the lock)
    # ------------------------------------------------------------------ #
    def _read_file(self) -> list[dict]:
        """Return the list of records stored in the file, or ``[]`` if absent."""
        if not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as fh:
            content = fh.read()
        if not content.strip():
            return []
        data = json.loads(content)
        if not isinstance(data, list):
            raise ValueError(f"{self._path} does not contain a JSON array")
        return data

    def _write_file_unlocked(self) -> None:
        """Persist the current records atomically via a temp file + os.replace."""
        records = list(self._data.values())
        with self._tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(self._tmp_path, self._path)

    def _count_confirmed_locked(self, event_id: str) -> int:
        """Count confirmed registrations for ``event_id``; caller holds the lock."""
        return sum(
            1
            for record in self._data.values()
            if record["event_id"] == event_id and record["status"] == CONFIRMED
        )

    # ------------------------------------------------------------------ #
    # AbstractRegistrationRepository implementation
    # ------------------------------------------------------------------ #
    def create_if_allowed(
        self,
        user_id: str,
        event_id: str,
        capacity: int,
        make_record: Callable[[], dict],
    ) -> dict:
        """Atomically check duplicate + capacity, then create and persist (design §5)."""
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
            self._write_file_unlocked()
            return copy.deepcopy(record)

    def get(self, reg_id: str) -> Optional[dict]:
        with self._lock:
            record = self._data.get(reg_id)
            return copy.deepcopy(record) if record is not None else None

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
                results.append(copy.deepcopy(record))
            return results

    def set_status(self, reg_id: str, new_status: str, now: str) -> Optional[dict]:
        """Apply ``new_status`` atomically and refresh ``updated_at`` (REQ-REG-B07)."""
        with self._lock:
            record = self._data.get(reg_id)
            if record is None:
                return None
            record["status"] = new_status
            record["updated_at"] = now
            self._write_file_unlocked()
            return copy.deepcopy(record)

    def delete(self, reg_id: str) -> bool:
        with self._lock:
            if reg_id in self._data:
                del self._data[reg_id]
                self._write_file_unlocked()
                return True
            return False

    def count_confirmed(self, event_id: str) -> int:
        with self._lock:
            return self._count_confirmed_locked(event_id)
