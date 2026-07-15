import sys
import json
import importlib
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
    def test_routeinn_hotel_list_parser_unifies_supported_subbrands(self):
        from toyoko_tracker.routeinn import parse_hotel_list_html

        html = """
        <div class="p-hotel"><ul>
          <li><p class="name">ホテルルートイン札幌駅前北口</p><div class="txt_address">北海道札幌市</div>
            <ul class="btns"><li class="c-btn1"><a href="/hotel_list/hokkaido/index_hotel_id_241/">ホテル詳細</a></li>
            <li class="c-btn1 c-btn1--black"><a href="/map">MAP</a></li>
            <li class="c-btn1 c-btn1--rsv"><a href="/hotel_list/hokkaido/index_hotel_id_241/plan/">予約</a></li></ul></li>
          <li><p class="name">ルートイングランティア函館駅前</p>
            <ul class="btns"><li class="c-btn1"><a href="https://www.hotel-grantia.co.jp/hakodate-st/">ホテル詳細</a></li>
            <li class="c-btn1 c-btn1--rsv"><a href="https://reserve.route-inn.co.jp/booking/result?code=95bc855d-d147-4422-868c-68f7cbf17f3f&type=plan">予約</a></li></ul></li>
          <li><p class="name">BIZCOURT CABINすすきの</p><ul class="btns"><li class="c-btn1"><a href="#">詳細</a></li><li class="c-btn1 c-btn1--rsv"><a href="#">予約</a></li></ul></li>
        </ul></div>
        """

        hotels = parse_hotel_list_html(html, "https://www.route-inn.co.jp/hotel_list/?area=1", "zh_cn")

        self.assertEqual(len(hotels), 2)
        self.assertEqual(hotels[0]["code"], "routeinn:241")
        self.assertEqual(hotels[0]["display_code"], "RI-241")
        self.assertEqual(hotels[0]["provider"], "routeinn")
        self.assertTrue(hotels[0]["name_primary"].startswith("露樱酒店"))
        self.assertEqual(hotels[1]["brand"], "grandia")
        self.assertTrue(hotels[1]["name_primary"].startswith("露樱Grandia"))

    def test_routeinn_storelocator_point_provides_radius_coordinates(self):
        from toyoko_tracker.routeinn import _storelocator_hotel

        hotel = _storelocator_hotel({
            "key": "241",
            "name": "ホテルルートイン札幌駅前北口",
            "latitude": 43.0691895,
            "longitude": 141.3493104,
            "address": "北海道札幌市北区北7条西4丁目2-2",
            "is_active": True,
            "extra_fields": {
                "name.en": "HOTEL ROUTE INN SAPPORO EKIMAE KITAGUCHI",
                "詳細ページへのリンク": "https://www.route-inn.co.jp/hotel_list/hokkaido/index_hotel_id_241/",
                "予約ページURL（PC）": "https://reserve.route-inn.co.jp/booking/result?code=booking-code",
            },
        }, "zh_cn")

        self.assertEqual(hotel["code"], "routeinn:241")
        self.assertEqual(hotel["display_code"], "RI-241")
        self.assertEqual(hotel["provider"], "routeinn")
        self.assertEqual(hotel["lat"], 43.0691895)
        self.assertEqual(hotel["lng"], 141.3493104)
        self.assertIn("43.0691895,141.3493104", hotel["map_url"])

    def test_routeinn_offer_adapter_returns_bilingual_member_prices(self):
        from toyoko_tracker import routeinn

        hotel = {
            "code": "routeinn:241", "display_code": "RI-241", "provider": "routeinn", "brand": "routeinn",
            "name_primary": "露樱酒店 札幌站前北口", "name_en": "Hotel Route-Inn Sapporo Ekimae Kitaguchi",
            "url": "https://example.test/hotel", "reservation_url": "https://reserve.example.test/?code=booking-code",
        }
        primary_payload = {"plans": [{"name": "标准方案", "rooms": [{
            "room_plan_code": "single-basic", "availability": "available", "room_type_name": "本馆禁烟单人房",
            "is_smoking": False, "inventory": 3, "total_price": 9000, "tax": 900,
            "sign_in_discount": {"total_price_after_discount": 8700, "total_price_after_discount_tax": 870},
        }]}]}
        english_payload = {"plans": [{"name": "Basic", "rooms": [{
            "room_plan_code": "single-basic", "availability": "available", "room_type_name": "Main Building Non-Smoking Single",
        }]}]}

        def fake_api(path, locale, params=None):
            if path.endswith("/rooms"):
                return english_payload if locale == "en" else primary_payload
            return {"booking_widget_setting_attributes": {"hotel_name": "Route Inn Sapporo Ekimae Kitaguchi"}}

        with patch.object(routeinn, "resolve_booking_code", return_value="booking-code"), \
             patch.object(routeinn, "_api_get", side_effect=fake_api):
            primary, english, booking_url, offers, stats = routeinn.fetch_offers(
                hotel, "2026-07-20", "2026-07-21", 1, 1, "zh_cn"
            )

        self.assertTrue(primary.startswith("露樱酒店"))
        self.assertTrue(english.startswith("Hotel Route-Inn"))
        self.assertIn("checkin_date=2026-07-20", booking_url)
        self.assertEqual(offers[0]["price_text"], "¥9,900")
        self.assertEqual(offers[0]["member_price_text"], "¥9,570")
        self.assertEqual(offers[0]["remaining_norm"], "3")
        self.assertEqual(offers[0]["room_title_primary"], "本馆禁烟单人房")
        self.assertEqual(offers[0]["room_title"], "Main Building Non-Smoking Single")
        self.assertEqual(offers[0]["room_smoking"], "non_smoking")
        self.assertTrue(stats["had_any_offer"])

    def test_routeinn_unavailable_scan_skips_english_rooms_request(self):
        from toyoko_tracker import routeinn

        hotel = {
            "code": "routeinn:241", "provider": "routeinn", "brand": "routeinn",
            "name_primary": "露樱酒店 札幌站前北口", "name_en": "Hotel Route-Inn Sapporo Ekimae Kitaguchi",
            "reservation_url": "https://reserve.example.test/?code=booking-code",
        }
        payload = {"plans": [{"rooms": [{
            "room_plan_code": "single-basic",
            "availability": "unavailable",
            "room_type_name": "本馆禁烟单人房",
        }]}]}

        with patch.object(routeinn, "_api_get", return_value=payload) as mock_api:
            _, _, _, offers, stats = routeinn.fetch_offers(
                hotel, "2026-07-20", "2026-07-21", 1, 1, "zh_cn"
            )

        self.assertEqual(offers, [])
        self.assertTrue(stats["had_any_offer"])
        self.assertEqual(mock_api.call_count, 1)
        self.assertEqual(mock_api.call_args.args[1], "zh_cn")

    def test_dormy_offer_adapter_keeps_room_smoking_and_inventory(self):
        from toyoko_tracker import chain_providers

        hotel = {
            "code": "dormy:347", "display_code": "DM-347", "provider": "dormy",
            "provider_hotel_id": "347", "search_keyword": "ドーミーイン千歳",
            "name_primary": "ドーミーイン千歳", "name_en": "Dormy Inn Chitose",
            "reservation_url": "https://example.test/reserve",
        }
        payload = {"data": [{"hotel": {"id": 347}, "rooms": [{
            "name": "【禁煙】ダブルルーム", "tags": [{"value": "禁煙"}, {"value": "ダブル"}],
            "inventories": [{"year": "2026", "month_day": "07/18", "price": 29250, "stock": 14, "is_available": True}],
        }]}]}
        with patch.object(chain_providers, "_dormy_get", return_value=payload):
            _, _, _, offers, _ = chain_providers.fetch_dormy_offers(
                hotel, "2026-07-18", "2026-07-19", 1, 1, "zh_cn"
            )

        self.assertEqual(offers[0]["room_smoking"], "non_smoking")
        self.assertEqual(offers[0]["remaining_norm"], "14")
        self.assertEqual(offers[0]["price_text"], "¥29,250")

    def test_routeinn_selection_metadata_survives_config_cleaning(self):
        from toyoko_tracker import runtime

        cleaned = runtime._clean_selected_hotels([{
            "code": "routeinn:241",
            "display_code": "RI-241",
            "provider": "routeinn",
            "brand": "routeinn",
            "name_primary": "露樱酒店 札幌站前北口",
            "name_en": "Hotel Route-Inn Sapporo Ekimae Kitaguchi",
            "url": "https://example.test/hotel",
            "reservation_url": "https://example.test/booking?code=abc",
        }])

        self.assertEqual(cleaned[0]["code"], "routeinn:241")
        self.assertEqual(cleaned[0]["display_code"], "RI-241")
        self.assertEqual(cleaned[0]["provider"], "routeinn")
        self.assertIn("booking?code=abc", cleaned[0]["reservation_url"])

    def test_official_hotel_catalog_parser(self):
        from toyoko_tracker.hotel_catalog import parse_official_catalog_html

        payload = {
            "props": {"pageProps": {"nested": [{
                "hotelCode": "00374",
                "name": "Toyoko Inn Kure-eki",
                "hotelStatus": "opened",
                "openDate": "2026-07-02T15:00:00.000Z",
                "country": 1,
                "prefecture": 34,
                "address": "3-33 Takara-machi",
            }]}}
        }
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'

        hotels = parse_official_catalog_html(html)

        self.assertEqual(len(hotels), 1)
        self.assertEqual(hotels[0]["code"], "00374")
        self.assertEqual(hotels[0]["status"], "opened")
        self.assertEqual(hotels[0]["country"], 1)

    def test_catalog_refresh_detects_new_hotel_and_updates_coordinate_cache(self):
        from toyoko_tracker import hotel_catalog

        current = []
        previous = []
        cached = []
        for number in range(1, 301):
            code = str(number).zfill(5)
            current.append({
                "code": code, "name": f"Hotel {code}", "name_en": f"Hotel {code}",
                "status": "operation", "country": 1, "prefecture": 13,
                "url": f"https://example.test/{code}",
            })
            if number < 300:
                previous.append({"code": code, "name": f"Hotel {code}", "status": "operation"})
                cached.append({"code": code, "name": f"Hotel {code}", "lat": 35.0, "lng": 139.0})

        class FakeResponse:
            text = "unused"

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = str(Path(tmp_dir) / "catalog.json")
            cache_path = str(Path(tmp_dir) / "radius.json")
            Path(snapshot_path).write_text(json.dumps({"checked_at": "2026-07-01T00:00:00+00:00", "current_hotels": previous}), encoding="utf-8")
            Path(cache_path).write_text(json.dumps({"generated_at": "2026-07-01T00:00:00+00:00", "hotels": cached}), encoding="utf-8")

            with patch.object(hotel_catalog, "HOTEL_CATALOG_SNAPSHOT_PATH", snapshot_path), \
                 patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path), \
                 patch.object(hotel_catalog, "parse_official_catalog_html", return_value=current), \
                 patch.object(hotel_catalog, "_resolve_official_coordinates", return_value=(35.1, 139.1)), \
                 patch.object(hotel_catalog.requests, "get", return_value=FakeResponse()):
                status = hotel_catalog.refresh_catalog(force=True)

            updated_cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            updated_snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))

        self.assertEqual(status["state"], "updated")
        self.assertEqual([item["code"] for item in status["new_hotels"]], ["00300"])
        self.assertEqual(len(updated_cache["hotels"]), 300)
        self.assertEqual(updated_cache["hotels"][-1]["lat"], 35.1)
        self.assertEqual(updated_snapshot["last_new_hotels"][0]["code"], "00300")

    def test_first_catalog_refresh_establishes_baseline_without_new_hotel_alerts(self):
        from toyoko_tracker import hotel_catalog

        current = [
            {
                "code": str(number).zfill(5),
                "name": f"Hotel {number:05d}",
                "name_en": f"Hotel {number:05d}",
                "status": "operation",
                "country": 1,
                "prefecture": 13,
                "lat": 35.0,
                "lng": 139.0,
            }
            for number in range(1, 301)
        ]

        class FakeResponse:
            text = "unused"

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = str(Path(tmp_dir) / "catalog.json")
            cache_path = str(Path(tmp_dir) / "radius.json")
            with patch.object(hotel_catalog, "HOTEL_CATALOG_SNAPSHOT_PATH", snapshot_path), \
                 patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path), \
                 patch.object(hotel_catalog, "parse_official_catalog_html", return_value=current), \
                 patch.object(hotel_catalog.requests, "get", return_value=FakeResponse()):
                status = hotel_catalog.refresh_catalog(force=True)

            snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))

        self.assertEqual(status["state"], "fresh")
        self.assertEqual(status["new_hotels"], [])
        self.assertEqual(snapshot["last_new_hotels"], [])
        self.assertEqual(snapshot["unseen_new_hotels"], [])
        self.assertEqual(len(snapshot["current_hotels"]), 300)

    def test_second_catalog_refresh_reports_only_the_real_addition(self):
        from toyoko_tracker import hotel_catalog

        baseline = [
            {
                "code": str(number).zfill(5),
                "name": f"Hotel {number:05d}",
                "status": "operation",
                "country": 1,
                "prefecture": 13,
                "lat": 35.0,
                "lng": 139.0,
            }
            for number in range(1, 301)
        ]
        updated = [*baseline, {
            "code": "00301", "name": "New Hotel", "status": "operation",
            "country": 1, "prefecture": 13, "lat": 35.1, "lng": 139.1,
        }]

        class FakeResponse:
            text = "unused"

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = str(Path(tmp_dir) / "catalog.json")
            cache_path = str(Path(tmp_dir) / "radius.json")
            with patch.object(hotel_catalog, "HOTEL_CATALOG_SNAPSHOT_PATH", snapshot_path), \
                 patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path), \
                 patch.object(hotel_catalog, "parse_official_catalog_html", side_effect=[baseline, updated]), \
                 patch.object(hotel_catalog.requests, "get", return_value=FakeResponse()):
                first = hotel_catalog.refresh_catalog(force=True)
                second = hotel_catalog.refresh_catalog(force=True)

        self.assertEqual(first["new_hotels"], [])
        self.assertEqual([hotel["code"] for hotel in second["new_hotels"]], ["00301"])

    def test_recent_snapshot_without_coordinate_cache_is_rebuilt(self):
        from datetime import datetime, timezone
        from toyoko_tracker import hotel_catalog

        current = [
            {
                "code": str(number).zfill(5),
                "name": f"Hotel {number:05d}",
                "status": "operation",
                "country": 1,
                "prefecture": 13,
                "lat": 35.0,
                "lng": 139.0,
            }
            for number in range(1, 301)
        ]

        class FakeResponse:
            text = "unused"

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = str(Path(tmp_dir) / "catalog.json")
            cache_path = str(Path(tmp_dir) / "missing-radius.json")
            Path(snapshot_path).write_text(
                json.dumps({
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "current_hotels": current,
                }),
                encoding="utf-8",
            )
            with patch.object(hotel_catalog, "HOTEL_CATALOG_SNAPSHOT_PATH", snapshot_path), \
                 patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path), \
                 patch.object(hotel_catalog, "parse_official_catalog_html", return_value=current) as parser, \
                 patch.object(hotel_catalog.requests, "get", return_value=FakeResponse()):
                status = hotel_catalog.refresh_catalog(force=False)

            rebuilt = json.loads(Path(cache_path).read_text(encoding="utf-8"))

        self.assertEqual(parser.call_count, 1)
        self.assertEqual(status["state"], "fresh")
        self.assertEqual(status["new_hotels"], [])
        self.assertEqual(len(rebuilt["hotels"]), 300)

    def test_mismatched_snapshot_and_cache_revision_is_rebuilt(self):
        from datetime import datetime, timezone
        from toyoko_tracker import hotel_catalog

        current = [
            {
                "code": str(number).zfill(5), "name": f"Hotel {number:05d}",
                "status": "operation", "country": 1, "prefecture": 13,
                "lat": 35.0, "lng": 139.0,
            }
            for number in range(1, 301)
        ]

        class FakeResponse:
            text = "unused"

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = str(Path(tmp_dir) / "catalog.json")
            cache_path = str(Path(tmp_dir) / "radius.json")
            Path(snapshot_path).write_text(json.dumps({
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "catalog_revision": "old-revision",
                "current_hotels": current,
            }), encoding="utf-8")
            Path(cache_path).write_text(json.dumps({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "catalog_revision": "partial-new-revision",
                "hotels": current,
            }), encoding="utf-8")
            with patch.object(hotel_catalog, "HOTEL_CATALOG_SNAPSHOT_PATH", snapshot_path), \
                 patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path), \
                 patch.object(hotel_catalog, "parse_official_catalog_html", return_value=current) as parser, \
                 patch.object(hotel_catalog.requests, "get", return_value=FakeResponse()):
                status = hotel_catalog.refresh_catalog(force=False)

            snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
            cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))

        self.assertEqual(parser.call_count, 1)
        self.assertEqual(status["state"], "fresh")
        self.assertEqual(snapshot["catalog_revision"], cache["catalog_revision"])

    def test_matching_revision_does_not_hide_truncated_coordinate_cache(self):
        from toyoko_tracker.hotel_catalog import _catalog_files_compatible

        snapshot = {
            "catalog_revision": "same-revision",
            "current_hotels": [{"code": "00001"}, {"code": "00002"}],
        }
        cache = {
            "catalog_revision": "same-revision",
            "hotels": [{"code": "00001", "lat": 35.0, "lng": 139.0}],
        }

        self.assertFalse(_catalog_files_compatible(snapshot, cache))

    def test_cache_write_failure_does_not_publish_fresh_snapshot(self):
        from toyoko_tracker import hotel_catalog

        current = [
            {
                "code": str(number).zfill(5),
                "name": f"Hotel {number:05d}",
                "status": "operation",
                "country": 1,
                "prefecture": 13,
                "lat": 35.0,
                "lng": 139.0,
            }
            for number in range(1, 301)
        ]

        class FakeResponse:
            text = "unused"

            def raise_for_status(self):
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = str(Path(tmp_dir) / "catalog.json")
            cache_path = str(Path(tmp_dir) / "radius.json")
            with patch.object(hotel_catalog, "HOTEL_CATALOG_SNAPSHOT_PATH", snapshot_path), \
                 patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path), \
                 patch.object(hotel_catalog, "parse_official_catalog_html", return_value=current), \
                 patch.object(hotel_catalog.requests, "get", return_value=FakeResponse()), \
                 patch.object(hotel_catalog, "_atomic_write_json", side_effect=OSError("disk full")) as writer:
                status = hotel_catalog.refresh_catalog(force=True)

            self.assertFalse(Path(snapshot_path).exists())

        self.assertEqual(status["state"], "failed")
        self.assertEqual(writer.call_args_list[0].args[0], cache_path)
        self.assertEqual(writer.call_count, 1)

    def test_legacy_full_catalog_alert_is_repaired(self):
        from toyoko_tracker.hotel_catalog import _repair_legacy_full_catalog_alert

        hotels = [
            {"code": str(number).zfill(5), "name": f"Hotel {number:05d}"}
            for number in range(1, 350)
        ]
        snapshot = {
            "schema_version": 1,
            "current_hotels": list(hotels),
            "unseen_new_hotels": list(hotels),
            "last_new_hotels": list(hotels),
        }

        repaired = _repair_legacy_full_catalog_alert(snapshot)

        self.assertTrue(repaired)
        self.assertTrue(snapshot["baseline_initialized"])
        self.assertEqual(snapshot["unseen_new_hotels"], [])
        self.assertEqual(snapshot["last_new_hotels"], [])

    def test_small_real_new_hotel_alert_is_not_repaired(self):
        from toyoko_tracker.hotel_catalog import _repair_legacy_full_catalog_alert

        hotels = [{"code": str(number).zfill(5)} for number in range(1, 350)]
        snapshot = {
            "schema_version": 1,
            "current_hotels": hotels,
            "unseen_new_hotels": [hotels[-1]],
        }

        self.assertFalse(_repair_legacy_full_catalog_alert(snapshot))
        self.assertEqual(snapshot["unseen_new_hotels"], [hotels[-1]])

    def test_region_hotel_search_uses_local_catalog_cache(self):
        from toyoko_tracker import runtime

        local_hotels = [
            {"code": "00165", "name": "Fukuoka", "prefecture": 40, "lat": 33.5, "lng": 130.4},
            {"code": "00001", "name": "Tokyo", "prefecture": 13, "lat": 35.6, "lng": 139.7},
        ]
        runtime._AREA_HOTELS_CACHE.clear()
        with patch.object(
            runtime, "_find_area_selection", return_value=("pref-40", [("prefecture", 40)])
        ), patch.object(
            runtime, "_load_catalog_coordinate_cache", return_value=local_hotels
        ), patch.object(runtime, "_fetch_hotels_for_selector") as network_fetch:
            hotels = runtime._hotels_for_area_selection(7, "pref-40", "en")

        self.assertEqual([hotel["code"] for hotel in hotels], ["00165"])
        network_fetch.assert_not_called()

    def test_catalog_coordinate_count_excludes_missing_and_invalid_points(self):
        from toyoko_tracker import hotel_catalog

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = str(Path(tmp_dir) / "radius.json")
            Path(cache_path).write_text(
                json.dumps({
                    "generated_at": "2026-07-15T00:00:00+00:00",
                    "hotels": [
                        {"code": "00001", "lat": 35.0, "lng": 139.0},
                        {"code": "00002", "lat": None, "lng": None},
                        {"code": "00003", "lat": 999, "lng": 139.0},
                    ],
                }),
                encoding="utf-8",
            )
            with patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path):
                metadata = hotel_catalog._cache_metadata()

        self.assertEqual(metadata["coordinate_count"], 1)

    def test_expired_coordinate_cache_can_still_be_used_while_refreshing(self):
        from toyoko_tracker import hotel_catalog

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = str(Path(tmp_dir) / "radius.json")
            Path(cache_path).write_text(json.dumps({
                "generated_at": "2020-01-01T00:00:00+00:00",
                "hotels": [{"code": "00001", "lat": 35.0, "lng": 139.0}],
            }), encoding="utf-8")
            with patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path):
                stale_allowed = hotel_catalog.load_coordinate_cache(allow_stale=True)
                fresh_only = hotel_catalog.load_coordinate_cache(allow_stale=False)

        self.assertEqual(stale_allowed[0]["code"], "00001")
        self.assertIsNone(fresh_only)

    def test_far_future_coordinate_cache_is_not_treated_as_fresh(self):
        from toyoko_tracker import hotel_catalog

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = str(Path(tmp_dir) / "radius.json")
            Path(cache_path).write_text(json.dumps({
                "generated_at": "2099-01-01T00:00:00+00:00",
                "hotels": [{"code": "00001", "lat": 35.0, "lng": 139.0}],
            }), encoding="utf-8")
            with patch.object(hotel_catalog, "RADIUS_HOTELS_CACHE_PATH", cache_path):
                stale_allowed = hotel_catalog.load_coordinate_cache(allow_stale=True)
                fresh_only = hotel_catalog.load_coordinate_cache(allow_stale=False)

        self.assertEqual(stale_allowed[0]["code"], "00001")
        self.assertIsNone(fresh_only)

    def test_far_future_chain_provider_cache_is_not_treated_as_fresh(self):
        from toyoko_tracker import chain_providers

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = str(Path(tmp_dir) / "providers.json")
            Path(cache_path).write_text(json.dumps({
                "providers": {
                    "dormy": {
                        "generated_at": 4_000_000_000,
                        "hotels": [{"code": "dormy:1"}],
                    }
                }
            }), encoding="utf-8")
            chain_providers._PROVIDER_CACHE.clear()
            with patch.object(chain_providers, "CHAIN_PROVIDER_CACHE_PATH", cache_path), patch.object(
                chain_providers.time, "time", return_value=1_000.0
            ):
                cached = chain_providers._cached("dormy")

        self.assertIsNone(cached)

    def test_official_hotel_info_parser_and_locale_urls(self):
        hotel_info = importlib.import_module("toyoko_tracker.hotel_info")
        hotel_data = {
            "hotelCode": "00119",
            "name": "东横INN 东京门前仲町永代桥",
            "zipcode": "135-0034",
            "city": "Koto-ku",
            "address": "1-15-3 Eitai",
            "googleMapUrl": "https://maps.example.test/hotel",
            "accessImage": {"image": "https://toyoko-inn.imagewave.pictures/test-map"},
            "trainAccess": [{"line": "地铁东西线", "station": "门前仲町站", "exit": "3号出口", "transportation": "walk", "time": 6}],
            "carAccess": [{"road": "首都高速", "ic": "福住出口", "time": 3}],
            "planeAccess": [{"airport": "羽田机场", "transportation": "bus", "time": 45}],
            "accessRemarks": "Official remark",
        }
        next_data = {
            "props": {"pageProps": {"trpcState": {"json": {"queries": [{"state": {"data": hotel_data}}]}}}}
        }
        schema = {
            "@context": "https://schema.org",
            "@type": "Hotel",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "1-15-3 Eitai",
                "addressLocality": "Koto-ku",
                "addressRegion": "Tokyo",
                "postalCode": "135-0034",
            },
        }
        html = (
            '<script type="application/ld+json">' + json.dumps(schema) + "</script>"
            '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(next_data) + "</script>"
        )

        info = hotel_info.parse_hotel_info_html(
            html,
            "00119",
            "zh_cn",
            "https://www.toyoko-inn.com/china_cn/search/detail/00119/",
        )

        self.assertEqual(info["name"], "东横INN 东京门前仲町永代桥")
        self.assertEqual(info["map_image_url"], "https://toyoko-inn.imagewave.pictures/test-map")
        self.assertIn("1-15-3 Eitai", info["address"])
        self.assertEqual(info["train_access"][0]["time"], 6)
        self.assertEqual(info["car_access"][0]["time"], 3)
        self.assertEqual(info["plane_access"][0]["time"], 45)
        self.assertIn("/china_cn/", hotel_info.official_hotel_url("00119", "zh_cn"))
        self.assertIn("/china/", hotel_info.official_hotel_url("00119", "zh_tw"))
        self.assertIn("/korea/", hotel_info.official_hotel_url("00119", "ko"))
        self.assertEqual(hotel_info.official_hotel_url("00119", "ja"), "https://www.toyoko-inn.com/search/detail/00119/")

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

        from toyoko_tracker import runtime

        with patch.object(runtime, "_http_get", lambda *args, **kwargs: FakeResponse()):
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

        from toyoko_tracker import runtime

        with patch.object(runtime, "_http_get", lambda *args, **kwargs: FakeResponse()):
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

    def test_check_hotel_http_reuses_cache_after_not_modified(self):
        from dataclasses import asdict
        from types import SimpleNamespace
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.engine = "http"
        cached_result = tracker_app.HotelResult(
            code="00001",
            url="https://example.test",
            name="Cached Hotel",
            available=False,
            engine_used="http",
        )
        entry = SimpleNamespace(
            result=asdict(cached_result),
            age_sec=45,
            etag='"version-1"',
            last_modified="Mon, 13 Jul 2026 10:00:00 GMT",
        )

        class NotModifiedResponse:
            status_code = 304
            headers = {}

        with patch.object(runtime, "_scan_cache_get", return_value=entry), \
             patch.object(runtime, "_http_get", return_value=NotModifiedResponse()) as mock_get, \
             patch.object(runtime, "_scan_cache_mark_conditional_hit") as mark_hit:
            result = runtime.check_hotel_http(cfg, "00001", "2026-07-17", "2026-07-18")

        headers = mock_get.call_args.kwargs["headers"]
        self.assertEqual(headers["If-None-Match"], '"version-1"')
        self.assertEqual(headers["If-Modified-Since"], "Mon, 13 Jul 2026 10:00:00 GMT")
        self.assertFalse(result.from_cache)
        self.assertTrue(result.cache_validated)
        self.assertEqual(result.name, "Cached Hotel")
        mark_hit.assert_called_once()

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
        self.assertTrue(cfg.adaptive_backoff_enabled)
        self.assertEqual(cfg.available_alert_repeat, 0)
        self.assertEqual(cfg.enabled_providers, ["toyoko"])

    def test_saved_provider_and_repeat_choices_survive_restart_load(self):
        from toyoko_tracker import runtime

        saved = {
            "enabled_providers": ["routeinn", "dormy"],
            "available_alert_repeat": 4,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auto_save.json"
            path.write_text(json.dumps(saved), encoding="utf-8")
            restored = tracker_app.AppConfig()
            with patch.object(runtime, "_CONFIG", restored):
                self.assertTrue(runtime._load_config_from_file(str(path)))

        self.assertEqual(restored.enabled_providers, ["routeinn", "dormy"])
        self.assertEqual(restored.available_alert_repeat, 4)

    def test_adaptive_backoff_escalates_and_recovers(self):
        unknown = tracker_app.HotelResult(code="00001", url="#", name=None, available=None)
        healthy = tracker_app.HotelResult(code="00002", url="#", name="Test", available=False)

        multiplier, consecutive, ratio = tracker_app._adaptive_backoff_state([unknown, healthy], 0, True)
        self.assertEqual((multiplier, consecutive, ratio), (2, 1, 50))

        multiplier, consecutive, ratio = tracker_app._adaptive_backoff_state([unknown, healthy], consecutive, True)
        self.assertEqual((multiplier, consecutive, ratio), (4, 2, 50))

        multiplier, consecutive, ratio = tracker_app._adaptive_backoff_state([healthy, healthy], consecutive, True)
        self.assertEqual((multiplier, consecutive, ratio), (1, 0, 0))

        multiplier, consecutive, ratio = tracker_app._adaptive_backoff_state([unknown], 2, False)
        self.assertEqual((multiplier, consecutive, ratio), (1, 0, 100))

    def test_failed_hotel_check_includes_telemetry(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.engine = "http"

        with patch.object(runtime, "_HAS_PLAYWRIGHT", False), \
             patch.object(runtime, "_http_get", side_effect=RuntimeError("network unavailable")):
            result = tracker_app.check_hotel(cfg, None, "00001", "2026-07-17", "2026-07-18")

        self.assertIsNone(result.available)
        self.assertEqual(result.engine_used, "http")
        self.assertIsInstance(result.elapsed_ms, int)
        self.assertIsNotNone(result.checked_at)
        self.assertIn("network unavailable", result.error_summary)

    def test_adaptive_backoff_setting_can_be_disabled(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        runtime._apply_payload_to_config(cfg, {"adaptive_backoff_enabled": False})

        self.assertFalse(cfg.adaptive_backoff_enabled)

    def test_round_wait_counts_scan_time_toward_target_cycle(self):
        from toyoko_tracker import runtime

        wait_seconds, target_period, scan_elapsed = runtime._round_wait_seconds(
            30,
            round_started_mono=100.0,
            jitter_percent=0,
            now_mono=112.0,
        )

        self.assertEqual(target_period, 30.0)
        self.assertEqual(scan_elapsed, 12.0)
        self.assertEqual(wait_seconds, 18.0)

    def test_round_wait_keeps_short_pause_after_slow_scan(self):
        from toyoko_tracker import runtime

        wait_seconds, target_period, scan_elapsed = runtime._round_wait_seconds(
            30,
            round_started_mono=100.0,
            jitter_percent=0,
            now_mono=135.0,
        )

        self.assertEqual(target_period, 30.0)
        self.assertEqual(scan_elapsed, 35.0)
        self.assertEqual(wait_seconds, 3.0)

    def test_parallel_http_preserves_order_and_publishes_each_result(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.engine = "http"
        cfg.smart_parallel_enabled = True
        cfg.smart_parallel_workers = 3
        cfg.per_hotel_delay_seconds = 1
        cfg.request_jitter_percent = 0
        codes = ["00003", "00001", "00002"]

        def fake_check(_cfg, _page, code, _start, _end):
            return tracker_app.HotelResult(code=code, url=f"https://example.test/{code}", name=code, available=False)

        with runtime._PROGRESS_LOCK:
            runtime._PROGRESS["done"] = 0
            runtime._PROGRESS["total"] = len(codes)
        runtime._stop_event.clear()
        with patch.object(runtime, "_jittered_spacing", return_value=0.0), \
             patch.object(runtime, "check_hotel", side_effect=fake_check), \
             patch.object(runtime, "_publish_partial_result") as mock_publish:
            results = runtime._check_hotels_parallel_http(cfg, codes, "2026-07-18", "2026-07-19")

        self.assertEqual([result.code for result in results], codes)
        self.assertEqual(mock_publish.call_count, len(codes))
        with runtime._PROGRESS_LOCK:
            self.assertEqual(runtime._PROGRESS["done"], len(codes))

    def test_provider_scheduler_interleaves_brands_but_spaces_same_brand(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.selected_hotels = [
            {"code": "00001", "provider": "toyoko"},
            {"code": "00002", "provider": "toyoko"},
            {"code": "routeinn:1", "provider": "routeinn"},
            {"code": "dormy:1", "provider": "dormy"},
        ]
        codes = ["00001", "00002", "routeinn:1", "dormy:1"]
        scheduler = runtime._ProviderAwareScheduler(cfg, codes, workers=3, base_delay=1, jitter_percent=0)

        with patch.object(runtime, "_provider_cooldown_until", return_value=0.0):
            first, _ = scheduler.pop_ready(now_mono=100.0)
            blocked, delay = scheduler.pop_ready(now_mono=100.0)
            second, _ = scheduler.pop_ready(now_mono=100.34)
            third, _ = scheduler.pop_ready(now_mono=100.68)
            fourth, _ = scheduler.pop_ready(now_mono=101.02)

        self.assertEqual(first[2], "toyoko")
        self.assertIsNone(blocked)
        self.assertGreater(delay, 0)
        self.assertEqual(second[2], "routeinn")
        self.assertEqual(third[2], "dormy")
        self.assertEqual(fourth[2], "toyoko")

    def test_provider_health_enters_cooldown_and_recovers(self):
        from toyoko_tracker import runtime

        runtime._reset_provider_health(["routeinn"])
        failed = tracker_app.HotelResult(
            code="routeinn:1", url="#", name=None, available=None, elapsed_ms=500,
            error_summary="temporary provider failure", provider="routeinn",
        )
        healthy = tracker_app.HotelResult(
            code="routeinn:1", url="#", name="Test", available=False, elapsed_ms=200,
            provider="routeinn",
        )

        with patch.object(runtime, "_now_mono", return_value=100.0):
            runtime._record_provider_result("routeinn", failed)
            runtime._record_provider_result("routeinn", failed)
            runtime._record_provider_result("routeinn", failed)
            cooling = runtime.provider_health_snapshot()["routeinn"]
            runtime._record_provider_result("routeinn", healthy)
            recovered = runtime.provider_health_snapshot()["routeinn"]

        self.assertEqual(cooling["state"], "cooldown")
        self.assertEqual(cooling["cooldown_remaining_sec"], 4)
        self.assertEqual(cooling["consecutive_failures"], 3)
        self.assertEqual(recovered["state"], "healthy")
        self.assertEqual(recovered["consecutive_failures"], 0)

    def test_provider_health_honors_retry_after_and_adapts_delay(self):
        from toyoko_tracker import runtime

        runtime._reset_provider_health(["toyoko"], base_delay=2)
        limited = tracker_app.HotelResult(
            code="00001", url="#", name=None, available=None, elapsed_ms=300,
            error_summary="HTTP 429", http_status=429, retry_after_sec=12,
            provider="toyoko",
        )

        with patch.object(runtime, "_now_mono", return_value=100.0):
            runtime._record_provider_result("toyoko", limited)
            state = runtime.provider_health_snapshot()["toyoko"]

        self.assertEqual(state["state"], "cooldown")
        self.assertEqual(state["cooldown_remaining_sec"], 12)
        self.assertEqual(state["rate_limited_count"], 1)
        self.assertEqual(state["adaptive_delay_sec"], 4.0)

    def test_hotel_priority_prefers_manual_then_recent_availability(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.selected_hotels = [
            {"code": "00001", "provider": "toyoko"},
            {"code": "00002", "provider": "toyoko", "priority": True},
            {"code": "00003", "provider": "toyoko"},
        ]
        with runtime._HOTEL_RUNTIME_LOCK:
            runtime._HOTEL_RUNTIME_STATE.clear()
        runtime._record_hotel_runtime_result(tracker_app.HotelResult(
            code="00003", url="#", name="Available", available=True,
        ))

        ordered = runtime._prioritized_codes(cfg, ["00001", "00002", "00003"])

        self.assertEqual(ordered, ["00002", "00003", "00001"])

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

    def test_unvalidated_cached_result_does_not_advance_notifications(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        notifications.clear_alert_state()
        cached = tracker_app.HotelResult(
            code="00001",
            url="https://example.test",
            name="Test",
            available=True,
            from_cache=True,
            cache_age_sec=12,
        )

        with patch.object(notifications, "notify_push_channels") as mock_notify:
            newly_available = notifications.process_notifications(
                cfg, [cached], "2026-05-16", "2026-05-17"
            )

        self.assertEqual(newly_available, [])
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
        self.assertIn("可用房间数量变动", mock_notify.call_args.args[1])
        self.assertNotIn("Available Room Count Changed", mock_notify.call_args.args[1])

    def test_english_notifications_do_not_include_chinese_labels(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        cfg.primary_language = "en"
        cfg.notify_available = True
        notifications.clear_alert_state()
        result = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test Hotel", name_en="Test Hotel",
            available=True, min_remaining="1", min_price_text="JPY 8,000", min_price_room="Single",
        )

        with patch.object(notifications, "notify_push_channels") as mock_notify:
            notifications.process_notifications(cfg, [result], "2026-05-16", "2026-05-17")

        title = mock_notify.call_args.args[1]
        message = mock_notify.call_args.args[2]
        self.assertIn("Room Available", title)
        self.assertIn("Hotel: Test Hotel", message)
        self.assertNotIn("发现空房", title)
        self.assertNotIn("酒店:", message)

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

    def test_transient_unknown_result_preserves_available_state(self):
        from toyoko_tracker import notifications

        cfg = tracker_app.AppConfig()
        cfg.notify_search_error = False
        notifications.clear_alert_state()
        available = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test", available=True,
            min_remaining="1", min_price_text="¥8,000", min_price_room="Single",
        )
        unknown = tracker_app.HotelResult(
            code="00001", url="https://example.test", name="Test", available=None,
            error_summary="temporary upstream timeout",
        )

        with patch.object(notifications, "notify_push_channels") as mock_notify:
            notifications.process_notifications(cfg, [available], "2026-05-16", "2026-05-17")
            notifications.process_notifications(cfg, [unknown], "2026-05-16", "2026-05-17")
            notifications.process_notifications(cfg, [available], "2026-05-16", "2026-05-17")

        self.assertEqual(mock_notify.call_count, 1)
        self.assertIn("发现空房", mock_notify.call_args.args[1])


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

    def test_runtime_status_is_lightweight(self):
        payload = self.client.get("/api/v1/runtime").get_json()

        self.assertTrue(payload["ok"])
        self.assertIn("progress", payload)
        self.assertIn("provider_health", payload)
        self.assertIn("diagnostics", payload)
        self.assertIn("traffic", payload)
        self.assertIn("download_bytes", payload["traffic"])
        self.assertIn("upload_bytes", payload["traffic"])
        self.assertIn("requests", payload["traffic"])
        self.assertIn("results_revision", payload)
        self.assertIn("availability_logs_revision", payload)
        for heavy_key in ("config", "results", "logs", "availability_logs", "hotel_catalog", "provider_catalog"):
            self.assertNotIn(heavy_key, payload)

    def test_traffic_status_exposes_only_aggregate_metrics(self):
        payload = self.client.get("/api/v1/traffic").get_json()

        self.assertTrue(payload["ok"])
        traffic = payload["traffic"]
        self.assertEqual(traffic["scope"], "webui_http_estimate")
        self.assertIn("requests", traffic)
        self.assertIn("page_views", traffic)
        self.assertIn("upload_bps", traffic)
        self.assertIn("download_bps", traffic)
        self.assertNotIn("clients", traffic)
        self.assertNotIn("addresses", traffic)

    def test_results_status_uses_revision_to_skip_unchanged_payload(self):
        from toyoko_tracker import runtime

        result = tracker_app.HotelResult(
            code="00001", url="https://example.test/00001", name="Test", available=False,
        )
        with patch.object(runtime, "_LAST_RESULTS", [result]), patch.object(runtime, "_RESULTS_REVISION", 7):
            unchanged = self.client.get("/api/v1/results?since=7").get_json()
            changed = self.client.get("/api/v1/results?since=6").get_json()

        self.assertFalse(unchanged["changed"])
        self.assertNotIn("results", unchanged)
        self.assertTrue(changed["changed"])
        self.assertEqual(changed["revision"], 7)
        self.assertEqual(changed["results"][0]["code"], "00001")

    def test_log_cursor_returns_only_new_lines(self):
        from toyoko_tracker import runtime

        with patch.object(runtime, "_LOG_LINES", ["first", "second", "third"]), \
             patch.object(runtime, "_LOG_SEQUENCE", 3):
            payload = self.client.get("/api/v1/logs?after=1").get_json()

        self.assertEqual(payload["cursor"], 3)
        self.assertFalse(payload["reset"])
        self.assertEqual(payload["logs"], ["second", "third"])

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

    def test_home_includes_result_search_refresh_and_export_tools(self):
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="result_query"', body)
        self.assertIn('data-result-filter="changes"', body)
        self.assertIn('id="btn_results_refresh"', body)
        self.assertIn('id="btn_results_export"', body)
        self.assertIn('id="results_updated_at"', body)
        self.assertIn('id="hotel_catalog_panel"', body)
        self.assertIn('id="btn_catalog_refresh"', body)
        self.assertIn('id="provider_toyoko"', body)
        self.assertIn('id="provider_routeinn"', body)
        self.assertIn('id="provider_dormy"', body)
        self.assertIn('id="provider_mystays"', body)
        self.assertIn('id="provider_daiwa"', body)
        self.assertIn('id="btn_provider_all"', body)
        self.assertIn('data-step-target="people"', body)
        self.assertIn('data-step-target="rooms"', body)
        self.assertIn('id="btn_area_selected_only"', body)
        self.assertIn('id="area_sort"', body)
        self.assertIn('id="hotel_workspace"', body)
        self.assertEqual(body.count('data-hotel-workspace-view='), 2)
        self.assertIn('id="app-sidebar"', body)
        self.assertIn('id="sidebar-collapse-button"', body)
        self.assertIn('class="sidebar-utilities"', body)
        self.assertIn('/static/toyoko-chan-mascot.png', body)
        self.assertIn('data-app-view="home"', body)
        self.assertIn('data-app-view="search"', body)
        self.assertIn('data-app-view="monitor"', body)
        self.assertIn('id="view-interface"', body)
        self.assertIn('id="language-menu-button"', body)
        self.assertIn('data-language="en"', body)
        self.assertIn("<option value='en'", body)
        self.assertIn('id="theme-toggle-button"', body)
        self.assertIn('id="guide-open-button"', body)
        self.assertIn('id="update-open-button"', body)
        self.assertIn('class="icon-button update-open-button"', body)
        self.assertIn('M12 3v11m0 0 4-4m-4 4-4-4M5 18.5h14', body)
        self.assertIn('id="interface-settings-button"', body)
        self.assertIn('id="interface-settings-button" data-app-view="interface"', body)
        self.assertNotIn('class="sidebar-nav-item" data-app-view="interface"', body)
        self.assertIn('id="update-modal"', body)
        self.assertIn('id="update-current-version"', body)
        self.assertIn('id="update-latest-version"', body)
        self.assertIn('id="btn_update_check"', body)
        self.assertIn('id="btn_upgrade"', body)
        self.assertNotIn('id="footer-app-name"', body)
        self.assertEqual(body.count("https://space.bilibili.com/4955287"), 1)
        self.assertEqual(body.count("https://github.com/JellyNekoNeko/toyoko-tracker"), 1)
        self.assertIn('id="guide-modal"', body)
        self.assertIn('id="guide-progress"', body)
        self.assertEqual(body.count('data-guide-jump='), 5)
        self.assertIn('data-app-version="v0.7.0"', body)
        self.assertIn('data-theme-choice="system"', body)

    def test_home_dashboard_is_default_and_has_overview_modules(self):
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn('class="app-view active" id="view-home"', body)
        self.assertIn('id="home-primary-action"', body)
        self.assertIn('id="home-metric-available"', body)
        self.assertIn('id="home-traffic-card"', body)
        self.assertIn('id="home-metric-traffic-down"', body)
        self.assertIn('id="home-metric-traffic-note"', body)
        self.assertIn('id="home-task-title"', body)
        self.assertIn('id="home-activity-list"', body)
        self.assertIn('id="home-trend-list"', body)
        self.assertIn('id="home-health-badge"', body)
        self.assertIn('data-home-quick="radius"', body)
        self.assertIn('data-app-view="push-settings"><span class="nav-icon">✉</span>', body)
        self.assertIn('data-home-quick="push"><i>✉</i>', body)
        self.assertIn('/static/app.js?v=v0.7.0-traffic-1', body)
        self.assertIn('/static/app.css?v=v0.7.0-traffic-1', body)

    def test_home_renders_after_search_results_exist(self):
        from toyoko_tracker import runtime

        result = tracker_app.HotelResult(
            code="00001",
            url="https://example.test/hotel",
            name="Test & Hotel",
            available=False,
        )
        with patch.object(runtime, "_LAST_RESULTS", [result]):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Test &amp; Hotel", response.get_data(as_text=True))

    def test_webui_guide_is_version_aware(self):
        script = self.client.get("/static/app.js").get_data(as_text=True)

        self.assertIn("GUIDE_SEEN_KEY", script)
        self.assertIn("guideAppVersion()", script)
        self.assertIn("storageGet(GUIDE_SEEN_KEY", script)
        self.assertIn("storageSet(GUIDE_SEEN_KEY, guideAppVersion())", script)

    def test_update_check_runs_in_background(self):
        from toyoko_tracker import runtime

        with patch.object(runtime, "_check_latest_async") as check:
            response = self.client.post("/update_check")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.get_json()["ok"])
        check.assert_called_once_with()

    def test_hotel_catalog_routes_delegate_to_background_service(self):
        from toyoko_tracker import runtime

        catalog = {"state": "fresh", "open_japan_count": 349}
        with patch.object(runtime, "_catalog_status_snapshot", return_value=catalog):
            response = self.client.get("/hotel_catalog_status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["catalog"], catalog)

        queued = {"state": "checking"}
        with patch.object(runtime, "_request_catalog_refresh", return_value=queued) as refresh:
            response = self.client.post("/hotel_catalog_refresh")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["catalog"], queued)
        refresh.assert_called_once_with(force=True)

    def test_hotel_info_route_returns_official_preview(self):
        from toyoko_tracker import runtime

        expected = {"code": "00119", "name": "Official Hotel", "address": "Official Address"}
        with patch.object(runtime, "_get_hotel_info", return_value=expected) as mock_get:
            response = self.client.get("/hotel_info?code=00119&language=ja")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["info"], expected)
        mock_get.assert_called_once_with("00119", "ja")

    def test_hotel_info_route_rejects_invalid_code(self):
        response = self.client.get("/hotel_info?code=invalid&language=zh_cn")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    def test_hotel_info_route_supports_database_providers(self):
        from toyoko_tracker import runtime

        hotel = {"code": "dormy:291", "provider": "dormy", "url": "https://hotel.example/"}
        expected = {"code": "dormy:291", "provider": "dormy", "name": "Dormy Test"}
        with patch.object(runtime, "_db_load_hotel", return_value=hotel) as mock_load, \
             patch.object(runtime, "_get_provider_hotel_info", return_value=expected) as mock_info:
            response = self.client.get("/hotel_info?code=dormy:291&language=ja")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["info"], expected)
        mock_load.assert_called_once_with("dormy:291", "ja")
        mock_info.assert_called_once_with(hotel, "ja")

    def test_atomic_json_write_replaces_complete_document(self):
        from toyoko_tracker import runtime

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir) / "state.json")
            runtime._atomic_write_json(path, {"version": 1})
            runtime._atomic_write_json(path, {"version": 2, "ready": True})
            with open(path, encoding="utf-8") as stream:
                payload = json.load(stream)

        self.assertEqual(payload, {"version": 2, "ready": True})

    def test_start_route_passes_single_scan_flag_to_worker(self):
        from toyoko_tracker import runtime

        created_threads = []

        class FakeThread:
            def __init__(self, *, target, args, name, daemon):
                self.target = target
                self.args = args
                self.name = name
                self.daemon = daemon
                self.started = False
                created_threads.append(self)

            def start(self):
                self.started = True

            def is_alive(self):
                return False

        cfg = tracker_app.AppConfig()
        payload = {
            "run_once": True,
            "start_date": "2026-07-17",
            "end_date": "2026-07-18",
            "hotel_codes": ["00001"],
            "selected_hotels": [{"code": "00001", "name": "Test Hotel"}],
        }
        with patch.object(runtime, "_CONFIG", cfg), \
             patch.object(runtime, "_worker_thread", None), \
             patch.object(runtime.threading, "Thread", FakeThread), \
             patch.object(runtime, "_save_config_to_file"), \
             patch.object(runtime, "_remember_search"), \
             patch.object(runtime, "clear_alert_state"), \
             patch.object(runtime, "send_start_notifications"):
            response = self.client.post("/start", json=payload)

        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["run_once"])
        self.assertEqual(body["message"], "scan_once_started")
        self.assertEqual(created_threads[0].args, (True,))
        self.assertTrue(created_threads[0].started)

    def test_preferences_route_persists_zero_repeat_count(self):
        from toyoko_tracker import runtime

        cfg = tracker_app.AppConfig()
        cfg.available_alert_repeat = 1
        with patch.object(runtime, "_CONFIG", cfg), \
             patch.object(runtime, "_save_config_to_file", return_value=True) as save_config:
            response = self.client.post(
                "/api/v1/preferences",
                json={"available_alert_repeat": 0},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(cfg.available_alert_repeat, 0)
        save_config.assert_called_once_with(runtime.AUTO_SAVE_PATH)

    def test_preference_controls_are_saved_without_starting_search(self):
        script = self.client.get("/static/app.js").get_data(as_text=True)

        self.assertIn("AUTO_SAVE_PREFERENCE_IDS", script)
        self.assertIn("schedulePreferenceSave", script)
        self.assertIn("/api/v1/preferences", script)

    def test_trend_panel_uses_one_hotel_selector_and_readable_observations(self):
        body = self.client.get("/").get_data(as_text=True)
        script = self.client.get("/static/app.js").get_data(as_text=True)

        self.assertIn('id="trend_hotel"', body)
        self.assertIn('id="trend-overview"', body)
        self.assertIn('id="trend-observations"', body)
        self.assertIn("trendAvailabilityAxis", script)
        self.assertIn("trend-observation-row", script)

    def test_hotel_picker_is_always_visible_without_nested_details_box(self):
        body = self.client.get("/").get_data(as_text=True)

        self.assertIn('<section id="area_picker_panel"', body)
        self.assertNotIn('<details class="box" id="area_picker_panel"', body)
        self.assertNotIn('<summary>区域酒店搜索 Area Hotel Picker</summary>', body)


if __name__ == "__main__":
    unittest.main()
