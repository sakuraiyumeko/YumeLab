import unittest
from unittest.mock import MagicMock
import json
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PC"))

from host import YumeCore
from interface import PicoInterface


class TestPCHostAndInterface(unittest.TestCase):
    def setUp(self):
        self.mock_transport = MagicMock()
        self.core = YumeCore(transport=self.mock_transport)

    def test_send_request_and_matching(self):
        # When request is sent, transport.readline returns response with matching ID
        self.mock_transport.readline.return_value = "0001 OK PONG"
        res = self.core.send_request("PING")
        self.assertEqual(res, "PONG")
        self.mock_transport.write.assert_called_with("0001 PING\n")

    def test_devices_proxy(self):
        # devices.list
        self.mock_transport.readline.return_value = '0001 OK [{"id": "led", "type": "led"}]'
        devs = self.core.devices.list()
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0]["id"], "led")

        # devices.read
        self.mock_transport.readline.return_value = '0002 OK {"device": "led", "property": "state", "value": "ON"}'
        val = self.core.devices.read("led", "state")
        self.assertEqual(val, "ON")

        # devices.write
        self.mock_transport.readline.return_value = '0003 OK {"device": "led", "property": "state", "value": "OFF"}'
        val = self.core.devices.write("led", "state", "OFF")
        self.assertEqual(val, "OFF")

    def test_apps_proxy(self):
        # apps.list
        self.mock_transport.readline.return_value = '0001 OK [{"name": "thermal"}]'
        apps = self.core.apps.list()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["name"], "thermal")

        # apps.read
        self.mock_transport.readline.return_value = '0002 OK {"app": "thermal", "property": "threshold", "value": 45.0}'
        val = self.core.apps.read("thermal", "threshold")
        self.assertEqual(val, 45.0)

        # apps.write
        self.mock_transport.readline.return_value = '0003 OK {"app": "thermal", "property": "threshold", "value": 50.0}'
        val = self.core.apps.write("thermal", "threshold", 50.0)
        self.assertEqual(val, 50.0)

    def test_legacy_convenience_methods(self):
        # led()
        self.mock_transport.readline.return_value = '0001 OK {"device": "led", "property": "state", "value": "ON"}'
        res = self.core.led(True)
        self.assertEqual(res, "ON")

        # auto()
        self.mock_transport.readline.return_value = '0002 OK AUTO=ON'
        res = self.core.auto(True)
        self.assertEqual(res, "AUTO=ON")

        # auto_set()
        self.mock_transport.readline.return_value = '0003 OK THRESHOLD=48.0C'
        res = self.core.auto_set(48.0)
        self.assertEqual(res, "THRESHOLD=48.0C")

    def test_reboot(self):
        self.core.reboot()
        self.mock_transport.write.assert_called_with("0001 REBOOT\n")
        self.mock_transport.close.assert_called()


if __name__ == "__main__":
    unittest.main()
