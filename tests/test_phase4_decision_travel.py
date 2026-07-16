import json
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import decision_intelligence, runtime, travel_lists
from toyoko_tracker.app import app
from toyoko_tracker.models import AppConfig


def _hotel(code: str, name: str, lat: float, lng: float) -> dict:
    return {
        "code": code,
        "display_code": code,
        "provider": "toyoko",
        "name_primary": name,
        "lat": lat,
        "lng": lng,
    }


def _night(code: str, stay_date: str, price: int, member: int = 0) -> dict:
    return {
        "hotel_code": code,
        "provider": "toyoko",
        "stay_date": stay_date,
        "checkout_date": stay_date,
        "observed_at": time.time(),
        "result": {
            "code": code,
            "available": True,
            "min_price": price,
            "min_price_text": f"¥{price:,}",
            "min_member_price_text": f"¥{member:,}" if member else None,
            "min_price_room": "Single",
            "url": f"https://example.test/{code}/{stay_date}",
        },
    }


def test_percentiles_price_assessment_and_anomaly_contract():
    assert decision_intelligence.percentile([10, 20, 30, 40], 0.25) == 17.5
    low = decision_intelligence.assess_price(100, [100, 200, 300, 400])
    normal = decision_intelligence.assess_price(250, [100, 200, 300, 400])
    high = decision_intelligence.assess_price(400, [100, 200, 300, 400])
    insufficient = decision_intelligence.assess_price(100, [100, 110, 120])
    assert low["label"] == "low"
    assert normal["label"] == "normal"
    assert high["label"] == "high"
    assert insufficient["label"] == "insufficient"
    assert "4" in insufficient["explanation"]


def test_historical_statistics_merge_sources_dedupe_and_expose_method():
    now = time.time()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "history.sqlite3")
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE scan_observations(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at REAL NOT NULL,
                    scope_key TEXT NOT NULL,
                    hotel_code TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    available INTEGER,
                    room_count INTEGER NOT NULL DEFAULT 0,
                    min_price INTEGER,
                    room_type TEXT NOT NULL DEFAULT '',
                    engine TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'live'
                );
                CREATE TABLE price_calendar_days(
                    condition_key TEXT NOT NULL,
                    hotel_code TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    stay_date TEXT NOT NULL,
                    checkout_date TEXT NOT NULL,
                    observed_at REAL NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY(condition_key,hotel_code,stay_date)
                );
                """
            )
            for index, price in enumerate(
                [9000, 9200, 9400, 9600, 9800, 10000, 10200, 50000]
            ):
                connection.execute(
                    """
                    INSERT INTO scan_observations(
                        observed_at,scope_key,hotel_code,provider,start_date,
                        end_date,available,room_count,min_price,room_type,engine,source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        now - (index + 1) * 3600,
                        "scope-a",
                        "00001",
                        "toyoko",
                        f"2026-08-{index + 1:02d}",
                        f"2026-08-{index + 2:02d}",
                        1,
                        1,
                        price,
                        "Single",
                        "http",
                        "live",
                    ),
                )
            # Mirrored sample inside 60 seconds is collapsed.
            connection.execute(
                """
                INSERT INTO price_calendar_days VALUES (?,?,?,?,?,?,?)
                """,
                (
                    "condition-a",
                    "00001",
                    "toyoko",
                    "2026-08-01",
                    "2026-08-02",
                    now - 3600 + 10,
                    json.dumps({"min_price": 9000, "available": True}),
                ),
            )
        with patch.object(
            decision_intelligence,
            "HOTEL_DATABASE_PATH",
            database,
        ):
            snapshot = decision_intelligence.price_statistics(
                ["00001"],
                days=30,
                scope_key="scope-a",
                condition_key="condition-a",
                current_prices={"00001": 9300},
                hotel_metadata={"00001": {"name_primary": "Alpha"}},
            )

    hotel = snapshot["hotels"][0]
    assert hotel["raw_sample_count"] == 8
    assert hotel["sample_count"] == 7
    assert hotel["excluded_anomaly_count"] == 1
    assert hotel["minimum"] == 9000
    assert hotel["maximum"] == 10200
    assert hotel["median"] == 9600
    assert hotel["assessment"]["label"] == "low"
    assert hotel["method"]["percentile"] == "R-7 linear interpolation"
    assert hotel["sample_window"]["days"] == 30


def test_split_stay_optimizer_requires_nightly_evidence_and_ranks_reproducibly():
    hotels = [
        _hotel("A", "Alpha", 35.0, 139.0),
        _hotel("B", "Beta", 35.01, 139.01),
    ]
    job = {
        "windows": [{
            "key": "2026-08-01:2026-08-04",
            "checkin_date": "2026-08-01",
            "checkout_date": "2026-08-04",
            "nights": 3,
        }],
        "hotels": hotels,
        "conditions": {"membership_status": "non_member"},
    }
    evidence = [
        _night("A", "2026-08-01", 6000),
        _night("B", "2026-08-01", 9000),
        _night("B", "2026-08-02", 7000),
        _night("A", "2026-08-03", 6000),
        _night("B", "2026-08-03", 9000),
    ]
    first = decision_intelligence.optimize_split_stays(
        job,
        evidence,
        move_penalty=500,
        distance_cost_per_km=10,
        top_k=6,
    )
    second = decision_intelligence.optimize_split_stays(
        job,
        evidence,
        move_penalty=500,
        distance_cost_per_km=10,
        top_k=6,
    )

    assert first == {
        **second,
        "generated_at": first["generated_at"],
    }
    assert first["complete_evidence"] is True
    assert first["plans"][0]["plan_type"] == "split"
    assert first["plans"][0]["total_price"] == 19000
    assert first["plans"][0]["moves"] == 2
    assert first["plans"][0]["evidence_complete"] is True
    assert len(first["plans"][0]["nightly"]) == 3
    assert first["weights"]["move_penalty"] == 500

    incomplete = decision_intelligence.optimize_split_stays(
        job,
        evidence[:-2],
    )
    assert incomplete["complete_evidence"] is False
    assert incomplete["missing_dates"] == ["2026-08-03"]
    assert incomplete["plans"] == []
    invalid = decision_intelligence.optimize_split_stays(
        job,
        evidence,
        window_key="missing-window",
    )
    assert invalid["window"] is None
    assert invalid["plans"] == []


def test_travel_list_crud_priorities_links_budget_and_secret_free_exports():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "travel.sqlite3")
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "CREATE TABLE external_resources(resource_id TEXT PRIMARY KEY)"
            )
            connection.execute(
                "INSERT INTO external_resources(resource_id) VALUES ('job-a')"
            )
        with patch.object(travel_lists, "HOTEL_DATABASE_PATH", database):
            created = travel_lists.create_travel_list({
                "name": "Tokyo trip",
                "start_date": "2026-08-01",
                "end_date": "2026-08-04",
                "budget_limit": 30000,
                "notes": "Near the station",
            })
            travel_lists.upsert_hotel(
                created["list_id"],
                "00001",
                {
                    "hotel": {
                        "code": "00001",
                        "name_primary": "Alpha",
                        "bot_token": "secret-value",
                    },
                    "priority": 5,
                    "notes": "First choice",
                },
            )
            travel_lists.link_resource(
                created["list_id"],
                "comparison",
                "job-a",
                {"name": "August comparison", "smtp_pass": "hidden"},
            )
            full = travel_lists.get_travel_list(created["list_id"])
            assert full["hotels"][0]["priority"] == 5
            assert "bot_token" not in json.dumps(full)
            assert "smtp_pass" not in json.dumps(full)
            assert full["links"][0]["resource_id"] == "job-a"

            updated = travel_lists.update_travel_list(
                created["list_id"],
                {"budget_limit": 25000},
                expected_revision=full["revision"],
            )
            summary = travel_lists.trip_summary_payload(
                updated,
                {
                    "estimated_total": 19000,
                    "split_plans": [{
                        "total_price": 19000,
                        "moves": 1,
                        "score": 21000,
                        "segments": [],
                    }],
                },
            )
            markdown = travel_lists.trip_summary_markdown(summary)
            html = travel_lists.trip_summary_html(summary)
            assert summary["budget"]["remaining"] == 6000
            assert summary["budget"]["status"] == "within_budget"
            assert "# Tokyo trip" in markdown
            assert "<h1>Tokyo trip</h1>" in html
            assert "secret-value" not in json.dumps(summary)
            with pytest.raises(travel_lists.TravelListConflictError):
                travel_lists.update_travel_list(
                    created["list_id"],
                    {"budget_limit": 24000},
                    expected_revision=full["revision"],
                )

            travel_lists.delete_travel_list(created["list_id"])
            assert travel_lists.list_travel_lists() == []
        with closing(sqlite3.connect(database)) as connection, connection:
            assert connection.execute(
                "SELECT resource_id FROM external_resources"
            ).fetchone()[0] == "job-a"


def test_phase4_api_routes_and_decision_center_markup():
    cfg = AppConfig(
        hotel_codes=["00001"],
        selected_hotels=[_hotel("00001", "Alpha", 35.0, 139.0)],
    )
    app.config.update(TESTING=True)
    with tempfile.TemporaryDirectory() as tmp_dir, \
         patch.object(
             travel_lists,
             "HOTEL_DATABASE_PATH",
             str(Path(tmp_dir) / "phase4.sqlite3"),
         ), \
         patch.object(
             decision_intelligence,
             "HOTEL_DATABASE_PATH",
             str(Path(tmp_dir) / "phase4.sqlite3"),
         ), \
         patch.object(runtime, "_CONFIG", cfg), \
         patch.object(runtime, "_resolve_task_id", return_value="task-a"), \
         patch.object(
             runtime,
             "_decision_statistics_for_task",
             return_value={
                 "task_id": "task-a",
                 "hotels": [],
                 "summary": {"hotel_count": 0},
             },
         ):
        client = app.test_client()
        decision = client.get("/api/v1/decision/prices?task_id=task-a")
        created = client.post(
            "/api/v1/travel-lists",
            data=json.dumps({
                "name": "Tokyo",
                "start_date": "2026-08-01",
                "end_date": "2026-08-04",
                "budget_limit": 30000,
            }),
            content_type="application/json",
        )
        list_id = created.get_json()["travel_list"]["list_id"]
        summary = client.get(
            f"/api/v1/travel-lists/{list_id}/summary?format=markdown"
        )
        page = client.get("/").get_data(as_text=True)

    assert decision.status_code == 200
    assert decision.get_json()["statistics"]["task_id"] == "task-a"
    assert created.status_code == 201
    assert created.get_json()["travel_list"]["name"] == "Tokyo"
    assert summary.status_code == 200
    assert "# Tokyo" in summary.get_data(as_text=True)
    assert 'data-app-view="travel"' in page
    assert 'id="view-travel"' in page
    assert 'id="travel-price-table-body"' in page
    assert 'id="travel-alert-rule-select"' in page
