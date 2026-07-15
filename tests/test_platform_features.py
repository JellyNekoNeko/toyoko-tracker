import sys
import tempfile
import unittest
import ntpath
import posixpath
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import analytics, event_center, notifications, simulation
from toyoko_tracker.models import AppConfig, HotelResult
from toyoko_tracker.providers import capability_matrix, get_provider


class ProviderPluginTests(unittest.TestCase):
    def test_builtin_provider_capability_matrix(self):
        matrix = capability_matrix(["toyoko"])
        ids = [provider["id"] for provider in matrix["providers"]]

        self.assertEqual(ids, ["toyoko", "routeinn", "dormy", "mystays", "daiwa"])
        self.assertTrue(get_provider("toyoko").capabilities.conditional_http)
        self.assertTrue(matrix["providers"][0]["enabled"])
        self.assertFalse(matrix["providers"][1]["enabled"])


class LocalNotificationPlatformTests(unittest.TestCase):
    def setUp(self):
        with notifications._PUSH_STATUS_LOCK:
            notifications._PUSH_STATUS.clear()

    def _local_status(self):
        items = notifications.notification_status_snapshot({"enable_local": True})
        return next(item for item in items if item["key"] == "local")

    def test_windows_notification_passes_unicode_through_environment(self):
        cfg = AppConfig(enable_local=True)
        with (
            patch.object(notifications.os, "name", "nt"),
            patch.object(notifications.sys, "platform", "win32"),
            patch.object(notifications.shutil, "which", side_effect=lambda name: "powershell.exe" if name == "powershell.exe" else None),
            patch.object(notifications.subprocess, "Popen") as popen,
        ):
            notifications.notify_local(cfg, '东横酱 "有房"', "房型：单人房 ✅")

        command = popen.call_args.args[0]
        environment = popen.call_args.kwargs["env"]
        self.assertEqual(command[0], "powershell.exe")
        self.assertIn("$env:TOYOKO_NOTIFICATION_TITLE", command[-1])
        self.assertNotIn("东横酱", command[-1])
        self.assertEqual(environment["TOYOKO_NOTIFICATION_TITLE"], '东横酱 "有房"')
        self.assertEqual(environment["TOYOKO_NOTIFICATION_BODY"], "房型：单人房 [OK]")
        self.assertEqual(self._local_status()["state"], "success")

    def test_linux_notification_checks_notify_send_exit_status(self):
        cfg = AppConfig(enable_local=True)
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with (
            patch.object(notifications.os, "name", "posix"),
            patch.object(notifications.sys, "platform", "linux"),
            patch.object(notifications.shutil, "which", return_value="/usr/bin/notify-send"),
            patch.object(notifications.subprocess, "run", return_value=completed) as run,
        ):
            notifications.notify_local(cfg, "Available", "A room is available")

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/notify-send")
        self.assertEqual(self._local_status()["state"], "success")

    def test_linux_notification_reports_missing_libnotify(self):
        cfg = AppConfig(enable_local=True)
        with (
            patch.object(notifications.os, "name", "posix"),
            patch.object(notifications.sys, "platform", "linux"),
            patch.object(notifications.shutil, "which", return_value=None),
        ):
            notifications.notify_local(cfg, "Available", "A room is available")

        status = self._local_status()
        self.assertEqual(status["state"], "failed")
        self.assertIn("libnotify", status["message"])

    def test_future_notification_status_never_reports_negative_age(self):
        with notifications._PUSH_STATUS_LOCK:
            notifications._PUSH_STATUS["local"] = {
                "state": "success", "message": "", "ts": 5_000.0,
            }

        with patch.object(notifications.time, "time", return_value=1_000.0):
            status = self._local_status()

        self.assertIsNone(status["age_sec"])


class PersistentPathPlatformTests(unittest.TestCase):
    def test_windows_uses_roaming_appdata(self):
        from toyoko_tracker import settings

        fake_os = SimpleNamespace(
            name="nt",
            environ={"APPDATA": r"C:\Users\jelly\AppData\Roaming"},
            path=ntpath,
        )
        with patch.object(settings, "os", fake_os):
            path = settings._default_config_dir()

        self.assertEqual(path, r"C:\Users\jelly\AppData\Roaming\toyoko-tracker")

    def test_macos_uses_application_support(self):
        from toyoko_tracker import settings

        fake_path = SimpleNamespace(
            join=posixpath.join,
            expanduser=lambda value: value.replace("~", "/Users/jelly", 1),
        )
        fake_os = SimpleNamespace(name="posix", environ={}, path=fake_path)
        with patch.object(settings, "os", fake_os), patch.object(settings.sys, "platform", "darwin"):
            path = settings._default_config_dir()

        self.assertEqual(path, "/Users/jelly/Library/Application Support/toyoko-tracker")

    def test_linux_honors_xdg_config_home(self):
        from toyoko_tracker import settings

        fake_os = SimpleNamespace(
            name="posix",
            environ={"XDG_CONFIG_HOME": "/home/jelly/.config-custom"},
            path=posixpath,
        )
        with patch.object(settings, "os", fake_os), patch.object(settings.sys, "platform", "linux"):
            path = settings._default_config_dir()

        self.assertEqual(path, "/home/jelly/.config-custom/toyoko-tracker")


class EventAndAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "platform.sqlite3")
        self.event_patch = patch.object(event_center, "HOTEL_DATABASE_PATH", self.database_path)
        self.analytics_patch = patch.object(analytics, "HOTEL_DATABASE_PATH", self.database_path)
        self.event_patch.start()
        self.analytics_patch.start()

    def tearDown(self):
        self.analytics_patch.stop()
        self.event_patch.stop()
        self.temp_dir.cleanup()

    def test_event_deduplication_and_channel_idempotency(self):
        first = event_center.publish_event("availability.available", "hotel-1", {"count": 1})
        second = event_center.publish_event("availability.available", "hotel-1", {"count": 1})

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.event_id, second.event_id)
        self.assertTrue(event_center.begin_delivery(first.event_id, "local"))
        event_center.finish_delivery(first.event_id, "local", "success")
        self.assertFalse(event_center.begin_delivery(first.event_id, "local"))
        self.assertEqual(event_center.list_events()[0]["deliveries"][0]["state"], "success")

    def test_future_event_does_not_suppress_notification_after_clock_rollback(self):
        with patch.object(event_center.time, "time", return_value=5_000.0):
            future = event_center.publish_event("availability.available", "hotel-1")
        with patch.object(event_center.time, "time", return_value=1_000.0):
            current = event_center.publish_event("availability.available", "hotel-1")

        self.assertTrue(future.created)
        self.assertTrue(current.created)
        self.assertNotEqual(future.event_id, current.event_id)

    def test_notification_dispatch_uses_event_channel_idempotency(self):
        cfg = AppConfig()
        cfg.enable_local = True
        with patch.object(notifications, "notify_local") as send_local:
            notifications.notify_push_channels(cfg, "Title", "Body", event_id="event-1")
            notifications.notify_push_channels(cfg, "Title", "Body", event_id="event-1")

        send_local.assert_called_once()

    def test_historical_trends_and_prediction(self):
        cfg = AppConfig(hotel_codes=["00001"])
        unavailable = HotelResult(
            code="00001", url="#", name="Test", available=False, provider="toyoko",
        )
        available = HotelResult(
            code="00001", url="#", name="Test", available=True, provider="toyoko",
            min_price=9000, min_remaining="2", min_price_room="Single",
        )

        self.assertEqual(analytics.record_results(cfg, [unavailable]), 1)
        self.assertEqual(analytics.record_results(cfg, [available]), 1)
        trends = analytics.trend_snapshot(["00001"])

        self.assertEqual(len(trends["points"]), 2)
        self.assertEqual(trends["hotels"][0]["latest_price"], 9000)
        self.assertTrue(trends["hotels"][0]["latest_available"])
        self.assertEqual(trends["hotels"][0]["available_checks"], 1)
        self.assertEqual(trends["hotels"][0]["unavailable_checks"], 1)
        self.assertIsNotNone(trends["hotels"][0]["prediction"]["probability_percent"])

        other_scope = AppConfig(
            hotel_codes=["00001"],
            start_date="2026-08-01",
            end_date="2026-08-02",
        )
        self.assertEqual(analytics.record_results(other_scope, [available]), 1)
        scoped = analytics.trend_snapshot(
            ["00001"],
            scope_key=analytics.scope_key_for_config(cfg),
        )
        self.assertEqual(len(scoped["points"]), 2)
        self.assertTrue(scoped["scope_filtered"])

    def test_future_observation_does_not_block_current_history(self):
        cfg = AppConfig(hotel_codes=["00001"])
        result = HotelResult(
            code="00001", url="#", name="Test", available=False, provider="toyoko",
        )
        with patch.object(analytics.time, "time", return_value=5_000.0):
            self.assertEqual(analytics.record_results(cfg, [result]), 1)
        with patch.object(analytics.time, "time", return_value=1_000.0):
            self.assertEqual(analytics.record_results(cfg, [result]), 1)
            trends = analytics.trend_snapshot(["00001"])

        self.assertEqual(len(trends["points"]), 1)
        self.assertEqual(trends["points"][0]["ts"], 1_000.0)


class SimulationAndPwaTests(unittest.TestCase):
    def test_simulated_response_and_stress_runner(self):
        parsed = simulation.parse_simulated_response(
            simulation.toyoko_response_fixture(available=True, room_count=3)
        )
        report = simulation.run_stress_test(iterations=20, concurrency=3)

        self.assertTrue(parsed["ok"])
        self.assertTrue(parsed["available"])
        self.assertEqual(report["completed"], 20)
        self.assertEqual(report["errors"], 0)

    def test_service_worker_supports_offline_data_snapshots(self):
        from toyoko_tracker.mobile_access import manifest_response, service_worker_response

        worker = service_worker_response().get_data(as_text=True)
        manifest = manifest_response().get_json()

        self.assertIn("toyoko-chan-data-v3", worker)
        self.assertIn("app.js?v=v0.7.0-traffic-1", worker)
        self.assertIn("networkFirst(event.request,CACHE)", worker)
        self.assertIn("/api/v1/results", worker)
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(len(manifest["shortcuts"]), 2)


if __name__ == "__main__":
    unittest.main()
