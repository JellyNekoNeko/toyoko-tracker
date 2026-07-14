import unittest

from flask import Flask, jsonify

from toyoko_tracker.traffic_meter import TrafficMeter, configure_traffic_meter


class TrafficMeterTests(unittest.TestCase):
    def test_counts_application_bytes_requests_and_live_rate(self):
        now = [100.0]
        meter = TrafficMeter(clock=lambda: now[0])
        measurement = meter.begin(
            method="GET",
            path="/",
            headers=(("Accept", "text/html"),),
            remote_addr="192.168.1.8",
        )
        now[0] += 1.0
        meter.finish(
            measurement,
            status_code=200,
            content_length=512,
            headers=(("Content-Type", "text/html"),),
        )

        snapshot = meter.snapshot()
        self.assertEqual(snapshot["requests"], 1)
        self.assertEqual(snapshot["page_views"], 1)
        self.assertEqual(snapshot["remote_requests"], 1)
        self.assertEqual(snapshot["failed_requests"], 0)
        self.assertGreater(snapshot["upload_bytes"], 0)
        self.assertGreater(snapshot["download_bytes"], 512)
        self.assertGreater(snapshot["upload_bps"], 0)
        self.assertGreater(snapshot["download_bps"], 0)
        self.assertEqual(snapshot["active_requests"], 0)

    def test_excludes_traffic_endpoint_and_cleans_aborted_request(self):
        meter = TrafficMeter()
        self.assertIsNone(meter.begin(method="GET", path="/api/v1/traffic"))
        measurement = meter.begin(method="POST", path="/start", content_length=20)
        self.assertEqual(meter.snapshot()["active_requests"], 1)
        meter.abort(measurement)
        self.assertEqual(meter.snapshot()["active_requests"], 0)
        self.assertEqual(meter.snapshot()["requests"], 0)

    def test_flask_integration_tracks_success_and_error_responses(self):
        app = Flask(__name__)
        meter = TrafficMeter()
        configure_traffic_meter(app, meter)

        @app.get("/")
        def home():
            return "home"

        @app.post("/echo")
        def echo():
            return jsonify({"ok": True})

        @app.get("/api/v1/traffic")
        def traffic():
            return jsonify(meter.snapshot())

        client = app.test_client()
        client.get("/api/v1/traffic")
        client.get("/")
        client.post("/echo", data="payload")
        client.get("/missing")
        snapshot = client.get("/api/v1/traffic").get_json()

        self.assertEqual(snapshot["requests"], 3)
        self.assertEqual(snapshot["page_views"], 1)
        self.assertEqual(snapshot["failed_requests"], 1)
        self.assertGreater(snapshot["upload_bytes"], 0)
        self.assertGreater(snapshot["download_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
