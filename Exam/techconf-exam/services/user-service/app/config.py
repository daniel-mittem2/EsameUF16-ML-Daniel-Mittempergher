"""Configuration loading for the user-service (REQ-USR-F13).

All environment variables are read exclusively in this module; no other
module may call ``os.environ`` directly (REQ-USR-F13-AC5).

Importing this module has **no side effects**: it does not read or validate
``PORT`` at import time. Reading ``PORT`` happens only inside
:func:`load_config`, so the ``app`` package can be imported for unit tests
without any environment variables set.
"""

from dataclasses import dataclass
from pathlib import Path
import os

__all__ = ["Config", "load_config"]


@dataclass
class Config:
    """Typed configuration values for the user-service.

    Attributes:
        port: TCP port the server listens on. Required only when the server
            is actually started (REQ-USR-F13-AC1/AC2).
        storage_backend: One of ``"memory"``, ``"json"`` or ``"sqlite"``;
            defaults to ``"memory"`` (REQ-USR-F13-AC3).
        data_dir: Directory for file-based persistence backends; defaults to
            ``Path("./data")`` (REQ-USR-F13-AC4).
    """

    port: int
    storage_backend: str
    data_dir: Path


# Module-level sentinel so that ``load_config(port=5001)`` bypasses the env
# read, while ``load_config()`` still requires PORT from the environment.
_SENTINEL = object()


def load_config(port=_SENTINEL) -> Config:
    """Build a :class:`Config` from environment variables.

    Reads ``PORT`` from the environment unless an explicit ``port`` argument
    is supplied. Raises :class:`ValueError` when ``PORT`` is absent or not an
    integer (REQ-USR-F13-AC1). ``STORAGE_BACKEND`` defaults to ``"memory"``
    (REQ-USR-F13-AC3) and ``DATA_DIR`` defaults to ``Path("./data")``
    (REQ-USR-F13-AC4).

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
    )
