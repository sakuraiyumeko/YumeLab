
import ujson
from machine import Pin, PWM, ADC


class Device:
    device_type = "generic"
    writable = False

    def __init__(self, name):
        self.name = name

    def read(self):
        raise NotImplementedError

    def write(self, value):
        raise ValueError("DEVICE_READ_ONLY")

    def info(self):
        return {
            "name": self.name,
            "type": self.device_type,
            "writable": self.writable,
        }


class DigitalOutput(Device):
    device_type = "digital_output"
    writable = True

    def __init__(self, name, pin, initial=0):
        super().__init__(name)
        self.pin = Pin(pin, Pin.OUT)
        self.pin.value(1 if initial else 0)

    def read(self):
        return self.pin.value()

    def write(self, value):
        value = str(value).upper()

        if value in ("1", "ON", "TRUE", "HIGH"):
            self.pin.on()
        elif value in ("0", "OFF", "FALSE", "LOW"):
            self.pin.off()
        else:
            raise ValueError("INVALID_DIGITAL_VALUE")

        return self.read()


class DigitalInput(Device):
    device_type = "digital_input"

    def __init__(self, name, pin, pull=None):
        super().__init__(name)

        if pull == "UP":
            self.pin = Pin(pin, Pin.IN, Pin.PULL_UP)
        elif pull == "DOWN":
            self.pin = Pin(pin, Pin.IN, Pin.PULL_DOWN)
        else:
            self.pin = Pin(pin, Pin.IN)

    def read(self):
        return self.pin.value()


class PWMOutput(Device):
    device_type = "pwm_output"
    writable = True

    def __init__(self, name, pin, freq=1000, duty=0):
        super().__init__(name)

        self.pwm = PWM(Pin(pin))
        self.pwm.freq(freq)
        self.pwm.duty_u16(
            int(max(0, min(100, duty)) * 65535 / 100)
        )

    def read(self):
        return {
            "frequency": self.pwm.freq(),
            "duty": round(
                self.pwm.duty_u16() * 100 / 65535, 2
            ),
        }

    def write(self, value):
        duty = float(value)

        if not 0 <= duty <= 100:
            raise ValueError("INVALID_PWM_DUTY")

        self.pwm.duty_u16(int(duty * 65535 / 100))
        return self.read()

    def deinit(self):
        self.pwm.deinit()


class AnalogInput(Device):
    device_type = "analog_input"

    def __init__(self, name, pin):
        super().__init__(name)
        self.adc = ADC(Pin(pin))

    def read(self):
        return self.adc.read_u16()


class Hardware:
    def __init__(self):
        self.devices = {}

        # Pico onboard LED
        self.register(
            DigitalOutput("led", "LED", initial=0)
        )

    def register(self, device):
        if not isinstance(device, Device):
            raise TypeError("INVALID_DEVICE")

        if not device.name:
            raise ValueError("INVALID_DEVICE_NAME")

        if device.name in self.devices:
            raise ValueError("DEVICE_ALREADY_REGISTERED")

        self.devices[device.name] = device
        return device

    def unregister(self, name):
        device = self.devices.get(name)

        if device is None:
            raise ValueError("DEVICE_NOT_FOUND")

        if isinstance(device, PWMOutput):
            device.deinit()

        del self.devices[name]

    def get_device(self, name):
        device = self.devices.get(name)

        if device is None:
            raise ValueError("DEVICE_NOT_FOUND")

        return device

    def list_devices(self):
        return [
            device.info()
            for device in self.devices.values()
        ]

    def read(self, name):
        return self.get_device(name).read()

    def write(self, name, value):
        return self.get_device(name).write(value)

    def get_status(self):
        led = self.read("led")
        return "LED={}".format("ON" if led else "OFF")

    def dispatch(self, command, args):
        if command == "STATUS":
            if args:
                raise ValueError("INVALID_ARGUMENT")
            return self.get_status()

        if command == "LED":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            state = self.write("led", args[0])
            return "LED={}".format("ON" if state else "OFF")

        if command == "HW_LIST":
            if args:
                raise ValueError("INVALID_ARGUMENT")

            return ujson.dumps(self.list_devices())

        if command == "HW_GET":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            device = self.get_device(args[0])

            return ujson.dumps({
                "name": device.name,
                "value": device.read(),
            })

        if command == "HW_SET":
            if len(args) != 2:
                raise ValueError("INVALID_ARGUMENT")

            result = self.write(args[0], args[1])

            return ujson.dumps({
                "name": args[0],
                "value": result,
            })

        raise ValueError("UNKNOWN_COMMAND")

    def deinit(self):
        for device in self.devices.values():
            if isinstance(device, PWMOutput):
                device.deinit()
