"""Native desktop shell for Toyoko Tracker, powered by pywebview."""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import platform
import sys
import threading
import time
from pathlib import Path
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


_QT_WEBVIEW_LIBRARY: Any = None
_ARM64_QML = b"""
import QtQuick
import QtWebView

Item {
    width: 1280
    height: 820
    WebView {
        anchors.fill: parent
        url: appUrl
    }
}
"""


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


def _is_windows_arm64() -> bool:
    return sys.platform == "win32" and platform.machine().lower() in {"arm64", "aarch64"}


def _initialize_qt_webview() -> None:
    global _QT_WEBVIEW_LIBRARY
    import PySide6

    library_path = Path(PySide6.__file__).resolve().parent / "Qt6WebView.dll"
    _QT_WEBVIEW_LIBRARY = ctypes.WinDLL(str(library_path))
    initialize = getattr(_QT_WEBVIEW_LIBRARY, "?initialize@QtWebView@@YAXXZ")
    initialize.argtypes = []
    initialize.restype = None
    initialize()


def _wait_for_qml_component(qt_app: Any, component: Any, timeout: float = 15.0) -> None:
    """Let asynchronous QML imports finish before creating the root object."""
    deadline = time.monotonic() + timeout
    while component.isLoading() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)


def _start_windows_arm64_shell(url: str) -> None:
    from PySide6.QtCore import QSize, QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlComponent
    from PySide6.QtQuick import QQuickView

    _initialize_qt_webview()
    qt_app = QGuiApplication.instance() or QGuiApplication([APP_NAME])
    view = QQuickView()
    view.setTitle(APP_NAME)
    view.setMinimumSize(QSize(960, 640))
    view.resize(1280, 820)
    if getattr(sys, "frozen", False):
        view.setIcon(QIcon(sys.executable))
    view.rootContext().setContextProperty("appUrl", QUrl(url))
    component = QQmlComponent(view.engine())
    component.setData(_ARM64_QML, QUrl("inmemory:toyoko-arm64.qml"))
    _wait_for_qml_component(qt_app, component)
    root = component.create()
    if root is None:
        errors = "; ".join(error.toString() for error in component.errors())
        status = getattr(component.status(), "name", str(component.status()))
        detail = errors or "QML component did not become ready"
        raise RuntimeError(f"Windows ARM64 QtWebView shell failed ({status}): {detail}")
    view.setContent(QUrl("inmemory:toyoko-arm64.qml"), component, root)
    view.show()
    qt_app.exec()


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
        if _is_windows_arm64():
            _start_windows_arm64_shell(url)
        else:
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
