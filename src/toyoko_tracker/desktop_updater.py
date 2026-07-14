"""Download, verify, stage, and apply frozen desktop updates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class PreparedDesktopUpdate:
    version: str
    asset_name: str
    archive_path: Path
    staged_root: Path
    install_root: Path
    helper_path: Path
    backup_root: Path


def _download(
    url: str,
    destination: Path,
    *,
    progress: Optional[ProgressCallback] = None,
    timeout: int = 60,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with requests.get(
        url,
        headers={"User-Agent": "ToyokoTracker-Updater"},
        stream=True,
        timeout=(10, timeout),
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        with temporary.open("wb") as stream:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                stream.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
    os.replace(temporary, destination)


def _expected_digest(checksums: str, asset_name: str) -> str:
    for line in checksums.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == asset_name:
            digest = parts[0].lower()
            if len(digest) == 64 and all(char in "0123456789abcdef" for char in digest):
                return digest
    raise ValueError(f"SHA256SUMS.txt does not contain {asset_name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_destination(root: Path, member_name: str) -> Path:
    destination = (root / member_name).resolve()
    resolved_root = root.resolve()
    try:
        destination.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"unsafe archive member: {member_name}") from exc
    return destination


def _validate_link_target(
    root: Path,
    member_name: str,
    link_name: str,
    *,
    relative_to_member: bool = True,
) -> None:
    member = Path(member_name)
    base = member.parent if relative_to_member else Path()
    _safe_destination(root, str(base / link_name))


def _extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = _safe_destination(destination, member.filename)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                link_name = bundle.read(member).decode("utf-8")
                _validate_link_target(destination, member.filename, link_name)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(link_name, target)
                continue
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            permissions = mode & 0o777
            if permissions:
                target.chmod(permissions)


def _extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            _safe_destination(destination, member.name)
            if member.issym():
                _validate_link_target(destination, member.name, member.linkname)
            elif member.islnk():
                _validate_link_target(
                    destination,
                    member.name,
                    member.linkname,
                    relative_to_member=False,
                )
            elif member.isdev():
                raise ValueError(f"unsupported archive member: {member.name}")
        bundle.extractall(destination, members=members)


def _desktop_install_root(executable: Optional[Path] = None) -> Path:
    path = (executable or Path(sys.executable)).resolve()
    if sys.platform == "darwin":
        for candidate in (path, *path.parents):
            if candidate.suffix.lower() == ".app":
                return candidate
        raise ValueError("the running executable is not inside a macOS app bundle")
    return path.parent


def _staged_application_root(extract_root: Path) -> Path:
    expected = "ToyokoTracker.app" if sys.platform == "darwin" else "ToyokoTracker"
    direct = extract_root / expected
    if direct.exists():
        return direct
    matches = [path for path in extract_root.rglob(expected) if path.is_dir()]
    if len(matches) != 1:
        raise ValueError(f"update archive did not contain one {expected} directory")
    return matches[0]


def _macos_authorities(application: Path) -> list[str]:
    result = subprocess.run(
        ["codesign", "-dv", "--verbose=4", str(application)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = f"{result.stdout}\n{result.stderr}"
    return [
        line.split("=", 1)[1].strip()
        for line in output.splitlines()
        if line.startswith("Authority=")
    ]


def _windows_signature(application: Path) -> dict[str, str]:
    executable = application / "ToyokoTracker.exe"
    environment = os.environ.copy()
    environment["TOYOKO_SIGNATURE_TARGET"] = str(executable)
    script = (
        "$signature = Get-AuthenticodeSignature -FilePath $env:TOYOKO_SIGNATURE_TARGET; "
        "[PSCustomObject]@{status=[string]$signature.Status; "
        "subject=[string]$signature.SignerCertificate.Subject} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
    except (TypeError, ValueError):
        return {}
    return {"status": str(data.get("status") or ""), "subject": str(data.get("subject") or "")}


def _verify_platform_signature(staged_root: Path, install_root: Path) -> None:
    """Preserve the native trust chain once the installed app is signed."""

    if sys.platform == "darwin":
        current = _macos_authorities(install_root)
        if not current:
            return
        candidate = _macos_authorities(staged_root)
        if not candidate or candidate[0] != current[0]:
            raise ValueError("the macOS update signing identity does not match the installed app")
        verification = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(staged_root)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if verification.returncode != 0:
            raise ValueError("the macOS update signature is invalid")
    elif os.name == "nt":
        current = _windows_signature(install_root)
        if current.get("status").lower() != "valid":
            return
        candidate = _windows_signature(staged_root)
        if (
            candidate.get("status").lower() != "valid"
            or candidate.get("subject") != current.get("subject")
        ):
            raise ValueError("the Windows update signer does not match the installed app")


def _ps_quote(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _write_windows_helper(
    path: Path,
    *,
    parent_pid: int,
    staged_root: Path,
    install_root: Path,
    backup_root: Path,
) -> None:
    executable = install_root / "ToyokoTracker.exe"
    script = f"""$ErrorActionPreference = 'Stop'
$parentPid = {int(parent_pid)}
$staged = {_ps_quote(staged_root)}
$install = {_ps_quote(install_root)}
$backup = {_ps_quote(backup_root)}
try {{ Wait-Process -Id $parentPid -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}
for ($i = 0; $i -lt 120; $i++) {{
  if (-not (Get-Process -Id $parentPid -ErrorAction SilentlyContinue)) {{ break }}
  Start-Sleep -Milliseconds 250
}}
if (Test-Path $backup) {{ Remove-Item -Recurse -Force $backup }}
Move-Item -Force $install $backup
try {{
  Move-Item -Force $staged $install
}} catch {{
  if (Test-Path $install) {{ Remove-Item -Recurse -Force $install }}
  Move-Item -Force $backup $install
  throw
}}
Start-Process {_ps_quote(executable)}
"""
    path.write_text(script, encoding="utf-8")


def _sh_quote(value: Path | str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _write_posix_helper(
    path: Path,
    *,
    parent_pid: int,
    staged_root: Path,
    install_root: Path,
    backup_root: Path,
) -> None:
    if sys.platform == "darwin":
        relaunch = f"open {_sh_quote(install_root)}"
    else:
        relaunch = f"nohup {_sh_quote(install_root / 'ToyokoTracker')} >/dev/null 2>&1 &"
    script = f"""#!/bin/sh
set -eu
parent_pid={int(parent_pid)}
staged={_sh_quote(staged_root)}
install={_sh_quote(install_root)}
backup={_sh_quote(backup_root)}
i=0
while kill -0 "$parent_pid" 2>/dev/null && [ "$i" -lt 240 ]; do
  sleep 0.25
  i=$((i + 1))
done
rm -rf "$backup"
mv "$install" "$backup"
if ! mv "$staged" "$install"; then
  rm -rf "$install"
  mv "$backup" "$install"
  exit 1
fi
{relaunch}
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o700)


def prepare_desktop_update(
    *,
    version: str,
    asset_name: str,
    download_url: str,
    checksum_url: str,
    config_dir: Path,
    parent_pid: Optional[int] = None,
    progress: Optional[ProgressCallback] = None,
) -> PreparedDesktopUpdate:
    if not download_url or not checksum_url:
        raise ValueError("release assets or SHA256SUMS.txt are missing")
    safe_version = "".join(char for char in version if char.isalnum() or char in ".-_") or "update"
    update_root = config_dir / "updates" / safe_version
    if update_root.exists():
        shutil.rmtree(update_root)
    extract_root = update_root / "extracted"
    extract_root.mkdir(parents=True)
    archive_path = update_root / asset_name
    checksums_path = update_root / "SHA256SUMS.txt"
    _download(checksum_url, checksums_path)
    _download(download_url, archive_path, progress=progress)
    expected = _expected_digest(checksums_path.read_text(encoding="utf-8"), asset_name)
    actual = _sha256(archive_path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {asset_name}")
    if asset_name.endswith(".zip"):
        _extract_zip(archive_path, extract_root)
    elif asset_name.endswith(".tar.gz"):
        _extract_tar(archive_path, extract_root)
    else:
        raise ValueError(f"unsupported desktop update archive: {asset_name}")
    staged_root = _staged_application_root(extract_root)
    install_root = _desktop_install_root()
    _verify_platform_signature(staged_root, install_root)
    backup_root = install_root.with_name(f"{install_root.name}.previous")
    helper_path = update_root / ("apply-update.ps1" if os.name == "nt" else "apply-update.sh")
    pid = int(parent_pid or os.getpid())
    if os.name == "nt":
        _write_windows_helper(
            helper_path,
            parent_pid=pid,
            staged_root=staged_root,
            install_root=install_root,
            backup_root=backup_root,
        )
    else:
        _write_posix_helper(
            helper_path,
            parent_pid=pid,
            staged_root=staged_root,
            install_root=install_root,
            backup_root=backup_root,
        )
    return PreparedDesktopUpdate(
        version=version,
        asset_name=asset_name,
        archive_path=archive_path,
        staged_root=staged_root,
        install_root=install_root,
        helper_path=helper_path,
        backup_root=backup_root,
    )


def launch_update_helper(update: PreparedDesktopUpdate) -> None:
    if os.name == "nt":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(update.helper_path),
        ]
    else:
        command = ["/bin/sh", str(update.helper_path)]
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def schedule_process_exit(delay_seconds: float = 1.2) -> None:
    """Give the HTTP response time to reach the UI, then let the helper replace us."""

    time.sleep(max(0.2, float(delay_seconds)))
    os._exit(0)
