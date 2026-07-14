from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from typing import Any

from flask import Flask

from . import runtime
from .mobile_access import manager
from .settings import AUTO_SAVE_PATH, INSTANCE_STATE_PATH, LEGACY_AUTO_SAVE_PATH, __version__


_RESTART_LOCK = threading.Lock()
_RESTART_PENDING = False


def _startup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Toyoko Chan vacancy tracker WebUI")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lan", action="store_true", help="enable authenticated LAN/mobile access")
    group.add_argument("--local-only", action="store_true", help="disable LAN/mobile access")
    parser.add_argument("--port", type=int, default=4170, help="preferred WebUI port")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser automatically")
    return parser


def _cleanup_instance_state() -> None:
    try:
        with open(INSTANCE_STATE_PATH, "r", encoding="utf-8") as stream:
            state = json.load(stream)
        if int(state.get("pid") or 0) == os.getpid():
            os.unlink(INSTANCE_STATE_PATH)
    except (OSError, ValueError, TypeError):
        pass


def _serve(app: Flask, host: str, port: int, lan_enabled: bool) -> None:
    if lan_enabled:
        try:
            from waitress import serve
        except ImportError:
            runtime._log("[mobile] Waitress is not installed; using the Flask server. Install toyoko-tracker[mobile].")
        else:
            serve(app, host=host, port=port, threads=6, clear_untrusted_proxy_headers=True)
            return
    app.run(host=host, port=port, debug=False)


def _restart_arguments(argv: Any = None) -> list[str]:
    source = list(sys.argv[1:] if argv is None else argv)
    return [argument for argument in source if argument not in {"--lan", "--local-only"}]


def schedule_restart(delay_seconds: float = 0.8) -> bool:
    global _RESTART_PENDING
    with _RESTART_LOCK:
        if _RESTART_PENDING:
            return True
        _RESTART_PENDING = True

    def replace_process() -> None:
        arguments = _restart_arguments()
        runtime._log("[mobile] restarting WebUI to apply the access mode...")
        if getattr(sys, "frozen", False):
            command = [sys.executable, *arguments]
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        else:
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "toyoko_tracker.restart_helper",
                    str(os.getpid()),
                    *arguments,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        os._exit(0)

    timer = threading.Timer(max(0.2, float(delay_seconds)), replace_process)
    timer.daemon = True
    timer.start()
    return True


def run(app: Flask, argv: Any = None) -> None:
    args = _startup_parser().parse_args(argv)
    try:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
    except Exception:
        pass

    if args.lan:
        manager.configure(enabled=True)
    elif args.local_only:
        manager.configure(enabled=False)

    try:
        if runtime._load_config_with_legacy(AUTO_SAVE_PATH, LEGACY_AUTO_SAVE_PATH):
            runtime._save_config_to_file(AUTO_SAVE_PATH)
    except Exception as exc:
        runtime._log(f"[boot] auto-load skipped: {exc}")
    try:
        runtime._prune_scan_cache()
        runtime._restore_runtime_checkpoint()
    except Exception as exc:
        runtime._log(f"[boot] checkpoint restore skipped: {exc}")
    runtime._check_pypi_latest_async()
    runtime._start_catalog_scheduler()
    runtime._start_provider_database_scheduler()

    lan_enabled = manager.snapshot().enabled
    host = "0.0.0.0" if lan_enabled else "127.0.0.1"
    port = runtime._find_free_port(max(1, min(65535, int(args.port))), host=host)
    browser_url = f"http://127.0.0.1:{port}"
    app.config["TOYOKO_LAN_BOUND"] = lan_enabled
    app.config["TOYOKO_SERVER_PORT"] = port

    state = {
        "app": "toyoko-tracker",
        "version": __version__,
        "pid": os.getpid(),
        "url": browser_url,
        "lan_enabled": lan_enabled,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    runtime._atomic_write_json(INSTANCE_STATE_PATH, state)
    if lan_enabled:
        runtime._log(f"[mobile] LAN access enabled on port {port}; pairing is required.")

    atexit.register(_cleanup_instance_state)
    atexit.register(runtime._stop_catalog_scheduler)
    atexit.register(runtime._stop_provider_database_scheduler)

    if not args.no_browser:
        try:
            threading.Thread(
                target=runtime._open_browser_when_ready,
                args=(browser_url, "127.0.0.1", port),
                daemon=True,
            ).start()
        except Exception:
            pass
    _serve(app, host, port, lan_enabled)
