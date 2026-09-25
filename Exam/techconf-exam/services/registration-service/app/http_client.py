"""HTTP clients toward the user-service and event-service dependencies.

The registration-service is the most connected mandatory service: it calls
**both** dependencies over HTTP to validate a registration
(REQ-REG-B01, REQ-REG-B02, REQ-REG-B09). Base URLs come from
``Config.user_service_url`` / ``Config.event_service_url`` (read from
``USER_SERVICE_URL`` / ``EVENT_SERVICE_URL`` in ``config.py``, REQ-REG-F12);
no URL is hard-coded here. Every request uses a **2-second** timeout
(REQ-REG-B01-AC2, REQ-REG-B02-AC2).

Error mapping (consumed by the service layer via ``errors.py``):

* dependency ``404``                 -> ``ReferenceNotFoundError``     -> 422 REFERENCE_NOT_FOUND
* timeout / connection refused /
  ``5xx`` / unexpected status         -> ``DependencyUnavailableError`` -> 503 DEPENDENCY_UNAVAILABLE

Business rules that depend on the *content* of the event object
(``status == published`` -> EVENT_NOT_OPEN, ``price`` -> amount,
``capacity`` -> EVENT_FULL) live in ``service.py``, not here: the client only
returns the parsed dependency object and maps transport/status failures.
"""
import requests


class ReferenceNotFoundError(Exception):
    """The referenced id does not exist in the dependency (404).

    Mapped by the service layer to 422 ``REFERENCE_NOT_FOUND``
    (REQ-REG-B01-AC3, REQ-REG-B02-AC3).
    """


class DependencyUnavailableError(Exception):
    """A dependency could not be reached or returned an unusable status.

    Raised on timeout, refused connection, ``5xx`` or any unexpected status;
    mapped by the service layer to 503 ``DEPENDENCY_UNAVAILABLE``
    (REQ-REG-B09).
    """


class _BaseClient:
    """Shared HTTP plumbing for the dependency clients.

    Normalizes the base URL (strips a trailing slash) and performs the single
    outbound ``GET`` with the mandated 2-second timeout, translating transport
    and status failures into the two domain exceptions above.
    """

    def __init__(self, base_url: str, timeout: float = 2.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _get(self, path: str) -> dict:
        """Issue ``GET base_url + path`` and map failures to exceptions.

        * ``404``                         -> ``ReferenceNotFoundError``
        * ``5xx`` / non-200 status        -> ``DependencyUnavailableError``
        * ``Timeout`` / ``ConnectionError`` -> ``DependencyUnavailableError``
        """
        url = f"{self._base_url}{path}"
        try:
            resp = requests.get(url, timeout=self._timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise DependencyUnavailableError(str(exc)) from exc
        if resp.status_code == 404:
            raise ReferenceNotFoundError(path)
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"dependency {resp.status_code}")
        if resp.status_code != 200:
            raise DependencyUnavailableError(f"unexpected {resp.status_code}")
        return resp.json()


class UserServiceClient(_BaseClient):
    """Thin client for user-service ``GET /api/v1/users/{id}`` (REQ-REG-B01)."""

    def get_user(self, user_id: str) -> dict:
        """Fetch a user by id; raises on 404 / unavailable dependency."""
        return self._get(f"/api/v1/users/{user_id}")


class EventServiceClient(_BaseClient):
    """Thin client for event-service ``GET /api/v1/events/{id}`` (REQ-REG-B02).

    The returned object carries ``status``, ``price`` and ``capacity`` used by
    the service to enforce REQ-REG-B03/B05/B06.
    """

    def get_event(self, event_id: str) -> dict:
        """Fetch an event by id; raises on 404 / unavailable dependency."""
        return self._get(f"/api/v1/events/{event_id}")
