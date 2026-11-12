"""
YumeCore Transport Layer for PC Host.
Manages USB CDC serial connection, low-level send/receive,
and line-based message framing.
"""

import time
from typing import Optional
import serial


class SerialTransport:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        self.connect()

    def connect(self) -> None:
        """Opens or reopens the serial port."""
        if self.serial and self.serial.is_open:
            self.serial.close()

        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout
        )
        time.sleep(1)
        self.serial.reset_input_buffer()

    def write(self, data: str) -> None:
        """Sends raw string data encoded as UTF-8."""
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Serial port is not open")
        self.serial.write(data.encode("utf-8"))
        self.serial.flush()

    def readline(self, deadline: Optional[float] = None) -> Optional[str]:
        """
        Reads a line from the serial port until deadline (monotonic timestamp).
        If deadline is None, calculates deadline as now + self.timeout.
        Returns the stripped line string, or None if timed out.
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Serial port is not open")

        if deadline is None:
            deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:
            line_bytes = self.serial.readline()
            if line_bytes:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:
                    return line
            else:
                time.sleep(0.005)

        return None

    def reset_input_buffer(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.reset_input_buffer()

    def close(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()

    @property
    def is_open(self) -> bool:
        return self.serial is not None and self.serial.is_open

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
