"""Unit tests for the application factory and health endpoint (T-03).

Covers REQ-USR-F01 (health check), REQ-USR-F10 (unsupported method / unknown
path) and REQ-USR-F12 (uniform error body).
"""
from app import create_app
from app.backends.memory import MemoryUserRepository


def _client():
    """Build a Flask test client backed by an in-memory repository."""
    return create_app(repo=MemoryUserRepository()).test_client()


def test_health_returns_exact_body_and_200_REQ_USR_F01():
    """GET /health returns 200 with the exact Health body (REQ-USR-F01-AC1/AC2)."""
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "service": "user-service"}


def test_health_is_json_content_type_REQ_USR_F12():
    """The health response is JSON (REQ-USR-F12-AC5)."""
    resp = _client().get("/health")
    assert resp.content_type.startswith("application/json")


def test_health_post_is_405_with_json_error_REQ_USR_F10():
    """POST /health returns 405 with a JSON Error body (REQ-USR-F01-AC3, F10)."""
    resp = _client().post("/health")
    assert resp.status_code == 405
    body = resp.get_json()
    assert body is not None
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert body["error"]["details"] == {}
    assert isinstance(body["error"]["message"], str)


def test_unknown_path_is_404_with_json_error_REQ_USR_F10():
    """An unknown path returns 404 with the standard Error body (REQ-USR-F10-AC2)."""
    resp = _client().get("/api/v1/unknown")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] == {}


def test_create_app_without_config_uses_memory_default_REQ_USR_F13():
    """create_app() with no repo/config builds a working app (REQ-USR-F13-AC3)."""
    client = create_app().test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
