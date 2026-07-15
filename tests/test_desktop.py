from unittest.mock import patch

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
        assert desktop._preferred_gui() == "qt"


def test_other_desktop_platforms_keep_default_backend():
    with patch.object(desktop.sys, "platform", "darwin"), patch.object(
        desktop.platform, "machine", return_value="arm64"
    ):
        assert desktop._preferred_gui() is None
