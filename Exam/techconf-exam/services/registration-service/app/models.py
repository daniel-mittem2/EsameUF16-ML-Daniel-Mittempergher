"""Record construction and serialisation helpers for the registration-service.

``new_registration_record`` builds the persistable dict for a new registration,
generating a UUID v4 ``id`` and setting ``status`` to ``"confirmed"`` — the only
status a freshly created registration can have (REQ-REG-F02-AC2/AC3). The
``amount`` is copied from ``event.price`` by the service and passed in
(REQ-REG-B06).

``registration_to_dict`` serialises an internal record into the response body,
exposing exactly the seven fields of the contract ``Registration`` schema
(REQ-REG-F02-AC7, REQ-REG-F10-AC5).

``utcnow_iso`` produces an ISO 8601 UTC timestamp with microsecond precision
(REQ-REG-F10).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# The seven fields of the contract ``Registration`` schema, in contract order.
REGISTRATION_FIELDS = (
    "id",
    "user_id",
    "event_id",
    "amount",
    "status",
    "created_at",
    "updated_at",
)

# A freshly created registration is always confirmed (REQ-REG-F02-AC3).
CONFIRMED = "confirmed"


def utcnow_iso() -> str:
    """ISO 8601 UTC timestamp with microsecond precision, suffix ``Z``.

    Example: ``2026-10-15T09:30:00.123456Z``. Microsecond precision ensures two
    consecutive operations produce distinct timestamps without artificial waits
    (REQ-REG-F10).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_registration_record(user_id: str, event_id: str, amount, now: str) -> dict:
    """Build the persistable dict for a new registration.

    - ``id`` is a freshly generated UUID v4 (REQ-REG-F02-AC2).
    - ``status`` is always ``"confirmed"`` at creation (REQ-REG-F02-AC3).
    - ``amount`` is copied from ``event.price`` by the service (REQ-REG-B06).
    - ``created_at`` and ``updated_at`` are set to the same timestamp ``now``
      (REQ-REG-F10-AC2).
    """
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_id": event_id,
        "amount": amount,
        "status": CONFIRMED,
        "created_at": now,
        "updated_at": now,
    }


def registration_to_dict(record: dict) -> dict:
    """Serialise an internal record into the response body (the 7 contract fields)."""
    return {field: record[field] for field in REGISTRATION_FIELDS}
