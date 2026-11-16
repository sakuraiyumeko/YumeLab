"""
YumeCore Audio Actuators: PassiveBuzzer and ActiveBuzzer.
Supports tones, melodic sequences, sound effects (SFX), and alarm beeps.
"""

try:
    import time
    sleep_ms = time.sleep_ms
except (ImportError, AttributeError):
    import time
    sleep_ms = lambda ms: time.sleep(ms / 1000.0)

from actuators import PWMOutput, DigitalOutput

# Standard Note Frequencies (Hz)
NOTES = {
    "REST": 0,
    "C4": 262, "D4": 294, "E4": 330, "F4": 349, "G4": 392, "A4": 440, "B4": 494,
    "C5": 523, "D5": 587, "E5": 659, "F5": 698, "G5": 784, "A5": 880, "B5": 988,
    "C6": 1047, "D6": 1175, "E6": 1319, "F6": 1397, "G6": 1568, "A6": 1760, "B6": 1976,
}

SFX_PRESETS = {
    "click": [(1800, 15)],
    "beep": [(2400, 60)],
    "tone_up": [(1047, 40), (1319, 50), (1568, 80)],
    "tone_down": [(1568, 40), (1319, 50), (1047, 80)],
    "stark_boot": [(523, 60), (659, 60), (784, 80), (1047, 180)],
    "alert": [(2000, 80), (0, 40), (2000, 80), (0, 40), (2000, 120)],
    "victory": [(523, 80), (659, 80), (784, 80), (1047, 240)],
}


class PassiveBuzzer(PWMOutput):
    """
    Passive buzzer actuator driven by PWM.
    Controls pitch via frequency (Hz) and sound volume via duty cycle (0-50%).
    Also exposes high-level presets via write('sfx', preset_name).
    """
    device_type = "passive_buzzer"

    def __init__(self, hardware, pin, device_id="actuator.buzzer.passive", default_duty=25):
        super().__init__(hardware, pin, device_id=device_id, freq=1000, duty=0)
        self.default_duty = float(default_duty)
        self._last_sfx = "none"

        self.properties = dict(self.properties)
        self.properties["sfx"] = {"readable": True, "writable": True, "type": "str"}
        self.properties["tone"] = {"readable": True, "writable": True, "unit": "Hz"}

    def tone(self, freq_hz, duration_ms=0, duty=None):
        """Plays a pure tone at given frequency."""
        freq = int(freq_hz)
        if freq <= 0:
            self.mute()
            if duration_ms > 0:
                sleep_ms(int(duration_ms))
            return 0

        use_duty = self.default_duty if duty is None else float(duty)
        self.write("frequency", freq)
        self.write("duty", use_duty)

        if duration_ms > 0:
            sleep_ms(int(duration_ms))
            self.mute()
        return freq

    def mute(self):
        """Stops sound output."""
        self.write("duty", 0)

    def play_sequence(self, sequence):
        """
        Plays a list of (freq_hz, duration_ms) tuples.
        0 frequency acts as a silent rest.
        """
        for freq, duration in sequence:
            if freq <= 0:
                self.mute()
                sleep_ms(int(duration))
            else:
                self.tone(freq, duration_ms=duration)
            sleep_ms(15)  # brief separation gap
        self.mute()

    def play_sfx(self, preset_name):
        name = str(preset_name).lower().strip()
        if name in SFX_PRESETS:
            self._last_sfx = name
            self.play_sequence(SFX_PRESETS[name])
            return name
        elif name in ("mute", "stop", "off"):
            self.mute()
            self._last_sfx = "mute"
            return "mute"
        raise ValueError("UNKNOWN_SFX: Expected one of {}".format(list(SFX_PRESETS.keys())))

    def read(self, property_name):
        if property_name == "sfx":
            return self._last_sfx
        elif property_name == "tone":
            return self.read("frequency") if self.read("duty") > 0 else 0
        return super().read(property_name)

    def write(self, property_name, value):
        if property_name == "sfx":
            return self.play_sfx(value)
        elif property_name == "tone":
            val = int(value)
            if val <= 0:
                self.mute()
                return 0
            return self.tone(val)
        return super().write(property_name, value)


class ActiveBuzzer(DigitalOutput):
    """
    Active buzzer actuator driven by high/low digital level.
    Sounds continuous beep when ON, silent when OFF.
    Supports write('beep', count) for short alarm bursts.
    """
    device_type = "active_buzzer"

    def __init__(self, hardware, pin, device_id="actuator.buzzer.active", initial="OFF"):
        super().__init__(hardware, pin, device_id=device_id, initial=initial)
        self.properties = dict(self.properties)
        self.properties["beep"] = {"readable": True, "writable": True, "type": "int"}
        self._last_beep_count = 0

    def beep(self, count=1, duration_ms=100, interval_ms=100):
        cnt = max(1, int(count))
        self._last_beep_count = cnt
        for i in range(cnt):
            self.write("state", "ON")
            sleep_ms(int(duration_ms))
            self.write("state", "OFF")
            if i < cnt - 1:
                sleep_ms(int(interval_ms))
        return cnt

    def read(self, property_name):
        if property_name == "beep":
            return self._last_beep_count
        return super().read(property_name)

    def write(self, property_name, value):
        if property_name == "beep":
            return self.beep(count=int(value))
        return super().write(property_name, value)
