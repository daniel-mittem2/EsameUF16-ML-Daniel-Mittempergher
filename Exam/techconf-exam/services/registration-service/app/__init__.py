"""registration-service application package.

Flask-based microservice that manages attendee registrations to TechConf
events. It is the most connected mandatory service: it calls **two**
dependencies over HTTP — user-service (to validate ``user_id``, REQ-REG-B01)
and event-service (to validate ``event_id`` and read ``status``/``price``/
``capacity``, REQ-REG-B02/B03/B05/B06) — via ``app.http_client``.

Importing this package MUST succeed without requiring the ``PORT`` environment
variable (REQ-REG-F12-AC5), so that unit tests can import ``app`` without any
environment configuration. Only :func:`app.config.load_config` (invoked from
``app/__main__.py``) reads and validates ``PORT``.

This module exposes :func:`create_app`, the Flask application factory. In T-03
the factory registers ``GET /health`` (REQ-REG-F01) and the standard 400/404/405
error handlers (REQ-REG-F09, REQ-REG-F11), and wires the storage repository and
the two dependency HTTP clients (user + event) into ``app.config`` so later
tasks can build the ``RegistrationService`` on top of them. The complete
registrations Blueprint (``app.routes.registrations_bp``) is registered in T-12;
it is intentionally not wired here yet.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify

from app import errors
from app.http_client import EventServiceClient, UserServiceClient
from app.repository import AbstractRegistrationRepository, get_repository

__all__ = ["create_app"]

# Defaults mirrored from ``app.config`` so that ``create_app`` can build its
# collaborators even when no :class:`app.config.Config` is supplied (e.g. unit
# tests that inject a repository and the two clients directly). These are the
# only environment reads outside ``config.py``, and they exist solely as a
# fallback for the injected-dependency test path; production always passes
# ``config`` (REQ-REG-F12-AC4).
_DEFAULT_STORAGE_BACKEND = "memory"
_DEFAULT_DATA_DIR = "./data"
_DEFAULT_USER_SERVICE_URL = "http://localhost:5001"
_DEFAULT_EVENT_SERVICE_URL = "http://localhost:5002"
_DEPENDENCY_TIMEOUT = 2.0


def _register_health(app: Flask) -> None:
    """Register ``GET /health`` (REQ-REG-F01).

    Responds 200 with the exact body ``{"status": "ok", "service":
    "registration-service"}`` conforming to the ``Health`` schema
    (REQ-REG-F01-AC1/AC2). The handler performs no persistence and no outbound
    HTTP call, so it answers regardless of storage backend state or the
    availability of the user-service and event-service dependencies
    (REQ-REG-F01-AC4). Only GET is bound, so any other method yields a 405
    handled by the error handlers (REQ-REG-F01-AC3, REQ-REG-F09).
    """

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "registration-service"}), 200


def _register_error_handlers(app: Flask) -> None:
    """Register 400/404/405 handlers producing the standard ``Error`` body.

    Guarantees that malformed JSON (400), unknown paths (404) and unsupported
    methods (405) all return ``{"error": {"code": ..., "message": ...,
    "details": {}}}`` (REQ-REG-F09, REQ-REG-F11). Flask emits these HTTP errors
    automatically; the handlers only reshape them into the contract format with
    ``details`` set to an empty object (REQ-REG-F11-AC4).
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
    repo: Optional[AbstractRegistrationRepository] = None,
    config=None,
    user_client: Optional[UserServiceClient] = None,
    event_client: Optional[EventServiceClient] = None,
) -> Flask:
    """Build and configure the Flask application (REQ-REG-F12).

    The factory accepts four optional collaborators so it can be driven both in
    production and in unit tests:

    * ``repo`` — an :class:`app.repository.AbstractRegistrationRepository`. When
      ``None`` it is built via ``get_repository(config.storage_backend,
      config.data_dir)`` (falling back to safe defaults when ``config`` is not
      supplied).
    * ``config`` — an :class:`app.config.Config` supplied in production
      (``create_app(config=load_config())``).
    * ``user_client`` — a :class:`app.http_client.UserServiceClient`. When
      ``None`` it is built from ``config.user_service_url`` (or the default URL)
      with the standard 2-second timeout (REQ-REG-B01-AC2).
    * ``event_client`` — a :class:`app.http_client.EventServiceClient`. When
      ``None`` it is built from ``config.event_service_url`` (or the default URL)
      with the standard 2-second timeout (REQ-REG-B02-AC2).

    Importing the package or calling this factory never requires ``PORT`` to be
    set: only :func:`app.config.load_config` reads and validates ``PORT``
    (REQ-REG-F12-AC5).

    The collaborators are stored under ``app.config`` (``REPO``, ``USER_CLIENT``,
    ``EVENT_CLIENT``) so the ``RegistrationService`` and the registrations
    Blueprint wired in later tasks (T-09..T-12) can retrieve them. The complete
    Blueprint is registered in T-12; this T-03 factory only exposes ``/health``
    and the standard error handlers.

    Args:
        repo: Optional repository instance to inject (used by tests).
        config: Optional :class:`app.config.Config` selecting the storage
            backend, data directory and the two dependency URLs when the
            corresponding collaborator is not injected.
        user_client: Optional user-service HTTP client to inject (used by tests
            together with the ``responses`` library).
        event_client: Optional event-service HTTP client to inject (used by
            tests together with the ``responses`` library).

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
        user_base_url = (
            config.user_service_url
            if config is not None
            else os.environ.get("USER_SERVICE_URL", _DEFAULT_USER_SERVICE_URL)
        )
        user_client = UserServiceClient(user_base_url, timeout=_DEPENDENCY_TIMEOUT)

    if event_client is None:
        event_base_url = (
            config.event_service_url
            if config is not None
            else os.environ.get("EVENT_SERVICE_URL", _DEFAULT_EVENT_SERVICE_URL)
        )
        event_client = EventServiceClient(event_base_url, timeout=_DEPENDENCY_TIMEOUT)

    app.config["REPO"] = repo
    app.config["USER_CLIENT"] = user_client
    app.config["EVENT_CLIENT"] = event_client

    _register_health(app)
    # T-12: register the complete registrations Blueprint
    # (``app.routes.registrations_bp``) here.
    _register_error_handlers(app)

    return app
