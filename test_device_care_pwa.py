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
        self.assertIn("My Signals", html)
        self.assertIn('id="activateBtn"', html)
        self.assertIn("Har nayi page par ek tap zaroori hai", html)
        self.assertIn("Score 90+", html)
        self.assertIn("startMonitoring()", html)

        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        activate = script[script.index("async function activateAlarm()"):]
        self.assertLess(activate.index("ensureAudioReady()"), activate.index("requestNotifications()"))
        self.assertLess(activate.index("requestNotifications()"), activate.index("playAlarmPattern"))
        self.assertLess(activate.index("playAlarmPattern"), activate.index("startMonitoring()"))
        self.assertLess(activate.index("startMonitoring()"), activate.index("loadAlerts()"))
        self.assertIn("startPersistentAlarm(pending)", activate)
        self.assertEqual(1, script.count("Notification.requestPermission()"))
        self.assertIn("activateBtn.addEventListener('click', activateAlarm)", script)
        # Signals list page-open pe load; awaaz ke liye Activate
        self.assertIn("startMonitoring();", script.split("updateCapabilityStatus();")[-1])

    def test_legacy_device_care_redirects_to_my_signals(self):
        response = self.client.get("/device-care/", follow_redirects=False)
        self.assertIn(response.status_code, (307, 302))
        self.assertTrue(response.headers["location"].startswith("/my-signals"))

    def test_manifest_icons_are_routable_pngs_with_declared_sizes(self):
        response = self.client.get("/my-signals/manifest.json")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        manifest = response.json()
        self.assertEqual("My Signals", manifest["name"])
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
        self.assertIn("My Signals", service_worker)
        for icon in manifest["icons"]:
            self.assertIn(f"${{BASE}}/{icon['src']}", service_worker)
        self.assertIn('e.request.method !== "GET"', service_worker)


if __name__ == "__main__":
    unittest.main()
