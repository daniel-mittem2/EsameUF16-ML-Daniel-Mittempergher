"""event-service application package.

Flask-based microservice for TechConf event (conference) management.

Importing this package MUST succeed without requiring the ``PORT`` environment
variable (see REQ-EVT-F13-AC5), so that unit tests can import ``app`` without
any environment configuration. Only :func:`app.config.load_config` (invoked
from ``app/__main__.py``) reads and validates ``PORT``.

Unlike user-service, event-service calls another microservice: it verifies the
organizer (``organizer_id``) against user-service over HTTP via
``app.http_client`` (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).

This module exposes :func:`create_app`, the Flask application factory. In T-03
the factory registers ``GET /health`` (REQ-EVT-F01) and the standard 400/404/405
error handlers (REQ-EVT-F10, REQ-EVT-F12). The complete events Blueprint
(``app.routes.events_bp``) is registered in T-12; it is intentionally not wired
here yet.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify

from app import errors
from app.http_client import UserServiceClient
from app.repository import AbstractEventRepository, get_repository

__all__ = ["create_app"]

# Defaults mirrored from ``app.config`` so that ``create_app`` can build its
# collaborators even when no :class:`app.config.Config` is supplied (e.g. unit
# tests that inject a repository and user client directly). These are the only
# environment reads outside ``config.py``, and they exist solely as a fallback
# for the injected-dependency test path; production always passes ``config``.
_DEFAULT_STORAGE_BACKEND = "memory"
_DEFAULT_DATA_DIR = "./data"
_DEFAULT_USER_SERVICE_URL = "http://localhost:5001"
_USER_SERVICE_TIMEOUT = 2.0


def _register_health(app: Flask) -> None:
    """Register ``GET /health`` (REQ-EVT-F01).

    Responds 200 with the exact body ``{"status": "ok", "service":
    "event-service"}`` conforming to the ``Health`` schema (REQ-EVT-F01-AC1/AC2).
    The handler performs no persistence and no outbound HTTP call, so it answers
    regardless of storage backend state or user-service availability
    (REQ-EVT-F01-AC4). Only GET is bound, so any other method yields a 405
    handled by the error handlers (REQ-EVT-F01-AC3, REQ-EVT-F10).
    """

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "event-service"}), 200


def _register_error_handlers(app: Flask) -> None:
    """Register 400/404/405 handlers producing the standard ``Error`` body.

    Guarantees that malformed JSON (400), unknown paths (404) and unsupported
    methods (405) all return ``{"error": {"code": ..., "message": ...,
    "details": {}}}`` (REQ-EVT-F10, REQ-EVT-F12). Flask emits these HTTP errors
    automatically; the handlers only reshape them into the contract format with
    ``details`` set to an empty object.
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
    repo: Optional[AbstractEventRepository] = None,
    config=None,
    user_client: Optional[UserServiceClient] = None,
) -> Flask:
    """Build and configure the Flask application (REQ-EVT-F13).

    The factory accepts three optional collaborators so it can be driven both in
    production and in unit tests:

    * ``repo`` — an :class:`app.repository.AbstractEventRepository`. When
      ``None`` it is built via ``get_repository(config.storage_backend,
      config.data_dir)`` (falling back to safe defaults when ``config`` is not
      supplied).
    * ``config`` — an :class:`app.config.Config` supplied in production
      (``create_app(config=load_config())``).
    * ``user_client`` — a :class:`app.http_client.UserServiceClient`. When
      ``None`` it is built from ``config.user_service_url`` (or the default URL)
      with the standard 2-second timeout (REQ-EVT-B01-AC2).

    Importing the package or calling this factory never requires ``PORT`` to be
    set: only :func:`app.config.load_config` reads and validates ``PORT``
    (REQ-EVT-F13-AC5).

    Args:
        repo: Optional repository instance to inject (used by tests).
        config: Optional :class:`app.config.Config` selecting the storage
            backend, data directory and user-service URL when the corresponding
            collaborator is not injected.
        user_client: Optional user-service HTTP client to inject (used by tests
            together with the ``responses`` library).

    Returns:
        A configured :class:`flask.Flask` application.
    """
    app = Flask(__name__)

    if repo is None:
        backend = (
            config.storage_backend
            if config is not None
            else os.environ.get("STORAGE_BACKEND", _DEFAULT_STORAGE_BACKEND)
        )
        data_dir = (
            config.data_dir
            if config is not None
            else Path(os.environ.get("DATA_DIR", _DEFAULT_DATA_DIR))
        )
        repo = get_repository(backend, data_dir)

    if user_client is None:
        base_url = (
            config.user_service_url
            if config is not None
            else os.environ.get("USER_SERVICE_URL", _DEFAULT_USER_SERVICE_URL)
        )
        user_client = UserServiceClient(base_url, timeout=_USER_SERVICE_TIMEOUT)

    app.config["REPO"] = repo
    app.config["USER_CLIENT"] = user_client

    _register_health(app)
    # NOTE: the events Blueprint (app.routes.events_bp) is registered in T-12.
    _register_error_handlers(app)

    return app
