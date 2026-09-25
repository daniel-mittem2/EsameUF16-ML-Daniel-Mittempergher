"""SQLite user repository backend (REQ-USR-F14-AC3).

Persists records in a SQLite database file (``users.db``) inside the configured
data directory. The connection is opened once in ``__init__`` with
``check_same_thread=False`` so it can be shared across the threads Flask uses to
serve concurrent requests (design §9, §10).

A single :class:`threading.RLock` per instance protects both reads and writes.
The "check email uniqueness + write" sequence runs entirely inside the lock so
that concurrent ``create``/``update`` requests can never both succeed with the
same email (REQ-USR-B01, design §10). As a second line of defence the schema
declares a ``UNIQUE INDEX`` on ``LOWER(email)``: any duplicate that reaches the
database raises :class:`sqlite3.IntegrityError`, which is caught here and
re-raised as :class:`EmailAlreadyExistsError` (REQ-USR-B01, REQ-USR-B01
IntegrityError mapping).

Every write is wrapped in ``with self._conn:`` so the change is committed on
success and rolled back automatically if an exception propagates.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.repository import AbstractUserRepository, EmailAlreadyExistsError

# Columns of the ``users`` table, in the internal record order.
_COLUMNS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "company",
    "role",
    "created_at",
    "updated_at",
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL,
    company     TEXT,
    role        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
"""

# Case-insensitive uniqueness at the database level (REQ-USR-B01).
_CREATE_EMAIL_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower "
    "ON users (LOWER(email))"
)


class SqliteUserRepository(AbstractUserRepository):
    """User repository backed by a SQLite database file.

    Args:
        path: Path to the ``users.db`` file. The parent directory is created if
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
            self._conn.execute(_CREATE_EMAIL_INDEX)

    # ------------------------------------------------------------------ #
    # Helpers (call sites already hold the lock)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict:
        """Convert a SQLite row into a plain record dict."""
        return {column: row[column] for column in _COLUMNS}

    def _find_by_email_unlocked(self, email: str) -> Optional[dict]:
        """Return the record matching ``email`` case-insensitively (no locking)."""
        cursor = self._conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    def _get_unlocked(self, user_id: str) -> Optional[dict]:
        cursor = self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    # ------------------------------------------------------------------ #
    # AbstractUserRepository implementation
    # ------------------------------------------------------------------ #
    def create(self, record: dict) -> dict:
        """Persist ``record``; raise if its email is already taken (REQ-USR-B01)."""
        with self._lock:
            if self._find_by_email_unlocked(record["email"]) is not None:
                raise EmailAlreadyExistsError()
            try:
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO users "
                        "(id, first_name, last_name, email, company, role, "
                        "created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        tuple(record[column] for column in _COLUMNS),
                    )
            except sqlite3.IntegrityError as exc:
                # The UNIQUE INDEX on LOWER(email) caught a duplicate that
                # slipped past the in-process check (REQ-USR-B01).
                raise EmailAlreadyExistsError() from exc
            return self._get_unlocked(record["id"])

    def get(self, user_id: str) -> Optional[dict]:
        with self._lock:
            return self._get_unlocked(user_id)

    def list_all(self, filters: dict) -> list[dict]:
        role = filters.get("role")
        email = filters.get("email")
        clauses = []
        params: list = []
        if role is not None:
            clauses.append("role = ?")
            params.append(role)
        if isinstance(email, str):
            clauses.append("LOWER(email) = LOWER(?)")
            params.append(email)
        query = "SELECT * FROM users"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock:
            cursor = self._conn.execute(query, tuple(params))
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def update(self, user_id: str, changes: dict) -> Optional[dict]:
        """Apply ``changes`` atomically; enforce email uniqueness (REQ-USR-B01)."""
        with self._lock:
            record = self._get_unlocked(user_id)
            if record is None:
                return None
            new_email = changes.get("email")
            if new_email is not None:
                existing = self._find_by_email_unlocked(new_email)
                if existing is not None and existing["id"] != user_id:
                    raise EmailAlreadyExistsError()
            # Only update columns that are known and actually provided.
            updatable = [c for c in _COLUMNS if c != "id" and c in changes]
            if not updatable:
                return record
            assignments = ", ".join(f"{column} = ?" for column in updatable)
            params = [changes[column] for column in updatable]
            params.append(user_id)
            try:
                with self._conn:
                    self._conn.execute(
                        f"UPDATE users SET {assignments} WHERE id = ?",
                        tuple(params),
                    )
            except sqlite3.IntegrityError as exc:
                raise EmailAlreadyExistsError() from exc
            return self._get_unlocked(user_id)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            with self._conn:
                cursor = self._conn.execute(
                    "DELETE FROM users WHERE id = ?", (user_id,)
                )
            return cursor.rowcount > 0

    def get_by_email(self, email: str) -> Optional[dict]:
        with self._lock:
            return self._find_by_email_unlocked(email)

    def close(self) -> None:
        """Close the shared connection. Safe to call more than once."""
        with self._lock:
            self._conn.close()
