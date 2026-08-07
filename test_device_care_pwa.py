import json
import struct
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from device_care.scanner import router, legacy_router


STATIC = Path(__file__).parent / "device_care" / "static"


class MySignalsPwaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(router)
        app.include_router(legacy_router)
        cls.client = TestClient(app)

    def test_activation_gate_precedes_live_monitoring(self):
        response = self.client.get("/my-signals/")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        html = response.text
        self.assertIn("Crypto Pumping", html)
        self.assertIn('id="updateBanner"', html)
        self.assertIn("Update Now", html)
        self.assertIn("checkServerVersion", html)
        self.assertIn("/api/version", html)
        self.assertIn("btnCheckUpdate", html)
        self.assertIn("btnUpdateMain", html)
        self.assertIn("btnUpdateAuth", html)
        self.assertIn("setButtonsReady", html)
        self.assertIn("updatePulse", html)
        self.assertIn("koi link nahi", html)
        self.assertIn('id="authScreen"', html)
        self.assertIn('id="userLoginForm"', html)
        self.assertIn('id="adminLoginForm"', html)
        self.assertIn('id="registerForm"', html)
        self.assertIn('id="adminView"', html)
        self.assertIn("User Login", html)
        self.assertIn("isAdminGateOpen", html)
        # Admin Login tab hidden from normal users
        self.assertIn('id="tabAdminLogin" class="hidden"', html)
        self.assertIn('id="activateBtn"', html)
        self.assertIn("Har nayi page par ek tap zaroori hai", html)
        self.assertIn("Score 90+", html)
        self.assertIn("bootAuth()", html)
        self.assertIn("startMonitoring()", html)

        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        self.assertIn("async function activateAlarm()", script)
        self.assertIn("ensureAudioReady()", script)
        self.assertIn("requestNotifications()", script)
        self.assertIn("playAlarmPattern", script)
        self.assertIn("startMonitoring()", script)
        self.assertIn("startPersistentAlarm(pending)", script)
        self.assertEqual(1, script.count("Notification.requestPermission()"))
        self.assertIn("activateBtn.addEventListener('click', activateAlarm)", script)
        self.assertIn("bootAuth()", script)
        self.assertIn("monitoringAllowed", script)

    def test_legacy_device_care_redirects_to_my_signals(self):
        response = self.client.get("/device-care/", follow_redirects=False)
        self.assertIn(response.status_code, (307, 302))
        self.assertTrue(response.headers["location"].startswith("/my-signals"))

    def test_manifest_icons_are_routable_pngs_with_declared_sizes(self):
        response = self.client.get("/my-signals/manifest.json")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        manifest = response.json()
        self.assertEqual("Crypto Pumping", manifest["name"])
        self.assertEqual("Crypto Pumping", manifest["short_name"])
        self.assertEqual("./", manifest["start_url"])
        self.assertEqual("./", manifest["scope"])

        for icon in manifest["icons"]:
            self.assertEqual("image/png", icon["type"])
            icon_response = self.client.get(f"/my-signals/{icon['src']}")
            self.assertEqual(200, icon_response.status_code)
            self.assertEqual("image/png", icon_response.headers["content-type"])
            self.assertEqual(b"\x89PNG\r\n\x1a\n", icon_response.content[:8])
            width, height = struct.unpack(">II", icon_response.content[16:24])
            declared = tuple(map(int, icon["sizes"].split("x")))
            self.assertEqual(declared, (width, height))

    def test_service_worker_precaches_current_manifest_assets(self):
        manifest = json.loads((STATIC / "manifest.json").read_text())
        response = self.client.get("/my-signals/sw.js")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        service_worker = response.text
        self.assertIn('"/my-signals"', service_worker)
        self.assertIn("Crypto Pumping", service_worker)
        self.assertIn("SKIP_WAITING", service_worker)
        self.assertIn("cps-v4.2.3", service_worker)
        for icon in manifest["icons"]:
            self.assertIn(f"${{BASE}}/{icon['src']}", service_worker)
        self.assertIn('e.request.method !== "GET"', service_worker)

    def test_version_endpoint_for_in_app_update(self):
        response = self.client.get("/my-signals/api/version")
        self.assertEqual(200, response.status_code)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual("4.2.3", data.get("version"))
        self.assertEqual("4.2.3", data.get("appVersion"))
        self.assertEqual("Crypto Pumping", data.get("app"))


if __name__ == "__main__":
    unittest.main()
