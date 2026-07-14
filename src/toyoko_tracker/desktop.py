"""Native desktop shell for Toyoko Tracker, powered by pywebview."""

from __future__ import annotations

import argparse
import logging
import os
import threading
from typing import Any

from werkzeug.serving import BaseWSGIServer, make_server

from . import runtime
from .app import app
from .server import (
    _cleanup_instance_state,
    initialize_runtime,
    stop_runtime_services,
    write_instance_state,
)
from .settings import APP_NAME


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} desktop application")
    access = parser.add_mutually_exclusive_group()
    access.add_argument("--lan", action="store_true", help="enable authenticated LAN/mobile access")
    access.add_argument("--local-only", action="store_true", help="disable LAN/mobile access")
    parser.add_argument("--port", type=int, default=4170, help="preferred local server port")
    parser.add_argument("--debug", action="store_true", help="enable pywebview debug tools")
    return parser


def _serve(server: BaseWSGIServer) -> None:
    server.serve_forever()


def main(argv: Any = None) -> None:
    args = _parser().parse_args(argv)
    os.environ["TOYOKO_TRACKER_FRONTEND"] = "desktop"
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    access_override = True if args.lan else False if args.local_only else None
    lan_enabled = initialize_runtime(access_override)
    host = "0.0.0.0" if lan_enabled else "127.0.0.1"
    preferred_port = max(1, min(65535, int(args.port)))
    port = runtime._find_free_port(preferred_port, host=host)
    server = make_server(host, port, app, threaded=True)
    url = f"http://127.0.0.1:{port}"
    app.config["TOYOKO_LAN_BOUND"] = lan_enabled
    app.config["TOYOKO_SERVER_PORT"] = port
    write_instance_state(url, port, lan_enabled)

    thread = threading.Thread(target=_serve, args=(server,), name="toyoko-web", daemon=True)
    thread.start()
    try:
        try:
            import webview
        except ImportError as exc:
            raise SystemExit(
                'pywebview is required; install with: pip install "toyoko-tracker[desktop]"'
            ) from exc
        webview.create_window(
            APP_NAME,
            url,
            width=1280,
            height=820,
            min_size=(960, 640),
            text_select=True,
        )
        webview.start(debug=bool(args.debug))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        stop_runtime_services()
        _cleanup_instance_state()


if __name__ == "__main__":
    main()
