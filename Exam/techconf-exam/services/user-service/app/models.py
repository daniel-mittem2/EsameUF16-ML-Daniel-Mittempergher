"""Record construction and serialisation helpers for the user-service.

``new_user_record`` builds the persistable dict for a new user, applying the
defaults declared by the contract (``role`` -> ``"attendee"``, ``company`` ->
``None``) and normalising the email to lower case (REQ-USR-B02).

``user_to_dict`` serialises an internal record into the response body, exposing
only the eight fields of the contract ``User`` schema.

``utcnow_iso`` produces an ISO 8601 UTC timestamp with microsecond precision.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

# The eight fields of the contract ``User`` schema, in contract order.
USER_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "company",
    "role",
    "created_at",
    "updated_at",
)

DEFAULT_ROLE = "attendee"


def utcnow_iso() -> str:
    """ISO 8601 UTC timestamp with microsecond precision, suffix ``Z``.

    Example: ``2026-10-15T09:30:00.123456Z``. Microsecond precision ensures two
    consecutive operations produce distinct timestamps without artificial waits.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_user_record(data: dict, now: str) -> dict:
    """Build the persistable dict for a new user.

    - ``email`` is normalised to lower case (REQ-USR-B02).
    - ``role`` defaults to ``"attendee"`` when omitted.
    - ``company`` defaults to ``None`` when omitted.
    - ``created_at`` and ``updated_at`` are set to the same timestamp ``now``.
    """
    return {
        "id": str(uuid.uuid4()),
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "email": data["email"].lower(),
        "company": data.get("company"),
        "role": data.get("role", DEFAULT_ROLE),
        "created_at": now,
        "updated_at": now,
    }


def user_to_dict(record: dict) -> dict:
    """Serialise an internal record into the response body (the 8 contract fields)."""
    return {field: record[field] for field in USER_FIELDS}
