"""Unit tests for ``app.http_client`` (UserServiceClient, EventServiceClient).

Every branch of both dependency clients is exercised with the ``responses``
library so that no real network call leaves the test process
(REQ-REG-T01-AC2). Covers REQ-REG-B01, REQ-REG-B02, REQ-REG-B09 and the
2-second timeout / configurable base URL of REQ-REG-F12.

Branch matrix (per client, via the shared ``_get``):

* 200                          -> parsed JSON object            (REQ-REG-B01/B02)
* 404                          -> ReferenceNotFoundError         (REQ-REG-B01-AC3, B02-AC3)
* 5xx                          -> DependencyUnavailableError     (REQ-REG-B09-AC3)
* unexpected status (e.g. 301) -> DependencyUnavailableError     (REQ-REG-B09)
* ConnectionError              -> DependencyUnavailableError     (REQ-REG-B09-AC2)
* Timeout                      -> DependencyUnavailableError     (REQ-REG-B09-AC1)
* 2s timeout wiring / base URL -> no hard-coded URL, 2s timeout  (REQ-REG-F12, B01/B02-AC2)
"""
import uuid

import pytest
import requests
import responses

from app.http_client import (
    DependencyUnavailableError,
    EventServiceClient,
    ReferenceNotFoundError,
    UserServiceClient,
)

USER_BASE_URL = "http://user-service.test"
EVENT_BASE_URL = "http://event-service.test"


def _user_url(user_id: str) -> str:
    return f"{USER_BASE_URL}/api/v1/users/{user_id}"


def _event_url(event_id: str) -> str:
    return f"{EVENT_BASE_URL}/api/v1/events/{event_id}"


def _user_payload(user_id: str) -> dict:
    return {
        "id": user_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "company": None,
        "role": "attendee",
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


def _event_payload(event_id: str) -> dict:
    return {
        "id": event_id,
        "title": "TechConf 2026",
        "description": None,
        "organizer_id": str(uuid.uuid4()),
        "venue": "Main Hall",
        "city": "Milano",
        "start_date": "2026-11-01",
        "end_date": "2026-11-02",
        "capacity": 100,
        "price": 149.00,
        "status": "published",
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


@pytest.fixture
def user_client():
    return UserServiceClient(USER_BASE_URL, timeout=2.0)


@pytest.fixture
def event_client():
    return EventServiceClient(EVENT_BASE_URL, timeout=2.0)


# --------------------------------------------------------------------------- #
# 200 -> parsed JSON (REQ-REG-B01, REQ-REG-B02)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_200_returns_parsed_json(user_client):
    """REQ-REG-B01: get_user returns the parsed user object on 200."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id),
                  json=_user_payload(user_id), status=200)

    user = user_client.get_user(user_id)

    assert user["id"] == user_id
    assert user["role"] == "attendee"


@responses.activate
def test_get_event_200_returns_parsed_json(event_client):
    """REQ-REG-B02: get_event returns the parsed event with status/price/capacity."""
    event_id = str(uuid.uuid4())
    responses.add(responses.GET, _event_url(event_id),
                  json=_event_payload(event_id), status=200)

    event = event_client.get_event(event_id)

    assert event["id"] == event_id
    assert event["status"] == "published"
    assert event["price"] == 149.00
    assert event["capacity"] == 100


# --------------------------------------------------------------------------- #
# 404 -> ReferenceNotFoundError (REQ-REG-B01-AC3, REQ-REG-B02-AC3)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_404_raises_reference_not_found(user_client):
    """REQ-REG-B01-AC3: a 404 from user-service maps to ReferenceNotFoundError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id),
                  json={"error": {"code": "NOT_FOUND", "message": "not found"}},
                  status=404)

    with pytest.raises(ReferenceNotFoundError):
        user_client.get_user(user_id)


@responses.activate
def test_get_event_404_raises_reference_not_found(event_client):
    """REQ-REG-B02-AC3: a 404 from event-service maps to ReferenceNotFoundError."""
    event_id = str(uuid.uuid4())
    responses.add(responses.GET, _event_url(event_id), status=404)

    with pytest.raises(ReferenceNotFoundError):
        event_client.get_event(event_id)


# --------------------------------------------------------------------------- #
# 5xx -> DependencyUnavailableError (REQ-REG-B09-AC3)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", [500, 502, 503])
@responses.activate
def test_get_user_5xx_raises_dependency_unavailable(user_client, status):
    """REQ-REG-B09-AC3: a 5xx from user-service maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id), status=status)

    with pytest.raises(DependencyUnavailableError):
        user_client.get_user(user_id)


@pytest.mark.parametrize("status", [500, 502, 503])
@responses.activate
def test_get_event_5xx_raises_dependency_unavailable(event_client, status):
    """REQ-REG-B09-AC3: a 5xx from event-service maps to DependencyUnavailableError."""
    event_id = str(uuid.uuid4())
    responses.add(responses.GET, _event_url(event_id), status=status)

    with pytest.raises(DependencyUnavailableError):
        event_client.get_event(event_id)


# --------------------------------------------------------------------------- #
# unexpected status -> DependencyUnavailableError (REQ-REG-B09)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_unexpected_status_raises_dependency_unavailable(user_client):
    """REQ-REG-B09: an unexpected non-200/404/5xx status maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id), status=301)

    with pytest.raises(DependencyUnavailableError):
        user_client.get_user(user_id)


@responses.activate
def test_get_event_unexpected_status_raises_dependency_unavailable(event_client):
    """REQ-REG-B09: an unexpected non-200/404/5xx status maps to DependencyUnavailableError."""
    event_id = str(uuid.uuid4())
    responses.add(responses.GET, _event_url(event_id), status=418)

    with pytest.raises(DependencyUnavailableError):
        event_client.get_event(event_id)


# --------------------------------------------------------------------------- #
# ConnectionError -> DependencyUnavailableError (REQ-REG-B09-AC2)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_connection_error_raises_dependency_unavailable(user_client):
    """REQ-REG-B09-AC2: a refused connection maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id),
                  body=requests.ConnectionError("connection refused"))

    with pytest.raises(DependencyUnavailableError):
        user_client.get_user(user_id)


@responses.activate
def test_get_event_connection_error_raises_dependency_unavailable(event_client):
    """REQ-REG-B09-AC2: a refused connection maps to DependencyUnavailableError."""
    event_id = str(uuid.uuid4())
    responses.add(responses.GET, _event_url(event_id),
                  body=requests.ConnectionError("connection refused"))

    with pytest.raises(DependencyUnavailableError):
        event_client.get_event(event_id)


# --------------------------------------------------------------------------- #
# Timeout -> DependencyUnavailableError (REQ-REG-B09-AC1)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_timeout_raises_dependency_unavailable(user_client):
    """REQ-REG-B09-AC1: a request timeout maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id),
                  body=requests.Timeout("timed out"))

    with pytest.raises(DependencyUnavailableError):
        user_client.get_user(user_id)


@responses.activate
def test_get_event_timeout_raises_dependency_unavailable(event_client):
    """REQ-REG-B09-AC1: a request timeout maps to DependencyUnavailableError."""
    event_id = str(uuid.uuid4())
    responses.add(responses.GET, _event_url(event_id),
                  body=requests.Timeout("timed out"))

    with pytest.raises(DependencyUnavailableError):
        event_client.get_event(event_id)


# --------------------------------------------------------------------------- #
# 2s timeout wiring + base URL (REQ-REG-B01-AC2, REQ-REG-B02-AC2, REQ-REG-F12)
# --------------------------------------------------------------------------- #
def test_user_request_uses_two_second_timeout(monkeypatch):
    """REQ-REG-B01-AC2: the user-service request is issued with a 2-second timeout."""
    user_id = str(uuid.uuid4())
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _user_payload(user_id)

    def _fake_get(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("app.http_client.requests.get", _fake_get)
    client = UserServiceClient(USER_BASE_URL, timeout=2.0)

    client.get_user(user_id)

    assert captured["timeout"] == 2.0
    assert captured["url"] == _user_url(user_id)


def test_event_request_uses_two_second_timeout(monkeypatch):
    """REQ-REG-B02-AC2: the event-service request is issued with a 2-second timeout."""
    event_id = str(uuid.uuid4())
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _event_payload(event_id)

    def _fake_get(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("app.http_client.requests.get", _fake_get)
    client = EventServiceClient(EVENT_BASE_URL, timeout=2.0)

    client.get_event(event_id)

    assert captured["timeout"] == 2.0
    assert captured["url"] == _event_url(event_id)


@responses.activate
def test_user_trailing_slash_in_base_url_is_normalized():
    """REQ-REG-F12: a user base URL with a trailing slash yields a single-slash path."""
    user_id = str(uuid.uuid4())
    client = UserServiceClient(USER_BASE_URL + "/", timeout=2.0)
    responses.add(responses.GET, _user_url(user_id),
                  json=_user_payload(user_id), status=200)

    client.get_user(user_id)

    assert responses.calls[0].request.url == _user_url(user_id)


@responses.activate
def test_event_trailing_slash_in_base_url_is_normalized():
    """REQ-REG-F12: an event base URL with a trailing slash yields a single-slash path."""
    event_id = str(uuid.uuid4())
    client = EventServiceClient(EVENT_BASE_URL + "/", timeout=2.0)
    responses.add(responses.GET, _event_url(event_id),
                  json=_event_payload(event_id), status=200)

    client.get_event(event_id)

    assert responses.calls[0].request.url == _event_url(event_id)
