"""JSON-file event repository backend (REQ-EVT-F14-AC2).

Persists records as a JSON array in ``events.json`` inside the configured data
directory. The whole file is read on open (an empty list is assumed when the
file does not yet exist) and rewritten on every mutation. Writes are made
durable and crash-safe by writing to a temporary file in the same directory and
then performing an atomic :func:`os.replace` (design §9); no ``.tmp`` file is
ever left behind on a successful write.

A single :class:`threading.RLock` per instance protects both reads and writes.
The "lookup + write" sequence of :meth:`update` runs entirely inside the lock so
concurrent updates stay consistent (design §10). ``os.replace`` guarantees the
file is never left half-written, but it is the in-process lock that makes the
read-modify-write atomic within a single process. The lock is re-entrant so
helpers that re-acquire it do not deadlock.

Unlike the user-service backend there is no uniqueness constraint; filtering by
``status`` and ``city`` (AND logic) is applied in :meth:`list_all`
(REQ-EVT-B06), mirroring :class:`app.backends.memory.MemoryEventRepository`.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Optional

from app.repository import AbstractEventRepository


class JsonEventRepository(AbstractEventRepository):
    """Event repository backed by a JSON file on disk.

    Args:
        path: Path to the ``events.json`` file. The parent directory is created
            if it does not exist. When the file is absent it is treated as an
            empty collection; it is created lazily on the first write.

    The shared :class:`threading.RLock` is created once per instance and reused
    for every operation. Because it is re-entrant, helper methods that acquire
    it while an outer method already holds it do not deadlock.
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

    # ------------------------------------------------------------------ #
    # AbstractEventRepository implementation
    # ------------------------------------------------------------------ #
    def create(self, record: dict) -> dict:
        """Persist ``record`` keyed by its ``id`` and return it (REQ-EVT-F14)."""
        with self._lock:
            self._data[record["id"]] = copy.deepcopy(record)
            self._write_file_unlocked()
            return copy.deepcopy(self._data[record["id"]])

    def get(self, event_id: str) -> Optional[dict]:
        with self._lock:
            record = self._data.get(event_id)
            return copy.deepcopy(record) if record is not None else None

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
                results.append(copy.deepcopy(record))
            return results

    def update(self, event_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` to the record atomically (REQ-EVT-F14, design §10)."""
        with self._lock:
            record = self._data.get(event_id)
            if record is None:
                return None
            record.update(changes)
            self._write_file_unlocked()
            return copy.deepcopy(record)

    def delete(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._data:
                del self._data[event_id]
                self._write_file_unlocked()
                return True
            return False
