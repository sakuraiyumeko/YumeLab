import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import importlib.util

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load PC transport
pc_transport_path = os.path.join(base_dir, "PC", "transport.py")
spec_pc = importlib.util.spec_from_file_location("pc_transport", pc_transport_path)
pc_transport = importlib.util.module_from_spec(spec_pc)
spec_pc.loader.exec_module(pc_transport)
PCSerialTransport = pc_transport.SerialTransport

# Load PICO transport
pico_transport_path = os.path.join(base_dir, "PICO", "transport.py")
spec_pico = importlib.util.spec_from_file_location("pico_transport", pico_transport_path)
pico_transport = importlib.util.module_from_spec(spec_pico)
spec_pico.loader.exec_module(pico_transport)
PicoTransport = pico_transport.Transport


class TestPCTransport(unittest.TestCase):
    @patch("serial.Serial")
    def test_write_and_readline(self, mock_serial_cls):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.readline.return_value = b"0001 OK PONG\r\n"
        mock_serial_cls.return_value = mock_serial

        t = PCSerialTransport("COM1", timeout=1.0)
        t.write("0001 PING\n")
        mock_serial.write.assert_called_with(b"0001 PING\n")

        line = t.readline()
        self.assertEqual(line, "0001 OK PONG")

    @patch("serial.Serial")
    def test_timeout(self, mock_serial_cls):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.readline.return_value = b""
        mock_serial_cls.return_value = mock_serial

        t = PCSerialTransport("COM1", timeout=0.05)
        line = t.readline()
        self.assertIsNone(line)


class TestPicoTransport(unittest.TestCase):
    def test_pico_transport_framing_and_overflow(self):
        # Test normal line reading
        t = PicoTransport(max_length=10)
        t._poller = MagicMock()
        
        chars = ["H", "i", "\n"]
        t._poller.poll.side_effect = lambda timeout: [1] if chars else []
        with patch("sys.stdin.read", side_effect=lambda n: chars.pop(0) if chars else ""):
            res = t.read_line()
            self.assertIsNotNone(res)
            line, overflow = res
            self.assertEqual(line, "Hi")
            self.assertFalse(overflow)

        # Test overflow
        long_chars = list("0123456789ABCDE\n")
        t._poller.poll.side_effect = lambda timeout: [1] if long_chars else []
        with patch("sys.stdin.read", side_effect=lambda n: long_chars.pop(0) if long_chars else ""):
            res = t.read_line()
            self.assertIsNotNone(res)
            line, overflow = res
            self.assertTrue(overflow)


if __name__ == "__main__":
    unittest.main()
