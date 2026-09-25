"""Entry point for ``python -m app`` (REQ-USR-F13).

Reads configuration through :func:`app.config.load_config`, which validates and
returns ``PORT`` (raising ``ValueError`` if it is absent). The port is never
read directly from ``os.environ`` here (REQ-USR-F13-AC6). The server listens on
``0.0.0.0:<PORT>`` (REQ-USR-F13-AC2).
"""
from app import create_app
from app.config import load_config

cfg = load_config()  # validates PORT here; explicit error if missing
application = create_app(config=cfg)

if __name__ == "__main__":  # pragma: no cover
    application.run(host="0.0.0.0", port=cfg.port, debug=False)
