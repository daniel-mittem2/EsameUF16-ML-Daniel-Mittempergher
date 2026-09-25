"""Unit tests for the HTTP routes Blueprint (T-12).

Exercises every endpoint through the Flask test client, backed by an in-memory
repository. Covers the happy paths plus the error mappings required by
REQ-USR-F02..F12: 201/Location on create, pagination + filters on list, 404 on
missing resources, 409 on email conflicts, 422 on validation failures, 400 on
malformed JSON, 204 on delete and 405 on unsupported methods.
"""
import pytest

from app import create_app
from app.backends.memory import MemoryUserRepository

USERS = "/api/v1/users"


@pytest.fixture()
def client():
    """A Flask test client backed by a fresh in-memory repository."""
    return create_app(repo=MemoryUserRepository()).test_client()


def _valid_payload(**overrides):
    """A valid UserCreate body; keyword args override individual fields."""
    payload = {
        "first_name": "Alice",
        "last_name": "Rossi",
        "email": "alice@example.com",
    }
    payload.update(overrides)
    return payload


def _create(client, **overrides):
    """Create a user through the API and return the parsed response body."""
    resp = client.post(USERS, json=_valid_payload(**overrides))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# --- POST -------------------------------------------------------------------

def test_post_creates_user_201_location_and_body_REQ_USR_F02(client):
    """POST returns 201, a Location header and the User body (REQ-USR-F02-AC1)."""
    resp = client.post(USERS, json=_valid_payload())
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["first_name"] == "Alice"
    assert body["email"] == "alice@example.com"
    assert body["role"] == "attendee"  # default (REQ-USR-F02-AC5)
    assert body["company"] is None  # default null (REQ-USR-F02-AC6)
    assert resp.headers["Location"] == f"{USERS}/{body['id']}"


def test_post_normalises_email_lowercase_REQ_USR_B02(client):
    """POST stores and returns the email lower-cased (REQ-USR-B02-AC1)."""
    body = _create(client, email="Alice@Example.COM")
    assert body["email"] == "alice@example.com"


def test_post_duplicate_email_case_insensitive_409_REQ_USR_B01(client):
    """A second POST with the same email (different case) is 409 (REQ-USR-B01-AC1)."""
    _create(client, email="bob@example.com")
    resp = client.post(USERS, json=_valid_payload(email="BOB@EXAMPLE.COM"))
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_post_missing_required_field_422_REQ_USR_F03(client):
    """POST without a required field is 422 VALIDATION_ERROR (REQ-USR-F03-AC1)."""
    resp = client.post(USERS, json={"first_name": "A", "last_name": "B"})
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_array_body_is_422_REQ_USR_F03(client):
    """A JSON array body is not an object → 422 (REQ-USR-F03-AC9)."""
    resp = client.post(USERS, json=[])
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_wrong_type_no_coercion_422_REQ_USR_F03(client):
    """A field with the wrong type is 422 — no coercion (REQ-USR-F03-AC10)."""
    resp = client.post(
        USERS,
        json={"first_name": 123, "last_name": "B", "email": "c@d.com"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_unknown_field_422_REQ_USR_F03(client):
    """An unknown field (additionalProperties: false) is 422 (REQ-USR-F03-AC4)."""
    resp = client.post(USERS, json=_valid_payload(id="nope"))
    assert resp.status_code == 422


def test_post_malformed_json_is_400_REQ_USR_F03(client):
    """A syntactically broken JSON body is 400 MALFORMED_JSON (REQ-USR-F03-AC7)."""
    resp = client.post(
        USERS, data="{not json", content_type="application/json"
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"


# --- GET list ---------------------------------------------------------------

def test_list_defaults_page_and_page_size_REQ_USR_F06(client):
    """GET without params defaults to page=1, page_size=20 (REQ-USR-F06-AC1)."""
    _create(client, email="a@b.com")
    resp = client.get(USERS)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 1


def test_list_filter_role_and_total_REQ_USR_B03(client):
    """role filter narrows items; total counts filtered records (REQ-USR-B03)."""
    _create(client, email="a@b.com", role="organizer")
    _create(client, email="c@d.com", role="attendee")
    resp = client.get(f"{USERS}?role=organizer")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["role"] == "organizer"


def test_list_page_size_over_max_is_422_REQ_USR_F06(client):
    """page_size above 100 is 422 VALIDATION_ERROR (REQ-USR-F06-AC4)."""
    resp = client.get(f"{USERS}?page_size=101")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_page_non_numeric_is_422_REQ_USR_F06(client):
    """A non-numeric page is 422 VALIDATION_ERROR (REQ-USR-F06-AC6)."""
    resp = client.get(f"{USERS}?page=abc")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_invalid_role_filter_is_422_REQ_USR_B03(client):
    """An invalid role filter value is 422 VALIDATION_ERROR (REQ-USR-B03-AC5)."""
    resp = client.get(f"{USERS}?role=wizard")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET by id --------------------------------------------------------------

def test_get_by_id_returns_user_REQ_USR_F05(client):
    """GET /{id} on an existing user returns 200 with the User (REQ-USR-F05-AC1)."""
    created = _create(client, email="a@b.com")
    resp = client.get(f"{USERS}/{created['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["id"] == created["id"]


def test_get_missing_id_is_404_REQ_USR_F05(client):
    """GET /{id} for an unknown id is 404 NOT_FOUND (REQ-USR-F05-AC2)."""
    resp = client.get(f"{USERS}/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# --- PUT --------------------------------------------------------------------

def test_put_replaces_user_200_REQ_USR_F07(client):
    """PUT replaces the mutable fields and returns 200 (REQ-USR-F07-AC1)."""
    created = _create(client, email="a@b.com")
    resp = client.put(
        f"{USERS}/{created['id']}",
        json={"first_name": "New", "last_name": "Name", "email": "a@b.com"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["first_name"] == "New"
    assert body["created_at"] == created["created_at"]  # preserved


def test_put_missing_user_is_404_REQ_USR_F07(client):
    """PUT with a valid body on an unknown id is 404 NOT_FOUND (REQ-USR-F07-AC3)."""
    resp = client.put(
        f"{USERS}/missing",
        json={"first_name": "A", "last_name": "B", "email": "x@y.com"},
    )
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_put_email_of_other_user_is_409_REQ_USR_B01(client):
    """PUT to an email owned by a different user is 409 (REQ-USR-B01-AC2)."""
    _create(client, email="one@example.com")
    two = _create(client, email="two@example.com")
    resp = client.put(
        f"{USERS}/{two['id']}",
        json={"first_name": "A", "last_name": "B", "email": "one@example.com"},
    )
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_put_missing_required_field_is_422_REQ_USR_F07(client):
    """PUT missing a required field is 422 VALIDATION_ERROR (REQ-USR-F07-AC6)."""
    created = _create(client, email="a@b.com")
    resp = client.put(f"{USERS}/{created['id']}", json={"first_name": "Only"})
    assert resp.status_code == 422


# --- PATCH ------------------------------------------------------------------

def test_patch_updates_subset_200_REQ_USR_F08(client):
    """PATCH updates only the provided field and returns 200 (REQ-USR-F08-AC1)."""
    created = _create(client, email="a@b.com")
    resp = client.patch(f"{USERS}/{created['id']}", json={"first_name": "Zed"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["first_name"] == "Zed"
    assert body["last_name"] == created["last_name"]  # unchanged


def test_patch_empty_body_unchanged_200_REQ_USR_F08(client):
    """An empty PATCH returns 200 with the resource and timestamps intact (F04-AC4)."""
    created = _create(client, email="a@b.com")
    resp = client.patch(f"{USERS}/{created['id']}", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["updated_at"] == created["updated_at"]


def test_patch_missing_user_is_404_REQ_USR_F08(client):
    """PATCH on an unknown id is 404 NOT_FOUND (REQ-USR-F08-AC2)."""
    resp = client.patch(f"{USERS}/missing", json={"first_name": "X"})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_patch_unknown_field_is_422_REQ_USR_F04(client):
    """PATCH with an unknown field is 422 VALIDATION_ERROR (REQ-USR-F04-AC3)."""
    created = _create(client, email="a@b.com")
    resp = client.patch(f"{USERS}/{created['id']}", json={"nope": 1})
    assert resp.status_code == 422


# --- DELETE -----------------------------------------------------------------

def test_delete_returns_204_no_body_no_json_ct_REQ_USR_F09(client):
    """DELETE returns 204 with an empty body and no JSON Content-Type (F09/F12)."""
    created = _create(client, email="a@b.com")
    resp = client.delete(f"{USERS}/{created['id']}")
    assert resp.status_code == 204
    assert resp.get_data() == b""
    # No JSON Content-Type constraint on 204 (REQ-USR-F12-AC5/AC6).
    assert "application/json" not in resp.headers.get("Content-Type", "")


def test_delete_then_get_is_404_REQ_USR_F09(client):
    """After a DELETE the same id returns 404 on GET (REQ-USR-F09-AC3)."""
    created = _create(client, email="a@b.com")
    client.delete(f"{USERS}/{created['id']}")
    resp = client.get(f"{USERS}/{created['id']}")
    assert resp.status_code == 404


def test_delete_missing_user_is_404_REQ_USR_F09(client):
    """DELETE on an unknown id is 404 NOT_FOUND (REQ-USR-F09-AC2)."""
    resp = client.delete(f"{USERS}/missing")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# --- Method not allowed -----------------------------------------------------

def test_post_on_item_path_is_405_REQ_USR_F10(client):
    """POST /api/v1/users/<id> (undefined method on a defined path) is 405 (F10-AC1)."""
    resp = client.post(f"{USERS}/some-id", json={"first_name": "X"})
    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_delete_on_collection_path_is_405_REQ_USR_F10(client):
    """DELETE /api/v1/users (undefined method on the collection) is 405 (F10-AC1)."""
    resp = client.delete(USERS)
    assert resp.status_code == 405
    assert resp.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"
