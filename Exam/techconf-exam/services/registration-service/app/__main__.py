"""Entry point for ``python -m app`` (REQ-REG-F12).

Configuration is read through :func:`app.config.load_config`, which validates
and returns ``PORT`` (raising ``ValueError`` if it is absent). ``PORT`` is never
read directly here. The server listens on ``0.0.0.0:<PORT>``.

Windows development launch::

    $env:PORT="5003"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; py -3.12 -m app

This is a T-01 stub: the application factory and configuration loader are
implemented in later tasks (T-02, T-03).
"""
from __future__ import annotations

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(
        "registration-service entry point is not implemented yet (see T-02/T-03)"
    )
