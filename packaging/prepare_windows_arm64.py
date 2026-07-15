"""Build the missing native clr-loader bridge for Windows ARM64.

clr-loader 0.3.1 publishes a universal Python wheel, but that wheel only
contains x86 and x64 .NET Framework bridge DLLs. pywebview therefore freezes
successfully on Windows ARM64 and then fails at runtime with error 0xc1 while
trying to load the bundled amd64 DLL. This build-time helper rebuilds the same
upstream release with its ARM64 target enabled before PyInstaller runs.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


CLR_LOADER_VERSION = "0.3.1"
PE_MACHINE_ARM64 = 0xAA64


def patch_project(source: str) -> str:
    source = source.replace(
        "<RuntimeIdentifiers>win-x86;win-x64</RuntimeIdentifiers>",
        "<RuntimeIdentifiers>win-x86;win-x64;win-arm64</RuntimeIdentifiers>",
    )
    if "'$(RuntimeIdentifier)' == 'win-arm64'" not in source:
        marker = "\n</Project>"
        if marker not in source:
            raise RuntimeError("clr-loader project layout was not recognized")
        target = """

  <PropertyGroup Condition=" '$(RuntimeIdentifier)' == 'win-arm64'">
    <PlatformTarget>ARM64</PlatformTarget>
  </PropertyGroup>"""
        source = source.replace(marker, f"{target}{marker}", 1)
    return source


def patch_architecture_detection(source: str) -> str:
    if 'arch = "arm64"' in source:
        return source
    source = source.replace("import sys\n", "import sys\nimport platform\n", 1)
    old = """    if sys.maxsize > 2**32:
        arch = "amd64"
    else:
        arch = "x86"
"""
    new = """    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        arch = "arm64"
    elif sys.maxsize > 2**32:
        arch = "amd64"
    else:
        arch = "x86"
"""
    if old not in source:
        raise RuntimeError("clr-loader architecture detection was not recognized")
    return source.replace(old, new, 1)


def _safe_extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe source archive member: {member.name}")
        bundle.extractall(destination, filter="data")


def _run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _pe_machine(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b"MZ":
        raise RuntimeError(f"not a Windows PE file: {path}")
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if pe_offset + 6 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise RuntimeError(f"invalid Windows PE header: {path}")
    return int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little")


def prepare() -> None:
    if sys.platform != "win32" or platform.machine().lower() not in {"arm64", "aarch64"}:
        print("Windows ARM64 clr-loader preparation skipped on this platform")
        return

    with tempfile.TemporaryDirectory(prefix="toyoko-clr-loader-") as temporary:
        work = Path(temporary)
        _run(
            sys.executable,
            "-m",
            "pip",
            "download",
            f"clr_loader=={CLR_LOADER_VERSION}",
            "--no-binary=clr_loader",
            "--no-deps",
            "--dest",
            str(work),
        )
        archives = list(work.glob("clr_loader-*.tar.gz"))
        if len(archives) != 1:
            raise RuntimeError("expected one clr-loader source archive")
        source_root = work / "source"
        source_root.mkdir()
        _safe_extract(archives[0], source_root)
        projects = list(source_root.glob("clr_loader-*/netfx_loader/ClrLoader.csproj"))
        if len(projects) != 1:
            raise RuntimeError("clr-loader source project was not found")
        project_root = projects[0].parents[1]

        project_path = project_root / "netfx_loader" / "ClrLoader.csproj"
        project_path.write_text(
            patch_project(project_path.read_text(encoding="utf-8")), encoding="utf-8"
        )
        output = work / "arm64-output"
        _run(
            "dotnet",
            "build",
            str(project_path),
            "--runtime",
            "win-arm64",
            "--configuration",
            "Release",
            "--output",
            str(output),
            cwd=project_root,
        )
        built_bridge = output / "ClrLoader.dll"
        if not built_bridge.is_file():
            raise RuntimeError("dotnet did not produce an ARM64 ClrLoader.dll")
        if _pe_machine(built_bridge) != PE_MACHINE_ARM64:
            raise RuntimeError("dotnet produced a ClrLoader.dll for the wrong architecture")

        spec = importlib.util.find_spec("clr_loader")
        if spec is None or not spec.submodule_search_locations:
            raise RuntimeError("installed clr-loader package is unavailable")
        package_root = Path(next(iter(spec.submodule_search_locations)))
        bridge = package_root / "ffi" / "dlls" / "arm64" / "ClrLoader.dll"
        bridge.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built_bridge, bridge)
        installed_ffi = package_root / "ffi" / "__init__.py"
        installed_ffi.write_text(
            patch_architecture_detection(installed_ffi.read_text(encoding="utf-8")),
            encoding="utf-8",
        )

    if not bridge.is_file():
        raise RuntimeError("Windows ARM64 ClrLoader.dll was not produced")
    if _pe_machine(bridge) != PE_MACHINE_ARM64:
        raise RuntimeError("installed ClrLoader.dll is not Windows ARM64")
    if shutil.which("dotnet") is None:
        raise RuntimeError("dotnet CLI disappeared after the ARM64 bridge build")
    print(f"Windows ARM64 clr-loader ready: {bridge}")


if __name__ == "__main__":
    prepare()
