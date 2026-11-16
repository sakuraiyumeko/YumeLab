import unittest
from unittest.mock import MagicMock, patch
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

from hardware import HardwareManager
import hardware
from buzzer import PassiveBuzzer, ActiveBuzzer


class TestBuzzers(unittest.TestCase):
    def setUp(self):
        self.hw = HardwareManager()

    def test_passive_buzzer_pwm_and_sfx(self):
        mock_pwm = MagicMock()
        freq_val = [1000]
        duty_val = [0]
        def fake_freq(v=None):
            if v is not None:
                freq_val[0] = v
            return freq_val[0]
        def fake_duty(v=None):
            if v is not None:
                duty_val[0] = v
            return duty_val[0]
        mock_pwm.freq.side_effect = fake_freq
        mock_pwm.duty_u16.side_effect = fake_duty

        with patch.object(hardware, "Pin", return_value=MagicMock()), \
             patch.object(hardware, "PWM", return_value=mock_pwm):
            buzzer = PassiveBuzzer(self.hw, pin=16)
            self.assertEqual(buzzer.device_id, "actuator.buzzer.passive")

            # Test play tone
            buzzer.write("tone", 440)
            self.assertEqual(buzzer.read("frequency"), 440)

            # Test SFX preset
            res = buzzer.write("sfx", "stark_boot")
            self.assertEqual(res, "stark_boot")

            # Test mute
            buzzer.write("sfx", "mute")
            self.assertEqual(buzzer.read("duty"), 0.0)

    def test_active_buzzer_beep(self):
        mock_pin = MagicMock()
        pin_val = [0]
        def fake_pin(v=None):
            if v is not None:
                pin_val[0] = 1 if v else 0
            return pin_val[0]
        mock_pin.value.side_effect = fake_pin

        with patch.object(hardware, "Pin", return_value=mock_pin):
            buzzer = ActiveBuzzer(self.hw, pin=17)
            self.assertEqual(buzzer.device_id, "actuator.buzzer.active")

            # Direct state write
            res = buzzer.write("state", "ON")
            self.assertEqual(res, "ON")
            self.assertEqual(pin_val[0], 1)

            res = buzzer.write("state", "OFF")
            self.assertEqual(res, "OFF")
            self.assertEqual(pin_val[0], 0)

            # Beep sequence
            res = buzzer.write("beep", 2)
            self.assertEqual(res, 2)


if __name__ == "__main__":
    unittest.main()
