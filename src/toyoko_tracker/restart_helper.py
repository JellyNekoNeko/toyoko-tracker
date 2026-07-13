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


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
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
