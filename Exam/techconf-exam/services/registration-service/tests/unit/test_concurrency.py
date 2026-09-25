"""Concurrency unit tests for the registration-service (T-13, REQ-REG-T01-AC6).

Proves that the combined *duplicate + capacity + create* sequence does not
oversell an event nor create a double confirmed registration under concurrent
requests (REQ-REG-B04-AC3, REQ-REG-B05-AC5, design §5). Two scenarios run the
service's ``create_registration`` from several ``threading.Thread`` workers
against a single :class:`MemoryRegistrationRepository`:

* capacity 1 + two (many) simultaneous creates for **different** users on the
  same event → exactly one 201-equivalent success and the rest ``EVENT_FULL``;
* two (many) simultaneous creates for the **same** user on the same event →
  exactly one success and the rest ``ALREADY_REGISTERED``.

The outbound user/event lookups are mocked at the library level with
``responses`` (a ``CallbackResponse`` matched with ``assert_all_requests_are_fired
=False`` so it may fire any number of times), so no real network call leaves the
test process (REQ-REG-T01-AC2). The critical section that must stay atomic is the
repository's ``create_if_allowed`` (design §5); the HTTP calls happen before it,
outside the lock.
"""
from __future__ import annotations

import json
import re
import threading
import uuid

import responses

from app import errors
from app.backends.memory import MemoryRegistrationRepository
from app.http_client import EventServiceClient, UserServiceClient
from app.service import RegistrationService, ServiceError

USER_BASE_URL = "http://user-service.test"
EVENT_BASE_URL = "http://event-service.test"


def _service(repo: MemoryRegistrationRepository) -> RegistrationService:
    return RegistrationService(
        repo,
        UserServiceClient(USER_BASE_URL, timeout=2.0),
        EventServiceClient(EVENT_BASE_URL, timeout=2.0),
    )


def _register_user_callback() -> None:
    """Mock every ``GET /api/v1/users/<id>`` with a 200 user payload.

    A regex-matched callback answers each concurrent worker's lookup regardless
    of the (distinct) user id; it may fire any number of times.
    """

    def _callback(request):
        user_id = request.url.rsplit("/", 1)[-1]
        payload = {
            "id": user_id,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "company": None,
            "role": "attendee",
            "created_at": "2026-10-15T09:30:00.000000Z",
            "updated_at": "2026-10-15T09:30:00.000000Z",
        }
        return (200, {}, json.dumps(payload))

    responses.add_callback(
        responses.GET,
        re.compile(rf"{re.escape(USER_BASE_URL)}/api/v1/users/.+"),
        callback=_callback,
        content_type="application/json",
    )


def _register_event_callback(event_id: str, *, capacity: int) -> None:
    """Mock ``GET /api/v1/events/<event_id>`` with a published event payload."""

    def _callback(request):
        payload = {
            "id": event_id,
            "title": "TechConf 2026",
            "description": None,
            "organizer_id": str(uuid.uuid4()),
            "venue": "Main Hall",
            "city": "Milano",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "capacity": capacity,
            "price": 149.00,
            "status": "published",
            "created_at": "2026-10-15T09:30:00.000000Z",
            "updated_at": "2026-10-15T09:30:00.000000Z",
        }
        return (200, {}, json.dumps(payload))

    responses.add_callback(
        responses.GET,
        f"{EVENT_BASE_URL}/api/v1/events/{event_id}",
        callback=_callback,
        content_type="application/json",
    )


def _run_concurrent_creates(service, payloads):
    """Run ``create_registration`` for each payload in its own thread.

    Returns ``(successes, errors_by_code)`` where ``successes`` is the list of
    created records and ``errors_by_code`` maps a ServiceError code to the count
    of failures with that code.
    """
    successes: list[dict] = []
    failures: list[ServiceError] = []
    guard = threading.Lock()
    barrier = threading.Barrier(len(payloads))

    def worker(payload):
        # Line up all threads so they hit the critical section together.
        barrier.wait()
        try:
            record = service.create_registration(payload)
            with guard:
                successes.append(record)
        except ServiceError as exc:
            with guard:
                failures.append(exc)

    threads = [threading.Thread(target=worker, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    codes: dict[str, int] = {}
    for exc in failures:
        codes[exc.code] = codes.get(exc.code, 0) + 1
    return successes, codes


# --------------------------------------------------------------------------- #
# Capacity 1: concurrent creates for different users → one wins, rest EVENT_FULL
# --------------------------------------------------------------------------- #
@responses.activate
def test_capacity_one_concurrent_creates_admit_exactly_one_REQ_REG_T01(  # noqa: N802
):
    """REQ-REG-B05-AC5 / design §5: capacity 1, many concurrent creates → one 201, rest EVENT_FULL."""
    repo = MemoryRegistrationRepository()
    service = _service(repo)
    event_id = str(uuid.uuid4())

    _register_user_callback()
    _register_event_callback(event_id, capacity=1)

    payloads = [
        {"user_id": str(uuid.uuid4()), "event_id": event_id} for _ in range(12)
    ]

    successes, codes = _run_concurrent_creates(service, payloads)

    assert len(successes) == 1
    assert codes.get(errors.EVENT_FULL, 0) == 11
    # No other error code appeared and nothing was oversold.
    assert set(codes) <= {errors.EVENT_FULL}
    assert repo.count_confirmed(event_id) == 1


# --------------------------------------------------------------------------- #
# Same user: concurrent creates → one wins, rest ALREADY_REGISTERED
# --------------------------------------------------------------------------- #
@responses.activate
def test_same_user_concurrent_creates_admit_exactly_one_REQ_REG_T01(  # noqa: N802
):
    """REQ-REG-B04-AC3 / design §5: same user, many concurrent creates → one 201, rest ALREADY_REGISTERED."""
    repo = MemoryRegistrationRepository()
    service = _service(repo)
    user_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    _register_user_callback()
    # High capacity so the only conflict possible is the duplicate check.
    _register_event_callback(event_id, capacity=100)

    payloads = [
        {"user_id": user_id, "event_id": event_id} for _ in range(12)
    ]

    successes, codes = _run_concurrent_creates(service, payloads)

    assert len(successes) == 1
    assert codes.get(errors.ALREADY_REGISTERED, 0) == 11
    assert set(codes) <= {errors.ALREADY_REGISTERED}
    # Exactly one confirmed registration for the pair persisted.
    assert repo.count_confirmed(event_id) == 1
