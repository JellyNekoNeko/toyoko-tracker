import os
import tempfile
import unittest
from unittest.mock import patch

from toyoko_tracker import app as tracker_app
from toyoko_tracker import mobile_access
from toyoko_tracker import restart_helper


class MobileAccessManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "mobile_access.json")
        self.manager = mobile_access.MobileAccessManager(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_configuration_is_persisted_and_rotation_changes_revision(self):
        initial = self.manager.snapshot()
        enabled = self.manager.configure(enabled=True, public_url="https://hotels.example.com:4170")
        rotated = self.manager.configure(rotate=True)
        reloaded = mobile_access.MobileAccessManager(self.path).snapshot()

        self.assertFalse(initial.enabled)
        self.assertTrue(enabled.enabled)
        self.assertNotEqual(enabled.pairing_code, rotated.pairing_code)
        self.assertNotEqual(enabled.revision, rotated.revision)
        self.assertEqual(reloaded.pairing_code, rotated.pairing_code)
        self.assertTrue(reloaded.enabled)
        self.assertEqual(reloaded.public_url, "https://hotels.example.com:4170")

    def test_pairing_attempts_are_rate_limited(self):
        for _ in range(6):
            valid, retry_after = self.manager.verify("WRONG-CODE", "192.168.1.20")
            self.assertFalse(valid)
            self.assertEqual(retry_after, 0)

        valid, retry_after = self.manager.verify("WRONG-CODE", "192.168.1.20")
        self.assertFalse(valid)
        self.assertGreater(retry_after, 0)

    def test_virtual_benchmark_network_is_not_advertised(self):
        self.assertTrue(mobile_access._is_usable_lan_address("192.168.31.66"))
        self.assertFalse(mobile_access._is_usable_lan_address("198.18.0.1"))
        self.assertFalse(mobile_access._is_usable_lan_address("127.0.0.1"))
        self.assertTrue(mobile_access._is_direct_public_address("8.8.8.8"))
        self.assertFalse(mobile_access._is_direct_public_address("192.168.31.66"))

    def test_tailscale_status_parser_extracts_remote_connection(self):
        details = mobile_access._tailscale_details_from_status({
            "Self": {
                "Online": True,
                "TailscaleIPs": ["100.76.240.29", "fd7a:115c:a1e0::1"],
                "DNSName": "melons-macbook-pro.example.ts.net.",
            }
        })

        self.assertTrue(details["available"])
        self.assertTrue(details["online"])
        self.assertEqual(details["address"], "100.76.240.29")
        self.assertEqual(details["dns_name"], "melons-macbook-pro.example.ts.net")

    def test_restart_helper_preserves_requested_port(self):
        self.assertEqual(restart_helper._preferred_port(["--port", "4180"]), 4180)
        self.assertEqual(restart_helper._preferred_port(["--port=4190"]), 4190)
        self.assertEqual(restart_helper._preferred_port(["--no-browser"]), 4170)


class MobileAccessRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = mobile_access.MobileAccessManager(
            os.path.join(self.temp_dir.name, "mobile_access.json")
        )
        self.client = tracker_app.app.test_client()
        self.remote = {"REMOTE_ADDR": "192.168.1.20"}
        self.manager_patch = patch.object(mobile_access, "manager", self.manager)
        self.manager_patch.start()
        self.tailscale_patch = patch.object(
            mobile_access,
            "tailscale_details",
            return_value={"available": False, "online": False},
        )
        self.tailscale_patch.start()

    def tearDown(self):
        self.tailscale_patch.stop()
        self.manager_patch.stop()
        self.temp_dir.cleanup()

    def test_remote_access_is_denied_while_disabled(self):
        response = self.client.get("/health", environ_overrides=self.remote)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Local access only")

    def test_remote_session_requires_pairing_and_survives_after_success(self):
        state = self.manager.configure(enabled=True)

        blocked = self.client.get(
            "/health",
            headers={"Accept": "application/json"},
            environ_overrides=self.remote,
        )
        paired = self.client.post(
            "/pair",
            data={"code": state.pairing_code},
            environ_overrides=self.remote,
        )
        allowed = self.client.get("/health", environ_overrides=self.remote)

        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(paired.status_code, 302)
        self.assertEqual(allowed.status_code, 200)

    def test_pairing_accepts_safari_null_origin(self):
        state = self.manager.configure(enabled=True)

        response = self.client.post(
            "/pair",
            data={"code": state.pairing_code},
            headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
            environ_overrides=self.remote,
        )

        self.assertEqual(response.status_code, 302)

    def test_rotating_code_invalidates_existing_remote_session(self):
        state = self.manager.configure(enabled=True)
        self.client.post("/pair", data={"code": state.pairing_code}, environ_overrides=self.remote)
        self.manager.configure(rotate=True)

        response = self.client.get(
            "/health",
            headers={"Accept": "application/json"},
            environ_overrides=self.remote,
        )

        self.assertEqual(response.status_code, 401)

    def test_only_localhost_can_change_mobile_access(self):
        self.manager.configure(enabled=True)
        self.client.post(
            "/pair",
            data={"code": self.manager.snapshot().pairing_code},
            environ_overrides=self.remote,
        )

        remote_response = self.client.post(
            "/mobile_access",
            json={"enabled": False},
            environ_overrides=self.remote,
        )
        local_response = self.client.post("/mobile_access", json={"enabled": True})

        self.assertEqual(remote_response.status_code, 403)
        self.assertEqual(local_response.status_code, 200)
        self.assertTrue(local_response.get_json()["enabled"])

    def test_local_setting_change_can_schedule_automatic_restart(self):
        tracker_app.app.config["TOYOKO_LAN_BOUND"] = False
        self.manager.configure(enabled=False)
        with patch("toyoko_tracker.server.schedule_restart", return_value=True) as restart:
            response = self.client.post(
                "/mobile_access",
                json={"enabled": True, "restart": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["restart_scheduled"])
        restart.assert_called_once_with()

    def test_mobile_status_groups_lan_tailscale_and_public_connections(self):
        self.manager.configure(enabled=True)
        with (
            patch.object(mobile_access, "local_ipv4_addresses", return_value=["192.168.1.10"]),
            patch.object(mobile_access, "direct_public_ipv4_addresses", return_value=[]),
            patch.object(
                mobile_access,
                "tailscale_details",
                return_value={
                    "available": True,
                    "online": True,
                    "address": "100.76.240.29",
                    "dns_name": "mac.example.ts.net",
                },
            ),
        ):
            response = self.client.get("/mobile_access")

        connections = response.get_json()["connections"]
        self.assertEqual(connections["lan"]["url"], "http://192.168.1.10")
        self.assertEqual(connections["tailscale"]["url"], "http://100.76.240.29")
        self.assertEqual(connections["tailscale"]["dns_url"], "http://mac.example.ts.net")
        self.assertFalse(connections["public"]["available"])

    def test_public_url_can_be_configured_and_is_validated(self):
        self.manager.configure(enabled=True)

        invalid = self.client.post(
            "/mobile_access",
            json={"enabled": True, "public_url": "not-a-url"},
        )
        valid = self.client.post(
            "/mobile_access",
            json={"enabled": True, "public_url": "https://hotels.example.com:4170/"},
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(valid.status_code, 200)
        public = valid.get_json()["connections"]["public"]
        self.assertTrue(public["available"])
        self.assertTrue(public["configured"])
        self.assertEqual(public["url"], "https://hotels.example.com:4170")

    def test_pwa_assets_are_available_before_pairing(self):
        self.manager.configure(enabled=True)

        manifest = self.client.get("/manifest.webmanifest", environ_overrides=self.remote)
        worker = self.client.get("/service-worker.js", environ_overrides=self.remote)

        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.mimetype, "application/manifest+json")
        self.assertIn("Toyoko Chan", manifest.get_data(as_text=True))
        self.assertEqual(worker.status_code, 200)
        self.assertIn("toyoko-chan-shell", worker.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
