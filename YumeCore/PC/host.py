"""
YumeCore PC Host Client.
Provides high-level Python API for interacting with Raspberry Pi Pico
running YumeCore. Uses SerialTransport for communication.
Includes proxies for Devices and Applications.
"""

import json
import time
from typing import Optional, List, Dict, Any

try:
    from transport import SerialTransport
except (ImportError, AttributeError):
    import importlib.util
    import os
    _spec = importlib.util.spec_from_file_location(
        "pc_transport",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "transport.py")
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    SerialTransport = _mod.SerialTransport
from protocol import (
    make_request,
    parse_response,
    CMD_PING,
    CMD_INFO,
    CMD_REBOOT,
    CMD_DEVICE_LIST,
    CMD_DEVICE_INFO,
    CMD_DEVICE_READ,
    CMD_DEVICE_WRITE,
    CMD_APP_LIST,
    CMD_APP_INFO,
    CMD_APP_READ,
    CMD_APP_WRITE,
)


class DevicesProxy:
    """
    Client-side proxy for remote devices on Pico.
    """
    def __init__(self, core: "YumeCore"):
        self._core = core

    def list(self) -> List[Dict[str, Any]]:
        raw = self._core.send_request(CMD_DEVICE_LIST)
        return json.loads(raw)

    def info(self, device_id: str) -> Dict[str, Any]:
        raw = self._core.send_request(CMD_DEVICE_INFO, device_id)
        return json.loads(raw)

    def read(self, device_id: str, property_name: str) -> Any:
        raw = self._core.send_request(CMD_DEVICE_READ, device_id, property_name)
        data = json.loads(raw)
        return data.get("value")

    def write(self, device_id: str, property_name: str, value: Any) -> Any:
        raw = self._core.send_request(CMD_DEVICE_WRITE, device_id, property_name, str(value))
        data = json.loads(raw)
        return data.get("value")


class AppsProxy:
    """
    Client-side proxy for remote applications on Pico.
    """
    def __init__(self, core: "YumeCore"):
        self._core = core

    def list(self) -> List[Dict[str, Any]]:
        raw = self._core.send_request(CMD_APP_LIST)
        return json.loads(raw)

    def info(self, app_name: str) -> Dict[str, Any]:
        raw = self._core.send_request(CMD_APP_INFO, app_name)
        return json.loads(raw)

    def read(self, app_name: str, property_name: str) -> Any:
        raw = self._core.send_request(CMD_APP_READ, app_name, property_name)
        data = json.loads(raw)
        return data.get("value")

    def write(self, app_name: str, property_name: str, value: Any) -> Any:
        raw = self._core.send_request(CMD_APP_WRITE, app_name, property_name, str(value))
        data = json.loads(raw)
        return data.get("value")


class YumeCore:
    def __init__(self, port: Optional[str] = None, baudrate: int = 115200, timeout: float = 2.0, transport: Optional[SerialTransport] = None):
        if transport is not None:
            self.transport = transport
        elif port is not None:
            self.transport = SerialTransport(port=port, baudrate=baudrate, timeout=timeout)
        else:
            raise ValueError("Either port or transport must be specified")

        self.timeout = timeout
        self.request_id = 0

        self.devices = DevicesProxy(self)
        self.apps = AppsProxy(self)

    def _next_id(self) -> str:
        self.request_id = (self.request_id + 1) % 10000
        return f"{self.request_id:04d}"

    def send_request(self, command: str, *args: Any) -> str:
        """
        Sends a request and waits for matching response ID.
        Returns payload string on OK. Raises RuntimeError on ERROR.
        """
        request_id = self._next_id()
        msg = make_request(request_id, command, *args)
        self.transport.write(msg)

        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:
            line = self.transport.readline(deadline=deadline)
            if not line:
                continue

            try:
                resp_id, status, payload = parse_response(line)
            except ValueError:
                continue

            if resp_id != request_id:
                continue

            if status == "ERROR":
                raise RuntimeError(payload)

            return payload

        raise TimeoutError(f"No response for request {request_id}")

    # Backward compatibility for _send
    def _send(self, command: str, *args: Any) -> str:
        return self.send_request(command, *args)

    def ping(self) -> bool:
        return self.send_request(CMD_PING) == "PONG"

    def info(self) -> str:
        return self.send_request(CMD_INFO)

    def reboot(self) -> None:
        """Sends REBOOT command directly without waiting and disconnects."""
        request_id = self._next_id()
        msg = make_request(request_id, CMD_REBOOT)
        self.transport.write(msg)
        time.sleep(0.5)
        self.close()

    # Backward-compatible convenience methods
    def status(self) -> str:
        return self.send_request("STATUS")

    def led(self, enabled: bool) -> str:
        state = "ON" if enabled else "OFF"
        return self.devices.write("led", "state", state)

    def temp(self) -> str:
        return self.send_request("TEMP")

    def auto(self, enabled: bool) -> str:
        return self.send_request("AUTO", "ON" if enabled else "OFF")

    def auto_set(self, threshold: float) -> str:
        return self.send_request("AUTO_SET", str(threshold))

    def close(self) -> None:
        if self.transport:
            self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
