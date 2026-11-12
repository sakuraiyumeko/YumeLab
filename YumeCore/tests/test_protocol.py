import unittest
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base_dir, "PICO"))

from protocol import (
    valid_id,
    make_request,
    parse_request,
    make_response,
    parse_response,
    CMD_PING,
    CMD_DEVICE_READ,
    CMD_APP_WRITE,
)


class TestProtocol(unittest.TestCase):
    def test_valid_id(self):
        self.assertTrue(valid_id("0001"))
        self.assertTrue(valid_id("9999"))
        self.assertFalse(valid_id("123"))
        self.assertFalse(valid_id("12345"))
        self.assertFalse(valid_id("abcd"))
        self.assertFalse(valid_id(1234))

    def test_make_and_parse_request(self):
        # Standard command
        msg = make_request("0001", CMD_PING)
        self.assertEqual(msg, "0001 PING\n")
        req_id, cmd, args, err = parse_request(msg)
        self.assertEqual(req_id, "0001")
        self.assertEqual(cmd, "PING")
        self.assertEqual(args, [])
        self.assertIsNone(err)

        # Arbitrary new command with args (no whitelist restriction!)
        msg2 = make_request("0042", "CUSTOM_FOO_BAR", "arg1", 123)
        self.assertEqual(msg2, "0042 CUSTOM_FOO_BAR arg1 123\n")
        req_id, cmd, args, err = parse_request(msg2)
        self.assertEqual(req_id, "0042")
        self.assertEqual(cmd, "CUSTOM_FOO_BAR")
        self.assertEqual(args, ["arg1", "123"])
        self.assertIsNone(err)

        # Device command
        msg3 = make_request("0099", CMD_DEVICE_READ, "sensor.temperature", "value")
        req_id, cmd, args, err = parse_request(msg3)
        self.assertEqual(cmd, "DEVICE_READ")
        self.assertEqual(args, ["sensor.temperature", "value"])
        self.assertIsNone(err)

        # App command
        msg4 = make_request("0100", CMD_APP_WRITE, "thermal", "threshold", "45.0")
        req_id, cmd, args, err = parse_request(msg4)
        self.assertEqual(cmd, "APP_WRITE")
        self.assertEqual(args, ["thermal", "threshold", "45.0"])
        self.assertIsNone(err)

    def test_parse_request_errors(self):
        # Empty
        req_id, cmd, args, err = parse_request("")
        self.assertEqual(err, "EMPTY_REQUEST")

        # Invalid ID
        req_id, cmd, args, err = parse_request("ABC PING")
        self.assertEqual(err, "INVALID_ID")

        # Missing command
        req_id, cmd, args, err = parse_request("0001")
        self.assertEqual(err, "INVALID_COMMAND")

    def test_make_and_parse_response(self):
        # OK with payload
        res = make_response("0001", "OK", "PONG")
        self.assertEqual(res, "0001 OK PONG\n")
        resp_id, status, payload = parse_response(res)
        self.assertEqual(resp_id, "0001")
        self.assertEqual(status, "OK")
        self.assertEqual(payload, "PONG")

        # OK without payload
        res2 = make_response("0002", "OK")
        self.assertEqual(res2, "0002 OK\n")
        resp_id, status, payload = parse_response(res2)
        self.assertEqual(resp_id, "0002")
        self.assertEqual(status, "OK")
        self.assertEqual(payload, "")

        # ERROR response
        res3 = make_response("0003", "ERROR", "DEVICE_NOT_FOUND")
        self.assertEqual(res3, "0003 ERROR DEVICE_NOT_FOUND\n")
        resp_id, status, payload = parse_response(res3)
        self.assertEqual(resp_id, "0003")
        self.assertEqual(status, "ERROR")
        self.assertEqual(payload, "DEVICE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
