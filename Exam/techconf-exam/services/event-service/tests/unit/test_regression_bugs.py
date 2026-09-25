"""Regression tests for real bugs found during T-18 (event-service).

Each test documents a genuine defect discovered during the bug-workflow
investigation (workflow §6.4/§6.5). The test is written to FAIL on the
unfixed code and PASS once the fix is applied. See ``BUGS.md`` for the
issue/commit references.
"""
from __future__ import annotations

import pytest

from app import validators


# --------------------------------------------------------------------------- #
# BUG-002 — validate_date accepts ISO week-date strings (YYYY-Www-D)
# --------------------------------------------------------------------------- #
# The contract declares start_date/end_date as OpenAPI ``format: date``
# (RFC 3339 full-date, i.e. strictly YYYY-MM-DD). ``date.fromisoformat`` in
# Python 3.11+ also parses ISO week dates like "2026-W40-1", which happen to be
# exactly 10 characters long, so the ``len(value) == 10`` guard fails to reject
# them. Such a value must be an invalid date (REQ-EVT-F03-AC5).
@pytest.mark.parametrize(
    "value",
    [
        "2026-W40-1",   # ISO week date -> Monday of week 40, len == 10
        "2026-W01-7",   # ISO week date -> Sunday of week 1, len == 10
    ],
)
def test_validate_date_rejects_iso_week_dates(value):
    """REQ-EVT-F03-AC5: ISO week-date strings are NOT valid YYYY-MM-DD dates."""
    assert validators.validate_date(value) is False


def test_validate_event_create_rejects_iso_week_date():
    """REQ-EVT-F03-AC5: POSTing an ISO week date in start_date is a validation error."""
    data = {
        "title": "Conf",
        "organizer_id": "11111111-1111-4111-8111-111111111111",
        "venue": "Hall",
        "city": "Rome",
        "start_date": "2026-W40-1",
        "end_date": "2026-10-05",
        "capacity": 100,
        "price": 149.0,
    }
    errs = validators.validate_event_create(data)
    assert any("start_date" in e for e in errs), errs
