from unittest.mock import patch
from importlib.metadata import version

from toyoko_tracker import runtime
from toyoko_tracker.desktop_version import DESKTOP_VERSION


def test_version_keys_treat_trailing_zero_as_equal():
    assert runtime._version_key("v0.6") == runtime._version_key("0.6.0")


def test_desktop_version_tracks_webui_version():
    assert DESKTOP_VERSION == version("toyoko-tracker")


def test_desktop_asset_name_for_macos_arm():
    with patch.object(runtime.sys, "platform", "darwin"), patch.object(
        runtime.platform, "machine", return_value="arm64"
    ):
        assert runtime._desktop_asset_name() == "ToyokoTracker-macos-arm64.zip"


def test_desktop_asset_name_for_macos_intel():
    with patch.object(runtime.sys, "platform", "darwin"), patch.object(
        runtime.platform, "machine", return_value="x86_64"
    ):
        assert runtime._desktop_asset_name() == "ToyokoTracker-macos-x64.zip"


def test_desktop_asset_name_for_linux_arm():
    with patch.object(runtime.sys, "platform", "linux"), patch.object(
        runtime.os, "name", "posix"
    ), patch.object(runtime.platform, "machine", return_value="aarch64"):
        assert runtime._desktop_asset_name() == "ToyokoTracker-linux-arm64.tar.gz"


def test_desktop_asset_name_for_windows_arm():
    with patch.object(runtime.sys, "platform", "win32"), patch.object(
        runtime.os, "name", "nt"
    ), patch.object(runtime.platform, "machine", return_value="ARM64"):
        assert runtime._desktop_asset_name() == "ToyokoTracker-windows-arm64.zip"


def test_github_release_selects_current_platform_asset():
    release = {
        "tag_name": "desktop-v0.7.0",
        "html_url": "https://example.test/release",
        "body": "Changes",
        "assets": [
            {
                "name": "ToyokoTracker-macos-arm64.zip",
                "browser_download_url": "https://example.test/app.zip",
            },
            {
                "name": "SHA256SUMS.txt",
                "browser_download_url": "https://example.test/SHA256SUMS.txt",
            },
        ],
    }
    with patch.object(runtime.sys, "platform", "darwin"), patch.object(
        runtime.platform, "machine", return_value="arm64"
    ):
        details = runtime._github_release_details(release)

    assert details["version"] == "0.7.0"
    assert details["download_url"] == "https://example.test/app.zip"
    assert details["checksum_url"] == "https://example.test/SHA256SUMS.txt"
    assert details["release_notes"] == "Changes"


def test_latest_desktop_release_ignores_webui_release():
    releases = [
        {"tag_name": "v9.0.0"},
        {"tag_name": "desktop-v0.2.0", "draft": False, "prerelease": False},
    ]
    assert runtime._latest_desktop_release(releases)["tag_name"] == "desktop-v0.2.0"


def test_update_dispatch_uses_github_for_frozen_desktop():
    with patch.object(runtime, "_is_desktop_distribution", return_value=True), patch.object(
        runtime, "_check_github_latest_async"
    ) as github, patch.object(runtime, "_check_pypi_latest_async") as pypi:
        runtime._check_latest_async()

    github.assert_called_once_with()
    pypi.assert_not_called()


def test_pipx_environment_is_detected_from_prefix():
    with patch.dict(runtime.os.environ, {}, clear=True), patch.object(
        runtime.sys, "prefix", "/Users/test/.local/pipx/venvs/toyoko-tracker"
    ), patch.object(runtime, "_is_desktop_distribution", return_value=False):
        assert runtime._install_method() == "pipx"


def test_pipx_upgrade_uses_pipx_executable():
    with patch.object(runtime, "_is_pipx_environment", return_value=True), patch.object(
        runtime.shutil, "which", return_value="/opt/homebrew/bin/pipx"
    ):
        assert runtime._pypi_upgrade_command() == [
            "/opt/homebrew/bin/pipx",
            "upgrade",
            "toyoko-tracker",
        ]


def test_pip_upgrade_is_used_outside_pipx():
    with patch.object(runtime, "_is_pipx_environment", return_value=False):
        assert runtime._pypi_upgrade_command() == [
            runtime.sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "toyoko-tracker",
        ]
