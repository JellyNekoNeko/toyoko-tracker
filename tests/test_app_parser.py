import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from bs4 import BeautifulSoup
    from toyoko_tracker import app as tracker_app
except ModuleNotFoundError as exc:
    BeautifulSoup = None
    tracker_app = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def _rendered(html: str) -> tracker_app.RenderedPage:
    return tracker_app.RenderedPage(BeautifulSoup(html, "html.parser"), BeautifulSoup(html, "html.parser").get_text(" ", strip=True))


@unittest.skipIf(tracker_app is None, f"runtime dependencies missing: {IMPORT_ERROR}")
class AppParserTests(unittest.TestCase):
    def test_parse_price_and_remaining(self):
        self.assertEqual(tracker_app._parse_price_int("¥8,700"), 8700)
        self.assertEqual(tracker_app._parse_price_int("Club Card Member Price ¥12,300"), 12300)
        self.assertIsNone(tracker_app._parse_price_int("No price"))
        self.assertEqual(tracker_app.parse_remaining("Only 3 Rooms Left"), "3")
        self.assertEqual(tracker_app.parse_remaining("Only 1 Room Left"), "1")
        self.assertEqual(tracker_app.parse_remaining("Reserve"), "≥10")

    def test_parse_coordinate_query_and_radius_distance(self):
        self.assertEqual(tracker_app._parse_coordinate_query("35.6812,139.7671"), (35.6812, 139.7671))
        self.assertEqual(
            tracker_app._parse_coordinate_query("https://www.google.com/maps/place/Tokyo/@35.6812,139.7671,17z"),
            (35.6812, 139.7671),
        )
        self.assertEqual(
            tracker_app._parse_coordinate_query("https://maps.google.com/?q=35.6812,139.7671"),
            (35.6812, 139.7671),
        )
        self.assertIsNone(tracker_app._parse_coordinate_query("Tokyo Station"))
        self.assertLess(tracker_app._haversine_km(35.6812, 139.7671, 35.6813, 139.7672), 0.1)

    def test_extract_maps_coordinates_from_common_shapes(self):
        self.assertEqual(
            tracker_app._extract_maps_coordinates("https://www.google.com/maps/place/x/data=!3d35.6812!4d139.7671"),
            (35.6812, 139.7671),
        )
        self.assertEqual(
            tracker_app._extract_maps_coordinates('{"center":{"lat":35.6812,"lng":139.7671}}'),
            (35.6812, 139.7671),
        )

    def test_radius_filter_uses_coordinates_and_distance(self):
        hotels = [
            {"code": "00001", "name": "Near", "name_en": "Near", "lat": 35.6813, "lng": 139.7672},
            {"code": "00002", "name": "Far", "name_en": "Far", "lat": 34.6937, "lng": 135.5023},
        ]
        with patch.object(tracker_app, "_all_hotels_for_radius", lambda primary_language=None: hotels):
            center, results = tracker_app._hotels_within_radius("35.6812,139.7671", 1, "zh_cn")

        self.assertEqual(center["source"], "coordinates")
        self.assertEqual([h["code"] for h in results], ["00001"])
        self.assertIn("distance_km", results[0])

    def test_radius_filter_uses_nominatim_for_names(self):
        hotels = [
            {"code": "00001", "name": "Near", "name_en": "Near", "lat": 35.4559, "lng": 139.6287},
        ]
        with patch.object(tracker_app, "_all_hotels_for_radius", lambda primary_language=None: hotels), \
             patch.object(tracker_app, "_geocode_nominatim", lambda query: (35.4558613, 139.6286854, "nominatim")):
            center, results = tracker_app._hotels_within_radius("Yokohama", 1, "zh_cn")

        self.assertEqual(center["source"], "nominatim")
        self.assertEqual([h["code"] for h in results], ["00001"])

    def test_check_hotel_ignores_accessible_rooms(self):
        html = """
        <html><body>
          <h1 class="room_plan_title">Toyoko Inn Test</h1>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Single Room</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_title">Basic Plan</div>
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥8,700</span>
              </div>
              <div class="SearchResultRoomPlanChildCard_member-section">
                <span class="SearchResultRoomPlanChildCard_value">¥8,200</span>
              </div>
              Only 3 Rooms Left
            </div>
          </div>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Double Room</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_title">Basic Plan</div>
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥12,000</span>
              </div>
              Reserve
            </div>
          </div>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Accessible Room</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥7,000</span>
              </div>
              Only 1 Room Left
            </div>
          </div>
        </body></html>
        """
        with patch.object(tracker_app, "fetch_rendered_any", lambda cfg, renderer, url: _rendered(html)):
            cfg = tracker_app.AppConfig()
            cfg.engine = "playwright"
            cfg.smoking = "all"

            result = tracker_app.check_hotel(cfg, None, "00001", "2026-05-09", "2026-05-10")

        self.assertIs(result.available, True)
        self.assertEqual(result.min_price, 8700)
        self.assertEqual(result.min_price_room, "Single Room")
        self.assertEqual(result.min_member_price_text, "¥8,200")
        self.assertEqual(
            result.offers_display,
            [
                {
                    "price_text": "¥8,700",
                    "member_price_text": "¥8,200",
                    "remaining_norm": "3",
                    "room_title": "Single Room",
                },
                {
                    "price_text": "¥12,000",
                    "member_price_text": None,
                    "remaining_norm": "≥10",
                    "room_title": "Double Room",
                }
            ],
        )

    def test_check_hotel_treats_accessible_only_as_unavailable(self):
        html = """
        <html><body>
          <h1 class="room_plan_title">Toyoko Inn Test</h1>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Heartful Single</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥7,000</span>
              </div>
              Only 1 Room Left
            </div>
          </div>
        </body></html>
        """
        with patch.object(tracker_app, "fetch_rendered_any", lambda cfg, renderer, url: _rendered(html)):
            cfg = tracker_app.AppConfig()
            cfg.engine = "playwright"
            result = tracker_app.check_hotel(cfg, None, "00001", "2026-05-09", "2026-05-10")

        self.assertIs(result.available, False)
        self.assertEqual(result.offers_display, [])

    def test_check_hotel_marks_unmet_room_requirement(self):
        html = """
        <html><body>
          <h1 class="room_plan_title">Toyoko Inn Test</h1>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Single Room</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥8,700</span>
              </div>
              Reserve
            </div>
          </div>
        </body></html>
        """
        with patch.object(tracker_app, "fetch_rendered_any", lambda cfg, renderer, url: _rendered(html)):
            cfg = tracker_app.AppConfig()
            cfg.engine = "playwright"
            cfg.room_requirement = "twin"

            result = tracker_app.check_hotel(cfg, None, "00001", "2026-05-09", "2026-05-10")

        self.assertIs(result.requirement_unmet, True)
        self.assertEqual(result.offers_display, [])

    def test_no_smoking_search_filters_explicit_smoking_rooms(self):
        html = """
        <html><body>
          <h1 class="room_plan_title">Toyoko Inn Test</h1>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Single Room</div>
            <div>喫煙</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥8,700</span>
              </div>
              Only 1 Room Left
            </div>
          </div>
          <div class="SearchResultRoomPlanParentCard_card">
            <div class="SearchResultRoomPlanParentCard_title">Single Room</div>
            <div>禁煙</div>
            <div class="SearchResultRoomPlanChildCard_card-wrapper">
              <div class="SearchResultRoomPlanChildCard_price">
                <span class="SearchResultRoomPlanChildCard_value">¥9,700</span>
              </div>
              Only 2 Rooms Left
            </div>
          </div>
        </body></html>
        """
        with patch.object(tracker_app, "fetch_rendered_any", lambda cfg, renderer, url: _rendered(html)):
            cfg = tracker_app.AppConfig()
            cfg.engine = "playwright"
            cfg.smoking = "noSmoking"

            result = tracker_app.check_hotel(cfg, None, "00001", "2026-05-09", "2026-05-10")

        self.assertIs(result.available, True)
        self.assertEqual(result.min_price, 9700)
        self.assertEqual(result.offers_display, [{
            "price_text": "¥9,700",
            "member_price_text": None,
            "remaining_norm": "2",
            "room_title": "Single Room",
            "room_smoking": "non_smoking",
        }])

    def test_no_smoking_search_treats_smoking_only_as_unavailable(self):
        payload = {
            "props": {
                "pageProps": {
                    "planResponse": {
                        "hotelTitle": "Toyoko Inn HTTP Test",
                        "roomTypeList": [
                            {
                                "roomTypeName": "Single Room",
                                "specs": {"isSmoking": True},
                                "plans": [
                                    {
                                        "planName": "Basic Plan",
                                        "price": {"generalPrice": 9100, "membershipPrice": 8700},
                                        "vacant": {"generalVacantRoom": 2, "membershipVacantRoom": 2},
                                    }
                                ],
                            },
                        ],
                    }
                }
            }
        }
        html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{tracker_app.json.dumps(payload)}</script></body></html>'

        class FakeResponse:
            text = html

            def raise_for_status(self):
                return None

        with patch.object(tracker_app.requests, "get", lambda *args, **kwargs: FakeResponse()):
            cfg = tracker_app.AppConfig()
            cfg.engine = "http"
            cfg.smoking = "noSmoking"

            result = tracker_app.check_hotel(cfg, None, "00001", "2026-05-09", "2026-05-10")

        self.assertIs(result.available, False)
        self.assertEqual(result.offers_display, [])

    def test_smoking_preferences_reject_unknown_smoking_state(self):
        unknown_offer = {"room_title": "Single Room", "room_smoking": None}

        self.assertFalse(tracker_app._offer_matches_smoking_preference(unknown_offer, "noSmoking"))
        self.assertFalse(tracker_app._offer_matches_smoking_preference(unknown_offer, "Smoking"))
        self.assertTrue(tracker_app._offer_matches_smoking_preference(unknown_offer, "all"))

    def test_check_hotel_http_reads_next_data_plan_response(self):
        payload = {
            "props": {
                "pageProps": {
                    "planResponse": {
                        "hotelTitle": "Toyoko Inn HTTP Test",
                        "roomTypeList": [
                            {
                                "roomTypeName": "Single Room",
                                "plans": [
                                    {
                                        "planName": "Basic Plan",
                                        "price": {"generalPrice": 9100, "membershipPrice": 8700},
                                        "vacant": {"generalVacantRoom": 2, "membershipVacantRoom": 2},
                                    }
                                ],
                            },
                            {
                                "roomTypeName": "Accessible Room",
                                "plans": [
                                    {
                                        "planName": "Accessible",
                                        "price": {"generalPrice": 5000},
                                        "vacant": {"generalVacantRoom": 1},
                                    }
                                ],
                            },
                        ],
                    }
                }
            }
        }
        html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{tracker_app.json.dumps(payload)}</script></body></html>'

        class FakeResponse:
            text = html

            def raise_for_status(self):
                return None

        with patch.object(tracker_app.requests, "get", lambda *args, **kwargs: FakeResponse()):
            cfg = tracker_app.AppConfig()
            cfg.engine = "http"
            cfg.smoking = "all"

            result = tracker_app.check_hotel(cfg, None, "00001", "2026-05-09", "2026-05-10")

        self.assertIs(result.available, True)
        self.assertEqual(result.name, "Toyoko Inn HTTP Test")
        self.assertEqual(result.min_price, 9100)
        self.assertEqual(result.min_member_price_text, "¥ 8,700")
        self.assertEqual(result.offers_display, [{
            "price_text": "¥ 9,100",
            "member_price_text": "¥ 8,700",
            "remaining_norm": "2",
            "room_title": "Single Room",
        }])

    def test_bark_key_validation_rejects_device_token_length(self):
        from toyoko_tracker.notifications import validate_bark_key

        self.assertEqual(validate_bark_key("N8yRQfPsATtXrqo86EsqVd"), (True, ""))
        ok, message = validate_bark_key("02217983c6eedd7898d8fdfd1398d3cf2def537fe4ba6af343fa0b134ba05a4d")
        self.assertFalse(ok)
        self.assertIn("Device Key", message)

    def test_notification_type_defaults(self):
        cfg = tracker_app.AppConfig()

        self.assertTrue(cfg.notify_available)
        self.assertTrue(cfg.notify_unavailable)
        self.assertTrue(cfg.notify_availability_count_change)
        self.assertTrue(cfg.notify_start)
        self.assertTrue(cfg.notify_stop)
        self.assertFalse(cfg.notify_search_error)
        self.assertFalse(cfg.bark_critical_enabled)
        self.assertEqual(cfg.bark_critical_volume, 5)
        self.assertEqual(cfg.bark_critical_sound, "alarm")

    def test_available_notification_switch_still_returns_watch_code(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        cfg.notify_available = False
        notifications.clear_alert_state()
        result = tracker_app.HotelResult(code="00001", url="https://example.test", name="Test", available=True)

        with patch.object(notifications, "notify_push_channels") as mock_notify:
            newly_available = notifications.process_notifications(cfg, [result], "2026-05-16", "2026-05-17")

        self.assertEqual(newly_available, ["00001"])
        mock_notify.assert_not_called()

    def test_bark_critical_alert_sends_room_message_once(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        cfg.enable_bark = True
        cfg.bark_key = "N8yRQfPsATtXrqo86EsqVd"
        cfg.bark_critical_enabled = True
        cfg.bark_critical_volume = 7
        cfg.bark_critical_sound = "alarm"

        with patch.object(notifications, "_send_bark_attempts", return_value=(True, "ok")) as mock_send, \
             patch.object(notifications.time, "sleep") as mock_sleep:
            notifications.notify_bark(cfg, "Room available", "Details", "https://example.test")

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(mock_send.call_args.args[2], "Room available")
        self.assertEqual(mock_send.call_args.args[3], "Details\n\nhttps://example.test")
        self.assertEqual(mock_send.call_args.args[5], {"level": "critical", "volume": 7, "sound": "alarm"})
        mock_sleep.assert_not_called()

    def test_area_selector_uses_default_dates(self):
        from toyoko_tracker.settings import DEFAULT_END_DATE, DEFAULT_START_DATE

        with patch.object(tracker_app.requests, "get") as mock_get:
            mock_get.side_effect = RuntimeError("stop after params check")

            with self.assertRaises(RuntimeError):
                tracker_app._fetch_hotels_for_selector_locale("lcl_id", 1, "eng")

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["start"], DEFAULT_START_DATE)
        self.assertEqual(params["end"], DEFAULT_END_DATE)

    def test_zero_repeat_count_disables_repeat_reminders(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        self.assertEqual(cfg.available_alert_repeat, 0)
        cfg.available_alert_repeat = 0
        cfg.available_alert_repeat_interval_sec = 60
        result = tracker_app.HotelResult(code="00001", url="https://example.test", name="Test", available=True)
        notifications.clear_alert_state()

        with patch.object(notifications, "notify_push_channels") as mock_notify:
            notifications.process_notifications(cfg, [result], "2026-05-16", "2026-05-17")
            notifications.process_notifications(cfg, [result], "2026-05-16", "2026-05-17")

        self.assertEqual(mock_notify.call_count, 1)

    def test_available_room_count_change_sends_independent_notification(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        cfg.notify_available = False
        cfg.notify_availability_count_change = True
        notifications.clear_alert_state()
        first = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test", available=True,
            min_remaining="1", min_price_text="¥8,000", min_price_room="Single",
        )
        second = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test", available=True,
            min_remaining="3", min_price_text="¥8,000", min_price_room="Single",
        )

        with patch.object(notifications, "notify_push_channels") as mock_notify:
            notifications.process_notifications(cfg, [first], "2026-05-16", "2026-05-17")
            notifications.process_notifications(cfg, [second], "2026-05-16", "2026-05-17")

        self.assertEqual(mock_notify.call_count, 1)
        self.assertIn("Available Room Count Changed", mock_notify.call_args.args[1])

    def test_availability_log_tracks_closed_duration(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        notifications.clear_alert_state()
        available = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test", available=True,
            min_remaining="1", min_price_text="¥8,000", min_price_room="Single",
        )
        unavailable = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test", available=False,
        )

        with patch.object(notifications, "notify_push_channels"):
            notifications.process_notifications(cfg, [available], "2026-05-16", "2026-05-17")
            notifications.process_notifications(cfg, [unavailable], "2026-05-16", "2026-05-17")

        logs = notifications.availability_log_snapshot()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["code"], "00001")
        self.assertIsNotNone(logs[0]["disappeared_ts"])
        self.assertIsInstance(logs[0]["duration_sec"], int)


@unittest.skipIf(tracker_app is None, f"runtime dependencies missing: {IMPORT_ERROR}")
class AppRouteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = tracker_app.app.test_client()

    def test_health_reports_current_version(self):
        response = self.client.get("/health")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["app"], "toyoko-tracker")
        self.assertEqual(payload["version"], tracker_app.__version__)

    def test_status_does_not_expose_notification_secrets(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.bot_token = "telegram-secret"
        cfg.bark_key = "bark-secret"
        cfg.serverchan_sendkey = "serverchan-secret"
        cfg.smtp_pass = "smtp-secret"
        with patch.object(runtime, "_CONFIG", cfg):
            payload = self.client.get("/status").get_json()

        public_config = payload["config"]
        for key in ("bot_token", "bark_key", "serverchan_sendkey", "smtp_pass"):
            self.assertNotIn(key, public_config)
            self.assertTrue(public_config["configured_secrets"][key])

    def test_cross_site_write_request_is_rejected(self):
        response = self.client.post(
            "/stop",
            headers={"Origin": "https://example.com", "Sec-Fetch-Site": "cross-site"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["ok"])

    def test_home_escapes_config_values_and_omits_saved_secrets(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.radius_query = '\"><script>alert(1)</script>'
        cfg.bot_token = "telegram-secret"
        cfg.smtp_pass = "smtp-secret"
        with patch.object(runtime, "_CONFIG", cfg):
            body = self.client.get("/").get_data(as_text=True)

        self.assertNotIn('<script>alert(1)</script>', body)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', body)
        self.assertNotIn("telegram-secret", body)
        self.assertNotIn("smtp-secret", body)

    def test_atomic_json_write_replaces_complete_document(self):
        from toyoko_tracker import runtime

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir) / "state.json")
            runtime._atomic_write_json(path, {"version": 1})
            runtime._atomic_write_json(path, {"version": 2, "ready": True})
            with open(path, encoding="utf-8") as stream:
                payload = json.load(stream)

        self.assertEqual(payload, {"version": 2, "ready": True})


if __name__ == "__main__":
    unittest.main()
