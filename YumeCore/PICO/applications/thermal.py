"""
YumeCore Application: ThermalButton.
Monitors temperature sensor events to implement a virtual thermal button.
Performs threshold evaluation, hysteresis, and debounce.
Optionally drives an LED actuator directly or via events.
"""

try:
    import time
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
except AttributeError:
    import time
    ticks_ms = lambda: int(time.monotonic() * 1000)
    ticks_diff = lambda a, b: a - b


class ThermalButton:
    """
    Virtual Thermal Button application.
    Subscribes to 'sensor.temperature.changed'.
    """
    def __init__(self, sensor, events, threshold=45.0, hysteresis=1.0, debounce_ms=100, led_device=None):
        self.name = "thermal"
        self.description = "Temperature threshold virtual button and auto-LED controller"
        self.sensor = sensor
        self.events = events
        self.threshold = float(threshold)
        self.hysteresis = float(hysteresis)
        self.debounce_ms = int(debounce_ms)
        self.led_device = led_device

        self._enabled = True
        self._state = "RELEASED"  # "RELEASED" or "PRESSED"
        self._pending_state = None
        self._pending_since = None
        self._last_temp = None

        self.properties = {
            "enabled": {"readable": True, "writable": True, "type": "bool"},
            "threshold": {"readable": True, "writable": True, "type": "float", "unit": "C"},
            "hysteresis": {"readable": True, "writable": True, "type": "float", "unit": "C"},
            "debounce_ms": {"readable": True, "writable": True, "type": "int", "unit": "ms"},
            "state": {"readable": True, "writable": False, "type": "str"},
            "last_temp": {"readable": True, "writable": False, "type": "float"},
        }

        if self.events is not None:
            self.events.subscribe("sensor.temperature.changed", self.on_temperature_changed)

        # Get initial reading if sensor is available
        if self.sensor is not None:
            try:
                self._last_temp = self.sensor.read("value")
                self._evaluate(self._last_temp, immediate=True)
            except Exception:
                pass

    def set_auto_led(self, led_device, enabled=True):
        self.led_device = led_device
        self._enabled = bool(enabled)
        if self._last_temp is not None:
            self._evaluate(self._last_temp, immediate=True)

    def on_temperature_changed(self, data):
        temp = data.get("value")
        if temp is not None:
            self._last_temp = float(temp)
            self._evaluate(self._last_temp, immediate=False)

    def _evaluate(self, temp, immediate=False):
        if not self._enabled or temp is None:
            return

        if self._state == "RELEASED":
            target = "PRESSED" if temp >= self.threshold else "RELEASED"
        else:
            target = "RELEASED" if temp < (self.threshold - self.hysteresis) else "PRESSED"

        if target != self._state:
            if immediate or self.debounce_ms <= 0:
                self._apply_state(target)
            else:
                if self._pending_state != target:
                    self._pending_state = target
                    self._pending_since = ticks_ms()
                else:
                    elapsed = ticks_diff(ticks_ms(), self._pending_since)
                    if elapsed >= self.debounce_ms:
                        self._apply_state(target)
        else:
            self._pending_state = None

    def _apply_state(self, new_state):
        self._state = new_state
        self._pending_state = None
        self._pending_since = None

        if self.led_device is not None:
            try:
                self.led_device.write("state", "ON" if new_state == "PRESSED" else "OFF")
            except Exception:
                pass

        if self.events is not None:
            event_name = "thermal.press" if new_state == "PRESSED" else "thermal.release"
            self.events.publish(event_name, {"temp": self._last_temp, "state": self._state})

    def update(self):
        """Called periodically by controller to service debounce timing."""
        if self._pending_state is not None:
            elapsed = ticks_diff(ticks_ms(), self._pending_since)
            if elapsed >= self.debounce_ms:
                self._apply_state(self._pending_state)

    def info(self):
        return {
            "name": self.name,
            "description": self.description,
            "properties": self.properties,
        }

    def read(self, property_name):
        if property_name == "enabled":
            return self._enabled
        elif property_name == "threshold":
            return self.threshold
        elif property_name == "hysteresis":
            return self.hysteresis
        elif property_name == "debounce_ms":
            return self.debounce_ms
        elif property_name == "state":
            return self._state
        elif property_name == "last_temp":
            return self._last_temp
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        if property_name == "enabled":
            val_str = str(value).lower()
            if val_str in ("true", "1", "on", "yes"):
                self._enabled = True
            elif val_str in ("false", "0", "off", "no"):
                self._enabled = False
            else:
                raise ValueError("INVALID_BOOLEAN_VALUE: {}".format(value))

            if self._last_temp is not None:
                self._evaluate(self._last_temp, immediate=True)
            return self._enabled

        elif property_name == "threshold":
            val = float(value)
            if not -40.0 <= val <= 125.0:
                raise ValueError("INVALID_THRESHOLD_RANGE")
            self.threshold = val
            if self._last_temp is not None:
                self._evaluate(self._last_temp, immediate=True)
            return self.threshold

        elif property_name == "hysteresis":
            val = float(value)
            if val < 0:
                raise ValueError("HYSTERESIS_MUST_BE_NON_NEGATIVE")
            self.hysteresis = val
            return self.hysteresis

        elif property_name == "debounce_ms":
            val = int(value)
            if val < 0:
                raise ValueError("DEBOUNCE_MUST_BE_NON_NEGATIVE")
            self.debounce_ms = val
            return self.debounce_ms

        raise ValueError("PROPERTY_NOT_WRITABLE_OR_UNKNOWN: {}".format(property_name))

    def deinit(self):
        if self.events is not None:
            self.events.unsubscribe("sensor.temperature.changed", self.on_temperature_changed)
