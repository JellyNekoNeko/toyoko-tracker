from __future__ import annotations

from flask import Flask, Response

from . import runtime as _runtime
from .app_compat import *  # noqa: F403 - legacy public API lives outside the route layer.
from .mobile_access import (
    configure_flask_app,
    logout as _mobile_logout,
    manifest_response,
    pairing_page,
    protect_request,
    qr_svg_response,
    require_local_request,
    service_worker_response,
    settings_endpoint,
)
from .traffic_meter import configure_traffic_meter, traffic_snapshot_response

app = Flask(__name__)
configure_flask_app(app)
configure_traffic_meter(app)


@app.before_request
def protect_local_api():
    return protect_request()


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


@app.route("/pair", methods=["GET", "POST"])
def pair() -> Response:
    return pairing_page()


@app.route("/mobile_access", methods=["GET", "POST"])
def mobile_access() -> Response:
    from .server import schedule_restart

    return settings_endpoint(
        bool(app.config.get("TOYOKO_LAN_BOUND", False)),
        restart_callback=schedule_restart,
    )


@app.route("/mobile_access_qr")
def mobile_access_qr() -> Response:
    return qr_svg_response()


@app.route("/mobile_logout", methods=["POST"])
def mobile_logout() -> Response:
    return _mobile_logout()


@app.route("/manifest.webmanifest")
def manifest() -> Response:
    return manifest_response()


@app.route("/service-worker.js")
def service_worker() -> Response:
    return service_worker_response()


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


@app.route("/api/v1/runtime")
def runtime_status() -> Response:
    return _runtime.runtime_status()


@app.route("/api/v1/traffic")
def traffic_status() -> Response:
    return traffic_snapshot_response()


@app.route("/api/v1/preferences", methods=["POST"])
def save_preferences() -> Response:
    return _runtime.save_preferences()


@app.route("/api/v1/tasks", methods=["GET", "POST"])
def tasks_collection() -> Response:
    return _runtime.tasks_collection()


@app.route("/api/v1/tasks/summary")
def tasks_summary() -> Response:
    return _runtime.tasks_summary()


@app.route("/api/v1/tasks/reorder", methods=["POST"])
def task_reorder() -> Response:
    return _runtime.task_reorder()


@app.route("/api/v1/tasks/<task_id>", methods=["GET", "PATCH", "DELETE"])
def task_detail(task_id: str) -> Response:
    return _runtime.task_detail(task_id)


@app.route("/api/v1/tasks/<task_id>/copy", methods=["POST"])
def task_copy(task_id: str) -> Response:
    return _runtime.task_copy(task_id)


@app.route("/api/v1/tasks/<task_id>/start", methods=["POST"])
def task_start(task_id: str) -> Response:
    return _runtime.task_start(task_id)


@app.route("/api/v1/tasks/<task_id>/pause", methods=["POST"])
def task_pause(task_id: str) -> Response:
    return _runtime.task_pause(task_id)


@app.route("/api/v1/tasks/<task_id>/status")
def task_status(task_id: str) -> Response:
    return _runtime.task_status(task_id)


@app.route("/api/v1/tasks/<task_id>/results")
def task_results(task_id: str) -> Response:
    return _runtime.task_results(task_id)


@app.route("/api/v1/tasks/<task_id>/runs")
def task_runs(task_id: str) -> Response:
    return _runtime.task_runs(task_id)


@app.route("/api/v1/alerts/rules", methods=["GET", "POST"])
def alert_rules_collection() -> Response:
    return _runtime.alert_rules_collection()


@app.route("/api/v1/alerts/rules/preview", methods=["POST"])
def alert_rule_preview() -> Response:
    return _runtime.alert_rule_preview()


@app.route("/api/v1/alerts/rules/<rule_id>", methods=["GET", "PATCH", "DELETE"])
def alert_rule_detail(rule_id: str) -> Response:
    return _runtime.alert_rule_detail(rule_id)


@app.route("/api/v1/alerts/policy", methods=["GET", "PATCH"])
def alert_policy_detail() -> Response:
    return _runtime.alert_policy_detail()


@app.route("/api/v1/alerts/history")
def alert_history_status() -> Response:
    return _runtime.alert_history_status()


@app.route("/api/v1/alerts/batches/<batch_id>/retry", methods=["POST"])
def alert_batch_retry(batch_id: str) -> Response:
    return _runtime.alert_batch_retry(batch_id)


@app.route("/api/v1/alerts/calendar-badges")
def alert_calendar_badges_status() -> Response:
    return _runtime.alert_calendar_badges_status()


@app.route("/api/v1/cache")
def cache_status() -> Response:
    return _runtime.cache_status()


@app.route("/api/v1/cache/clear", methods=["POST"])
def cache_clear() -> Response:
    return _runtime.cache_clear()


@app.route("/api/v1/providers")
def provider_capabilities_status() -> Response:
    return _runtime.provider_capabilities_status()


@app.route("/api/v1/price-calendar", methods=["GET", "POST"])
def price_calendar_status() -> Response:
    return _runtime.price_calendar_status()


@app.route("/api/v1/price-calendar/refresh", methods=["POST"])
def price_calendar_refresh() -> Response:
    return _runtime.price_calendar_refresh()


@app.route("/api/v1/events")
def events_status() -> Response:
    return _runtime.events_status()


@app.route("/api/v1/trends")
def trends_status() -> Response:
    return _runtime.trends_status()


@app.route("/api/v1/simulation/stress", methods=["POST"])
def simulation_stress() -> Response:
    local_only = require_local_request()
    if local_only is not None:
        return local_only
    return _runtime.simulation_stress()


@app.route("/api/v1/results")
def results_status() -> Response:
    return _runtime.results_status()


@app.route("/api/v1/availability-logs")
def availability_logs_status() -> Response:
    return _runtime.availability_logs_status()


@app.route("/api/v1/logs")
def logs_status() -> Response:
    return _runtime.logs_status()


@app.route("/hotel_info")
def hotel_info() -> Response:
    return _runtime.hotel_info()


@app.route("/health")
def health() -> Response:
    return _runtime.health()


@app.route("/update_status")
def update_status() -> Response:
    return _runtime.update_status()


@app.route("/update_check", methods=["POST"])
def update_check() -> Response:
    return _runtime.update_check()


@app.route("/hotel_catalog_status")
def hotel_catalog_status() -> Response:
    return _runtime.hotel_catalog_status()


@app.route("/hotel_catalog_refresh", methods=["POST"])
def hotel_catalog_refresh() -> Response:
    return _runtime.hotel_catalog_refresh()


@app.route("/hotel_catalog_acknowledge", methods=["POST"])
def hotel_catalog_acknowledge() -> Response:
    return _runtime.hotel_catalog_acknowledge()


@app.route("/provider_catalog_status")
def provider_catalog_status() -> Response:
    return _runtime.provider_catalog_status()


@app.route("/provider_catalog_refresh", methods=["POST"])
def provider_catalog_refresh() -> Response:
    return _runtime.provider_catalog_refresh()


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
    from .server import run

    run(app)


def __getattr__(name: str):
    return getattr(_runtime, name)


if __name__ == "__main__":
    main()
