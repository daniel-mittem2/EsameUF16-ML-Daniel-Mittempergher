"""HTTP client toward the user-service dependency.

Isolates the outbound call used to verify an event organizer
(REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05). The base URL comes from
``Config.user_service_url`` (read from ``USER_SERVICE_URL``, REQ-EVT-F13);
no URL is hard-coded here. All requests use a 2-second timeout.

Error mapping (consumed by the service layer via ``errors.py``):

* user-service ``404``              -> ``ReferenceNotFoundError``      -> 422 REFERENCE_NOT_FOUND
* ``200`` with ``role != organizer`` -> ``InvalidOrganizerError``       -> 422 INVALID_ORGANIZER
* timeout / connection refused /
  ``5xx`` / unexpected status         -> ``DependencyUnavailableError``  -> 503 DEPENDENCY_UNAVAILABLE
"""
import requests


class ReferenceNotFoundError(Exception):
    """The organizer_id does not reference any existing user (404)."""


class InvalidOrganizerError(Exception):
    """The referenced user exists but its role is not ``organizer``."""


class DependencyUnavailableError(Exception):
    """The user-service could not be reached or returned an unusable status."""


class UserServiceClient:
    """Thin HTTP client for the user-service ``GET /api/v1/users/{id}`` endpoint."""

    def __init__(self, base_url: str, timeout: float = 2.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get_user(self, user_id: str) -> dict:
        """Fetch a user by id, mapping transport/status failures to exceptions.

        REQ-EVT-B01, REQ-EVT-B05.
        """
        url = f"{self._base_url}/api/v1/users/{user_id}"
        try:
            resp = requests.get(url, timeout=self._timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if resp.status_code == 404:
            raise ReferenceNotFoundError(user_id)
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"user-service {resp.status_code}")
        if resp.status_code != 200:
            raise DependencyUnavailableError(f"unexpected {resp.status_code}")
        return resp.json()

    def verify_organizer(self, user_id: str) -> dict:
        """Verify existence (B01) and organizer role (B02) of ``user_id``.

        Returns the user object on success; raises the mapped exception otherwise.
        """
        user = self.get_user(user_id)
        if user.get("role") != "organizer":
            raise InvalidOrganizerError(user_id)
        return user
