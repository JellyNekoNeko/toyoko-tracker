import json
import sys
import tempfile
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import flexible_stays, runtime
from toyoko_tracker.app import app
from toyoko_tracker.models import AppConfig, HotelResult


def _hotel(code: str, name: str) -> dict:
    return {
        "code": code,
        "display_code": code,
        "provider": "toyoko",
        "name_primary": name,
    }


def _night_result(
    code: str,
    stay_date: str,
    price: int,
    *,
    member_price: Optional[int] = None,
    room: str = "Non-Smoking Single",
    available: Optional[bool] = True,
) -> HotelResult:
    return HotelResult(
        code=code,
        provider="toyoko",
        url=f"https://example.test/{code}/{stay_date}",
        name=f"Hotel {code}",
        available=available,
        min_price=price if available else None,
        min_price_text=f"¥{price:,}" if available else None,
        min_member_price_text=(
            f"¥{member_price:,}" if available and member_price is not None else None
        ),
        min_price_room=room if available else None,
        offers_display=(
            [{
                "room_title": room,
                "price_text": f"¥{price:,}",
                "member_price_text": (
                    f"¥{member_price:,}" if member_price is not None else None
                ),
            }]
            if available
            else []
        ),
        checked_at="2026-07-17T10:00:00+08:00",
        engine_used="http",
    )


def test_date_combinations_are_deterministic_unique_and_weekend_filtered():
    first = flexible_stays.generate_stay_windows(
        "2026-07-17",
        "2026-07-27",
        2,
        "weekend",
    )
    second = flexible_stays.generate_stay_windows(
        "2026-07-17",
        "2026-07-27",
        2,
        "weekend",
    )

    assert first == second
    assert len(first) == len({item["key"] for item in first})
    assert all(
        date.fromisoformat(item["checkin_date"]).weekday() in {4, 5}
        for item in first
    )
    assert flexible_stays.required_stay_dates(first) == sorted(
        flexible_stays.required_stay_dates(first)
    )


def test_continuous_stay_uses_same_room_and_calculates_regular_and_member_totals():
    window = flexible_stays.generate_stay_windows(
        "2026-08-01", "2026-08-04", 3
    )[0]
    evidence = []
    for offset, (price, member) in enumerate(
        [(9000, 8500), (10000, 9400), (11000, 10200)]
    ):
        stay = (date(2026, 8, 1) + timedelta(days=offset)).isoformat()
        evidence.append({
            "stay_date": stay,
            "observed_at": 1.0,
            "result": {
                **vars(_night_result("00001", stay, price, member_price=member)),
            },
        })

    result = flexible_stays.evaluate_continuous_stay("00001", window, evidence)

    assert result["state"] == "available"
    assert result["full_stay_available"] is True
    assert result["room_continuity"] == "same_room"
    assert result["total_price"] == 30000
    assert result["average_nightly_price"] == 10000
    assert result["member_total_price"] == 28100
    assert result["provider_verified_full_stay"] is False


def test_continuous_stay_distinguishes_isolated_availability_and_room_changes():
    window = flexible_stays.generate_stay_windows(
        "2026-08-10", "2026-08-12", 2
    )[0]
    evidence = [
        {
            "stay_date": "2026-08-10",
            "result": vars(
                _night_result("00001", "2026-08-10", 9000, room="Single")
            ),
        },
        {
            "stay_date": "2026-08-11",
            "result": vars(
                _night_result("00001", "2026-08-11", 9500, room="Twin")
            ),
        },
    ]
    changed = flexible_stays.evaluate_continuous_stay("00001", window, evidence)
    assert changed["state"] == "available"
    assert changed["isolated_available_nights"] == 2
    assert changed["room_continuity"] == "room_change_required"
    assert changed["total_price"] == 18500

    evidence[1]["result"] = vars(
        _night_result(
            "00001",
            "2026-08-11",
            9500,
            room="Twin",
            available=False,
        )
    )
    unavailable = flexible_stays.evaluate_continuous_stay(
        "00001", window, evidence
    )
    assert unavailable["state"] == "unavailable"
    assert unavailable["full_stay_available"] is False
    assert unavailable["isolated_available_nights"] == 1


def test_repository_resumes_only_missing_nights_and_builds_heatmap_minima():
    with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
        flexible_stays,
        "HOTEL_DATABASE_PATH",
        str(Path(tmp_dir) / "flexible.sqlite3"),
    ):
        job = flexible_stays.create_job({
            "task_id": "task-a",
            "earliest_date": "2026-09-01",
            "latest_date": "2026-09-03",
            "nights": 2,
            "shortcut": "custom",
            "hotel_codes": ["00001", "00002"],
            "selected_hotels": [
                _hotel("00001", "Alpha"),
                _hotel("00002", "Beta"),
            ],
            "conditions": {"membership_status": "member"},
        })
        for code, base in (("00001", 9000), ("00002", 10500)):
            for offset in range(2):
                stay = (date(2026, 9, 1) + timedelta(days=offset)).isoformat()
                result = _night_result(
                    code,
                    stay,
                    base + offset * 500,
                    member_price=base - 500 + offset * 500,
                )
                flexible_stays.record_night(
                    job["job_id"],
                    code,
                    "toyoko",
                    stay,
                    (date.fromisoformat(stay) + timedelta(days=1)).isoformat(),
                    result,
                )
        assert flexible_stays.pending_work(job["job_id"]) == []
        flexible_stays.update_job_progress(job["job_id"])
        flexible_stays.recompute_results(job["job_id"])
        comparison = flexible_stays.comparison_snapshot(job["job_id"])

        assert comparison["summary"]["available_stays"] == 2
        assert comparison["summary"]["lowest_total_price"] == 17500
        assert comparison["daily_minima"]["2026-09-01"]["hotel_codes"] == [
            "00001"
        ]
        assert comparison["rows"][0]["cells"][0]["daily_cheapest"] is True
        assert comparison["rows"][0]["cells"][0]["heat_level"] == 1
        assert comparison["rows"][1]["cells"][0]["heat_level"] == 5


def test_unknown_night_stays_visible_and_is_retried_after_resume():
    with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
        flexible_stays,
        "HOTEL_DATABASE_PATH",
        str(Path(tmp_dir) / "resume.sqlite3"),
    ):
        job = flexible_stays.create_job({
            "earliest_date": "2026-10-01",
            "latest_date": "2026-10-02",
            "nights": 1,
            "hotel_codes": ["00001"],
            "selected_hotels": [_hotel("00001", "Alpha")],
        })
        flexible_stays.record_night(
            job["job_id"],
            "00001",
            "toyoko",
            "2026-10-01",
            "2026-10-02",
            _night_result(
                "00001",
                "2026-10-01",
                0,
                available=None,
            ),
        )
        updated = flexible_stays.update_job_progress(
            job["job_id"],
            error="temporary provider error",
        )

        assert updated["completed_work"] == 0
        assert flexible_stays.list_nights(job["job_id"])[0]["state"] == "unknown"
        assert flexible_stays.pending_work(job["job_id"]) == [{
            "hotel_code": "00001",
            "provider": "toyoko",
            "stay_date": "2026-10-01",
            "checkout_date": "2026-10-02",
        }]


def test_worker_uses_shared_provider_pacing_and_completes_unique_nights():
    cfg = AppConfig(
        hotel_codes=["00001"],
        selected_hotels=[_hotel("00001", "Alpha")],
    )
    first = date.today() + timedelta(days=2)
    latest = first + timedelta(days=2)
    with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
        flexible_stays,
        "HOTEL_DATABASE_PATH",
        str(Path(tmp_dir) / "worker.sqlite3"),
    ):
        job = flexible_stays.create_job({
            "earliest_date": first.isoformat(),
            "latest_date": latest.isoformat(),
            "nights": 2,
            "hotel_codes": ["00001"],
            "selected_hotels": [_hotel("00001", "Alpha")],
            "conditions": {"membership_status": "member"},
        })
        checker = Mock(side_effect=[
            _night_result("00001", first.isoformat(), 9000),
            _night_result(
                "00001",
                (first + timedelta(days=1)).isoformat(),
                9500,
            ),
        ])
        pacer = Mock()
        pacer.acquire.side_effect = lambda *args, **kwargs: nullcontext()
        with patch.object(runtime, "_CONFIG", cfg), \
             patch.object(runtime, "_check_hotel_cached", checker), \
             patch.object(runtime, "_provider_pacer", pacer), \
             patch.object(runtime, "_provider_cooldown_until", return_value=0), \
             patch.object(runtime, "_record_provider_result"), \
             patch.object(runtime, "_record_price_calendar_day"):
            runtime._run_flexible_stay_job(job["job_id"])

        finished = flexible_stays.get_job(job["job_id"])
        assert finished["status"] == "complete"
        assert finished["completed_work"] == 2
        assert checker.call_count == 2
        assert pacer.acquire.call_count == 2
        assert all(
            call.kwargs["task_id"] == f"flexible-stay:{job['job_id']}"
            for call in pacer.acquire.call_args_list
        )


def test_flexible_stay_api_and_price_view_expose_phase_three_controls():
    cfg = AppConfig(
        hotel_codes=["00001"],
        selected_hotels=[_hotel("00001", "Alpha")],
    )
    first = date.today() + timedelta(days=2)
    latest = first + timedelta(days=2)
    app.config.update(TESTING=True)
    with tempfile.TemporaryDirectory() as tmp_dir, \
         patch.object(
             flexible_stays,
             "HOTEL_DATABASE_PATH",
             str(Path(tmp_dir) / "api.sqlite3"),
         ), \
         patch.object(runtime, "_CONFIG", cfg), \
         patch.object(runtime, "_resolve_task_id", return_value="task-a"), \
         patch.object(
             runtime,
             "_start_flexible_stay_job",
             side_effect=lambda job_id: (
                 flexible_stays.get_job(job_id),
                 True,
             ),
         ):
        response = app.test_client().post(
            "/api/v1/flexible-stays",
            data=json.dumps({
                "earliest_date": first.isoformat(),
                "latest_date": latest.isoformat(),
                "nights": 2,
                "hotel_codes": ["00001"],
                "selected_hotels": [_hotel("00001", "Alpha")],
            }),
            content_type="application/json",
        )
        body = app.test_client().get("/").get_data(as_text=True)

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["job"]["task_id"] == "task-a"
    assert payload["job"]["total_work"] == 2
    assert 'id="flexible-stay-card"' in body
    assert 'id="flexible-shortcut-weekend"' in body
    assert 'id="flexible-comparison-body"' in body
