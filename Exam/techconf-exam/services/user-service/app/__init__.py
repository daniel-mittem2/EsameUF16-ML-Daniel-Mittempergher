"""user-service application package.

Flask-based microservice for TechConf user management.
Import of this package must succeed without requiring the PORT
environment variable (see REQ-USR-F13).

This module exposes :func:`create_app`, the Flask application factory. In this
task (T-03) the factory registers only the ``GET /health`` endpoint and the
standard error handlers (400/404/405). The complete users Blueprint is
registered in a later task (T-12), once the service layer exists.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify

from app import errors
from app.repository import AbstractUserRepository, get_repository

__all__ = ["create_app"]


def _register_health(app: Flask) -> None:
    """Register ``GET /health`` (REQ-USR-F01).

    Responds 200 with the exact body ``{"status": "ok", "service":
    "user-service"}`` conforming to the ``Health`` schema. The handler has no
    dependency on the storage backend (REQ-USR-F01-AC4). Only GET is bound to
    the route, so any other method yields a 405 handled by the error handlers
    (REQ-USR-F01-AC3, REQ-USR-F10).
    """

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "user-service"}), 200


def _register_error_handlers(app: Flask) -> None:
    """Register 400/404/405 handlers producing the standard ``Error`` body.

    Guarantees that malformed JSON (400), unknown paths (404) and unsupported
    methods (405) all return ``{"error": {"code": ..., "message": ...,
    "details": {}}}`` (REQ-USR-F10, REQ-USR-F12). Flask emits these HTTP errors
    automatically; the handlers only reshape them into the contract format.
    """

    @app.errorhandler(400)
    def bad_request(e):
        return errors.make_error_response(
            errors.MALFORMED_JSON, "Malformed request body", status=400
        )

    @app.errorhandler(404)
    def not_found(e):
        return errors.make_error_response(
            errors.NOT_FOUND, "Resource not found", status=404
        )

    @app.errorhandler(405)
    def method_not_allowed(e):
        return errors.make_error_response(
            errors.METHOD_NOT_ALLOWED, "Method not allowed", status=405
        )


def create_app(
    repo: Optional[AbstractUserRepository] = None,
    config=None,
) -> Flask:
    """Build and configure the Flask application (REQ-USR-F13).

    The factory accepts an optional ``repo`` (injected by unit tests) and an
    optional ``config`` (a :class:`app.config.Config`, supplied in production).
    Importing the package or calling this factory never requires ``PORT`` to be
    set: only :func:`app.config.load_config` reads and validates ``PORT``.

    When ``repo`` is ``None`` the repository is built from the configuration —
    from ``config`` when provided, otherwise from safe defaults
    (``STORAGE_BACKEND`` defaulting to ``memory``, ``DATA_DIR`` to ``./data``).

    Args:
        repo: Optional repository instance to inject (used by tests).
        config: Optional :class:`app.config.Config` used to select the storage
            backend and data directory when ``repo`` is not supplied.

    Returns:
        A configured :class:`flask.Flask` application.
    """
    app = Flask(__name__)

    if repo is None:
        backend = (
            config.storage_backend
            if config is not None
            else os.environ.get("STORAGE_BACKEND", "memory")
        )
        data_dir = (
            config.data_dir
            if config is not None
            else Path(os.environ.get("DATA_DIR", "./data"))
        )
        repo = get_repository(backend, data_dir)

    app.config["REPO"] = repo

    _register_health(app)
    _register_error_handlers(app)

    return app
