"""Unit tests for ``app.config`` — configuration loading (REQ-EVT-F13, T-13).

All environment variables are read exclusively in ``app.config`` (REQ-EVT-F13-AC4).
These tests exercise :func:`app.config.load_config` in isolation:

* ``PORT`` absent          -> ``ValueError``                        (REQ-EVT-F13-AC1)
* ``PORT`` not an integer  -> ``ValueError``                        (REQ-EVT-F13-AC1)
* explicit ``port`` arg    -> bypasses the environment              (REQ-EVT-F13-AC1)
* defaults                 -> memory / ./data / localhost:5001      (REQ-EVT-F13-AC2/AC3)
* overrides                -> env values are honoured               (REQ-EVT-F13-AC2/AC3)
* importing ``app`` needs no ``PORT``                               (REQ-EVT-F13-AC5)

Each test cleans the four environment variables it touches so that the process
environment cannot leak between cases (``monkeypatch.delenv`` / ``setenv``).
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app import config as config_module
from app.config import Config, load_config

_ENV_VARS = ("PORT", "STORAGE_BACKEND", "DATA_DIR", "USER_SERVICE_URL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove all config env vars so each test starts from a known clean state."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


# --------------------------------------------------------------------------- #
# PORT handling — REQ-EVT-F13-AC1
# --------------------------------------------------------------------------- #
def test_load_config_without_port_raises_value_error():
    """REQ-EVT-F13-AC1: load_config() with no PORT in the env raises ValueError."""
    with pytest.raises(ValueError):
        load_config()


def test_load_config_non_integer_port_raises_value_error(monkeypatch):
    """REQ-EVT-F13-AC1: a non-integer PORT is rejected with ValueError."""
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(ValueError):
        load_config()


def test_load_config_reads_port_from_environment(monkeypatch):
    """REQ-EVT-F13-AC1: PORT is read from the environment and coerced to int."""
    monkeypatch.setenv("PORT", "5002")
    cfg = load_config()
    assert cfg.port == 5002
    assert isinstance(cfg.port, int)


def test_load_config_explicit_port_bypasses_environment():
    """REQ-EVT-F13-AC1: an explicit port argument works without PORT in the env."""
    cfg = load_config(port=5002)
    assert cfg.port == 5002


def test_load_config_explicit_port_takes_precedence_over_env(monkeypatch):
    """REQ-EVT-F13-AC1: an explicit port argument overrides the PORT env var."""
    monkeypatch.setenv("PORT", "9999")
    cfg = load_config(port=5002)
    assert cfg.port == 5002


# --------------------------------------------------------------------------- #
# defaults — REQ-EVT-F13-AC2/AC3
# --------------------------------------------------------------------------- #
def test_load_config_defaults_when_optional_env_absent():
    """REQ-EVT-F13-AC2/AC3: optional settings fall back to their documented defaults."""
    cfg = load_config(port=5002)
    assert cfg.storage_backend == "memory"
    assert cfg.data_dir == Path("./data")
    assert cfg.user_service_url == "http://localhost:5001"


def test_load_config_returns_config_dataclass():
    """REQ-EVT-F13: load_config returns a fully-populated Config instance."""
    cfg = load_config(port=5002)
    assert isinstance(cfg, Config)


# --------------------------------------------------------------------------- #
# overrides — REQ-EVT-F13-AC2/AC3
# --------------------------------------------------------------------------- #
def test_load_config_honours_storage_backend_override(monkeypatch):
    """REQ-EVT-F13-AC3: STORAGE_BACKEND from the env is honoured."""
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    cfg = load_config(port=5002)
    assert cfg.storage_backend == "sqlite"


def test_load_config_honours_data_dir_override(monkeypatch):
    """REQ-EVT-F13-AC3: DATA_DIR from the env is honoured as a Path."""
    monkeypatch.setenv("DATA_DIR", "/tmp/events-data")
    cfg = load_config(port=5002)
    assert cfg.data_dir == Path("/tmp/events-data")


def test_load_config_honours_user_service_url_override(monkeypatch):
    """REQ-EVT-F13-AC2: USER_SERVICE_URL from the env is honoured."""
    monkeypatch.setenv("USER_SERVICE_URL", "http://user-service.internal:8080")
    cfg = load_config(port=5002)
    assert cfg.user_service_url == "http://user-service.internal:8080"


# --------------------------------------------------------------------------- #
# import without PORT — REQ-EVT-F13-AC5
# --------------------------------------------------------------------------- #
def test_importing_app_package_does_not_require_port():
    """REQ-EVT-F13-AC5: importing the app package succeeds without PORT set."""
    import app  # noqa: F401 - the import itself is the assertion

    reloaded = importlib.import_module("app")
    assert reloaded is not None


def test_importing_config_module_has_no_side_effects():
    """REQ-EVT-F13-AC4/AC5: re-importing app.config does not read/validate PORT."""
    reloaded = importlib.reload(config_module)
    assert hasattr(reloaded, "load_config")
    assert hasattr(reloaded, "Config")
