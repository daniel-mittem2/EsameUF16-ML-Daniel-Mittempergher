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

This module will expose :func:`create_app`, the Flask application factory
(implemented in T-03). The complete registrations Blueprint
(``app.routes.registrations_bp``) is wired in T-12. This T-01 scaffold only
establishes the package structure; the modules are intentionally still stubs.
"""
from __future__ import annotations

__all__: list[str] = []
