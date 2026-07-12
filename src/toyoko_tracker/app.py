from __future__ import annotations

import atexit
import ipaddress
import logging
import os
import threading
from datetime import datetime
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request

from . import runtime as _runtime
from .app_compat import *  # noqa: F403 - legacy public API lives outside the route layer.
from .settings import AUTO_SAVE_PATH, INSTANCE_STATE_PATH, LEGACY_AUTO_SAVE_PATH, __version__

app = Flask(__name__)


@app.before_request
def protect_local_api():
    try:
        if not ipaddress.ip_address(request.remote_addr or "").is_loopback:
            return jsonify({"ok": False, "error": "Local access only"}), 403
    except ValueError:
        return jsonify({"ok": False, "error": "Local access only"}), 403

    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        return jsonify({"ok": False, "error": "Cross-site request blocked"}), 403
    origin = request.headers.get("Origin")
    if origin:
        source = urlsplit(origin)
        target = urlsplit(request.host_url)
        if (source.scheme, source.netloc) != (target.scheme, target.netloc):
            return jsonify({"ok": False, "error": "Origin not allowed"}), 403
    return None


@app.after_request
def add_local_security_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response


@app.route("/")
def home() -> Response:
    return _runtime.home()


@app.route("/start", methods=["POST"])
def start() -> Response:
    return _runtime.start()


@app.route("/stop", methods=["POST"])
def stop() -> Response:
    return _runtime.stop()


@app.route("/local_notify_test", methods=["POST"])
def local_notify_test() -> Response:
    return _runtime.local_notify_test()


@app.route("/bark_notify_test", methods=["POST"])
def bark_notify_test() -> Response:
    return _runtime.bark_notify_test()


@app.route("/bark_sound_test", methods=["POST"])
def bark_sound_test() -> Response:
    return _runtime.bark_sound_test()


@app.route("/status")
def status() -> Response:
    return _runtime.status()


@app.route("/health")
def health() -> Response:
    return _runtime.health()


@app.route("/update_status")
def update_status() -> Response:
    return _runtime.update_status()


@app.route("/upgrade", methods=["POST"])
def upgrade() -> Response:
    return _runtime.upgrade()


@app.route("/area_index")
def area_index() -> Response:
    return _runtime.area_index()


@app.route("/search_history")
def search_history() -> Response:
    return _runtime.search_history()


@app.route("/search_history/clear", methods=["POST"])
def search_history_clear() -> Response:
    return _runtime.search_history_clear()


@app.route("/area_hotels", methods=["POST"])
def area_hotels() -> Response:
    return _runtime.area_hotels()


@app.route("/radius_hotels", methods=["POST"])
def radius_hotels() -> Response:
    return _runtime.radius_hotels()


def main() -> None:
    try:
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
    except Exception:
        pass

    try:
        if _runtime._load_config_with_legacy(AUTO_SAVE_PATH, LEGACY_AUTO_SAVE_PATH):
            _runtime._save_config_to_file(AUTO_SAVE_PATH)
    except Exception as e:
        _runtime._log(f"[boot] auto-load skipped: {e}")
    _runtime._check_pypi_latest_async()

    host = "127.0.0.1"
    port = _runtime._find_free_port(4170)
    url = f"http://{host}:{port}"

    _runtime._atomic_write_json(INSTANCE_STATE_PATH, {
        "app": "toyoko-tracker",
        "version": __version__,
        "pid": os.getpid(),
        "url": url,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    })

    def cleanup_instance_state() -> None:
        try:
            import json
            with open(INSTANCE_STATE_PATH, "r", encoding="utf-8") as stream:
                state = json.load(stream)
            if int(state.get("pid") or 0) == os.getpid():
                os.unlink(INSTANCE_STATE_PATH)
        except (OSError, ValueError, TypeError):
            pass

    atexit.register(cleanup_instance_state)

    try:
        threading.Thread(target=_runtime._open_browser_when_ready, args=(url, host, port), daemon=True).start()
    except Exception:
        pass

    app.run(host=host, port=port, debug=False)


def __getattr__(name: str):
    return getattr(_runtime, name)


if __name__ == "__main__":
    main()
