"""SQLite event repository backend (REQ-EVT-F14-AC3).

Persists records in a SQLite database file (``events.db``) inside the configured
data directory. The connection is opened once in ``__init__`` with
``check_same_thread=False`` so it can be shared across the threads Flask uses to
serve concurrent requests (design §9, §10).

A single :class:`threading.RLock` per instance protects both reads and writes.
The "lookup + write" sequence of :meth:`update` runs entirely inside the lock so
concurrent updates stay consistent (design §10). The lock is re-entrant so
helpers that re-acquire it while an outer method already holds it do not
deadlock.

Every write is wrapped in ``with self._conn:`` so the change is committed on
success and rolled back automatically if an exception propagates.

Unlike the user-service backend there is no uniqueness constraint; filtering by
``status`` and ``city`` (AND logic) is applied in :meth:`list_all`
(REQ-EVT-B06), mirroring :class:`app.backends.memory.MemoryEventRepository` and
:class:`app.backends.json_backend.JsonEventRepository`. Reopening an existing
``events.db`` restores persisted state because the schema is created with
``IF NOT EXISTS`` (REQ-EVT-F14-AC3); ``events.db`` lives in ``DATA_DIR`` and is
excluded from git via ``data/``.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.repository import AbstractEventRepository

# Columns of the ``events`` table, in the internal record order (the thirteen
# contract fields produced by :func:`app.models.new_event_record`).
_COLUMNS = (
    "id",
    "title",
    "description",
    "organizer_id",
    "venue",
    "city",
    "start_date",
    "end_date",
    "capacity",
    "price",
    "status",
    "created_at",
    "updated_at",
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    organizer_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    city TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class SqliteEventRepository(AbstractEventRepository):
    """Event repository backed by a SQLite database file.

    Args:
        path: Path to the ``events.db`` file. The parent directory is created if
            it does not exist. Reopening an existing file restores persisted
            state because the schema is created with ``IF NOT EXISTS``.

    The shared :class:`threading.RLock` is created once per instance and reused
    for every operation. Because it is re-entrant, helper methods that acquire
    it while an outer method already holds it do not deadlock. The single
    connection is shared across threads (``check_same_thread=False``) and closed
    by :meth:`close`.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        # Ensure the containing directory exists so the file can be created.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Shared connection: Flask serves requests across threads (design §10).
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.execute(_CREATE_TABLE)

    # ------------------------------------------------------------------ #
    # Helpers (call sites already hold the lock)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict:
        """Convert a SQLite row into a plain record dict (13 contract fields)."""
        return {column: row[column] for column in _COLUMNS}

    def _get_unlocked(self, event_id: str) -> Optional[dict]:
        cursor = self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    # ------------------------------------------------------------------ #
    # AbstractEventRepository implementation
    # ------------------------------------------------------------------ #
    def create(self, record: dict) -> dict:
        """Persist ``record`` keyed by its ``id`` and return it (REQ-EVT-F14)."""
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO events "
                    "(id, title, description, organizer_id, venue, city, "
                    "start_date, end_date, capacity, price, status, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    tuple(record[column] for column in _COLUMNS),
                )
            return self._get_unlocked(record["id"])

    def get(self, event_id: str) -> Optional[dict]:
        with self._lock:
            return self._get_unlocked(event_id)

    def list_all(self, filters: dict) -> list[dict]:
        """Return records matching ``status`` and/or ``city`` (AND logic, REQ-EVT-B06)."""
        status = filters.get("status")
        city = filters.get("city")
        clauses = []
        params: list = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if city is not None:
            clauses.append("city = ?")
            params.append(city)
        query = "SELECT * FROM events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            cursor = self._conn.execute(query, tuple(params))
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def update(self, event_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` to the record atomically (REQ-EVT-F14, design §10)."""
        with self._lock:
            record = self._get_unlocked(event_id)
            if record is None:
                return None
            # Only update columns that are known and actually provided.
            updatable = [c for c in _COLUMNS if c != "id" and c in changes]
            if not updatable:
                return record
            assignments = ", ".join(f"{column} = ?" for column in updatable)
            params = [changes[column] for column in updatable]
            params.append(event_id)
            with self._conn:
                self._conn.execute(
                    f"UPDATE events SET {assignments} WHERE id = ?",
                    tuple(params),
                )
            return self._get_unlocked(event_id)

    def delete(self, event_id: str) -> bool:
        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM events WHERE id = ?", (event_id,)
                )
            return cursor.rowcount > 0

    def close(self) -> None:
        """Close the shared connection. Safe to call more than once."""
        with self._lock:
            self._conn.close()
