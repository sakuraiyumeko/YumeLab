"""
YumeCore Actuators.
Implements actuator devices (LED, DigitalOutput, PWMOutput).
Actuators operate hardware on command; they make no policy decisions.
"""

from devices import Device

try:
    from machine import Pin, PWM
except ImportError:
    Pin = None
    PWM = None


class LED(Device):
    """
    LED actuator (defaults to board LED, can be mapped to any pin).
    """
    device_id = "led"
    device_type = "led"

    def __init__(self, hardware, pin="LED", device_id="led", initial="OFF"):
        self.device_id = device_id
        self.hardware = hardware
        self.pin = pin

        self.properties = {
            "state": {"readable": True, "writable": True},
        }

        mode = getattr(Pin, "OUT", 1) if Pin else 1
        self._pin_obj = hardware.create_pin(pin, mode=mode, owner=self.device_id)

        self.write("state", initial)

    def read(self, property_name):
        if property_name == "state":
            val = self._pin_obj.value()
            return "ON" if val else "OFF"
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        if property_name != "state":
            raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

        val_str = str(value).upper()
        if val_str in ("ON", "1", "TRUE", "HIGH"):
            self._pin_obj.value(1)
        elif val_str in ("OFF", "0", "FALSE", "LOW"):
            self._pin_obj.value(0)
        elif val_str == "TOGGLE":
            current = self._pin_obj.value()
            self._pin_obj.value(0 if current else 1)
        else:
            raise ValueError("INVALID_VALUE: Expected ON/OFF/TOGGLE, got {}".format(value))

        return self.read("state")

    def deinit(self):
        self.hardware.release_pin(self.pin)


class DigitalOutput(Device):
    """
    General digital output on a GPIO pin.
    """
    device_type = "digital_output"

    def __init__(self, hardware, pin, device_id=None, initial="OFF"):
        self.device_id = device_id or "actuator.digital.{}".format(pin)
        self.hardware = hardware
        self.pin = pin

        self.properties = {
            "state": {"readable": True, "writable": True},
        }

        mode = getattr(Pin, "OUT", 1) if Pin else 1
        self._pin_obj = hardware.create_pin(pin, mode=mode, owner=self.device_id)
        self.write("state", initial)

    def read(self, property_name):
        if property_name == "state":
            return "ON" if self._pin_obj.value() else "OFF"
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        if property_name != "state":
            raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

        val_str = str(value).upper()
        if val_str in ("ON", "1", "TRUE", "HIGH"):
            self._pin_obj.value(1)
        elif val_str in ("OFF", "0", "FALSE", "LOW"):
            self._pin_obj.value(0)
        elif val_str == "TOGGLE":
            current = self._pin_obj.value()
            self._pin_obj.value(0 if current else 1)
        else:
            raise ValueError("INVALID_VALUE: Expected ON/OFF/TOGGLE, got {}".format(value))

        return self.read("state")

    def deinit(self):
        self.hardware.release_pin(self.pin)


class PWMOutput(Device):
    """
    General PWM output on a GPIO pin.
    """
    device_type = "pwm_output"

    def __init__(self, hardware, pin, device_id=None, freq=1000, duty=0):
        self.device_id = device_id or "actuator.pwm.{}".format(pin)
        self.hardware = hardware
        self.pin = pin

        self.properties = {
            "duty": {"readable": True, "writable": True, "unit": "%"},
            "frequency": {"readable": True, "writable": True, "unit": "Hz"},
        }

        duty_u16 = int(max(0.0, min(100.0, float(duty))) * 65535 / 100)
        self._pwm = hardware.create_pwm(pin, freq=freq, duty_u16=duty_u16, owner=self.device_id)

    def read(self, property_name):
        if property_name == "duty":
            return round(self._pwm.duty_u16() * 100 / 65535, 2)
        elif property_name == "frequency":
            return self._pwm.freq()
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def write(self, property_name, value):
        if property_name == "duty":
            duty_val = float(value)
            if not 0.0 <= duty_val <= 100.0:
                raise ValueError("INVALID_DUTY: Must be 0..100")
            self._pwm.duty_u16(int(duty_val * 65535 / 100))
            return self.read("duty")
        elif property_name == "frequency":
            freq_val = int(value)
            if freq_val <= 0:
                raise ValueError("INVALID_FREQ: Must be > 0")
            self._pwm.freq(freq_val)
            return self.read("frequency")
        raise ValueError("UNKNOWN_PROPERTY: {}".format(property_name))

    def deinit(self):
        self.hardware.release_pin(self.pin)
