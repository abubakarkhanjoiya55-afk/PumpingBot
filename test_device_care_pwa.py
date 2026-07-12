import json
import struct
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from device_care.scanner import router


STATIC = Path(__file__).parent / "device_care" / "static"


class DeviceCarePwaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(router)
        cls.client = TestClient(app)

    def test_activation_gate_precedes_live_monitoring(self):
        response = self.client.get("/device-care/")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        html = response.text
        self.assertIn('id="activateBtn"', html)
        self.assertIn("Har nayi page par ek tap zaroori hai", html)
        self.assertIn("musalsal background alarm guaranteed nahi", html)
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

    def test_manifest_icons_are_routable_pngs_with_declared_sizes(self):
        response = self.client.get("/device-care/manifest.json")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        manifest = response.json()
        self.assertEqual("./", manifest["start_url"])
        self.assertEqual("./", manifest["scope"])

        for icon in manifest["icons"]:
            self.assertEqual("image/png", icon["type"])
            icon_response = self.client.get(f"/device-care/{icon['src']}")
            self.assertEqual(200, icon_response.status_code)
            self.assertEqual("image/png", icon_response.headers["content-type"])
            self.assertEqual(b"\x89PNG\r\n\x1a\n", icon_response.content[:8])
            width, height = struct.unpack(">II", icon_response.content[16:24])
            declared = tuple(map(int, icon["sizes"].split("x")))
            self.assertEqual(declared, (width, height))

    def test_service_worker_precaches_current_manifest_assets(self):
        manifest = json.loads((STATIC / "manifest.json").read_text())
        response = self.client.get("/device-care/sw.js")

        self.assertEqual(200, response.status_code)
        self.assertEqual("no-cache", response.headers["cache-control"])
        service_worker = response.text
        for icon in manifest["icons"]:
            self.assertIn(f"${{BASE}}/{icon['src']}", service_worker)
        self.assertIn('e.request.method !== "GET"', service_worker)


if __name__ == "__main__":
    unittest.main()
