"""Contract-conformance unit tests for the user-service (T-13, REQ-USR-T01-AC3).

For EACH HTTP operation defined in the ``user-service.yaml`` contract there is
at least one test that drives the Flask test client and asserts the response
against the OpenAPI contract via ``assert_matches_contract("user", method,
path, response)`` from ``contracts/validator.py``.

The validator lives in the (non-modifiable) template under
``Exam/techconf-exam/contracts/``. We add that directory to ``sys.path`` the
same way ``tests/integration/conftest.py`` does, resolving the repo root
relative to this file.

Per design.md §11/§12 the validator is used ONLY for responses the contract
actually declares. Infrastructure exceptions (400 malformed JSON, 405 method
not allowed) are NOT part of the per-operation contract, so those are covered
by ``test_routes.py``/``test_app_factory.py`` with manual assertions, never
through ``assert_matches_contract``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import create_app
from app.backends.memory import MemoryUserRepository

# Make contracts/validator.py importable, mirroring tests/integration/conftest.py.
# This file: .../services/user-service/tests/unit/test_contracts.py
#   parents[0]=unit [1]=tests [2]=user-service [3]=services [4]=techconf-exam (repo root)
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "contracts"))

from validator import assert_matches_contract  # noqa: E402

USERS = "/api/v1/users"


def flask_to_contract_dict(resp) -> dict:
    """Convert a Flask test response into the dict accepted by the validator.

    Design.md §11: the validator's dict branch reads ``response["json"]``
    directly, so we build the dict rather than adapting the Flask response
    object (whose ``.json`` is a property, not a callable). ``get_json`` with
    ``silent=True`` returns ``None`` for a body-less 204, which the validator
    treats as "no body expected".
    """
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "json": resp.get_json(silent=True),
    }


@pytest.fixture()
def client():
    """A Flask test client backed by a fresh in-memory repository."""
    return create_app(repo=MemoryUserRepository()).test_client()


def _create_user(client, email="alice@example.com"):
    """Create a user through the API and return the parsed User body."""
    resp = client.post(
        USERS,
        json={"first_name": "Alice", "last_name": "Rossi", "email": email},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --------------------------------------------------------------------------- #
# 1/7 — GET /health (REQ-USR-F01)
# --------------------------------------------------------------------------- #
def test_health_matches_contract_REQ_USR_F01(client):
    """GET /health 200 conforms to the Health schema (REQ-USR-T01-AC3)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert_matches_contract("user", "GET", "/health", flask_to_contract_dict(resp))


# --------------------------------------------------------------------------- #
# 2/7 — POST /api/v1/users (REQ-USR-F02)
# --------------------------------------------------------------------------- #
def test_post_users_matches_contract_REQ_USR_F02(client):
    """POST /api/v1/users 201 conforms to the User schema (REQ-USR-T01-AC3)."""
    resp = client.post(
        USERS,
        json={"first_name": "Alice", "last_name": "Rossi", "email": "a@example.com"},
    )
    assert resp.status_code == 201
    assert_matches_contract("user", "POST", USERS, flask_to_contract_dict(resp))


# --------------------------------------------------------------------------- #
# 3/7 — GET /api/v1/users (REQ-USR-F06)
# --------------------------------------------------------------------------- #
def test_get_users_list_matches_contract_REQ_USR_F06(client):
    """GET /api/v1/users 200 conforms to the UserPage schema (REQ-USR-T01-AC3)."""
    _create_user(client, email="list@example.com")
    resp = client.get(USERS)
    assert resp.status_code == 200
    assert_matches_contract("user", "GET", USERS, flask_to_contract_dict(resp))


# --------------------------------------------------------------------------- #
# 4/7 — GET /api/v1/users/<id> (REQ-USR-F05)
# --------------------------------------------------------------------------- #
def test_get_user_by_id_matches_contract_REQ_USR_F05(client):
    """GET /api/v1/users/<id> 200 conforms to the User schema (REQ-USR-T01-AC3)."""
    created = _create_user(client, email="byid@example.com")
    resp = client.get(f"{USERS}/{created['id']}")
    assert resp.status_code == 200
    assert_matches_contract(
        "user", "GET", f"{USERS}/{created['id']}", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 5/7 — PUT /api/v1/users/<id> (REQ-USR-F07)
# --------------------------------------------------------------------------- #
def test_put_user_matches_contract_REQ_USR_F07(client):
    """PUT /api/v1/users/<id> 200 conforms to the User schema (REQ-USR-T01-AC3)."""
    created = _create_user(client, email="put@example.com")
    resp = client.put(
        f"{USERS}/{created['id']}",
        json={"first_name": "New", "last_name": "Name", "email": "put2@example.com"},
    )
    assert resp.status_code == 200
    assert_matches_contract(
        "user", "PUT", f"{USERS}/{created['id']}", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 6/7 — PATCH /api/v1/users/<id> (REQ-USR-F08)
# --------------------------------------------------------------------------- #
def test_patch_user_matches_contract_REQ_USR_F08(client):
    """PATCH /api/v1/users/<id> 200 conforms to the User schema (REQ-USR-T01-AC3)."""
    created = _create_user(client, email="patch@example.com")
    resp = client.patch(
        f"{USERS}/{created['id']}", json={"first_name": "Patched"}
    )
    assert resp.status_code == 200
    assert_matches_contract(
        "user", "PATCH", f"{USERS}/{created['id']}", flask_to_contract_dict(resp)
    )


# --------------------------------------------------------------------------- #
# 7/7 — DELETE /api/v1/users/<id> (REQ-USR-F09)
# --------------------------------------------------------------------------- #
def test_delete_user_matches_contract_REQ_USR_F09(client):
    """DELETE /api/v1/users/<id> 204 (no body) conforms to the contract.

    REQ-USR-T01-AC3: the validator returns without error for a 204 because the
    contract declares no response body for that status (design.md §11).
    """
    created = _create_user(client, email="del@example.com")
    resp = client.delete(f"{USERS}/{created['id']}")
    assert resp.status_code == 204
    assert_matches_contract(
        "user", "DELETE", f"{USERS}/{created['id']}", flask_to_contract_dict(resp)
    )
