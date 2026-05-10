import sys
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


if __name__ == "__main__":
    unittest.main()
