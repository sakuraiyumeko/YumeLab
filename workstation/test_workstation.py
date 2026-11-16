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

    def test_piano_player_and_sfx_in_workstation(self):
        app = create_app(hub=self.hub)
        with TestClient(app) as client:
            r = client.get("/api/piano/sheets")
            self.assertEqual(r.status_code, 200)
            sheets = r.json()["sheets"]
            self.assertGreaterEqual(len(sheets), 1)
            sheet_ids = [s["id"] for s in sheets]
            self.assertIn("Sakura", sheet_ids)

            r = client.post("/api/piano/play", json={"sheet": "Sakura"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["player"]["state"], "PLAYING")
            self.assertEqual(r.json()["player"]["sheet"], "Sakura")

            r = client.post("/api/piano/pause")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["player"]["state"], "PAUSED")

            r = client.post("/api/piano/resume")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["player"]["state"], "PLAYING")

            r = client.post("/api/piano/stop")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["player"]["state"], "IDLE")

            # CLI bridge piano commands
            r = client.post("/api/cli", json={"text": "piano ls"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["ok"])
            self.assertIn("Sakura", r.json()["output"])

            # Natural language piano play & stop
            r = client.post("/api/command", json={"text": "演奏樱花"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["snapshot"]["player"]["state"], "PLAYING")

            r = client.post("/api/command", json={"text": "停止演奏"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["snapshot"]["player"]["state"], "IDLE")

            # SFX property write via REST API
            r = client.post(
                "/api/devices/actuator.buzzer.passive/properties/sfx",
                json={"value": "click"},
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["value"], "click")

            # Verify HUD static HTML & JS expose sheet player and non-numeric SFX input
            html = client.get("/").text
            self.assertIn("sheetSelect", html)
            js = client.get("/static/app.js").text
            self.assertIn("SFX_PRESETS_OPTIONS", js)

    def test_first_note_duration_not_truncated(self):
        import time
        from buzzer_piano import BuzzerPlayer

        notes_log = []

        class DummyDevices:
            def write(self, dev, prop, val):
                # Simulate 80ms RTT for first command (e.g. hub overhead / serial latency)
                if not notes_log:
                    time.sleep(0.08)
                else:
                    time.sleep(0.005)
                notes_log.append((time.monotonic(), val))
                return val

        class DummyCore:
            def __init__(self):
                self.devices = DummyDevices()

        sheet_file = self.state_dir / "first_note_test.toml"
        # 120 BPM quarter note = 0.5s duration, gate=0.9 -> sound ~0.45s
        sheet_file.write_text(
            'title = "First Note"\nbpm = 120\ngate = 0.9\nmelody = ["C5:4"]\n',
            encoding="utf-8",
        )
        player = BuzzerPlayer(DummyCore())
        player.play(sheet_file)
        if player.thread:
            player.thread.join(timeout=2.0)

        # Expected 2 writes: note on (freq=523) and note off (freq=0)
        self.assertEqual(len(notes_log), 2)
        on_time, on_val = notes_log[0]
        off_time, off_val = notes_log[1]
        self.assertEqual(on_val, 524)
        self.assertEqual(off_val, 0)
        sounding_duration = off_time - on_time
        # Duration should be close to 0.45s, definitely NOT truncated by the 80ms startup delay
        self.assertGreaterEqual(sounding_duration, 0.40)

    def test_buzzer_player_absolute_bpm_timing(self):
        import time
        from buzzer_piano import BuzzerPlayer

        class DummyDevices:
            def __init__(self):
                self.calls = []

            def write(self, dev, prop, val):
                # Simulate 15ms serial RTT per command
                time.sleep(0.015)
                self.calls.append((time.monotonic(), val))
                return val

        class DummyCore:
            def __init__(self):
                self.devices = DummyDevices()

        sheet_file = self.state_dir / "bpm_test.toml"
        sheet_file.write_text(
            'title = "BPM Test"\nbpm = 240\ngate = 0.8\nmelody = ["C5:4", "D5:4", "E5:4", "F5:4"]\n',
            encoding="utf-8",
        )
        # 4 quarter notes at 240 BPM = 1.000s total expected duration
        player = BuzzerPlayer(DummyCore())
        t0 = time.monotonic()
        player.play(sheet_file)
        if player.thread:
            player.thread.join(timeout=3.0)
        elapsed = time.monotonic() - t0
        self.assertAlmostEqual(elapsed, 1.0, delta=0.12)

    def test_active_buzzer_morse_and_commander(self):
        cmd = WorkstationCommander(self.hub)
        # Test direct device write
        res = self.hub.write_device("actuator.buzzer.active", "morse", "SOS", sync_poll=False)
        self.assertEqual(res["value"], "SOS")
        self.assertEqual(self.hub.core.devices.read("actuator.buzzer.active", "morse"), "SOS")

        # Test Commander natural language
        nl_res = cmd.interpret_and_execute("发报 SOS")
        self.assertTrue(nl_res["ok"])
        self.assertIn("SOS", nl_res["reply"])

        nl_res2 = cmd.interpret_and_execute("用摩斯码发报 HELLO")
        self.assertTrue(nl_res2["ok"])
        self.assertIn("HELLO", nl_res2["reply"])


if __name__ == "__main__":
    unittest.main()
