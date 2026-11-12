import serial
import time

from protocol import make_request, parse_response


class YumeCore:
    def __init__(self, port, baudrate=115200, timeout=2):
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout
        )

        self.timeout = timeout
        self.request_id = 0

        time.sleep(1)
        self.serial.reset_input_buffer()

    def _next_id(self):
        self.request_id = (self.request_id + 1) % 10000
        return f"{self.request_id:04d}"

    def _send(self, command, *args):
        request_id = self._next_id()

        message = make_request(request_id, command, *args)
        self.serial.write(message.encode("utf-8"))

        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:
            line = self.serial.readline().decode(
                "utf-8",
                errors="replace"
            ).strip()

            if not line:
                continue

            response_id, status, payload = parse_response(line)

            if response_id != request_id:
                continue

            if status == "ERROR":
                raise RuntimeError(payload)

            return payload

        raise TimeoutError(
            f"No response for request {request_id}"
        )

    def ping(self):
        return self._send("PING") == "PONG"

    def info(self):
        return self._send("INFO")

    def status(self):
        return self._send("STATUS")

    def led(self, enabled):
        state = "ON" if enabled else "OFF"
        return self._send("LED", state)

    def reboot(self):
        request_id = self._next_id()
        message = make_request(request_id, "REBOOT")
        self.serial.write(message.encode("utf-8"))
        # Pico sends response then resets — no need to wait for it.
        time.sleep(0.5)
        self.close()

    def close(self):
        if self.serial.is_open:
            self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()