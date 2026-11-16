"""
YumeCore Application: AmbientLightController.
Monitors light sensor events to drive an ambient/desk light actuator
with hysteresis, debounce, and optional inverted brightness proportional PWM output.
"""

try:
    import time
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
except AttributeError:
    import time
    ticks_ms = lambda: int(time.monotonic() * 1000)
    ticks_diff = lambda a, b: a - b


class AmbientLightController:
    """
    Ambient light auto-lighting application.
    Subscribes to 'sensor.light.changed'.
    """
    def __init__(
        self,
        sensor,
        events,
        dark_threshold=35.0,
        hysteresis=5.0,
        debounce_ms=200,
        actuator_device=None,
        target_brightness=None,
    ):
        self.name = "ambient_light"
        self.description = "Ambient light reactive desk lighting controller"
        self.sensor = sensor
        self.events = events
        self.dark_threshold = float(dark_threshold)
        self.hysteresis = float(hysteresis)
        self.debounce_ms = int(debounce_ms)
        self.actuator_device = actuator_device
        self.target_brightness = 60.0 if target_brightness is None else float(target_brightness)

        self._enabled = True
        self._state = "IDLE"  # "IDLE" (bright enough) or "ACTIVE" (dark, light turned on)
        self._pending_state = None
        self._pending_since = None
        self._last_brightness = None
        self._output_level = 0.0

        self.properties = {
            "enabled": {"readable": True, "writable": True, "type": "bool"},
            "dark_threshold": {"readable": True, "writable": True, "type": "float", "unit": "%"},
            "hysteresis": {"readable": True, "writable": True, "type": "float", "unit": "%"},
            "debounce_ms": {"readable": True, "writable": True, "type": "int", "unit": "ms"},
            "target_brightness": {"readable": True, "writable": True, "type": "float", "unit": "%"},
            "state": {"readable": True, "writable": False, "type": "str"},
            "last_brightness": {"readable": True, "writable": False, "type": "float", "unit": "%"},
            "output_level": {"readable": True, "writable": False, "type": "float", "unit": "%"},
        }

        if self.events is not None:
            self.events.subscribe("sensor.light.changed", self.on_light_changed)

        if self.sensor is not None:
            try:
                self._last_brightness = float(self.sensor.read("brightness"))
                self._evaluate(self._last_brightness, immediate=True)
            except Exception:
                pass

    def on_light_changed(self, data):
        brightness = data.get("value")
        if brightness is not None:
            self._last_brightness = float(brightness)
            self._evaluate(self._last_brightness, immediate=False)

    def _evaluate(self, brightness, immediate=False):
        if not self._enabled or brightness is None:
            return

        if self._state == "IDLE":
            target = "ACTIVE" if brightness <= self.dark_threshold else "IDLE"
        else:
            target = "IDLE" if brightness > (self.dark_threshold + self.hysteresis) else "ACTIVE"

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

    def _drive_actuator(self, active):
        if self.actuator_device is None:
            self._output_level = self.target_brightness if active else 0.0
            return

        props = getattr(self.actuator_device, "properties", {})
        try:
            if "duty" in props:
                duty = self.target_brightness if active else 0.0
                self.actuator_device.write("duty", duty)
                self._output_level = duty
            elif "state" in props:
                self.actuator_device.write("state", "ON" if active else "OFF")
                self._output_level = 100.0 if active else 0.0
        except Exception:
            pass

    def _apply_state(self, new_state):
        self._state = new_state
        self._pending_state = None
        self._pending_since = None

        self._drive_actuator(new_state == "ACTIVE")

        if self.events is not None:
            event_name = "ambient_light.active" if new_state == "ACTIVE" else "ambient_light.idle"
            self.events.publish(
                event_name,
                {
                    "brightness": self._last_brightness,
                    "state": self._state,
                    "output_level": self._output_level,
                },
            )

    def update(self):
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
        elif property_name == "dark_threshold":
            return self.dark_threshold
        elif property_name == "hysteresis":
            return self.hysteresis
        elif property_name == "debounce_ms":
            return self.debounce_ms
        elif property_name == "target_brightness":
            return self.target_brightness
        elif property_name == "state":
            return self._state
        elif property_name == "last_brightness":
            return self._last_brightness
        elif property_name == "output_level":
            return self._output_level
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

            if self._enabled and self._last_brightness is not None:
                self._evaluate(self._last_brightness, immediate=True)
            elif not self._enabled:
                self._pending_state = None
                self._state = "IDLE"
                self._drive_actuator(False)
            return self._enabled

        elif property_name == "dark_threshold":
            val = float(value)
            if not 0.0 <= val <= 100.0:
                raise ValueError("INVALID_THRESHOLD_RANGE")
            self.dark_threshold = val
            if self._last_brightness is not None:
                self._evaluate(self._last_brightness, immediate=True)
            return self.dark_threshold

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

        elif property_name == "target_brightness":
            val = float(value)
            if not 0.0 <= val <= 100.0:
                raise ValueError("INVALID_BRIGHTNESS_RANGE")
            self.target_brightness = val
            if self._state == "ACTIVE":
                self._drive_actuator(True)
            return self.target_brightness

        raise ValueError("PROPERTY_NOT_WRITABLE_OR_UNKNOWN: {}".format(property_name))

    def deinit(self):
        if self.events is not None:
            self.events.unsubscribe("sensor.light.changed", self.on_light_changed)
