import unittest
from unittest.mock import MagicMock, patch
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

import hardware
from hardware import HardwareManager


class TestHardwareManager(unittest.TestCase):
    def setUp(self):
        self.hw = HardwareManager()

    def test_pin_claim_and_conflict(self):
        # Claim pin 15 for led
        self.hw.claim_pin(15, "led")
        self.assertTrue(self.hw.is_pin_claimed(15))
        self.assertEqual(self.hw.get_claimed_pins()[15], "led")

        # Same owner claiming again is fine (idempotent)
        self.hw.claim_pin(15, "led")

        # Different owner claiming pin 15 should raise ValueError
        with self.assertRaises(ValueError) as ctx:
            self.hw.claim_pin(15, "button")
        self.assertIn("PIN_CONFLICT", str(ctx.exception))

        # Release pin 15
        self.hw.release_pin(15)
        self.assertFalse(self.hw.is_pin_claimed(15))

        # Now button can claim pin 15
        self.hw.claim_pin(15, "button")
        self.assertTrue(self.hw.is_pin_claimed(15))

    def test_internal_temp_adc_vs_gpio4_isolation(self):
        # Claim internal temp sensor (channel 4)
        mock_adc = MagicMock()
        with patch.object(hardware, "ADC", return_value=mock_adc):
            adc_inst = self.hw.create_internal_temp_adc(owner="thermal_sensor")
            self.assertIsNotNone(adc_inst)
            hardware.ADC.assert_called_with(4)

            # Crucial check: GPIO 4 must NOT be claimed!
            self.assertFalse(self.hw.is_pin_claimed(4))

            # Another owner claims physical GPIO 4
            self.hw.claim_pin(4, "spi_cs")
            self.assertTrue(self.hw.is_pin_claimed(4))

            # Internal temp ADC conflict check: another device claiming internal temp raises
            with self.assertRaises(ValueError) as ctx:
                self.hw.create_internal_temp_adc(owner="another_sensor")
            self.assertIn("RESOURCE_CONFLICT", str(ctx.exception))

    def test_create_adc_channel_routing(self):
        mock_adc = MagicMock()
        with patch.object(hardware, "ADC", return_value=mock_adc):
            # Calling create_adc(4) routes to internal temp, does not claim GPIO 4
            self.hw.create_adc(4, owner="sys_temp")
            self.assertFalse(self.hw.is_pin_claimed(4))

            # Invalid ADC GPIO (e.g. GPIO 10 is digital only)
            with self.assertRaises(ValueError) as ctx:
                self.hw.create_adc(10, owner="light_sensor")
            self.assertIn("INVALID_ADC_PIN", str(ctx.exception))

            # Valid ADC GPIO (26) claims GPIO 26
            with patch.object(hardware, "Pin", return_value=MagicMock()):
                self.hw.create_adc(26, owner="potentiometer")
                self.assertTrue(self.hw.is_pin_claimed(26))


if __name__ == "__main__":
    unittest.main()
