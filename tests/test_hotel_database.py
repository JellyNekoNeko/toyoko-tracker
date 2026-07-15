from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from toyoko_tracker import hotel_database
from toyoko_tracker.hotel_info import parse_provider_hotel_info_html
from toyoko_tracker import runtime
from toyoko_tracker.runtime import _classify_provider_hotels, _provider_database_is_fresh


class HotelDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temporary_directory.name) / "hotels.sqlite3")
        self.path_patch = patch.object(hotel_database, "HOTEL_DATABASE_PATH", self.database_path)
        self.path_patch.start()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temporary_directory.cleanup()

    @staticmethod
    def hotel(code: str, area_id: int, lat: float = 35.0, lng: float = 139.0):
        return {
            "provider": "dormy",
            "code": code,
            "display_code": code,
            "name_ja": code,
            "name_en": code,
            "region_id": 3,
            "prefecture_id": 13,
            "detail_area_id": area_id,
            "lat": lat,
            "lng": lng,
        }

    def test_baseline_does_not_report_every_hotel_as_new(self) -> None:
        result = hotel_database.sync_provider("dormy", [self.hotel("A", 468), self.hotel("B", 462)])
        self.assertEqual(result["new"], [])
        self.assertEqual(hotel_database.provider_count("dormy"), 2)
        self.assertEqual([row["code"] for row in hotel_database.load_hotels("dormy", detail_area_id=468)], ["A"])

    def test_later_sync_records_additions_and_removals(self) -> None:
        hotel_database.sync_provider("dormy", [self.hotel("A", 468), self.hotel("B", 462)])
        result = hotel_database.sync_provider("dormy", [self.hotel("B", 462), self.hotel("C", 468)])
        self.assertEqual([row["code"] for row in result["new"]], ["C"])
        self.assertEqual([row["code"] for row in result["removed"]], ["A"])
        self.assertEqual(hotel_database.provider_count("dormy"), 2)

    def test_provider_coordinate_count_excludes_invalid_points(self) -> None:
        hotels = [
            self.hotel("A", 468, 35.0, 139.0),
            self.hotel("B", 462, 999.0, 139.0),
            self.hotel("C", 462, None, None),
        ]

        hotel_database.sync_provider("dormy", hotels)
        status = hotel_database.status_snapshot()["providers"]["dormy"]

        self.assertEqual(status["hotel_count"], 3)
        self.assertEqual(status["coordinate_count"], 1)

    def test_first_success_after_initial_error_still_establishes_baseline(self) -> None:
        hotel_database.record_sync_error("dormy", "temporary network error")

        result = hotel_database.sync_provider(
            "dormy", [self.hotel("A", 468), self.hotel("B", 462)]
        )

        self.assertEqual(result["new"], [])
        status = hotel_database.status_snapshot()["providers"]["dormy"]
        self.assertEqual(status["initialized"], 1)
        self.assertEqual(status["error"], "")

    def test_existing_database_schema_is_migrated_without_losing_baseline(self) -> None:
        import sqlite3

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE provider_sync (
                    provider TEXT PRIMARY KEY,
                    checked_at TEXT NOT NULL,
                    hotel_count INTEGER NOT NULL DEFAULT 0,
                    coordinate_count INTEGER NOT NULL DEFAULT 0,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    removed_count INTEGER NOT NULL DEFAULT 0,
                    new_hotels_json TEXT NOT NULL DEFAULT '[]',
                    removed_hotels_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO provider_sync(provider, checked_at, hotel_count)
                VALUES ('dormy', '2026-07-15T00:00:00', 2);
                """
            )

        result = hotel_database.sync_provider("dormy", [self.hotel("C", 468)])

        self.assertEqual([row["code"] for row in result["new"]], ["C"])
        self.assertEqual(hotel_database.status_snapshot()["providers"]["dormy"]["initialized"], 1)

    def test_migration_clears_legacy_full_provider_alert(self) -> None:
        import sqlite3

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE provider_sync (
                    provider TEXT PRIMARY KEY,
                    checked_at TEXT NOT NULL,
                    hotel_count INTEGER NOT NULL DEFAULT 0,
                    coordinate_count INTEGER NOT NULL DEFAULT 0,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    removed_count INTEGER NOT NULL DEFAULT 0,
                    new_hotels_json TEXT NOT NULL DEFAULT '[]',
                    removed_hotels_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO provider_sync(
                    provider, checked_at, hotel_count, new_count, new_hotels_json
                ) VALUES (
                    'dormy', '2026-07-15T00:00:00', 100, 100,
                    '[{"code":"A","name":"Hotel A"}]'
                );
                """
            )

        status = hotel_database.status_snapshot()["providers"]["dormy"]

        self.assertEqual(status["new_count"], 0)
        self.assertEqual(status["new_hotels"], [])
        self.assertEqual(status["initialized"], 1)

    def test_coordinate_classifier_uses_nearest_area_in_same_prefecture(self) -> None:
        hotels = [{
            "provider": "dormy", "code": "A", "address": "東京都大田区",
            "lat": 35.56, "lng": 139.71,
        }]
        references = {13: [(462, 35.72, 139.79), (468, 35.561, 139.711)]}
        classified = _classify_provider_hotels(hotels, references)
        self.assertEqual(classified[0]["prefecture_id"], 13)
        self.assertEqual(classified[0]["region_id"], 3)
        self.assertEqual(classified[0]["detail_area_id"], 468)

    def test_provider_preview_uses_official_schema_and_local_access(self) -> None:
        hotel = self.hotel("dormy:A", 468, 35.56, 139.71)
        hotel.update({
            "provider": "dormy", "name_ja": "テストホテル", "name_en": "Test Hotel",
            "address": "東京都大田区", "access": "蒲田駅から徒歩3分",
            "map_url": "https://maps.example/hotel",
        })
        html = """
        <meta property="og:image" content="/images/hotel.jpg">
        <script type="application/ld+json">
        {"@type":"Hotel","name":"Official Test Hotel","address":{
          "@type":"PostalAddress","postalCode":"144-0000","addressRegion":"Tokyo",
          "addressLocality":"Ota-ku","streetAddress":"1-2-3 Kamata"}}
        </script>
        """
        info = parse_provider_hotel_info_html(html, hotel, "ja", "https://hotel.example/detail/")
        self.assertEqual(info["provider"], "dormy")
        self.assertEqual(info["name"], "テストホテル")
        self.assertIn("1-2-3 Kamata", info["address"])
        self.assertEqual(info["map_image_url"], "https://hotel.example/images/hotel.jpg")
        self.assertEqual(info["access_remarks"], "蒲田駅から徒歩3分")

    def test_provider_database_freshness_requires_complete_initialized_data(self) -> None:
        from datetime import datetime

        checked_at = datetime.now().isoformat(timespec="seconds")
        providers = {
            provider: {
                "checked_at": checked_at,
                "hotel_count": 50,
                "initialized": 1,
                "error": "",
            }
            for provider in ("routeinn", "dormy", "mystays", "daiwa")
        }

        self.assertTrue(_provider_database_is_fresh({"providers": providers}))
        providers["mystays"]["error"] = "temporary failure"
        self.assertFalse(_provider_database_is_fresh({"providers": providers}))

    def test_fresh_provider_database_skips_network_refresh(self) -> None:
        from datetime import datetime

        status = {
            "providers": {
                provider: {
                    "checked_at": datetime.now().isoformat(timespec="seconds"),
                    "hotel_count": 50,
                    "initialized": 1,
                    "error": "",
                }
                for provider in ("routeinn", "dormy", "mystays", "daiwa")
            }
        }
        with patch.object(runtime, "_db_status_snapshot", return_value=status), patch.object(
            runtime, "_detail_area_references"
        ) as references:
            result = runtime._refresh_provider_database(force=False)

        self.assertEqual(result["state"], "fresh")
        references.assert_not_called()

    def test_missing_area_reference_data_aborts_provider_refresh(self) -> None:
        with patch.object(runtime, "_db_status_snapshot", return_value={"providers": {}}), patch.object(
            runtime, "_detail_area_references", return_value={}
        ), patch.object(runtime, "_db_record_sync_error") as record_error:
            result = runtime._refresh_provider_database(force=False)

        self.assertEqual(result["state"], "failed")
        self.assertIn("area reference validation failed", result["error"])
        self.assertEqual(record_error.call_count, 4)


if __name__ == "__main__":
    unittest.main()
