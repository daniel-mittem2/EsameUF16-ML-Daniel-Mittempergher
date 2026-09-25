"""Unit tests for configuration loading (T-13, REQ-USR-F13).

Covers:
- ``load_config()`` without ``PORT`` raises ``ValueError`` (REQ-USR-F13-AC1).
- ``STORAGE_BACKEND`` defaults to ``"memory"`` (REQ-USR-F13-AC3).
- ``DATA_DIR`` defaults to ``Path("./data")`` (REQ-USR-F13-AC4).
- Importing the ``app`` package (and ``app.config``) has no side effects and
  does NOT require ``PORT`` to be set (design.md §3: import must not read PORT).
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.config import Config, load_config


# --------------------------------------------------------------------------- #
# PORT is required at load time (REQ-USR-F13-AC1)
# --------------------------------------------------------------------------- #
def test_load_config_without_port_raises_value_error_REQ_USR_F13(monkeypatch):
    """load_config() with no PORT in the environment raises ValueError."""
    monkeypatch.delenv("PORT", raising=False)
    with pytest.raises(ValueError):
        load_config()


def test_load_config_invalid_port_raises_value_error_REQ_USR_F13(monkeypatch):
    """A non-integer PORT value raises ValueError (int() conversion fails)."""
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(ValueError):
        load_config()


def test_load_config_explicit_port_argument_bypasses_env_REQ_USR_F13(monkeypatch):
    """An explicit port argument is used without consulting the environment."""
    monkeypatch.delenv("PORT", raising=False)
    cfg = load_config(port=5001)
    assert isinstance(cfg, Config)
    assert cfg.port == 5001


# --------------------------------------------------------------------------- #
# Defaults for STORAGE_BACKEND and DATA_DIR (REQ-USR-F13-AC3/AC4)
# --------------------------------------------------------------------------- #
def test_load_config_defaults_backend_and_data_dir_REQ_USR_F13(monkeypatch):
    """With PORT set but no other vars, backend defaults to memory and
    data_dir to ./data (REQ-USR-F13-AC3/AC4)."""
    monkeypatch.setenv("PORT", "5002")
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    cfg = load_config()
    assert cfg.port == 5002
    assert cfg.storage_backend == "memory"
    assert cfg.data_dir == Path("./data")


def test_load_config_reads_explicit_backend_and_data_dir_REQ_USR_F13(monkeypatch):
    """Explicit STORAGE_BACKEND and DATA_DIR env vars override the defaults."""
    monkeypatch.setenv("PORT", "5003")
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATA_DIR", "/tmp/techconf-data")
    cfg = load_config()
    assert cfg.storage_backend == "sqlite"
    assert cfg.data_dir == Path("/tmp/techconf-data")


# --------------------------------------------------------------------------- #
# Importing the package must not require PORT (design.md §3)
# --------------------------------------------------------------------------- #
def test_importing_app_does_not_require_port_REQ_USR_F13(monkeypatch):
    """Re-importing the app package with PORT unset must not raise.

    The import of ``app`` and ``app.config`` has no side effects; PORT is only
    read inside load_config(), so unit tests can import the service without any
    environment variables (REQ-USR-F13-AC1 rationale, design.md §3).
    """
    monkeypatch.delenv("PORT", raising=False)
    import app as app_pkg
    import app.config as app_config

    # Reloading must not read or validate PORT.
    importlib.reload(app_config)
    importlib.reload(app_pkg)
    assert hasattr(app_pkg, "create_app")
