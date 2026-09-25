"""Configuration loading for the registration-service (REQ-REG-F12).

All environment variables are read exclusively in this module; no other
module may call ``os.environ`` directly and no service URL is hard-coded
elsewhere (REQ-REG-F12-AC4).

The registration-service depends on **two** upstream services, so this module
resolves both ``USER_SERVICE_URL`` and ``EVENT_SERVICE_URL`` (REQ-REG-F12-AC2,
REQ-REG-B01/B02).

Importing this module has **no side effects**: it does not read or validate
``PORT`` at import time. Reading ``PORT`` happens only inside
:func:`load_config`, so the ``app`` package can be imported for unit tests
without any environment variables set (REQ-REG-F12-AC5).
"""

from dataclasses import dataclass
from pathlib import Path
import os

__all__ = ["Config", "load_config"]


@dataclass
class Config:
    """Typed configuration values for the registration-service.

    Attributes:
        port: TCP port the server listens on. Required only when the server
            is actually started (REQ-REG-F12-AC1).
        storage_backend: One of ``"memory"``, ``"json"`` or ``"sqlite"``;
            defaults to ``"memory"`` (REQ-REG-F12-AC3).
        data_dir: Directory for file-based persistence backends; defaults to
            ``Path("./data")`` (REQ-REG-F12-AC3).
        user_service_url: Base URL of the user-service dependency used to
            verify users; defaults to ``"http://localhost:5001"``
            (REQ-REG-F12-AC2, REQ-REG-B01).
        event_service_url: Base URL of the event-service dependency used to
            verify events, read status/price/capacity; defaults to
            ``"http://localhost:5002"`` (REQ-REG-F12-AC2, REQ-REG-B02).
    """

    port: int
    storage_backend: str
    data_dir: Path
    user_service_url: str
    event_service_url: str


# Module-level sentinel so that ``load_config(port=5003)`` bypasses the env
# read, while ``load_config()`` still requires PORT from the environment.
_SENTINEL = object()


def load_config(port=_SENTINEL) -> Config:
    """Build a :class:`Config` from environment variables.

    Reads ``PORT`` from the environment unless an explicit ``port`` argument
    is supplied. Raises :class:`ValueError` when ``PORT`` is absent or not an
    integer (REQ-REG-F12-AC1). ``STORAGE_BACKEND`` defaults to ``"memory"``
    and ``DATA_DIR`` defaults to ``Path("./data")`` (REQ-REG-F12-AC3).
    ``USER_SERVICE_URL`` defaults to ``"http://localhost:5001"`` and
    ``EVENT_SERVICE_URL`` defaults to ``"http://localhost:5002"``
    (REQ-REG-F12-AC2).

    Args:
        port: Optional explicit port. When provided, the ``PORT`` environment
            variable is not consulted. Useful for tests that construct a
            config without touching the environment.

    Returns:
        A populated :class:`Config` instance.

    Raises:
        ValueError: If ``PORT`` is neither supplied nor present in the
            environment, or if the resolved value is not a valid integer.
    """
    raw_port = port if port is not _SENTINEL else os.environ.get("PORT")
    if raw_port is None:
        raise ValueError("PORT environment variable is required to start the server")
    return Config(
        port=int(raw_port),
        storage_backend=os.environ.get("STORAGE_BACKEND", "memory"),
        data_dir=Path(os.environ.get("DATA_DIR", "./data")),
        user_service_url=os.environ.get("USER_SERVICE_URL", "http://localhost:5001"),
        event_service_url=os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002"),
    )
