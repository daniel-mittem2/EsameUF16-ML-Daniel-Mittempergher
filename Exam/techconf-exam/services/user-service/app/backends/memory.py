"""In-memory user repository backend (REQ-USR-F14-AC1).

Stores records in a process-local dictionary keyed by user id. Data is lost on
restart. A single :class:`threading.RLock` per instance protects both reads and
writes; the "check email uniqueness + write" sequence runs entirely inside the
lock so that concurrent ``create``/``update`` requests can never both succeed
with the same email (REQ-USR-B01, design §10).
"""
from __future__ import annotations

import threading
from typing import Optional

from app.repository import AbstractUserRepository, EmailAlreadyExistsError


class MemoryUserRepository(AbstractUserRepository):
    """User repository backed by an in-process dictionary.

    The shared :class:`threading.RLock` is created once per instance and reused
    for every operation. Because it is re-entrant, helper methods that also
    acquire it (e.g. :meth:`get_by_email` reused inside :meth:`create`) do not
    deadlock when called from an already-locked section.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _find_by_email_unlocked(self, email: str) -> Optional[dict]:
        """Return the record matching ``email`` case-insensitively (no locking)."""
        target = email.lower()
        for record in self._data.values():
            if record["email"].lower() == target:
                return record
        return None

    def create(self, record: dict) -> dict:
        """Persist ``record``; raise if its email is already taken (REQ-USR-B01)."""
        with self._lock:
            if self._find_by_email_unlocked(record["email"]) is not None:
                raise EmailAlreadyExistsError()
            self._data[record["id"]] = record
            return record

    def get(self, user_id: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(user_id)

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
                results.append(record)
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
            return record

    def delete(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._data:
                del self._data[user_id]
                return True
            return False

    def get_by_email(self, email: str) -> Optional[dict]:
        with self._lock:
            return self._find_by_email_unlocked(email)
