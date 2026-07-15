from toyoko_tracker.desktop import _parser

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


_PREPARE_SPEC = spec_from_file_location(
    "prepare_windows_arm64",
    Path(__file__).resolve().parents[1] / "packaging" / "prepare_windows_arm64.py",
)
assert _PREPARE_SPEC and _PREPARE_SPEC.loader
prepare_windows_arm64 = module_from_spec(_PREPARE_SPEC)
_PREPARE_SPEC.loader.exec_module(prepare_windows_arm64)


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


def test_arm64_clr_loader_source_patches():
    project = "<RuntimeIdentifiers>win-x86;win-x64</RuntimeIdentifiers>\n</Project>"
    architecture = """import sys

def load_netfx():
    if sys.maxsize > 2**32:
        arch = "amd64"
    else:
        arch = "x86"
"""

    patched_project = prepare_windows_arm64.patch_project(project)
    patched_architecture = prepare_windows_arm64.patch_architecture_detection(architecture)

    assert "win-arm64" in patched_project
    assert "<PlatformTarget>ARM64</PlatformTarget>" in patched_project
    assert 'arch = "arm64"' in patched_architecture


def test_arm64_clr_loader_pe_machine_check(tmp_path):
    bridge = tmp_path / "ClrLoader.dll"
    data = bytearray(256)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    data[132:134] = prepare_windows_arm64.PE_MACHINE_ARM64.to_bytes(2, "little")
    bridge.write_bytes(data)

    assert prepare_windows_arm64._pe_machine(bridge) == 0xAA64
