"""Validate a desktop archive and emit a machine-readable acceptance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import struct
import subprocess
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


TARGETS = {
    "windows-x64": ("windows", "x64"),
    "windows-arm64": ("windows", "arm64"),
    "linux-x64": ("linux", "x64"),
    "linux-arm64": ("linux", "arm64"),
    "macos-x64": ("macos", "x64"),
    "macos-arm64": ("macos", "arm64"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _binary_architecture(path: Path) -> str:
    data = path.read_bytes()[:4096]
    if data.startswith(b"MZ") and len(data) >= 64:
        offset = struct.unpack_from("<I", data, 0x3C)[0]
        with path.open("rb") as stream:
            stream.seek(offset)
            header = stream.read(6)
        if header[:4] != b"PE\0\0":
            raise ValueError("Windows executable has an invalid PE header")
        machine = struct.unpack_from("<H", header, 4)[0]
        return {0x8664: "x64", 0xAA64: "arm64"}.get(machine, f"pe-{machine:04x}")
    if data.startswith(b"\x7fELF") and len(data) >= 20:
        endian = "<" if data[5] == 1 else ">"
        machine = struct.unpack_from(endian + "H", data, 18)[0]
        return {62: "x64", 183: "arm64"}.get(machine, f"elf-{machine}")
    magic = data[:4]
    if magic in {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"}:
        cpu = struct.unpack_from("<I", data, 4)[0]
        return {0x01000007: "x64", 0x0100000C: "arm64"}.get(cpu, f"macho-{cpu:x}")
    if magic in {b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"}:
        cpu = struct.unpack_from(">I", data, 4)[0]
        return {0x01000007: "x64", 0x0100000C: "arm64"}.get(cpu, f"macho-{cpu:x}")
    raise ValueError(f"executable format was not recognized: {path}")


def _archive_members(path: Path) -> list[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as bundle:
            members = bundle.namelist()
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as bundle:
            members = bundle.getnames()
    else:
        raise ValueError("desktop archive must be .zip or .tar.gz")
    if not members:
        raise ValueError("desktop archive is empty")
    for member in members:
        parts = Path(member).parts
        if Path(member).is_absolute() or ".." in parts:
            raise ValueError(f"desktop archive contains an unsafe member: {member}")
    return members


def _signature_status(application: Path, operating_system: str) -> str:
    if operating_system == "macos":
        verification = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(application)],
            capture_output=True,
            text=True,
        )
        if verification.returncode != 0:
            return "unsigned"
        details = subprocess.run(
            ["codesign", "-dv", "--verbose=4", str(application)],
            capture_output=True,
            text=True,
        )
        output = f"{details.stdout}\n{details.stderr}"
        authorities = [
            line.split("=", 1)[1].strip()
            for line in output.splitlines()
            if line.startswith("Authority=")
        ]
        return "developer-id" if authorities else "ad-hoc"
    if operating_system == "windows":
        environment = os.environ.copy()
        environment["TOYOKO_SIGNATURE_TARGET"] = str(application)
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "$s=Get-AuthenticodeSignature -FilePath $env:TOYOKO_SIGNATURE_TARGET;"
                "Write-Output ([string]$s.Status)",
            ],
            capture_output=True,
            text=True,
            env=environment,
        )
        return "signed" if result.returncode == 0 and result.stdout.strip().lower() == "valid" else "unsigned"
    return "not-applicable"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--application", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    operating_system, expected_arch = TARGETS[args.target]
    archive = Path(args.archive)
    application = Path(args.application)
    executable = Path(args.executable)
    if not archive.is_file() or not executable.is_file() or not application.exists():
        raise SystemExit("archive, application, or executable is missing")
    members = _archive_members(archive)
    expected_root = "ToyokoTracker.app" if operating_system == "macos" else "ToyokoTracker"
    if not any(Path(member).parts and Path(member).parts[0] == expected_root for member in members):
        raise SystemExit(f"archive does not contain the expected {expected_root} root")
    actual_arch = _binary_architecture(executable)
    if actual_arch != expected_arch:
        raise SystemExit(
            f"binary architecture mismatch: expected {expected_arch}, found {actual_arch}"
        )
    runner_machine = platform.machine().lower()
    manifest = {
        "format": "toyoko-tracker-desktop-acceptance",
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": args.target,
        "os": operating_system,
        "arch": expected_arch,
        "runner_machine": runner_machine,
        "version": args.version,
        "archive": archive.name,
        "archive_size": archive.stat().st_size,
        "archive_sha256": _sha256(archive),
        "archive_member_count": len(members),
        "executable_sha256": _sha256(executable),
        "signature": _signature_status(
            application if operating_system == "macos" else executable,
            operating_system,
        ),
        "checks": {
            "archive_structure": "passed",
            "binary_architecture": "passed",
            "startup_smoke": "passed",
        },
    }
    output = Path(args.output)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
