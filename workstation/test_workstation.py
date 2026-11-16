import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from workstation.commander import WorkstationCommander
from workstation.hub import WorkstationHub
from workstation.server import create_app


class TestWorkstationEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)
        self.hub = WorkstationHub(simulate=True, poll_interval=10.0, state_dir=self.state_dir)
        self.hub.connect()

    def tearDown(self):
        self.hub.stop()
        self._tmp.cleanup()

    def test_hub_connect_snapshot_and_state_files(self):
        snap = self.hub.get_snapshot()
        self.assertTrue(snap["connection"]["connected"])
        self.assertEqual(snap["connection"]["mode"], "simulated")
        self.assertIn("sensor.temperature", snap["devices"])
        self.assertIn("sensor.light", snap["devices"])
        self.assertIn("actuator.desk_lamp", snap["devices"])
        self.assertIn("thermal", snap["apps"])
        self.assertIn("ambient_light", snap["apps"])

        snapshot_file = self.state_dir / "snapshot.json"
        self.assertTrue(snapshot_file.exists())
        disk_data = json.loads(snapshot_file.read_text(encoding="utf-8"))
        self.assertEqual(disk_data["connection"]["mode"], "simulated")

    def test_simulated_env_triggers_thermal_and_light_apps(self):
        # Dark + hot environment -> lamp turns on and LED turns on
        snap = self.hub.set_simulation_env(temp_c=48.0, light_pct=20.0)
        self.assertEqual(snap["telemetry"]["led_state"], "ON")
        self.assertEqual(snap["telemetry"]["desk_lamp_duty"], 60.0)

        # Bright + cool environment -> lamp off and LED off
        snap = self.hub.set_simulation_env(temp_c=25.0, light_pct=85.0)
        self.assertEqual(snap["telemetry"]["led_state"], "OFF")
        self.assertEqual(snap["telemetry"]["desk_lamp_duty"], 0.0)

    def test_commander_natural_language_and_modes(self):
        cmd = WorkstationCommander(self.hub)

        # Switch to focus mode
        res = cmd.interpret_and_execute("切换到专注模式")
        self.assertTrue(res["ok"])
        self.assertEqual(res["snapshot"]["workstation"]["active_mode"], "focus")

        # Set lamp duty manually
        res = cmd.interpret_and_execute("把台灯调到 85%")
        self.assertTrue(res["ok"])
        self.assertEqual(res["snapshot"]["telemetry"]["desk_lamp_duty"], 85.0)

        # Adjust thermal threshold
        res = cmd.interpret_and_execute("把温控阈值设为 39.5 度")
        self.assertTrue(res["ok"])
        self.assertEqual(res["snapshot"]["apps"]["thermal"]["values"]["threshold"], 39.5)

        # Query status
        res = cmd.interpret_and_execute("汇报当前状态")
        self.assertIn("温度", res["reply"])
        self.assertIn("85", res["reply"])

    def test_fastapi_hud_and_rest_api(self):
        app = create_app(hub=self.hub)
        with TestClient(app) as client:
            r = client.get("/")
            self.assertEqual(r.status_code, 200)
            self.assertIn("YUMELAB", r.text)

            r = client.get("/api/state")
            self.assertEqual(r.status_code, 200)
            payload = r.json()
            self.assertIn("snapshot", payload)
            self.assertIn("modes", payload)

            r = client.post("/api/mode", json={"mode": "night_bench"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["snapshot"]["workstation"]["active_mode"], "night_bench")

            r = client.post("/api/sim/env", json={"temp_c": 46.5, "light_pct": 15.0})
            self.assertEqual(r.status_code, 200)
            tel = r.json()["snapshot"]["telemetry"]
            self.assertEqual(tel["led_state"], "ON")
            self.assertEqual(tel["desk_lamp_duty"], 95.0)

            r = client.post("/api/command", json={"text": "把温控阈值设为 41 度"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["snapshot"]["apps"]["thermal"]["values"]["threshold"], 41.0)


if __name__ == "__main__":
    unittest.main()
