import sqlite3
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from toyoko_tracker import alerting, runtime, workspace
from toyoko_tracker.app import app
from toyoko_tracker.models import AppConfig, HotelResult


def _config() -> AppConfig:
    return AppConfig(
        start_date="2026-07-20",
        end_date="2026-07-21",
        hotel_codes=["00001"],
        selected_hotels=[{
            "code": "00001",
            "provider": "toyoko",
            "name": "Test Hotel",
        }],
        loop_interval_seconds=60,
    )


def _result(price=9800, member=8800, available=True) -> HotelResult:
    return HotelResult(
        code="00001",
        provider="toyoko",
        name="Test Hotel",
        url="https://example.test/00001",
        available=available,
        min_price=price,
        min_price_text=f"¥{price:,}" if price is not None else None,
        min_member_price_text=f"¥{member:,}" if member is not None else None,
        checked_at="2026-07-17T10:00:00+00:00",
        http_status=200,
    )


def _database_context():
    temporary = tempfile.TemporaryDirectory()
    database = str(Path(temporary.name) / "alerts.sqlite3")
    patches = [
        patch.object(workspace, "HOTEL_DATABASE_PATH", database),
        patch.object(alerting, "HOTEL_DATABASE_PATH", database),
    ]
    for item in patches:
        item.start()
    workspace.initialize_workspace()
    workspace.ensure_default_task(_config())
    alerting.initialize_alerting()
    return temporary, patches, database


def _close_context(temporary, patches):
    for item in reversed(patches):
        item.stop()
    temporary.cleanup()


def test_rule_crud_policy_revision_and_schema():
    temporary, patches, database = _database_context()
    try:
        created = alerting.create_rule("default", {
            "name": "Target",
            "rule_type": "target_price",
            "threshold_value": 10000,
            "hotel_code": "00001",
            "date_start": "2026-07-20",
            "date_end": "2026-07-31",
            "config": {
                "price_basis": "best",
                "token": "rule-secret",
            },
        })
        updated = alerting.update_rule(
            created["rule_id"],
            {"critical": True},
            expected_revision=created["revision"],
        )
        assert updated["critical"] is True
        assert updated["revision"] == created["revision"] + 1
        policy = alerting.update_policy("default", {
            "timezone": "Asia/Shanghai",
            "quiet_start": "23:00",
            "quiet_end": "07:00",
            "aggregation_window_seconds": 300,
            "digest_mode": "daily",
            "digest_time": "09:30",
            "allow_critical": True,
            "config": {"password": "policy-secret"},
        }, expected_revision=0)
        assert policy["revision"] == 1
        assert policy["digest_mode"] == "daily"
        assert "rule-secret" not in str(created)
        assert "policy-secret" not in str(policy)
        with sqlite3.connect(database) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert {
            "alert_observations",
            "alert_events",
            "alert_batches",
            "alert_deliveries",
        }.issubset(tables)
        deleted = alerting.delete_rule(
            created["rule_id"], expected_revision=updated["revision"]
        )
        assert deleted["rule_id"] == created["rule_id"]
    finally:
        _close_context(temporary, patches)


def test_target_member_and_drop_rules_use_transition_baselines():
    temporary, patches, _database = _database_context()
    try:
        alerting.update_policy("default", {
            "timezone": "UTC",
            "aggregation_window_seconds": 120,
        }, expected_revision=0)
        alerting.create_rule("default", {
            "name": "Target",
            "rule_type": "target_price",
            "threshold_value": 10000,
        })
        alerting.create_rule("default", {
            "name": "Member",
            "rule_type": "member_price",
            "threshold_value": 9000,
        })
        alerting.create_rule("default", {
            "name": "Drop",
            "rule_type": "price_drop",
            "threshold_percent": 10,
            "config": {"price_basis": "non_member"},
        })

        first = alerting.evaluate_results(
            "default", [_result()], "2026-07-20", "2026-07-21", now=1000
        )
        assert {item["payload"]["event_type"] for item in first} == {
            "price.target_reached",
            "price.member_target_reached",
        }
        assert len({item["batch_id"] for item in first}) == 1

        second = alerting.evaluate_results(
            "default",
            [_result(price=8000, member=7800)],
            "2026-07-20",
            "2026-07-21",
            now=1100,
        )
        assert [item["payload"]["event_type"] for item in second] == ["price.drop"]

        unchanged = alerting.evaluate_results(
            "default",
            [_result(price=8000, member=7800)],
            "2026-07-20",
            "2026-07-21",
            now=1200,
        )
        assert unchanged == []
        assert alerting.alert_summary("default")["events"] == 3
    finally:
        _close_context(temporary, patches)


def test_quiet_hours_daily_digest_critical_override_and_dispatch_trace():
    temporary, patches, _database = _database_context()
    try:
        quiet_now = datetime(2026, 7, 17, 23, 0, tzinfo=timezone.utc).timestamp()
        alerting.update_policy("default", {
            "timezone": "UTC",
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "aggregation_window_seconds": 120,
            "digest_mode": "off",
            "allow_critical": True,
        }, expected_revision=0)
        alerting.create_rule("default", {
            "name": "Quiet target",
            "rule_type": "target_price",
            "threshold_value": 10000,
        })
        events = alerting.evaluate_results(
            "default", [_result()], "2026-07-20", "2026-07-21", now=quiet_now
        )
        assert events[0]["mode"] == "quiet_queue"
        assert events[0]["due_at"] == datetime(
            2026, 7, 18, 7, 0, tzinfo=timezone.utc
        ).timestamp()
        assert alerting.claim_due_batches(now=quiet_now) == []

        rule = alerting.create_rule("default", {
            "name": "Critical member",
            "rule_type": "member_price",
            "threshold_value": 9000,
            "critical": True,
        })
        critical = alerting.evaluate_results(
            "default", [_result()], "2026-07-20", "2026-07-21", now=quiet_now + 1
        )
        assert critical[0]["mode"] == "critical"

        delivered = []

        def send(_cfg, title, body, _url):
            delivered.append((title, body))
            return {
                "local": {"state": "sent", "detail": "sent OK"},
                "email": {"state": "failed", "detail": "password=hidden-secret"},
            }

        dispatcher = alerting.AlertDispatcher(
            lambda _task_id: _config(),
            send,
            poll_interval=0.01,
        )
        assert dispatcher.deliver_due_once(now=quiet_now + 1) == 1
        history = alerting.list_history(task_id="default")
        critical_history = next(item for item in history if item["rule_id"] == rule["rule_id"])
        assert critical_history["state"] == "partial"
        assert {item["state"] for item in critical_history["deliveries"]} == {
            "sent",
            "failed",
        }
        assert "hidden-secret" not in str(critical_history["deliveries"])
        assert delivered

        retried_channels = []

        def retry_send(_cfg, _title, _body, _url, channels):
            retried_channels.extend(channels or [])
            return {
                channel: {"state": "sent", "detail": "retry OK"}
                for channel in (channels or [])
            }

        queued_retry = alerting.retry_batch(critical_history["batch_id"])
        assert queued_retry["state"] == "queued"
        assert alerting.list_history(task_id="default")[0]["state"] == "queued"
        retry_dispatcher = alerting.AlertDispatcher(
            lambda _task_id: _config(),
            retry_send,
            poll_interval=0.01,
        )
        assert retry_dispatcher.deliver_due_once(now=quiet_now + 2) == 1
        retried = alerting.get_batch(critical_history["batch_id"])
        assert retried["state"] == "sent"
        assert retried_channels == ["email"]
        assert {item["channel"] for item in retried["deliveries"]} == {
            "local",
            "email",
        }

        current_policy = alerting.get_policy("default")
        digest = alerting.update_policy("default", {
            "quiet_start": "",
            "quiet_end": "",
            "digest_mode": "daily",
            "digest_time": "09:00",
        }, expected_revision=current_policy["revision"])
        assert digest["digest_mode"] == "daily"
    finally:
        _close_context(temporary, patches)


def test_alert_api_rules_policy_history_and_calendar_badges():
    temporary, patches, _database = _database_context()
    try:
        app.config.update(TESTING=True)

        class Dispatcher:
            running = True

            def start(self):
                return None

            def wake(self):
                return None

        with patch.object(runtime, "_CONFIG", _config()), \
             patch.object(runtime, "_ALERT_DISPATCHER", Dispatcher()):
            client = app.test_client()
            created_response = client.post("/api/v1/alerts/rules", json={
                "task_id": "default",
                "name": "API target",
                "rule_type": "target_price",
                "threshold_value": 10000,
            })
            assert created_response.status_code == 201
            created = created_response.get_json()["rule"]

            policy_response = client.patch("/api/v1/alerts/policy", json={
                "task_id": "default",
                "timezone": "UTC",
                "quiet_start": "23:00",
                "quiet_end": "07:00",
                "digest_mode": "daily",
                "digest_time": "09:00",
                "aggregation_window_seconds": 60,
                "allow_critical": True,
                "expected_revision": 0,
            })
            assert policy_response.status_code == 200

            alerting.evaluate_results(
                "default", [_result()], "2026-07-20", "2026-07-21", now=1000
            )
            history = client.get(
                "/api/v1/alerts/history?task_id=default"
            ).get_json()
            assert history["history"][0]["rule_id"] == created["rule_id"]
            badges = client.get(
                "/api/v1/alerts/calendar-badges"
                "?task_id=default&hotel_code=00001&month=2026-07"
            ).get_json()
            assert badges["badges"]["2026-07-20"]["count"] == 1

            listed = client.get(
                "/api/v1/alerts/rules?task_id=default"
            ).get_json()
            assert listed["rules"][0]["name"] == "API target"
            assert listed["policy"]["digest_mode"] == "daily"

            class TaskService:
                def start(self):
                    return None

                def public_task(self, _task_id, include_results=False):
                    return {
                        "config": workspace.get_task("default")["config"],
                        "results": [asdict(_result())]
                        if include_results
                        else [],
                    }

            with patch.object(runtime, "_TASK_SERVICE", TaskService()):
                preview = client.post("/api/v1/alerts/rules/preview", json={
                    "task_id": "default",
                    "rule": {
                        "name": "Preview",
                        "rule_type": "target_price",
                        "threshold_value": 10000,
                    },
                })
            assert preview.status_code == 200
            assert preview.get_json()["match_count"] == 1
    finally:
        _close_context(temporary, patches)


def test_daily_digest_due_time_and_restart_requeues_sending_batch():
    temporary, patches, database = _database_context()
    try:
        morning = datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc).timestamp()
        alerting.update_policy("default", {
            "timezone": "UTC",
            "quiet_start": "",
            "quiet_end": "",
            "digest_mode": "daily",
            "digest_time": "09:00",
            "aggregation_window_seconds": 30,
        }, expected_revision=0)
        alerting.create_rule("default", {
            "name": "Digest target",
            "rule_type": "target_price",
            "threshold_value": 10000,
        })
        events = alerting.evaluate_results(
            "default", [_result()], "2026-07-20", "2026-07-21", now=morning
        )
        assert events[0]["mode"] == "daily_digest"
        assert events[0]["due_at"] == datetime(
            2026, 7, 17, 9, 0, tzinfo=timezone.utc
        ).timestamp()
        batch_id = events[0]["batch_id"]
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE alert_batches SET state='sending',due_at=? WHERE batch_id=?",
                (morning + 86400, batch_id),
            )

        deliveries = []
        dispatcher = alerting.AlertDispatcher(
            lambda _task_id: _config(),
            lambda *_args: deliveries.append("sent") or {
                "local": {"state": "sent"}
            },
            poll_interval=0.01,
        )
        dispatcher.start()
        deadline = time.monotonic() + 1
        while alerting.get_batch(batch_id)["state"] != "sent" and time.monotonic() < deadline:
            time.sleep(0.01)
        dispatcher.stop()
        assert alerting.get_batch(batch_id)["state"] == "sent"
        assert deliveries == ["sent"]
    finally:
        _close_context(temporary, patches)


def test_repeated_drop_inside_cooldown_is_aggregated_into_one_event():
    temporary, patches, _database = _database_context()
    try:
        alerting.create_rule("default", {
            "name": "Drop aggregate",
            "rule_type": "price_drop",
            "threshold_value": 500,
            "cooldown_seconds": 3600,
            "config": {"price_basis": "non_member"},
        })
        alerting.evaluate_results(
            "default", [_result(price=10000)], "2026-07-20", "2026-07-21", now=1000
        )
        alerting.evaluate_results(
            "default", [_result(price=9000)], "2026-07-20", "2026-07-21", now=1100
        )
        alerting.evaluate_results(
            "default", [_result(price=8000)], "2026-07-20", "2026-07-21", now=1200
        )
        history = alerting.list_history(task_id="default")
        assert len(history) == 1
        assert history[0]["event_type"] == "price.drop"
        assert history[0]["occurrence_count"] == 2
        assert history[0]["payload"]["price"] == 8000
    finally:
        _close_context(temporary, patches)


def test_scoped_vacancy_rule_only_suppresses_matching_legacy_transition():
    cfg = _config()
    second = _result()
    second.code = "00002"
    calls = []

    def process(call_cfg, results, _start, _end):
        calls.append({
            "codes": [result.code for result in results],
            "available": call_cfg.notify_available,
            "unavailable": call_cfg.notify_unavailable,
        })
        return []

    with patch.object(runtime, "_list_alert_rules", return_value=[{
        "rule_type": "vacancy_transition",
        "hotel_code": "00001",
        "date_start": "2026-07-20",
        "date_end": "2026-07-20",
    }]), patch.object(runtime, "process_notifications", side_effect=process):
        runtime._process_legacy_notifications(
            "default",
            cfg,
            [_result(), second],
            "2026-07-20",
            "2026-07-21",
        )

    assert calls == [
        {"codes": ["00002"], "available": True, "unavailable": True},
        {"codes": ["00001"], "available": False, "unavailable": False},
    ]


def test_unknown_observation_preserves_price_and_vacancy_baselines():
    temporary, patches, _database = _database_context()
    try:
        alerting.create_rule("default", {
            "name": "Stable target",
            "rule_type": "target_price",
            "threshold_value": 10000,
        })
        alerting.create_rule("default", {
            "name": "Drop after error",
            "rule_type": "price_drop",
            "threshold_value": 500,
            "config": {"price_basis": "non_member"},
        })
        alerting.create_rule("default", {
            "name": "Vacancy",
            "rule_type": "vacancy_transition",
            "config": {"direction": "available"},
        })
        first = alerting.evaluate_results(
            "default", [_result(price=10000)], "2026-07-20", "2026-07-21", now=1000
        )
        assert {event["payload"]["event_type"] for event in first} == {
            "price.target_reached",
            "availability.available",
        }

        unknown = _result(price=None, member=None, available=None)
        assert alerting.evaluate_results(
            "default", [unknown], "2026-07-20", "2026-07-21", now=1100
        ) == []
        after_error = alerting.evaluate_results(
            "default", [_result(price=9000)], "2026-07-20", "2026-07-21", now=1200
        )
        assert [event["payload"]["event_type"] for event in after_error] == [
            "price.drop"
        ]
    finally:
        _close_context(temporary, patches)


def test_daily_digest_handles_dst_spring_forward_with_a_valid_utc_due_time():
    temporary, patches, _database = _database_context()
    try:
        zone = ZoneInfo("America/New_York")
        before_jump = datetime(2026, 3, 8, 1, 30, tzinfo=zone).timestamp()
        alerting.update_policy("default", {
            "timezone": "America/New_York",
            "digest_mode": "daily",
            "digest_time": "02:30",
            "aggregation_window_seconds": 0,
        }, expected_revision=0)
        alerting.create_rule("default", {
            "name": "DST target",
            "rule_type": "target_price",
            "threshold_value": 10000,
        })
        event = alerting.evaluate_results(
            "default",
            [_result()],
            "2026-07-20",
            "2026-07-21",
            now=before_jump,
        )[0]
        local_due = datetime.fromtimestamp(event["due_at"], zone)
        assert local_due.date().isoformat() == "2026-03-08"
        assert (local_due.hour, local_due.minute) == (3, 30)
    finally:
        _close_context(temporary, patches)


def test_semantic_rule_update_resets_baseline_and_uses_new_revision():
    temporary, patches, _database = _database_context()
    try:
        rule = alerting.create_rule("default", {
            "name": "Editable target",
            "rule_type": "target_price",
            "threshold_value": 10000,
            "cooldown_seconds": 3600,
        })
        first = alerting.evaluate_results(
            "default", [_result(price=9000)], "2026-07-20", "2026-07-21", now=1000
        )
        assert len(first) == 1
        updated = alerting.update_rule(
            rule["rule_id"],
            {"threshold_value": 8000},
            expected_revision=rule["revision"],
        )
        assert alerting.evaluate_results(
            "default", [_result(price=9000)], "2026-07-20", "2026-07-21", now=1100
        ) == []
        second = alerting.evaluate_results(
            "default", [_result(price=7500)], "2026-07-20", "2026-07-21", now=1200
        )
        assert len(second) == 1
        assert updated["revision"] == 2
        assert alerting.alert_summary("default")["events"] == 2
    finally:
        _close_context(temporary, patches)
