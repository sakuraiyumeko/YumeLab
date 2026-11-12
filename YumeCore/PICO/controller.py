
import time
from machine import ADC
from hardware import Hardware


class Controller:
    SAMPLE_INTERVAL = 1000
    DEFAULT_THRESHOLD = 45.0

    def __init__(self, hardware=None):
        self.hardware = hardware or Hardware()
        self.sensor = ADC(4)

        self.running = True
        self.auto_mode = True
        self.threshold = self.DEFAULT_THRESHOLD

        self.temperature = None
        self.last_sample = None
        self.last_error = None

        self.request_count = 0
        self.error_count = 0
        self.last_command = None

    def read_temperature(self):
        raw = self.sensor.read_u16()
        voltage = raw * 3.3 / 65535
        return 27 - (voltage - 0.706) / 0.001721

    def apply_control(self):
        if not self.auto_mode or self.temperature is None:
            return

        if self.temperature >= self.threshold:
            self.hardware.write("led", "ON")
        else:
            self.hardware.write("led", "OFF")

    def tick(self):
        if not self.running:
            return False

        now = time.ticks_ms()

        if self.last_sample is not None:
            elapsed = time.ticks_diff(now, self.last_sample)
            if elapsed < self.SAMPLE_INTERVAL:
                return False

        self.last_sample = now

        try:
            self.temperature = self.read_temperature()
            self.apply_control()
            self.last_error = None
            return True

        except Exception as exc:
            self.last_error = str(exc)
            self.error_count += 1
            return False

    def get_status(self):
        led = self.hardware.read("led")
        led_state = "ON" if led else "OFF"

        if self.temperature is None:
            temp = "N/A"
        else:
            temp = "{:.1f}C".format(self.temperature)

        mode = "AUTO" if self.auto_mode else "MANUAL"

        return (
            "TEMP={} LED={} MODE={} THRESHOLD={:.1f}C"
            .format(temp, led_state, mode, self.threshold)
        )

    def dispatch(self, command, args):
        if not self.running:
            raise RuntimeError("CONTROLLER_STOPPED")

        self.request_count += 1
        self.last_command = command

        try:
            if command == "STATUS":
                if args:
                    raise ValueError("INVALID_ARGUMENT")
                return self.get_status()

            if command == "TEMP":
                if args:
                    raise ValueError("INVALID_ARGUMENT")

                if self.temperature is None:
                    return "TEMP=UNAVAILABLE"

                return "TEMP={:.1f}C".format(self.temperature)

            if command == "AUTO":
                if len(args) != 1:
                    raise ValueError("INVALID_ARGUMENT")

                state = args[0].upper()

                if state == "ON":
                    self.auto_mode = True
                    self.apply_control()
                elif state == "OFF":
                    self.auto_mode = False
                else:
                    raise ValueError("INVALID_AUTO_STATE")

                return "AUTO={}".format(state)

            if command == "AUTO_SET":
                if len(args) != 1:
                    raise ValueError("INVALID_ARGUMENT")

                threshold = float(args[0])

                if not 0 <= threshold <= 100:
                    raise ValueError("INVALID_THRESHOLD")

                self.threshold = threshold
                self.apply_control()

                return "THRESHOLD={:.1f}C".format(threshold)

            if command == "LED":
                # Manual LED control switches to manual mode.
                self.auto_mode = False

            if command == "HW_SET":
                if len(args) == 2 and args[0] == "led":
                    self.auto_mode = False

            return self.hardware.dispatch(command, args)

        except Exception:
            self.error_count += 1
            raise

    def stop(self):
        self.running = False
        self.auto_mode = False
        self.hardware.deinit()

    def start(self):
        if self.running:
            return

        self.hardware = Hardware()
        self.running = True
        self.auto_mode = True
        self.temperature = None
        self.last_sample = None

    def reset_stats(self):
        self.request_count = 0
        self.error_count = 0
        self.last_command = None
