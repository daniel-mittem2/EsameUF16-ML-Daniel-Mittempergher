"""Regression tests for real bugs found during T-18 (registration-service).

Each test documents a genuine defect discovered during the bug-workflow
investigation (workflow §6.4/§6.5). The test is written to FAIL on the
unfixed code and PASS once the fix is applied. See ``BUGS.md`` for the
issue/commit references.
"""
from __future__ import annotations

from app.backends.memory import MemoryRegistrationRepository
from app.models import new_registration_record, utcnow_iso

USER_A = "11111111-1111-4111-8111-111111111111"
EVENT_X = "33333333-3333-4333-8333-333333333333"


def _maker(user_id=USER_A, event_id=EVENT_X, amount=149.0):
    def _make():
        return new_registration_record(user_id, event_id, amount, utcnow_iso())
    return _make


# --------------------------------------------------------------------------- #
# BUG-001 — memory backend returns internal references (no isolation)
# --------------------------------------------------------------------------- #
# The json and sqlite backends return isolated copies of every record (deepcopy
# / freshly-built rows), so a caller can never mutate the stored state through a
# returned dict. The memory backend returned the *internal* dict object, so a
# mutation of a returned record silently corrupted the store. This breaks the
# cross-backend equivalence guarantee (REQ-REG-F13-AC4) and the read-only /
# immutability guarantee on stored fields (REQ-REG-F10-AC5). The memory backend
# must mirror json/sqlite and return isolated copies.

def test_memory_get_returns_isolated_copy():
    """REQ-REG-F13-AC4/F10: mutating a record from get() must not corrupt the store."""
    repo = MemoryRegistrationRepository()
    rec = repo.create_if_allowed(USER_A, EVENT_X, 10, _maker())
    got = repo.get(rec["id"])
    got["status"] = "HACKED"
    got["amount"] = -999
    fresh = repo.get(rec["id"])
    assert fresh["status"] == "confirmed"
    assert fresh["amount"] == 149.0


def test_memory_create_returns_isolated_copy():
    """REQ-REG-F13-AC4/F10: mutating the record returned by create must not corrupt the store."""
    repo = MemoryRegistrationRepository()
    rec = repo.create_if_allowed(USER_A, EVENT_X, 10, _maker())
    rec["status"] = "HACKED"
    assert repo.get(rec["id"])["status"] == "confirmed"


def test_memory_list_all_returns_isolated_copies():
    """REQ-REG-F13-AC4/F10: mutating a record from list_all must not corrupt the store."""
    repo = MemoryRegistrationRepository()
    repo.create_if_allowed(USER_A, EVENT_X, 10, _maker())
    listed = repo.list_all({})
    listed[0]["status"] = "HACKED"
    assert repo.list_all({})[0]["status"] == "confirmed"


def test_memory_set_status_returns_isolated_copy():
    """REQ-REG-F13-AC4/F10: mutating the record returned by set_status must not corrupt the store."""
    repo = MemoryRegistrationRepository()
    rec = repo.create_if_allowed(USER_A, EVENT_X, 10, _maker())
    updated = repo.set_status(rec["id"], "cancelled", utcnow_iso())
    updated["status"] = "HACKED"
    assert repo.get(rec["id"])["status"] == "cancelled"
