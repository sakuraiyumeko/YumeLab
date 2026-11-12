import unittest
from unittest.mock import MagicMock, patch
import json
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

from devices import Device, DeviceRegistry
from hardware import HardwareManager
import hardware
from sensors import TemperatureSensor
import actuators
from actuators import LED, DigitalOutput
from device_service import DeviceService


class TestDevices(unittest.TestCase):
    def setUp(self):
        self.hw = HardwareManager()
        self.registry = DeviceRegistry()
        self.service = DeviceService(self.registry)

    def test_device_registry(self):
        class DummyDevice(Device):
            device_id = "test.dummy"
            device_type = "dummy"

        dev = DummyDevice()
        self.registry.register(dev)
        self.assertTrue(self.registry.has("test.dummy"))
        self.assertEqual(self.registry.get("test.dummy"), dev)

        # Duplicate register raises
        with self.assertRaises(ValueError):
            self.registry.register(dev)

        # List returns info dict
        lst = self.registry.list()
        self.assertEqual(len(lst), 1)
        self.assertEqual(lst[0]["id"], "test.dummy")

        # Unregister
        self.registry.unregister("test.dummy")
        self.assertFalse(self.registry.has("test.dummy"))

    def test_temperature_sensor(self):
        mock_adc = MagicMock()
        mock_adc.read_u16.return_value = 14000

        with patch.object(hardware, "ADC", return_value=mock_adc):
            sensor = TemperatureSensor(self.hw)
            self.assertEqual(sensor.device_id, "sensor.temperature")
            val = sensor.read("value")
            self.assertIsInstance(val, float)
            raw = sensor.read("raw")
            self.assertEqual(raw, 14000)

            # Property write not allowed
            with self.assertRaises(ValueError):
                sensor.write("value", 30)

    def test_led_actuator(self):
        mock_pin = MagicMock()
        mock_pin_state = [0]
        def fake_value(val=None):
            if val is not None:
                mock_pin_state[0] = 1 if val else 0
            return mock_pin_state[0]
        mock_pin.value.side_effect = fake_value

        with patch.object(actuators, "Pin", return_value=mock_pin), \
             patch.object(hardware, "Pin", return_value=mock_pin):
            led = LED(self.hw)
            self.assertEqual(led.device_id, "led")

            # Write ON
            res = led.write("state", "ON")
            self.assertEqual(res, "ON")
            self.assertEqual(mock_pin_state[0], 1)

            # Write OFF
            res = led.write("state", "OFF")
            self.assertEqual(res, "OFF")
            self.assertEqual(mock_pin_state[0], 0)

            # Invalid value raises
            with self.assertRaises(ValueError):
                led.write("state", "INVALID")

    def test_device_service_protocol_commands(self):
        mock_pin = MagicMock()
        mock_pin_state = [1]
        def fake_value(val=None):
            if val is not None:
                mock_pin_state[0] = 1 if val else 0
            return mock_pin_state[0]
        mock_pin.value.side_effect = fake_value

        with patch.object(actuators, "Pin", return_value=mock_pin), \
             patch.object(hardware, "Pin", return_value=mock_pin):
            led = LED(self.hw, initial="ON")
            self.registry.register(led)

            # DEVICE_LIST
            status, payload = self.service.handle("DEVICE_LIST", [])
            self.assertEqual(status, "OK")
            data = json.loads(payload)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], "led")

            # DEVICE_INFO
            status, payload = self.service.handle("DEVICE_INFO", ["led"])
            self.assertEqual(status, "OK")
            info = json.loads(payload)
            self.assertEqual(info["id"], "led")
            self.assertIn("state", info["properties"])

            # DEVICE_READ
            status, payload = self.service.handle("DEVICE_READ", ["led", "state"])
            self.assertEqual(status, "OK")
            res = json.loads(payload)
            self.assertEqual(res["device"], "led")
            self.assertEqual(res["property"], "state")
            self.assertEqual(res["value"], "ON")

            # DEVICE_WRITE
            status, payload = self.service.handle("DEVICE_WRITE", ["led", "state", "OFF"])
            self.assertEqual(status, "OK")
            self.assertEqual(mock_pin_state[0], 0)

            # Backward compatibility: STATUS and LED
            status, payload = self.service.handle("STATUS", [])
            self.assertEqual(status, "OK")
            self.assertIn("LED=", payload)

            status, payload = self.service.handle("LED", ["ON"])
            self.assertEqual(status, "OK")
            self.assertEqual(payload, "LED=ON")


if __name__ == "__main__":
    unittest.main()
