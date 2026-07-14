import hashlib
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from toyoko_tracker import desktop_updater


def test_expected_digest_selects_exact_asset():
    digest = "a" * 64
    checksums = f"{digest}  ToyokoTracker-linux-x64.tar.gz\n"
    assert desktop_updater._expected_digest(
        checksums, "ToyokoTracker-linux-x64.tar.gz"
    ) == digest


def test_expected_digest_rejects_missing_asset():
    with pytest.raises(ValueError, match="does not contain"):
        desktop_updater._expected_digest("", "ToyokoTracker-linux-x64.tar.gz")


def test_zip_extraction_rejects_parent_traversal(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "bad")

    with pytest.raises(ValueError, match="unsafe archive member"):
        desktop_updater._extract_zip(archive, tmp_path / "extract")


def test_zip_extraction_preserves_safe_symbolic_link(tmp_path: Path):
    archive = tmp_path / "links.zip"
    link = zipfile.ZipInfo("ToyokoTracker/current")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("ToyokoTracker/versions/app", "binary")
        bundle.writestr(link, "versions/app")

    destination = tmp_path / "extract"
    desktop_updater._extract_zip(archive, destination)

    extracted_link = destination / "ToyokoTracker" / "current"
    assert extracted_link.is_symlink()
    assert extracted_link.resolve().read_text() == "binary"


def test_zip_extraction_rejects_escaping_symbolic_link(tmp_path: Path):
    archive = tmp_path / "unsafe-link.zip"
    link = zipfile.ZipInfo("ToyokoTracker/current")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(link, "../../outside")

    with pytest.raises(ValueError, match="unsafe archive member"):
        desktop_updater._extract_zip(archive, tmp_path / "extract")


def test_prepare_desktop_update_verifies_and_stages_zip(tmp_path: Path):
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as bundle:
        bundle.writestr("ToyokoTracker/ToyokoTracker", "new executable")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def fake_download(url, destination, **kwargs):
        if destination.name == "SHA256SUMS.txt":
            destination.write_text(
                f"{digest}  ToyokoTracker-linux-x64.zip\n", encoding="utf-8"
            )
        else:
            destination.write_bytes(source.read_bytes())

    install_root = tmp_path / "installed" / "ToyokoTracker"
    install_root.mkdir(parents=True)
    with patch.object(desktop_updater, "_download", side_effect=fake_download), patch.object(
        desktop_updater, "_desktop_install_root", return_value=install_root
    ), patch.object(desktop_updater.sys, "platform", "linux"):
        prepared = desktop_updater.prepare_desktop_update(
            version="0.7.0",
            asset_name="ToyokoTracker-linux-x64.zip",
            download_url="https://example.test/app.zip",
            checksum_url="https://example.test/SHA256SUMS.txt",
            config_dir=tmp_path / "config",
            parent_pid=123,
        )

    assert prepared.staged_root.name == "ToyokoTracker"
    assert (prepared.staged_root / "ToyokoTracker").read_text() == "new executable"
    assert prepared.helper_path.exists()
    assert "parent_pid=123" in prepared.helper_path.read_text()
    assert prepared.backup_root.name == "ToyokoTracker.previous"


def test_prepare_desktop_update_rejects_bad_checksum(tmp_path: Path):
    def fake_download(url, destination, **kwargs):
        if destination.name == "SHA256SUMS.txt":
            destination.write_text(
                f"{'0' * 64}  ToyokoTracker-linux-x64.zip\n", encoding="utf-8"
            )
        else:
            destination.write_bytes(b"not the signed archive")

    with patch.object(desktop_updater, "_download", side_effect=fake_download):
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            desktop_updater.prepare_desktop_update(
                version="0.7.0",
                asset_name="ToyokoTracker-linux-x64.zip",
                download_url="https://example.test/app.zip",
                checksum_url="https://example.test/SHA256SUMS.txt",
                config_dir=tmp_path / "config",
            )


def test_macos_signed_update_requires_same_authority(tmp_path: Path):
    with patch.object(desktop_updater.sys, "platform", "darwin"), patch.object(
        desktop_updater,
        "_macos_authorities",
        side_effect=[["Developer ID Application: Current"], ["Developer ID Application: Other"]],
    ):
        with pytest.raises(ValueError, match="does not match"):
            desktop_updater._verify_platform_signature(
                tmp_path / "new.app", tmp_path / "current.app"
            )


def test_macos_signed_update_is_verified(tmp_path: Path):
    completed = SimpleNamespace(returncode=0, stdout="", stderr="")
    with patch.object(desktop_updater.sys, "platform", "darwin"), patch.object(
        desktop_updater,
        "_macos_authorities",
        side_effect=[["Developer ID Application: Same"], ["Developer ID Application: Same"]],
    ), patch.object(desktop_updater.subprocess, "run", return_value=completed) as run:
        desktop_updater._verify_platform_signature(
            tmp_path / "new.app", tmp_path / "current.app"
        )

    assert "--verify" in run.call_args.args[0]


def test_windows_signed_update_requires_same_subject(tmp_path: Path):
    with patch.object(desktop_updater.sys, "platform", "win32"), patch.object(
        desktop_updater.os, "name", "nt"
    ), patch.object(
        desktop_updater,
        "_windows_signature",
        side_effect=[
            {"status": "Valid", "subject": "CN=Current"},
            {"status": "Valid", "subject": "CN=Other"},
        ],
    ):
        with pytest.raises(ValueError, match="does not match"):
            desktop_updater._verify_platform_signature(
                tmp_path / "new", tmp_path / "current"
            )
