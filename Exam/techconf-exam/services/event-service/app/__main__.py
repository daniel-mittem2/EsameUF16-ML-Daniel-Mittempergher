"""Entry point for ``python -m app`` (REQ-EVT-F13).

Scaffold stub for T-01. The real entry point is implemented in T-03: it will
read configuration through :func:`app.config.load_config` (which validates and
returns ``PORT``, raising ``ValueError`` when absent), build the application via
``create_app(config=cfg)`` and start the server on ``0.0.0.0:<PORT>``.

``PORT`` is never read directly from ``os.environ`` here (REQ-EVT-F13-AC4).
"""
from __future__ import annotations

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(
        "event-service entry point not implemented yet (see task T-03)"
    )
