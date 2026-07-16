"""Launch a frozen POSIX desktop build and verify its local WebUI."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True)
    parser.add_argument("--port", type=int, default=45170)
    args = parser.parse_args()

    executable = Path(args.executable).resolve()
    if not executable.is_file():
        raise SystemExit(f"desktop executable was not found: {executable}")
    config_directory = Path(tempfile.mkdtemp(prefix="toyoko-desktop-smoke-"))
    environment = os.environ.copy()
    environment["TOYOKO_TRACKER_CONFIG_DIR"] = str(config_directory)
    command = [
        str(executable),
        "--local-only",
        "--port",
        str(args.port),
    ]
    process = subprocess.Popen(
        command,
        cwd=executable.parent,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    output = ""
    try:
        deadline = time.monotonic() + 60
        last_error = ""
        while time.monotonic() < deadline:
            code = process.poll()
            if code is not None:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(
                    f"desktop process exited during startup with code {code}\n{output}"
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{args.port}/health",
                    timeout=3,
                ) as response:
                    body = response.read().decode("utf-8", "replace")
                    if response.status == 200 and '"ok":true' in body.replace(" ", ""):
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{args.port}/",
                            timeout=3,
                        ) as home:
                            markup = home.read().decode("utf-8", "replace")
                        if "phase6-data-card" not in markup:
                            raise RuntimeError("Phase 6 data card is missing from the frozen UI")
                        print(
                            f"Desktop smoke test passed: HTTP 200, PID {process.pid}, "
                            f"executable {executable.name}"
                        )
                        return
                last_error = "health response was not ready"
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1)
        startup_log = config_directory / "desktop-startup-error.log"
        if startup_log.exists():
            output += "\n" + startup_log.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(f"desktop build did not become ready: {last_error}\n{output}")
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=8)
            except Exception:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
        shutil.rmtree(config_directory, ignore_errors=True)


if __name__ == "__main__":
    main()
