"""
YumeCore Hardware Layer.
Manages low-level hardware resources (GPIO, PWM, ADC) on Raspberry Pi Pico.
Enforces pin conflict detection and hardware resource ownership.
Strictly distinguishes internal temperature sensor ADC(4) from GPIO ADC.
"""

try:
    from machine import Pin, PWM, ADC
except ImportError:
    Pin = None
    PWM = None
    ADC = None


class HardwareManager:
    # On RP2040, valid ADC GPIOs are 26, 27, 28 (and 29 on some boards)
    VALID_ADC_GPIOS = {26: 0, 27: 1, 28: 2, 29: 3}
    INTERNAL_TEMP_CHANNEL = 4

    def __init__(self):
        # Maps pin identifier to owner string
        self._claimed_pins = {}
        # Tracks created PWM instances for cleanup
        self._pwms = {}
        # Flag for internal temp sensor claim
        self._internal_temp_claimed_by = None

    def _normalize_pin_id(self, pin_id):
        """Converts pin identifier into canonical form (e.g. 'LED', or int 0..29)."""
        if isinstance(pin_id, str):
            pin_id_upper = pin_id.upper()
            if pin_id_upper == "LED":
                return "LED"
            if pin_id_upper.startswith("GP"):
                try:
                    return int(pin_id_upper[2:])
                except ValueError:
                    pass
            try:
                return int(pin_id)
            except ValueError:
                return pin_id_upper
        return pin_id

    def claim_pin(self, pin_id, owner):
        norm_pin = self._normalize_pin_id(pin_id)
        if norm_pin in self._claimed_pins:
            current_owner = self._claimed_pins[norm_pin]
            if current_owner != owner:
                raise ValueError(
                    "PIN_CONFLICT: Pin {} already claimed by {}".format(norm_pin, current_owner)
                )
        self._claimed_pins[norm_pin] = owner
        return norm_pin

    def release_pin(self, pin_id):
        norm_pin = self._normalize_pin_id(pin_id)
        if norm_pin in self._claimed_pins:
            del self._claimed_pins[norm_pin]
        if norm_pin in self._pwms:
            try:
                self._pwms[norm_pin].deinit()
            except Exception:
                pass
            del self._pwms[norm_pin]

    def is_pin_claimed(self, pin_id):
        norm_pin = self._normalize_pin_id(pin_id)
        return norm_pin in self._claimed_pins

    def get_claimed_pins(self):
        return dict(self._claimed_pins)

    def create_pin(self, pin_id, mode=None, pull=None, owner="generic"):
        norm_pin = self.claim_pin(pin_id, owner)

        if Pin is None:
            raise RuntimeError("machine.Pin is not available in this environment")

        if mode is None:
            mode = Pin.OUT

        kwargs = {}
        if pull is not None:
            kwargs["pull"] = pull

        if norm_pin == "LED":
            return Pin("LED", mode, **kwargs)
        return Pin(norm_pin, mode, **kwargs)

    def create_pwm(self, pin_id, freq=1000, duty_u16=0, owner="pwm"):
        norm_pin = self.claim_pin(pin_id, owner)

        if PWM is None:
            raise RuntimeError("machine.PWM is not available in this environment")

        pin_obj = self.create_pin(norm_pin, mode=Pin.OUT, owner=owner)
        pwm = PWM(pin_obj)
        pwm.freq(freq)
        pwm.duty_u16(duty_u16)
        self._pwms[norm_pin] = pwm
        return pwm

    def create_adc(self, channel_or_pin, owner="adc"):
        """
        Creates an ADC instance.
        - If channel_or_pin is 4 or 'INTERNAL_TEMP', configures ADC(4) without claiming a GPIO pin!
        - If channel_or_pin is a GPIO (26, 27, 28, 29), claims that GPIO pin and configures ADC(Pin(gpio)).
        """
        if channel_or_pin == self.INTERNAL_TEMP_CHANNEL or str(channel_or_pin).upper() in ("INTERNAL_TEMP", "TEMP"):
            return self.create_internal_temp_adc(owner=owner)

        norm_pin = self._normalize_pin_id(channel_or_pin)

        # Check if it's a valid ADC GPIO
        if isinstance(norm_pin, int) and norm_pin not in self.VALID_ADC_GPIOS:
            raise ValueError(
                "INVALID_ADC_PIN: GPIO {} is not an ADC pin (valid: 26, 27, 28, 29)".format(norm_pin)
            )

        norm_pin = self.claim_pin(norm_pin, owner)

        if ADC is None:
            raise RuntimeError("machine.ADC is not available in this environment")

        pin_obj = Pin(norm_pin, Pin.IN)
        return ADC(pin_obj)

    def create_internal_temp_adc(self, owner="temp_sensor"):
        """
        Creates internal RP2040 temperature sensor ADC(4).
        Does NOT claim or touch physical GPIO 4!
        """
        if self._internal_temp_claimed_by and self._internal_temp_claimed_by != owner:
            raise ValueError(
                "RESOURCE_CONFLICT: Internal temp sensor already claimed by {}".format(
                    self._internal_temp_claimed_by
                )
            )
        self._internal_temp_claimed_by = owner

        if ADC is None:
            raise RuntimeError("machine.ADC is not available in this environment")

        return ADC(self.INTERNAL_TEMP_CHANNEL)

    def release_internal_temp_adc(self):
        self._internal_temp_claimed_by = None

    def deinit(self):
        """Releases and deinits all claimed hardware resources."""
        for norm_pin, pwm in list(self._pwms.items()):
            try:
                pwm.deinit()
            except Exception:
                pass
        self._pwms.clear()
        self._claimed_pins.clear()
        self._internal_temp_claimed_by = None
