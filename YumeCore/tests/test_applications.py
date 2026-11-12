import unittest
from unittest.mock import MagicMock
import json
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

from events import EventBus
from applications.thermal import ThermalButton
from app_service import AppService


class TestApplications(unittest.TestCase):
    def setUp(self):
        self.events = EventBus()
        self.mock_sensor = MagicMock()
        self.mock_sensor.read.return_value = 25.0
        self.mock_led = MagicMock()
        self.thermal = ThermalButton(
            sensor=self.mock_sensor,
            events=self.events,
            threshold=45.0,
            hysteresis=2.0,
            debounce_ms=0,  # immediate for testing
            led_device=self.mock_led
        )
        self.app_service = AppService()
        self.app_service.register_app(self.thermal)

    def test_thermal_button_threshold_and_hysteresis(self):
        # Initial reading 25.0 -> state RELEASED
        self.assertEqual(self.thermal.read("state"), "RELEASED")

        # Temp rises to 44.0 (below threshold 45.0) -> still RELEASED
        self.events.publish("sensor.temperature.changed", {"value": 44.0})
        self.assertEqual(self.thermal.read("state"), "RELEASED")

        # Temp rises to 45.5 (>= 45.0) -> PRESSED, LED ON
        self.events.publish("sensor.temperature.changed", {"value": 45.5})
        self.assertEqual(self.thermal.read("state"), "PRESSED")
        self.mock_led.write.assert_called_with("state", "ON")

        # Temp drops to 44.0 (>= threshold - hysteresis = 43.0) -> still PRESSED! (Hysteresis check)
        self.events.publish("sensor.temperature.changed", {"value": 44.0})
        self.assertEqual(self.thermal.read("state"), "PRESSED")

        # Temp drops to 42.5 (< 43.0) -> RELEASED, LED OFF
        self.events.publish("sensor.temperature.changed", {"value": 42.5})
        self.assertEqual(self.thermal.read("state"), "RELEASED")
        self.mock_led.write.assert_called_with("state", "OFF")

    def test_app_service_generic_commands(self):
        # APP_LIST
        status, payload = self.app_service.handle("APP_LIST", [])
        self.assertEqual(status, "OK")
        apps = json.loads(payload)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["name"], "thermal")

        # APP_INFO
        status, payload = self.app_service.handle("APP_INFO", ["thermal"])
        self.assertEqual(status, "OK")
        info = json.loads(payload)
        self.assertIn("threshold", info["properties"])

        # APP_READ
        status, payload = self.app_service.handle("APP_READ", ["thermal", "threshold"])
        self.assertEqual(status, "OK")
        res = json.loads(payload)
        self.assertEqual(res["value"], 45.0)

        # APP_WRITE
        status, payload = self.app_service.handle("APP_WRITE", ["thermal", "threshold", "50.5"])
        self.assertEqual(status, "OK")
        self.assertEqual(self.thermal.read("threshold"), 50.5)

    def test_legacy_backward_compatibility(self):
        # TEMP
        self.thermal._last_temp = 32.4
        status, payload = self.app_service.handle("TEMP", [])
        self.assertEqual(status, "OK")
        self.assertEqual(payload, "TEMP=32.4C")

        # AUTO OFF
        status, payload = self.app_service.handle("AUTO", ["OFF"])
        self.assertEqual(status, "OK")
        self.assertEqual(payload, "AUTO=OFF")
        self.assertFalse(self.thermal.read("enabled"))

        # AUTO ON
        status, payload = self.app_service.handle("AUTO", ["ON"])
        self.assertEqual(status, "OK")
        self.assertEqual(payload, "AUTO=ON")
        self.assertTrue(self.thermal.read("enabled"))

        # AUTO_SET
        status, payload = self.app_service.handle("AUTO_SET", ["48.0"])
        self.assertEqual(status, "OK")
        self.assertEqual(payload, "THRESHOLD=48.0C")
        self.assertEqual(self.thermal.read("threshold"), 48.0)


if __name__ == "__main__":
    unittest.main()
