"""Record construction and serialisation helpers for the event-service.

``new_event_record`` builds the persistable dict for a new event, applying the
defaults declared by the contract (``status`` -> ``"draft"``, ``description`` ->
``None``) and generating a UUID v4 ``id`` (REQ-EVT-F02, REQ-EVT-B04-AC3).

``event_to_dict`` serialises an internal record into the response body, exposing
exactly the thirteen fields of the contract ``Event`` schema (REQ-EVT-F02-AC8).

``utcnow_iso`` produces an ISO 8601 UTC timestamp with microsecond precision
(REQ-EVT-F11).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# The thirteen fields of the contract ``Event`` schema, in contract order.
EVENT_FIELDS = (
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

DEFAULT_STATUS = "draft"


def utcnow_iso() -> str:
    """ISO 8601 UTC timestamp with microsecond precision, suffix ``Z``.

    Example: ``2026-10-15T09:30:00.123456Z``. Microsecond precision ensures two
    consecutive operations produce distinct timestamps without artificial waits
    (REQ-EVT-F11).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_event_record(data: dict, now: str) -> dict:
    """Build the persistable dict for a new event.

    - ``id`` is a freshly generated UUID v4 (REQ-EVT-F02-AC2).
    - ``status`` defaults to ``"draft"`` when omitted (REQ-EVT-B04-AC3).
    - ``description`` defaults to ``None`` when omitted (REQ-EVT-F02-AC6).
    - ``created_at`` and ``updated_at`` are set to the same timestamp ``now``
      (REQ-EVT-F11-AC2).
    """
    return {
        "id": str(uuid.uuid4()),
        "title": data["title"],
        "description": data.get("description"),
        "organizer_id": data["organizer_id"],
        "venue": data["venue"],
        "city": data["city"],
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "capacity": data["capacity"],
        "price": data["price"],
        "status": data.get("status", DEFAULT_STATUS),
        "created_at": now,
        "updated_at": now,
    }


def event_to_dict(record: dict) -> dict:
    """Serialise an internal record into the response body (the 13 contract fields)."""
    return {field: record[field] for field in EVENT_FIELDS}
