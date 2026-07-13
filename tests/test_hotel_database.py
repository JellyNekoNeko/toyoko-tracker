from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toyoko_tracker import hotel_database
from toyoko_tracker.hotel_info import parse_provider_hotel_info_html
from toyoko_tracker.runtime import _classify_provider_hotels


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


if __name__ == "__main__":
    unittest.main()
