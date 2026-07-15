from pathlib import Path
from unittest.mock import Mock, patch

from toyoko_tracker import desktop
from toyoko_tracker.desktop import _parser


def test_desktop_parser_defaults():
    args = _parser().parse_args([])
    assert args.port == 4170
    assert args.lan is False
    assert args.local_only is False
    assert args.debug is False


def test_desktop_parser_supports_local_mode_and_port():
    args = _parser().parse_args(["--local-only", "--port", "5180", "--debug"])
    assert args.local_only is True
    assert args.port == 5180
    assert args.debug is True


def test_windows_arm64_uses_native_qt_backend():
    with patch.object(desktop.sys, "platform", "win32"), patch.object(
        desktop.platform, "machine", return_value="ARM64"
    ):
        assert desktop._is_windows_arm64()


def test_other_desktop_platforms_keep_default_backend():
    with patch.object(desktop.sys, "platform", "darwin"), patch.object(
        desktop.platform, "machine", return_value="arm64"
    ):
        assert not desktop._is_windows_arm64()


def test_windows_arm64_shell_uses_qt_webview():
    qml = desktop._ARM64_QML.decode("utf-8")

    assert "import QtWebView" in qml
    assert "WebView" in qml
    assert "url: appUrl" in qml


def test_qml_component_waits_for_async_imports():
    qt_app = Mock()
    component = Mock()
    component.isLoading.side_effect = [True, True, False]

    with patch.object(desktop.time, "sleep"):
        desktop._wait_for_qml_component(qt_app, component)

    assert qt_app.processEvents.call_count == 2


def test_desktop_entry_persists_unhandled_startup_errors():
    entrypoint = (
        Path(__file__).resolve().parents[1] / "packaging" / "desktop_entry.py"
    ).read_text(encoding="utf-8")

    assert "desktop-startup-error.log" in entrypoint
    assert "traceback.print_exc" in entrypoint
