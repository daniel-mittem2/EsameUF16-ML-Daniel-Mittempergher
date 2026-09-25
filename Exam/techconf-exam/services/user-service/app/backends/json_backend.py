"""JSON-file user repository backend (REQ-USR-F14-AC2).

Persists records as a JSON array in ``users.json`` inside the configured data
directory. The whole file is read on open (an empty list is assumed when the
file does not yet exist) and rewritten on every mutation. Writes are made
durable and crash-safe by writing to a temporary file in the same directory and
then performing an atomic :func:`os.replace` (design §9).

A single :class:`threading.RLock` per instance protects both reads and writes.
The "check email uniqueness + write" sequence runs entirely inside the lock so
that concurrent ``create``/``update`` requests can never both succeed with the
same email (REQ-USR-B01, design §10). ``os.replace`` guarantees the file is
never left half-written, but it is the in-process lock that makes the
check-then-write atomic within a single process.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Optional

from app.repository import AbstractUserRepository, EmailAlreadyExistsError


class JsonUserRepository(AbstractUserRepository):
    """User repository backed by a JSON file on disk.

    Args:
        path: Path to the ``users.json`` file. The parent directory is created
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

    def _find_by_email_unlocked(self, email: str) -> Optional[dict]:
        """Return the record matching ``email`` case-insensitively (no locking)."""
        target = email.lower()
        for record in self._data.values():
            if record["email"].lower() == target:
                return record
        return None

    # ------------------------------------------------------------------ #
    # AbstractUserRepository implementation
    # ------------------------------------------------------------------ #
    def create(self, record: dict) -> dict:
        """Persist ``record``; raise if its email is already taken (REQ-USR-B01)."""
        with self._lock:
            if self._find_by_email_unlocked(record["email"]) is not None:
                raise EmailAlreadyExistsError()
            self._data[record["id"]] = copy.deepcopy(record)
            self._write_file_unlocked()
            return copy.deepcopy(self._data[record["id"]])

    def get(self, user_id: str) -> Optional[dict]:
        with self._lock:
            record = self._data.get(user_id)
            return copy.deepcopy(record) if record is not None else None

    def list_all(self, filters: dict) -> list[dict]:
        role = filters.get("role")
        email = filters.get("email")
        email_lower = email.lower() if isinstance(email, str) else None
        with self._lock:
            results = []
            for record in self._data.values():
                if role is not None and record["role"] != role:
                    continue
                if email_lower is not None and record["email"].lower() != email_lower:
                    continue
                results.append(copy.deepcopy(record))
            return results

    def update(self, user_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` atomically; enforce email uniqueness (REQ-USR-B01)."""
        with self._lock:
            record = self._data.get(user_id)
            if record is None:
                return None
            new_email = changes.get("email")
            if new_email is not None:
                existing = self._find_by_email_unlocked(new_email)
                if existing is not None and existing["id"] != user_id:
                    raise EmailAlreadyExistsError()
            record.update(changes)
            self._write_file_unlocked()
            return copy.deepcopy(record)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._data:
                del self._data[user_id]
                self._write_file_unlocked()
                return True
            return False

    def get_by_email(self, email: str) -> Optional[dict]:
        with self._lock:
            record = self._find_by_email_unlocked(email)
            return copy.deepcopy(record) if record is not None else None
