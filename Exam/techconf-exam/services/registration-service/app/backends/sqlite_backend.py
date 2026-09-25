"""SQLite registration repository backend (REQ-REG-F13-AC3).

Persists records in a SQLite database file (``registrations.db``) inside the
configured data directory. The connection is opened once in ``__init__`` with
``check_same_thread=False`` so it can be shared across the threads Flask uses to
serve concurrent requests (design §5, §6).

A single :class:`threading.RLock` per instance protects both reads and writes.
The critical sequences run entirely inside the lock so concurrent requests never
oversell an event or create a duplicate confirmed registration (design §5):

- :meth:`create_if_allowed` performs the duplicate-confirmed check
  (REQ-REG-B04), the capacity count (REQ-REG-B05), the record creation and the
  commit under the same lock — no window between check and write.
- :meth:`set_status` reads the current record and writes the new status under
  the lock (REQ-REG-B07).
- :meth:`count_confirmed` counts under the lock for a consistent snapshot
  (REQ-REG-B08).

Every write is wrapped in ``with self._conn:`` so the change is committed on
success and rolled back automatically if an exception propagates.

Two indexes support the design (design §6):

- ``idx_reg_event_status`` on ``(event_id, status)`` speeds the confirmed-count
  query used by the capacity check and by ``stats``.
- ``idx_reg_user_event_confirmed``, a **partial unique** index on
  ``(user_id, event_id) WHERE status = 'confirmed'``, is a DB-level safety net
  against a double confirmed registration (REQ-REG-B04): even if the in-process
  lock were bypassed, the ``UNIQUE`` constraint would reject the insert. A
  resulting :class:`sqlite3.IntegrityError` is translated into
  :class:`AlreadyRegisteredError` so the service still maps it to 409
  ``ALREADY_REGISTERED``. Capacity (REQ-REG-B05) is enforced only under the lock,
  since it has no single-row uniqueness expression.

Reopening an existing ``registrations.db`` restores persisted state because the
schema is created with ``IF NOT EXISTS`` (REQ-REG-F13-AC3); ``registrations.db``
lives in ``DATA_DIR`` and is excluded from git via ``data/``.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Callable, Optional

from app.models import CONFIRMED
from app.repository import (
    AbstractRegistrationRepository,
    AlreadyRegisteredError,
    EventFullError,
)

# Columns of the ``registrations`` table, in the internal record order (the seven
# contract fields produced by :func:`app.models.new_registration_record`).
_COLUMNS = (
    "id",
    "user_id",
    "event_id",
    "amount",
    "status",
    "created_at",
    "updated_at",
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS registrations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEX_EVENT_STATUS = """
CREATE INDEX IF NOT EXISTS idx_reg_event_status
    ON registrations (event_id, status)
"""

_CREATE_INDEX_UNIQUE_CONFIRMED = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_user_event_confirmed
    ON registrations (user_id, event_id) WHERE status = 'confirmed'
"""


class SqliteRegistrationRepository(AbstractRegistrationRepository):
    """Registration repository backed by a SQLite database file.

    Args:
        path: Path to the ``registrations.db`` file. The parent directory is
            created if it does not exist. Reopening an existing file restores
            persisted state because the schema is created with ``IF NOT EXISTS``.

    The shared :class:`threading.RLock` is created once per instance and reused
    for every operation. Because it is re-entrant, helper methods that acquire it
    while an outer method already holds it do not deadlock. The single connection
    is shared across threads (``check_same_thread=False``) and closed by
    :meth:`close`.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        # Ensure the containing directory exists so the file can be created.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Shared connection: Flask serves requests across threads (design §5).
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.execute(_CREATE_TABLE)
            self._conn.execute(_CREATE_INDEX_EVENT_STATUS)
            self._conn.execute(_CREATE_INDEX_UNIQUE_CONFIRMED)

    # ------------------------------------------------------------------ #
    # Helpers (call sites already hold the lock)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict:
        """Convert a SQLite row into a plain record dict (7 contract fields)."""
        return {column: row[column] for column in _COLUMNS}

    def _get_unlocked(self, reg_id: str) -> Optional[dict]:
        cursor = self._conn.execute(
            "SELECT * FROM registrations WHERE id = ?", (reg_id,)
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    def _count_confirmed_unlocked(self, event_id: str) -> int:
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM registrations WHERE event_id = ? AND status = ?",
            (event_id, CONFIRMED),
        )
        return int(cursor.fetchone()[0])

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
        """Atomically check duplicate + capacity, then create and persist (design §5).

        The duplicate check (REQ-REG-B04) and the capacity count (REQ-REG-B05)
        run under the instance lock together with the insert, so there is no
        window between check and write. The partial unique index provides a
        DB-level safety net: an :class:`sqlite3.IntegrityError` is translated
        into :class:`AlreadyRegisteredError`.
        """
        with self._lock:
            # REQ-REG-B04: duplicate confirmed registration for the pair.
            cursor = self._conn.execute(
                "SELECT 1 FROM registrations "
                "WHERE user_id = ? AND event_id = ? AND status = ? LIMIT 1",
                (user_id, event_id, CONFIRMED),
            )
            if cursor.fetchone() is not None:
                raise AlreadyRegisteredError(
                    f"user {user_id} already confirmed for event {event_id}"
                )
            # REQ-REG-B05: capacity check (only confirmed rows occupy a seat).
            confirmed = self._count_confirmed_unlocked(event_id)
            if confirmed >= capacity:
                raise EventFullError(
                    f"event {event_id} is full ({confirmed}/{capacity})"
                )
            record = make_record()
            try:
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO registrations "
                        "(id, user_id, event_id, amount, status, "
                        "created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        tuple(record[column] for column in _COLUMNS),
                    )
            except sqlite3.IntegrityError as exc:
                # Safety net: the partial unique index rejected a second
                # confirmed row for the pair (REQ-REG-B04, design §6).
                raise AlreadyRegisteredError(
                    f"user {user_id} already confirmed for event {event_id}"
                ) from exc
            return self._get_unlocked(record["id"])

    def get(self, reg_id: str) -> Optional[dict]:
        with self._lock:
            return self._get_unlocked(reg_id)

    def list_all(self, filters: dict) -> list[dict]:
        """Return records matching ``user_id``/``event_id``/``status`` (AND logic)."""
        user_id = filters.get("user_id")
        event_id = filters.get("event_id")
        status = filters.get("status")
        clauses = []
        params: list = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if event_id is not None:
            clauses.append("event_id = ?")
            params.append(event_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        query = "SELECT * FROM registrations"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            cursor = self._conn.execute(query, tuple(params))
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def set_status(self, reg_id: str, new_status: str, now: str) -> Optional[dict]:
        """Apply ``new_status`` atomically and refresh ``updated_at`` (REQ-REG-B07)."""
        with self._lock:
            record = self._get_unlocked(reg_id)
            if record is None:
                return None
            with self._conn:
                self._conn.execute(
                    "UPDATE registrations SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now, reg_id),
                )
            return self._get_unlocked(reg_id)

    def delete(self, reg_id: str) -> bool:
        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM registrations WHERE id = ?", (reg_id,)
                )
            return cursor.rowcount > 0

    def count_confirmed(self, event_id: str) -> int:
        with self._lock:
            return self._count_confirmed_unlocked(event_id)

    def close(self) -> None:
        """Close the shared connection. Safe to call more than once."""
        with self._lock:
            self._conn.close()
