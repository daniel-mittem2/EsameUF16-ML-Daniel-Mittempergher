"""Unit tests for the application factory and health endpoint (T-03).

Covers REQ-EVT-F01 (health check), REQ-EVT-F10 (unsupported method / unknown
path) and REQ-EVT-F12 (uniform error body). The user-service HTTP client is
injected as a plain instance; no outbound call is made because the health and
error paths never touch the dependency (REQ-EVT-F01-AC4).
"""
from app import create_app
from app.backends.memory import MemoryEventRepository
from app.http_client import UserServiceClient


def _client():
    """Build a Flask test client backed by an in-memory repository.

    A ``UserServiceClient`` is injected so the factory does not construct one
    from the environment; it is never called on the health/error paths.
    """
    app = create_app(
        repo=MemoryEventRepository(),
        user_client=UserServiceClient("http://user-service.invalid"),
    )
    return app.test_client()


def test_health_returns_exact_body_and_200_REQ_EVT_F01():
    """GET /health returns 200 with the exact Health body (REQ-EVT-F01-AC1/AC2)."""
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "service": "event-service"}


def test_health_is_json_content_type_REQ_EVT_F12():
    """The health response uses a JSON content type (REQ-EVT-F01-AC2)."""
    resp = _client().get("/health")
    assert resp.content_type.startswith("application/json")


def test_health_post_is_405_with_json_error_REQ_EVT_F10():
    """POST /health returns 405 with a JSON Error body (REQ-EVT-F01-AC3, F10, F12)."""
    resp = _client().post("/health")
    assert resp.status_code == 405
    body = resp.get_json()
    assert body is not None
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert body["error"]["details"] == {}
    assert isinstance(body["error"]["message"], str)


def test_unknown_path_is_404_with_json_error_REQ_EVT_F10():
    """An unknown path returns 404 with the standard Error body (REQ-EVT-F10-AC2)."""
    resp = _client().get("/api/v1/unknown")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] == {}
    assert isinstance(body["error"]["message"], str)


def test_create_app_without_config_uses_defaults_REQ_EVT_F13():
    """create_app() with no args builds a working app without requiring PORT (REQ-EVT-F13-AC5)."""
    client = create_app().test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "service": "event-service"}
