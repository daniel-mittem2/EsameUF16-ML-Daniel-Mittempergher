"""Unit tests for ``app.config.load_config`` (T-13, REQ-REG-F12).

Covers the environment-driven configuration contract:

* ``PORT`` absent / non-integer            -> ValueError                (REQ-REG-F12-AC1)
* explicit ``port`` argument bypasses env   -> no env read               (REQ-REG-F12-AC1)
* ``STORAGE_BACKEND`` / ``DATA_DIR`` defaults                            (REQ-REG-F12-AC3)
* ``USER_SERVICE_URL`` / ``EVENT_SERVICE_URL`` defaults + overrides      (REQ-REG-F12-AC2)
* importing the ``app`` package never requires ``PORT``                  (REQ-REG-F12-AC5)

All environment variables are read exclusively in ``config.py`` (REQ-REG-F12-AC4);
``monkeypatch.delenv`` / ``setenv`` isolate each test from the ambient
environment.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.config import Config, load_config

_ENV_VARS = (
    "PORT",
    "STORAGE_BACKEND",
    "DATA_DIR",
    "USER_SERVICE_URL",
    "EVENT_SERVICE_URL",
)


@pytest.fixture()
def clean_env(monkeypatch):
    """Remove every configuration variable so each test starts from a blank slate."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# --------------------------------------------------------------------------- #
# PORT handling — REQ-REG-F12-AC1
# --------------------------------------------------------------------------- #
def test_load_config_without_port_raises_value_error_REQ_REG_F12(clean_env):
    """PORT absent from the environment → ValueError (REQ-REG-F12-AC1)."""
    with pytest.raises(ValueError):
        load_config()


def test_load_config_non_integer_port_raises_value_error_REQ_REG_F12(clean_env):
    """A non-integer PORT → ValueError (REQ-REG-F12-AC1)."""
    clean_env.setenv("PORT", "not-a-number")
    with pytest.raises(ValueError):
        load_config()


def test_load_config_reads_port_from_env_REQ_REG_F12(clean_env):
    """A valid PORT in the environment is parsed into an int (REQ-REG-F12-AC1)."""
    clean_env.setenv("PORT", "5003")
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.port == 5003


def test_load_config_explicit_port_bypasses_env_REQ_REG_F12(clean_env):
    """An explicit ``port`` argument builds a Config even without PORT in env."""
    cfg = load_config(port=6000)
    assert cfg.port == 6000


# --------------------------------------------------------------------------- #
# Defaults — REQ-REG-F12-AC2 / AC3
# --------------------------------------------------------------------------- #
def test_load_config_defaults_REQ_REG_F12(clean_env):
    """With only PORT set, the other values fall back to their documented defaults."""
    clean_env.setenv("PORT", "5003")
    cfg = load_config()
    assert cfg.storage_backend == "memory"
    assert cfg.data_dir == Path("./data")
    assert cfg.user_service_url == "http://localhost:5001"
    assert cfg.event_service_url == "http://localhost:5002"


def test_load_config_default_dependency_urls_REQ_REG_F12(clean_env):
    """The two dependency URLs default to localhost:5001 / :5002 (REQ-REG-F12-AC2)."""
    cfg = load_config(port=5003)
    assert cfg.user_service_url == "http://localhost:5001"
    assert cfg.event_service_url == "http://localhost:5002"


def test_load_config_reads_overrides_from_env_REQ_REG_F12(clean_env):
    """Every configuration variable is overridable via the environment."""
    clean_env.setenv("PORT", "5999")
    clean_env.setenv("STORAGE_BACKEND", "sqlite")
    clean_env.setenv("DATA_DIR", "/tmp/reg-data")
    clean_env.setenv("USER_SERVICE_URL", "http://user.internal:8001")
    clean_env.setenv("EVENT_SERVICE_URL", "http://event.internal:8002")

    cfg = load_config()

    assert cfg.port == 5999
    assert cfg.storage_backend == "sqlite"
    assert cfg.data_dir == Path("/tmp/reg-data")
    assert cfg.user_service_url == "http://user.internal:8001"
    assert cfg.event_service_url == "http://event.internal:8002"


# --------------------------------------------------------------------------- #
# Import without PORT — REQ-REG-F12-AC5
# --------------------------------------------------------------------------- #
def test_importing_app_package_does_not_require_port_REQ_REG_F12(clean_env):
    """Importing (and reloading) the ``app`` package never requires PORT.

    REQ-REG-F12-AC5: only ``load_config`` reads and validates PORT, so importing
    the package with no environment configured must succeed.
    """
    import app

    reloaded = importlib.reload(app)
    assert hasattr(reloaded, "create_app")
