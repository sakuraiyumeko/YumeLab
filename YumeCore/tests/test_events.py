import unittest
from unittest.mock import MagicMock, patch
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

from events import EventBus
from hardware import HardwareManager
import hardware
from sensors import TemperatureSensor


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_subscribe_and_publish(self):
        events_received_1 = []
        events_received_2 = []

        def sub1(data):
            events_received_1.append(data)

        def sub2(data):
            events_received_2.append(data)

        self.bus.subscribe("button.press", sub1)
        self.bus.subscribe("button.press", sub2)

        count = self.bus.publish("button.press", {"pin": 15})
        self.assertEqual(count, 2)
        self.assertEqual(len(events_received_1), 1)
        self.assertEqual(events_received_1[0], {"pin": 15})
        self.assertEqual(len(events_received_2), 1)

        # Unsubscribe sub1
        self.bus.unsubscribe("button.press", sub1)
        count = self.bus.publish("button.press", {"pin": 16})
        self.assertEqual(count, 1)
        self.assertEqual(len(events_received_1), 1)  # not called again
        self.assertEqual(len(events_received_2), 2)

    def test_subscriber_exception_isolation(self):
        received_by_healthy = []

        def failing_sub(data):
            raise RuntimeError("Sub failed intentionally")

        def healthy_sub(data):
            received_by_healthy.append(data)

        self.bus.subscribe("alert", failing_sub)
        self.bus.subscribe("alert", healthy_sub)

        # Publish should not raise RuntimeError, and healthy_sub must still run!
        count = self.bus.publish("alert", {"msg": "fire"})
        self.assertEqual(count, 1)
        self.assertEqual(len(received_by_healthy), 1)
        self.assertEqual(received_by_healthy[0], {"msg": "fire"})

    def test_temperature_sensor_event_integration(self):
        hw = HardwareManager()
        mock_adc = MagicMock()
        mock_adc.read_u16.return_value = 14000

        temp_events = []
        self.bus.subscribe("sensor.temperature.changed", lambda data: temp_events.append(data))

        with patch.object(hardware, "ADC", return_value=mock_adc):
            # Init temperature sensor with event bus
            sensor = TemperatureSensor(hw, event_bus=self.bus, deadband=0.1)
            # Initial sample published
            self.assertEqual(len(temp_events), 1)
            self.assertIn("value", temp_events[0])
            self.assertIn("raw", temp_events[0])

            # Update with same temp -> no new event
            sensor.update()
            self.assertEqual(len(temp_events), 1)

            # Update with significant temp change -> event published!
            mock_adc.read_u16.return_value = 16000
            sensor.update()
            self.assertEqual(len(temp_events), 2)


if __name__ == "__main__":
    unittest.main()
