"""event-service application package.

Flask-based microservice for TechConf event (conference) management.

Importing this package MUST succeed without requiring the ``PORT`` environment
variable (see REQ-EVT-F13-AC5), so that unit tests can import ``app`` without
any environment configuration. Only :func:`app.config.load_config` (invoked
from ``app/__main__.py``) reads and validates ``PORT``.

Unlike user-service, event-service calls another microservice: it verifies the
organizer (``organizer_id``) against user-service over HTTP via
``app.http_client`` (REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05).

The Flask application factory :func:`create_app` and the ``/health`` endpoint
are introduced in T-03; this module is a docstring-only scaffold for T-01.
"""
from __future__ import annotations
