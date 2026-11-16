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
from sensors import TemperatureSensor, LightSensor
import actuators
from actuators import LED, DigitalOutput, PWMOutput
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

    def test_light_sensor_and_calibration(self):
        mock_adc = MagicMock()
        mock_adc.read_u16.return_value = 33287  # ~50%

        with patch.object(hardware, "ADC", return_value=mock_adc), \
             patch.object(hardware, "Pin", return_value=MagicMock()):
            bus = MagicMock()
            sensor = LightSensor(
                self.hw,
                pin=26,
                device_id="sensor.light",
                dark_raw=1040,
                bright_raw=65535,
                event_bus=bus,
                deadband=2.0,
            )
            self.assertEqual(sensor.device_id, "sensor.light")
            brightness = sensor.read("brightness")
            self.assertAlmostEqual(brightness, 50.0, delta=0.2)
            bus.publish.assert_called_once()

            # Small change within deadband (<2.0) should not publish
            mock_adc.read_u16.return_value = 33600
            sensor.update()
            self.assertEqual(bus.publish.call_count, 1)

            # Clamping at extremes (below dark_raw and above bright_raw)
            mock_adc.read_u16.return_value = 0
            sensor.update()
            self.assertEqual(sensor.read("brightness"), 0.0)
            self.assertEqual(bus.publish.call_count, 2)

            mock_adc.read_u16.return_value = 70000
            sensor.update()
            self.assertEqual(sensor.read("brightness"), 100.0)
            self.assertEqual(bus.publish.call_count, 3)

        # Invalid calibration raises ValueError
        with self.assertRaises(ValueError):
            LightSensor(self.hw, pin=27, dark_raw=1000, bright_raw=1000)

    def test_pwm_output_actuator(self):
        mock_pwm = MagicMock()
        duty_holder = [0]
        freq_holder = [1000]
        def fake_duty(v=None):
            if v is not None:
                duty_holder[0] = v
            return duty_holder[0]
        def fake_freq(v=None):
            if v is not None:
                freq_holder[0] = v
            return freq_holder[0]
        mock_pwm.duty_u16.side_effect = fake_duty
        mock_pwm.freq.side_effect = fake_freq

        with patch.object(hardware, "Pin", return_value=MagicMock()), \
             patch.object(hardware, "PWM", return_value=mock_pwm):
            lamp = PWMOutput(self.hw, pin=15, device_id="actuator.desk_lamp", freq=1000, duty=0)
            self.assertEqual(lamp.read("duty"), 0.0)
            lamp.write("duty", 50)
            self.assertAlmostEqual(lamp.read("duty"), 50.0, delta=0.1)
            with self.assertRaises(ValueError):
                lamp.write("duty", 120)

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
