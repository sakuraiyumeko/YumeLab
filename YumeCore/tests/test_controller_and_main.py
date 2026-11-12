import unittest
from unittest.mock import MagicMock, patch
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

from controller import Controller
from devices import DeviceRegistry
from device_service import DeviceService
from app_service import AppService
from filesystem import FileSystem
from main import CommandDispatcher


class TestControllerAndMain(unittest.TestCase):
    def test_controller_scheduling(self):
        registry = DeviceRegistry()
        from devices import Device

        class MockDev(Device):
            device_id = "mock_dev"
            device_type = "mock"
            properties = {}

        mock_dev = MockDev()
        mock_dev.update = MagicMock()
        registry.register(mock_dev)

        ctrl = Controller(registry=registry, update_interval_ms=10)

        task_calls = []
        ctrl.register_task("task1", lambda: task_calls.append(1), interval_ms=10)

        mock_app = MagicMock()
        ctrl.register_app(mock_app)

        # First tick should trigger initial device update and task
        ctrl.tick()
        mock_dev.update.assert_called()
        mock_app.update.assert_called()
        self.assertEqual(len(task_calls), 1)

        # Fault isolation test: faulty task should not crash tick
        ctrl.register_task("bad_task", lambda: 1 / 0, interval_ms=10)
        ctrl.tick()
        self.assertGreater(ctrl.error_count, 0)
        self.assertIsNotNone(ctrl.last_error)

    def test_command_dispatcher(self):
        mock_dev_service = MagicMock()
        mock_dev_service.can_handle.side_effect = lambda cmd: cmd.startswith("DEVICE_")
        mock_dev_service.handle.return_value = ("OK", '{"test": 1}')

        mock_app_service = MagicMock()
        mock_app_service.can_handle.side_effect = lambda cmd: cmd.startswith("APP_")
        mock_app_service.handle.return_value = ("OK", '{"app_test": 1}')

        mock_fs = MagicMock()
        mock_fs.dispatch.return_value = ("OK", "DIR /")

        dispatcher = CommandDispatcher(mock_dev_service, mock_app_service, mock_fs)

        # Test PING
        res, reboot = dispatcher.dispatch("0001 PING\n")
        self.assertEqual(res, "0001 OK PONG\n")
        self.assertFalse(reboot)

        # Test REBOOT
        res, reboot = dispatcher.dispatch("0002 REBOOT\n")
        self.assertEqual(res, "0002 OK REBOOTING\n")
        self.assertTrue(reboot)

        # Test DEVICE_* routing
        res, reboot = dispatcher.dispatch("0003 DEVICE_LIST\n")
        self.assertEqual(res, '0003 OK {"test": 1}\n')
        self.assertFalse(reboot)
        mock_dev_service.handle.assert_called_with("DEVICE_LIST", [])

        # Test APP_* routing
        res, reboot = dispatcher.dispatch("0004 APP_LIST\n")
        self.assertEqual(res, '0004 OK {"app_test": 1}\n')
        self.assertFalse(reboot)
        mock_app_service.handle.assert_called_with("APP_LIST", [])

        # Test FS_* routing
        res, reboot = dispatcher.dispatch("0005 FS_LIST /\n")
        self.assertEqual(res, "0005 OK DIR /\n")
        self.assertFalse(reboot)

        # Test UNKNOWN_COMMAND
        res, reboot = dispatcher.dispatch("0006 NON_EXISTENT_COMMAND\n")
        self.assertEqual(res, "0006 ERROR UNKNOWN_COMMAND\n")
        self.assertFalse(reboot)


if __name__ == "__main__":
    unittest.main()
