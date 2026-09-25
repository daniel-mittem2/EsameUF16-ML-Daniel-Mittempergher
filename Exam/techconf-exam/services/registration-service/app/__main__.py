"""Entry point for ``python -m app`` (REQ-REG-F12).

Configuration is read through :func:`app.config.load_config`, which validates
and returns ``PORT`` (raising ``ValueError`` if it is absent, REQ-REG-F12-AC1).
``PORT`` is never read directly from ``os.environ`` here (REQ-REG-F12-AC4). The
server listens on ``0.0.0.0:<PORT>``.

Windows development launch::

    $env:PORT="5003"; $env:USER_SERVICE_URL="http://localhost:5001"; $env:EVENT_SERVICE_URL="http://localhost:5002"; py -3.12 -m app
"""
from app import create_app
from app.config import load_config

cfg = load_config()  # validates PORT here; explicit error if missing
application = create_app(config=cfg)

if __name__ == "__main__":  # pragma: no cover
    application.run(host="0.0.0.0", port=cfg.port, debug=False)
