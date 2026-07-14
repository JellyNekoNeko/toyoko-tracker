from __future__ import annotations

import os
import socket
import sys
import time
from typing import List


def _preferred_port(arguments: List[str], default: int = 4170) -> int:
    for index, argument in enumerate(arguments):
        if argument == "--port" and index + 1 < len(arguments):
            try:
                return int(arguments[index + 1])
            except ValueError:
                return default
        if argument.startswith("--port="):
            try:
                return int(argument.split("=", 1)[1])
            except ValueError:
                return default
    return default


def _windows_process_exists(pid: int) -> bool:
    """Check a Windows PID without using ``os.kill(pid, 0)``.

    On Windows, ``os.kill`` delegates non-console signals to
    ``TerminateProcess``.  Signal 0 is therefore not a harmless existence
    probe like it is on POSIX systems.
    """
    try:
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            # Access denied still proves that a process with this PID exists.
            return ctypes.get_last_error() == 5
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_process_exists(pid)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _port_is_free(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def main() -> None:
    try:
        parent_pid = int(sys.argv[1])
    except (IndexError, ValueError):
        raise SystemExit(2)
    arguments = list(sys.argv[2:])
    port = _preferred_port(arguments)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not _process_exists(parent_pid) and _port_is_free(port):
            break
        time.sleep(0.15)
    os.execv(
        sys.executable,
        [sys.executable, "-m", "toyoko_tracker", *arguments],
    )


if __name__ == "__main__":
    main()
