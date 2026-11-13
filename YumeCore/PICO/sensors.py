"""
YumeCore Sensors.
Implements sensor devices (TemperatureSensor, AnalogSensor, DigitalInputSensor).
Sensors gather data and publish events; they make no business decisions.
"""

from devices import Device

try:
    from machine import Pin
except ImportError:
    Pin = None


class TemperatureSensor(Device):
    """
    RP2040 internal temperature sensor device.
    Uses ADC channel 4, isolated from physical GPIO 4.
    """
    device_id = "sensor.temperature"
    device_type = "temperature_sensor"

    def __init__(self, hardware, device_id="sensor.temperature", event_bus=None, deadband=0.1):
        self.device_id = device_id
        self.hardware = hardware
        self.event_bus = event_bus
        self.deadband = deadband

        self.properties = {
            "value": {"readable": True, "writable": False, "unit": "C"},
            "raw": {"readable": True, "writable": False, "unit": "u16"},
        }

        self._adc = hardware.create_internal_temp_adc(owner=self.device_id)
        self._current_raw = 0
        self._current_temp = 0.0
        self._last_published_temp = None

        # Take initial reading
        self.update()

    def _sample(self):
        raw = self._adc.read_u16()
        voltage = raw * 3.3 / 65535
        # RP2040 datasheet formula: Temp = 27 - (ADC_V - 0.706) / 0.001721
        temp = 27.0 - (voltage - 0.706) / 0.001721
        return raw, round(temp, 2)

    def update(self):
        """Samples the ADC and optionally fires a change event."""
        self._current_raw, self._current_temp = self._sample()

        if self.event_bus is not None:
            should_publish = False
            if self._last_published_temp is None:
                should_publish = True
            elif abs(self._current_temp - self._last_published_temp) >= self.deadband:
                should_publish = True

            if should_publish:
                self._last_published_temp = self._current_temp
                self.event_bus.publish(
                    "sensor.temperature.changed",
                    {"value": self._current_temp, "raw": self._current_raw}
                )

    def read(self, property_name):
        if property_name == "value":
            return self._current_temp
        elif property_name == "raw":
            return self._current_raw
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        raise ValueError("PROPERTY_READ_ONLY: {}".format(property_name))

    def deinit(self):
        self.hardware.release_internal_temp_adc()


class AnalogSensor(Device):
    """
    General analog sensor using an external GPIO pin (26, 27, 28, 29).
    """
    device_type = "analog_sensor"

    def __init__(self, hardware, pin, device_id=None):
        self.device_id = device_id or "sensor.analog.{}".format(pin)
        self.hardware = hardware
        self.pin = pin

        self.properties = {
            "raw": {"readable": True, "writable": False, "unit": "u16"},
            "voltage": {"readable": True, "writable": False, "unit": "V"},
        }

        self._adc = hardware.create_adc(pin, owner=self.device_id)
        self._current_raw = 0
        self.update()

    def update(self):
        self._current_raw = self._adc.read_u16()

    def read(self, property_name):
        if property_name == "raw":
            return self._current_raw
        elif property_name == "voltage":
            return round(self._current_raw * 3.3 / 65535, 3)
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        raise ValueError("PROPERTY_READ_ONLY: {}".format(property_name))

    def deinit(self):
        self.hardware.release_pin(self.pin)


class DigitalInputSensor(Device):
    """
    General digital input sensor (e.g. physical button, reed switch).
    """
    device_type = "digital_input"

    def __init__(self, hardware, pin, device_id=None, pull=None):
        self.device_id = device_id or "sensor.digital.{}".format(pin)
        self.hardware = hardware
        self.pin = pin

        self.properties = {
            "value": {"readable": True, "writable": False},
        }

        pull_mode = None
        if Pin is not None:
            if pull == "UP":
                pull_mode = getattr(Pin, "PULL_UP", None)
            elif pull == "DOWN":
                pull_mode = getattr(Pin, "PULL_DOWN", None)

        self._pin_obj = hardware.create_pin(pin, mode=getattr(Pin, "IN", 0) if Pin else 0, pull=pull_mode, owner=self.device_id)

    def read(self, property_name):
        if property_name == "value":
            return self._pin_obj.value()
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        raise ValueError("PROPERTY_READ_ONLY: {}".format(property_name))

    def deinit(self):
        self.hardware.release_pin(self.pin)
