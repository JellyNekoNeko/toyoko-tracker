import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import scan_cache


class ScanCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "hotels.sqlite3")
        self.path_patch = patch.object(scan_cache, "HOTEL_DATABASE_PATH", self.database_path)
        self.path_patch.start()
        with scan_cache._LOCK:
            for key in scan_cache._METRICS:
                scan_cache._METRICS[key] = 0
            scan_cache._STATUS_CACHE.update({"checked_at": 0.0, "entries": 0, "fresh_entries": 0})

    def tearDown(self):
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_put_get_and_expiry(self):
        with patch.object(scan_cache.time, "time", return_value=1_000.0):
            scan_cache.put("key", "toyoko", "00001", {"available": False}, 10)
        with patch.object(scan_cache.time, "time", return_value=1_004.0):
            entry = scan_cache.get("key")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.age_sec, 4)
        self.assertFalse(entry.expired)

        with patch.object(scan_cache.time, "time", return_value=1_011.0):
            self.assertIsNone(scan_cache.get("key"))
            expired = scan_cache.get("key", allow_expired=True, count_metrics=False)
        self.assertTrue(expired.expired)
        self.assertEqual(expired.result["available"], False)

    def test_coalesced_call_runs_one_producer(self):
        calls = []

        def producer():
            calls.append(time.time())
            time.sleep(0.05)
            return {"value": 7}

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(scan_cache.coalesced_call, "same", producer) for _ in range(2)]
            outputs = [future.result() for future in futures]

        self.assertEqual(len(calls), 1)
        self.assertEqual([output[0]["value"] for output in outputs], [7, 7])
        self.assertEqual(sorted(output[1] for output in outputs), [False, True])

    def test_checkpoint_round_trip(self):
        scan_cache.save_checkpoint("scope", {"round": 3, "results": [{"code": "00001"}]})
        checkpoint = scan_cache.load_checkpoint("scope")
        self.assertEqual(checkpoint["round"], 3)
        self.assertEqual(checkpoint["results"][0]["code"], "00001")
        self.assertGreaterEqual(checkpoint["checkpoint_age_sec"], 0)

    def test_future_scan_entry_is_evicted_after_clock_rollback(self):
        with patch.object(scan_cache.time, "time", return_value=5_000.0):
            scan_cache.put("future", "toyoko", "00001", {"available": True}, 60)
        with patch.object(scan_cache.time, "time", return_value=1_000.0):
            entry = scan_cache.get("future", allow_expired=True)

        self.assertIsNone(entry)
        self.assertEqual(scan_cache.status_snapshot()["entries"], 0)

    def test_future_checkpoint_is_not_restored_after_clock_rollback(self):
        with patch.object(scan_cache.time, "time", return_value=5_000.0):
            scan_cache.save_checkpoint("future", {"round": 99})
        with patch.object(scan_cache.time, "time", return_value=1_000.0):
            checkpoint = scan_cache.load_checkpoint("future")

        self.assertIsNone(checkpoint)


if __name__ == "__main__":
    unittest.main()
