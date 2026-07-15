import json
import sqlite3
import sys
import tempfile
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import price_calendar, runtime
from toyoko_tracker.app import app
from toyoko_tracker.models import AppConfig, HotelResult


def _config() -> AppConfig:
    cfg = AppConfig(
        people=2,
        rooms=1,
        smoking="noSmoking",
        membership_status="member",
        hotel_codes=["00001"],
        selected_hotels=[{
            "code": "00001",
            "display_code": "00001",
            "provider": "toyoko",
            "name_primary": "东横INN测试酒店",
            "name_en": "Toyoko Inn Test Hotel",
        }],
    )
    cfg.room_requirement = "single"
    cfg.engine = "http"
    return cfg


def _result(stay_date: str, available=True) -> HotelResult:
    return HotelResult(
        code="00001",
        provider="toyoko",
        url=f"https://example.test/book?start={stay_date}",
        name="Toyoko Inn Test Hotel",
        available=available,
        min_price=9800 if available else None,
        min_price_text="¥ 9,800" if available else None,
        min_member_price_text="¥ 9,300" if available else None,
        min_price_room="Non-Smoking Single" if available else None,
        min_remaining="2" if available else None,
        checked_at="2026-07-15T10:00:00+08:00",
        engine_used="http",
    )


def test_condition_key_tracks_price_conditions_but_not_selected_dates():
    cfg = _config()
    original = price_calendar.condition_key(cfg)
    cfg.start_date = "2027-01-10"
    cfg.end_date = "2027-01-11"
    assert price_calendar.condition_key(cfg) == original
    cfg.primary_language = "ja"
    assert price_calendar.condition_key(cfg) == original
    cfg.people = 3
    assert price_calendar.condition_key(cfg) != original


def test_month_dates_validates_and_expands_month():
    assert price_calendar.month_dates("2028-02")[-1] == "2028-02-29"
    for invalid in ("2028-2", "2028-13", "not-a-month"):
        try:
            price_calendar.month_dates(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected {invalid!r} to be rejected")


def test_price_calendar_persists_member_price_and_marks_stale_rows():
    cfg = _config()
    stay = "2027-01-18"
    checkout = "2027-01-19"
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "hotels.sqlite3")
        with patch.object(price_calendar, "HOTEL_DATABASE_PATH", database):
            price_calendar.record_day(cfg, "00001", "toyoko", stay, checkout, _result(stay))
            snapshot = price_calendar.calendar_snapshot(cfg, "00001", "2027-01")

            assert snapshot["summary"]["loaded_days"] == 1
            assert snapshot["summary"]["available_days"] == 1
            assert snapshot["summary"]["lowest_price"] == 9800
            assert snapshot["summary"]["lowest_member_price"] == 9300
            assert snapshot["days"][0]["room_type"] == "Non-Smoking Single"
            assert snapshot["days"][0]["stale"] is False

            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE price_calendar_days SET observed_at=observed_at-7200"
                )
                connection.commit()
            stale = price_calendar.calendar_snapshot(cfg, "00001", "2027-01")
            assert stale["days"][0]["stale"] is True
            assert stale["summary"]["stale_days"] == 1


def test_price_calendar_endpoint_lists_selected_hotels_and_conditions():
    cfg = _config()
    current_month = date.today().strftime("%Y-%m")
    app.config.update(TESTING=True)
    with tempfile.TemporaryDirectory() as tmp_dir, \
         patch.object(runtime, "_CONFIG", cfg), \
         patch.object(price_calendar, "HOTEL_DATABASE_PATH", str(Path(tmp_dir) / "calendar.sqlite3")):
        response = app.test_client().get(
            f"/api/v1/price-calendar?hotel_code=00001&month={current_month}"
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["hotel"]["code"] == "00001"
    assert payload["hotels"][0]["name"] == "东横INN测试酒店"
    assert payload["conditions"]["people"] == 2
    assert payload["conditions"]["room_requirement"] == "single"
    assert payload["days"] == []


def test_price_calendar_refresh_reports_existing_other_job():
    cfg = _config()
    current_month = date.today().strftime("%Y-%m")
    active = {"state": "running", "running": True, "hotel_code": "00002", "month": current_month}
    app.config.update(TESTING=True)
    with patch.object(runtime, "_CONFIG", cfg), \
         patch.object(runtime, "_start_price_calendar_job", return_value=(active, False)):
        response = app.test_client().post(
            "/api/v1/price-calendar/refresh",
            data=json.dumps({"hotel_code": "00001", "month": current_month}),
            content_type="application/json",
        )

    assert response.status_code == 409
    assert response.get_json()["job"]["hotel_code"] == "00002"


def test_price_calendar_worker_scans_each_future_night_without_notifications():
    cfg = _config()
    first = date.today().isoformat()
    second = (date.today() + timedelta(days=1)).isoformat()
    job_id = "job-test"
    with runtime._PRICE_CALENDAR_JOB_LOCK:
        runtime._PRICE_CALENDAR_JOB = {
            "id": job_id,
            "state": "queued",
            "running": True,
            "done": 0,
            "errors": 0,
            "successful": 0,
            "cached": 0,
        }
    checker = Mock(side_effect=[_result(first), _result(second, available=False)])
    recorder = Mock()
    with patch.object(runtime, "_price_calendar_month_dates", return_value=[first, second]), \
         patch.object(runtime, "_price_calendar_data_snapshot", return_value={"days": []}), \
         patch.object(runtime, "_check_hotel_cached", checker), \
         patch.object(runtime, "_record_price_calendar_day", recorder), \
         patch.object(runtime, "_record_provider_result"), \
         patch.object(runtime, "_provider_cooldown_until", return_value=0), \
         patch.object(runtime.time, "sleep"):
        runtime._run_price_calendar_job(job_id, deepcopy(cfg), "00001", first[:7], False)

    with runtime._PRICE_CALENDAR_JOB_LOCK:
        job = deepcopy(runtime._PRICE_CALENDAR_JOB)
    assert checker.call_count == 2
    assert recorder.call_count == 2
    assert job["state"] == "complete"
    assert job["done"] == 2
    assert job["successful"] == 2
    assert job["errors"] == 0
