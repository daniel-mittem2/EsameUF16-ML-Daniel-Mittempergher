"""Unit tests for ``app.http_client.UserServiceClient``.

Every organizer-verification branch is exercised with the ``responses`` library
so that no real network call leaves the test process (REQ-EVT-T01-AC2):

* 200 + role=organizer        -> success                       (REQ-EVT-B01, REQ-EVT-B02)
* 200 + wrong role            -> InvalidOrganizerError          (REQ-EVT-B02)
* 404                         -> ReferenceNotFoundError         (REQ-EVT-B01)
* 5xx                         -> DependencyUnavailableError     (REQ-EVT-B05)
* unexpected status (e.g. 301)-> DependencyUnavailableError     (REQ-EVT-B05)
* ConnectionError / Timeout   -> DependencyUnavailableError     (REQ-EVT-B05)
* timeout wiring / base URL   -> 2s timeout, no hard-coded URL  (REQ-EVT-F13, REQ-EVT-B01-AC2)
"""
import uuid

import pytest
import requests
import responses

from app.http_client import (
    DependencyUnavailableError,
    InvalidOrganizerError,
    ReferenceNotFoundError,
    UserServiceClient,
)

BASE_URL = "http://user-service.test"


def _user_url(user_id: str) -> str:
    return f"{BASE_URL}/api/v1/users/{user_id}"


def _user_payload(user_id: str, role: str) -> dict:
    return {
        "id": user_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "company": None,
        "role": role,
        "created_at": "2026-10-15T09:30:00.000000Z",
        "updated_at": "2026-10-15T09:30:00.000000Z",
    }


@pytest.fixture
def client():
    return UserServiceClient(BASE_URL, timeout=2.0)


# --------------------------------------------------------------------------- #
# 200 + role=organizer -> success (REQ-EVT-B01, REQ-EVT-B02)
# --------------------------------------------------------------------------- #
@responses.activate
def test_verify_organizer_success_returns_user(client):
    """REQ-EVT-B01, REQ-EVT-B02: 200 with role=organizer returns the user."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        json=_user_payload(user_id, "organizer"),
        status=200,
    )

    user = client.verify_organizer(user_id)

    assert user["id"] == user_id
    assert user["role"] == "organizer"


@responses.activate
def test_get_user_returns_parsed_json(client):
    """REQ-EVT-B01: get_user returns the parsed user object on 200."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        json=_user_payload(user_id, "attendee"),
        status=200,
    )

    user = client.get_user(user_id)

    assert user["id"] == user_id
    assert user["role"] == "attendee"


# --------------------------------------------------------------------------- #
# 200 + wrong role -> InvalidOrganizerError (REQ-EVT-B02)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["attendee", "speaker"])
@responses.activate
def test_verify_organizer_wrong_role_raises(client, role):
    """REQ-EVT-B02: an existing user whose role != organizer raises InvalidOrganizerError."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        json=_user_payload(user_id, role),
        status=200,
    )

    with pytest.raises(InvalidOrganizerError):
        client.verify_organizer(user_id)


@responses.activate
def test_verify_organizer_missing_role_raises(client):
    """REQ-EVT-B02: a 200 payload without a role field raises InvalidOrganizerError."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        json={"id": user_id},
        status=200,
    )

    with pytest.raises(InvalidOrganizerError):
        client.verify_organizer(user_id)


# --------------------------------------------------------------------------- #
# 404 -> ReferenceNotFoundError (REQ-EVT-B01, REQ-EVT-B05-AC5)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_404_raises_reference_not_found(client):
    """REQ-EVT-B01: a 404 from user-service maps to ReferenceNotFoundError (not unavailable)."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        json={"error": {"code": "NOT_FOUND", "message": "not found"}},
        status=404,
    )

    with pytest.raises(ReferenceNotFoundError):
        client.get_user(user_id)


@responses.activate
def test_verify_organizer_404_raises_reference_not_found(client):
    """REQ-EVT-B01, REQ-EVT-B05-AC5: verify_organizer surfaces 404 as ReferenceNotFoundError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id), status=404)

    with pytest.raises(ReferenceNotFoundError):
        client.verify_organizer(user_id)


# --------------------------------------------------------------------------- #
# 5xx -> DependencyUnavailableError (REQ-EVT-B05-AC3)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", [500, 502, 503])
@responses.activate
def test_get_user_5xx_raises_dependency_unavailable(client, status):
    """REQ-EVT-B05-AC3: a 5xx response maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id), status=status)

    with pytest.raises(DependencyUnavailableError):
        client.get_user(user_id)


# --------------------------------------------------------------------------- #
# unexpected status -> DependencyUnavailableError (REQ-EVT-B05)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_unexpected_status_raises_dependency_unavailable(client):
    """REQ-EVT-B05: an unexpected non-200/404/5xx status maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(responses.GET, _user_url(user_id), status=301)

    with pytest.raises(DependencyUnavailableError):
        client.get_user(user_id)


# --------------------------------------------------------------------------- #
# ConnectionError -> DependencyUnavailableError (REQ-EVT-B05-AC2)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_connection_error_raises_dependency_unavailable(client):
    """REQ-EVT-B05-AC2: a refused connection maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        body=requests.ConnectionError("connection refused"),
    )

    with pytest.raises(DependencyUnavailableError):
        client.get_user(user_id)


# --------------------------------------------------------------------------- #
# Timeout -> DependencyUnavailableError (REQ-EVT-B05-AC1)
# --------------------------------------------------------------------------- #
@responses.activate
def test_get_user_timeout_raises_dependency_unavailable(client):
    """REQ-EVT-B05-AC1: a request timeout maps to DependencyUnavailableError."""
    user_id = str(uuid.uuid4())
    responses.add(
        responses.GET,
        _user_url(user_id),
        body=requests.Timeout("timed out"),
    )

    with pytest.raises(DependencyUnavailableError):
        client.get_user(user_id)


# --------------------------------------------------------------------------- #
# timeout wiring + base URL normalization (REQ-EVT-B01-AC2, REQ-EVT-F13)
# --------------------------------------------------------------------------- #
def test_request_uses_two_second_timeout(monkeypatch):
    """REQ-EVT-B01-AC2: the outbound request is issued with a 2-second timeout."""
    user_id = str(uuid.uuid4())
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _user_payload(user_id, "organizer")

    def _fake_get(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("app.http_client.requests.get", _fake_get)
    client = UserServiceClient(BASE_URL, timeout=2.0)

    client.get_user(user_id)

    assert captured["timeout"] == 2.0
    assert captured["url"] == _user_url(user_id)


@responses.activate
def test_trailing_slash_in_base_url_is_normalized():
    """REQ-EVT-F13: a base URL with a trailing slash produces a single-slash path."""
    user_id = str(uuid.uuid4())
    client = UserServiceClient(BASE_URL + "/", timeout=2.0)
    responses.add(
        responses.GET,
        _user_url(user_id),
        json=_user_payload(user_id, "organizer"),
        status=200,
    )

    client.get_user(user_id)

    assert responses.calls[0].request.url == _user_url(user_id)
