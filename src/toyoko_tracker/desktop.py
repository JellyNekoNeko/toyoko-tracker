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

import requests
from werkzeug.serving import BaseWSGIServer, make_server

from . import runtime
from .app import app
from .desktop_lifecycle import (
    DesktopLifecycleController,
    deep_link_to_local_url,
    forward_deep_link_to_running,
)
from .server import (
    _cleanup_instance_state,
    initialize_runtime,
    stop_runtime_services,
    write_instance_state,
)
from .settings import APP_NAME


_QT_WEBVIEW_LIBRARY: Any = None
_MAC_URL_HANDLER: Any = None
_TRAY_LABELS = {
    "zh_cn": ("显示主窗口", "空房监控", "启动当前任务", "暂停当前任务", "打开最新通知", "清除角标", "退出"),
    "zh_tw": ("顯示主視窗", "空房監控", "啟動目前任務", "暫停目前任務", "開啟最新通知", "清除徽章", "結束"),
    "ja": ("メイン画面を表示", "空室監視", "現在のタスクを開始", "現在のタスクを一時停止", "最新通知を開く", "バッジを消去", "終了"),
    "ko": ("기본 창 표시", "객실 모니터", "현재 작업 시작", "현재 작업 일시 중지", "최근 알림 열기", "배지 지우기", "종료"),
    "en": ("Show", "Vacancy Monitor", "Start current task", "Pause current task", "Open latest notification", "Clear badge", "Quit"),
}
_ARM64_QML = b"""
import QtQuick
import QtWebView

Item {
    property alias currentUrl: browser.url
    width: 1280
    height: 820
    WebView {
        id: browser
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
    parser.add_argument("--background", action="store_true", help="start in the system tray")
    parser.add_argument(
        "deep_link",
        nargs="?",
        default="",
        help="toyoko-tracker:// notification deep link",
    )
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


class _PywebviewWindowAdapter:
    def __init__(self, window: Any) -> None:
        self.window = window

    def show(self) -> None:
        self.window.show()

    def hide(self) -> None:
        self.window.hide()

    def destroy(self) -> None:
        self.window.destroy()

    def load_url(self, url: str) -> None:
        self.window.load_url(url)

    def set_title(self, title: str) -> None:
        try:
            self.window.set_title(title)
        except AttributeError:
            self.window.title = title


class _TrayAdapter:
    """Optional cross-platform tray implemented with pystray."""

    available = False

    def __init__(self, controller: DesktopLifecycleController, base_url: str) -> None:
        self.controller = controller
        self.base_url = base_url
        self.icon: Any = None

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image

            icon_path = Path(__file__).resolve().parent / "static" / "toyoko-chan-mascot.png"
            image = Image.open(icon_path).convert("RGBA")
            try:
                with runtime._CONFIG_LOCK:
                    language = str(runtime._CONFIG.primary_language or "zh_cn")
            except Exception:
                language = "zh_cn"
            labels = _TRAY_LABELS.get(language, _TRAY_LABELS["en"])

            def item(label: str, callback: Any, **kwargs: Any) -> Any:
                return pystray.MenuItem(label, callback, **kwargs)

            self.icon = pystray.Icon(
                "ToyokoTracker",
                image,
                APP_NAME,
                pystray.Menu(
                    item(labels[0], self._show, default=True),
                    item(labels[1], self._monitor),
                    item(labels[2], self._start_task),
                    item(labels[3], self._pause_task),
                    pystray.Menu.SEPARATOR,
                    item(labels[4], self._latest),
                    item(labels[5], self._mark_read),
                    pystray.Menu.SEPARATOR,
                    item(labels[6], self._quit),
                ),
            )
            self.icon.run_detached()
            self.available = True
            return True
        except Exception as exc:
            runtime._log(f"[desktop] tray unavailable: {exc}")
            self.icon = None
            self.available = False
            return False

    def stop(self) -> None:
        self.available = False
        if self.icon is not None:
            self.icon.stop()

    def set_badge(self, unread: int) -> None:
        if self.icon is not None:
            self.icon.title = f"{APP_NAME} ({unread})" if unread else APP_NAME
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def _show(self, *_args: Any) -> None:
        self.controller.show_window()

    def _monitor(self, *_args: Any) -> None:
        from .desktop_lifecycle import build_deep_link

        self.controller.show_window(build_deep_link(view="monitor"))

    def _latest(self, *_args: Any) -> None:
        from .desktop_lifecycle import desktop_status

        link = str(desktop_status().get("state", {}).get("last_deep_link") or "")
        self.controller.show_window(link, mark_read=True)

    def _mark_read(self, *_args: Any) -> None:
        from .desktop_lifecycle import mark_desktop_notifications_read

        mark_desktop_notifications_read()

    def _quit(self, *_args: Any) -> None:
        self.controller.quit()

    def _task_id_for_action(self, action: str) -> str:
        try:
            response = requests.get(f"{self.base_url}/api/v1/tasks", timeout=3)
            response.raise_for_status()
            tasks = response.json().get("tasks") or []
            if action == "pause":
                selected = next(
                    (
                        task
                        for task in tasks
                        if str(task.get("desired_state") or "") == "active"
                    ),
                    tasks[0] if tasks else {},
                )
            else:
                selected = next(
                    (
                        task
                        for task in tasks
                        if str(task.get("desired_state") or "") != "active"
                    ),
                    tasks[0] if tasks else {},
                )
            return str(selected.get("task_id") or "")
        except Exception:
            return ""

    def _task_action(self, action: str) -> None:
        task_id = self._task_id_for_action(action)
        if not task_id:
            self.controller.show_window()
            return
        try:
            requests.post(
                f"{self.base_url}/api/v1/tasks/{task_id}/{action}",
                json={},
                timeout=5,
            ).raise_for_status()
        except Exception as exc:
            runtime._log(f"[desktop] tray task action failed: {exc}")

    def _start_task(self, *_args: Any) -> None:
        self._task_action("start")

    def _pause_task(self, *_args: Any) -> None:
        self._task_action("pause")


def _recover_runtime_services(reason: str) -> None:
    """Wake idempotent background services after resume or network recovery."""
    try:
        runtime.start_task_scheduler()
        with runtime._TASK_SERVICE_LOCK:
            service = runtime._TASK_SERVICE
        if service is not None:
            service.wake()
        dispatcher = runtime._ensure_alert_dispatcher()
        dispatcher.wake()
        runtime.recover_flexible_stay_jobs()
        runtime._log(f"[desktop] services recovered after {reason}")
    except Exception as exc:
        runtime._log(f"[desktop] recovery after {reason} failed: {exc}")


def _four_char_code(value: str) -> int:
    return int.from_bytes(value.encode("ascii"), "big")


def _register_macos_url_handler(controller: DesktopLifecycleController) -> bool:
    """Receive toyoko-tracker:// Apple Events in an already running app."""
    global _MAC_URL_HANDLER
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSAppleEventManager
        from Foundation import NSObject

        class URLHandler(NSObject):
            def initWithController_(self, desktop_controller: Any) -> Any:
                self = self.init()
                if self is not None:
                    self.desktop_controller = desktop_controller
                return self

            def handleGetURLEvent_withReplyEvent_(self, event: Any, _reply: Any) -> None:
                descriptor = event.paramDescriptorForKeyword_(0x2D2D2D2D)
                value = str(descriptor.stringValue() or "") if descriptor else ""
                if value:
                    self.desktop_controller.show_window(value, mark_read=True)

        _MAC_URL_HANDLER = URLHandler.alloc().initWithController_(controller)
        NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
            _MAC_URL_HANDLER,
            "handleGetURLEvent:withReplyEvent:",
            _four_char_code("GURL"),
            _four_char_code("GURL"),
        )
        return True
    except Exception as exc:
        runtime._log(f"[desktop] macOS URL handler unavailable: {exc}")
        return False


def _start_windows_arm64_shell(
    url: str,
    controller: DesktopLifecycleController,
    *,
    hidden: bool = False,
) -> None:
    from PySide6.QtCore import QObject, QSize, QUrl, Signal
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlComponent
    from PySide6.QtQuick import QQuickView

    class QtWindowBridge(QObject):
        show_signal = Signal()
        hide_signal = Signal()
        close_signal = Signal()
        url_signal = Signal(str)
        title_signal = Signal(str)

    class QtWindowAdapter:
        def __init__(self, bridge: Any) -> None:
            self.bridge = bridge

        def show(self) -> None:
            self.bridge.show_signal.emit()

        def hide(self) -> None:
            self.bridge.hide_signal.emit()

        def destroy(self) -> None:
            self.bridge.close_signal.emit()

        def load_url(self, target: str) -> None:
            self.bridge.url_signal.emit(target)

        def set_title(self, title: str) -> None:
            self.bridge.title_signal.emit(title)

    _initialize_qt_webview()
    qt_app = QGuiApplication.instance() or QGuiApplication([APP_NAME])
    view = QQuickView()
    bridge = QtWindowBridge()
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
    bridge.show_signal.connect(view.show)
    bridge.hide_signal.connect(view.hide)
    bridge.close_signal.connect(qt_app.quit)
    bridge.url_signal.connect(lambda target: root.setProperty("currentUrl", QUrl(target)))
    bridge.title_signal.connect(view.setTitle)
    controller.attach_window(QtWindowAdapter(bridge))
    tray = _TrayAdapter(controller, url)
    if tray.start():
        controller.attach_tray(tray)
        qt_app.setQuitOnLastWindowClosed(False)
    controller.start()

    def closing(event: Any) -> None:
        accepted = controller.on_window_closing()
        if not accepted:
            event.setAccepted(False)

    view.closing.connect(closing)
    if not hidden or not tray.available:
        view.show()
    else:
        controller.visible = False
    qt_app.exec()


def main(argv: Any = None) -> None:
    args = _parser().parse_args(argv)
    if args.deep_link and forward_deep_link_to_running(args.deep_link):
        return
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
    write_instance_state(url, port, lan_enabled, frontend="desktop")

    thread = threading.Thread(target=_serve, args=(server,), name="toyoko-web", daemon=True)
    thread.start()
    controller = DesktopLifecycleController(
        url,
        recovery_callback=_recover_runtime_services,
    )
    try:
        if _is_windows_arm64():
            if args.deep_link:
                from .desktop_lifecycle import queue_deep_link

                queue_deep_link(args.deep_link)
            _start_windows_arm64_shell(url, controller, hidden=bool(args.background))
        else:
            try:
                import webview
            except ImportError as exc:
                raise SystemExit(
                    'pywebview is required; install with: pip install "toyoko-tracker[desktop]"'
                ) from exc
            window = webview.create_window(
                APP_NAME,
                deep_link_to_local_url(url, args.deep_link) if args.deep_link else url,
                width=1280,
                height=820,
                min_size=(960, 640),
                text_select=True,
                hidden=bool(args.background),
            )
            controller.attach_window(_PywebviewWindowAdapter(window))
            window.events.closing += controller.on_window_closing
            tray = _TrayAdapter(controller, url)
            if tray.start():
                controller.attach_tray(tray)
            controller.start()
            _register_macos_url_handler(controller)
            if args.background and tray.available:
                controller.visible = False
            webview.start(
                (
                    lambda: controller.show_window()
                    if args.background and not tray.available
                    else None
                ),
                debug=bool(args.debug),
            )
    finally:
        controller.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        stop_runtime_services()
        _cleanup_instance_state()


if __name__ == "__main__":
    main()
