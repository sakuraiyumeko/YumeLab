"""
YumeCore Audio Actuators: PassiveBuzzer and ActiveBuzzer.
Supports tones, melodic sequences, sound effects (SFX), and alarm beeps.
"""

try:
    import time
    sleep_ms = time.sleep_ms
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
except (ImportError, AttributeError):
    import time
    sleep_ms = lambda ms: time.sleep(ms / 1000.0)
    ticks_ms = lambda: int(time.monotonic() * 1000)
    ticks_diff = lambda a, b: a - b

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

MORSE_TABLE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".",
    "F": "..-.", "G": "--.", "H": "....", "I": "..", "J": ".---",
    "K": "-.-", "L": ".-..", "M": "--", "N": "-.", "O": "---",
    "P": ".--.", "Q": "--.-", "R": ".-.", "S": "...", "T": "-",
    "U": "..-", "V": "...-", "W": ".--", "X": "-..-", "Y": "-.--",
    "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    "?": "..--..", "/": "-..-.", "-": "-....-", ".": ".-.-.-", ",": "--..--",
    ":": "---...", "=": "-...-", "+": ".-.-.", "!": "-.-.--",
}


class PassiveBuzzer(PWMOutput):
    """
    Passive buzzer actuator driven by PWM.
    Controls pitch via frequency (Hz) and sound volume via duty cycle (0-50%).
    Supports non-blocking melodies, tone steps, and SFX sequences.
    """
    device_type = "passive_buzzer"

    def __init__(self, hardware, pin, device_id="actuator.buzzer.passive", default_duty=25):
        super().__init__(hardware, pin, device_id=device_id, freq=1000, duty=0)
        self.default_duty = float(default_duty)
        self._last_sfx = "none"
        self._seq_queue = []  # list of (freq_hz, dur_ms)
        self._next_switch_ms = None

        self.properties = dict(self.properties)
        self.properties["sfx"] = {"readable": True, "writable": True, "type": "str"}
        self.properties["tone"] = {"readable": True, "writable": True, "unit": "Hz"}

    def update(self):
        """Called by Controller.tick() on each loop iteration."""
        if not self._seq_queue:
            return

        now = ticks_ms()
        if self._next_switch_ms is None or ticks_diff(now, self._next_switch_ms) >= 0:
            target_freq, dur_ms = self._seq_queue.pop(0)
            if target_freq <= 0:
                self.mute()
            else:
                self.write("frequency", target_freq)
                self.write("duty", self.default_duty)
            self._next_switch_ms = (now + dur_ms) if self._seq_queue else None

    def tone(self, freq_hz, duration_ms=0, duty=None):
        """Plays a tone. If duration_ms > 0, enqueues non-blocking silence."""
        freq = int(freq_hz)
        self._seq_queue = []
        self._next_switch_ms = None
        if freq <= 0:
            self.mute()
            return 0

        use_duty = self.default_duty if duty is None else float(duty)
        self.write("frequency", freq)
        self.write("duty", use_duty)

        if duration_ms > 0:
            self._seq_queue = [(0, 0)]
            self._next_switch_ms = ticks_ms() + int(duration_ms)
        return freq

    def mute(self):
        """Stops sound output."""
        self._seq_queue = []
        self._next_switch_ms = None
        self.write("duty", 0)

    def play_sequence(self, sequence):
        """Enqueues non-blocking sequence of (freq_hz, duration_ms) tuples."""
        queue = []
        for freq, duration in sequence:
            queue.append((freq, int(duration)))
            queue.append((0, 15))  # brief separation gap
        queue.append((0, 0))  # settle to mute
        self._seq_queue = queue
        self._next_switch_ms = None
        self.update()

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
    Supports non-blocking write('morse', text) for Morse code telegraph transmission.
    """
    device_type = "active_buzzer"

    def __init__(self, hardware, pin, device_id="actuator.buzzer.active", initial="OFF"):
        super().__init__(hardware, pin, device_id=device_id, initial=initial)
        self.properties = dict(self.properties)
        self.properties["beep"] = {"readable": True, "writable": True, "type": "int"}
        self.properties["morse"] = {"readable": True, "writable": True, "type": "str"}
        self._last_beep_count = 0
        self._last_morse = ""
        # Non-blocking async telegraph state machine
        self._morse_queue = []  # list of (state_val, duration_ms)
        self._next_switch_ms = None

    def update(self):
        """Called by Controller.tick() on each loop iteration."""
        if not self._morse_queue:
            return

        now = ticks_ms()
        if self._next_switch_ms is None or ticks_diff(now, self._next_switch_ms) >= 0:
            target_state, dur_ms = self._morse_queue.pop(0)
            self.write("state", target_state)
            self._next_switch_ms = (now + dur_ms) if self._morse_queue else None

    def beep(self, count=1, duration_ms=100, interval_ms=100):
        cnt = max(1, int(count))
        self._last_beep_count = cnt
        # Enqueue non-blocking beeps so serial communication does not freeze
        queue = []
        for i in range(cnt):
            queue.append(("ON", int(duration_ms)))
            if i < cnt - 1:
                queue.append(("OFF", int(interval_ms)))
            else:
                queue.append(("OFF", 0))
        self._morse_queue = queue
        self._next_switch_ms = None
        self.update()
        return cnt

    def play_morse(self, text, unit_ms=60):
        raw = str(text).upper().strip()
        self._last_morse = raw
        unit = max(20, int(unit_ms))
        dot_ms = unit
        dash_ms = unit * 3
        intra_elem_ms = unit
        char_gap_ms = unit * 3
        word_gap_ms = unit * 7

        queue = []
        words = raw.split(" ")
        for w_idx, word in enumerate(words):
            if not word:
                continue
            for c_idx, char in enumerate(word):
                symbols = MORSE_TABLE.get(char, "")
                for s_idx, sym in enumerate(symbols):
                    queue.append(("ON", dash_ms if sym == "-" else dot_ms))
                    if s_idx < len(symbols) - 1:
                        queue.append(("OFF", intra_elem_ms))
                if c_idx < len(word) - 1:
                    queue.append(("OFF", char_gap_ms))
            if w_idx < len(words) - 1:
                queue.append(("OFF", word_gap_ms))

        # Ensure final state settles to OFF
        queue.append(("OFF", 0))

        self._morse_queue = queue
        self._next_switch_ms = None
        # Start immediately
        self.update()
        return raw

    def read(self, property_name):
        if property_name == "beep":
            return self._last_beep_count
        elif property_name == "morse":
            return self._last_morse
        return super().read(property_name)

    def write(self, property_name, value):
        if property_name == "beep":
            return self.beep(count=int(value))
        elif property_name == "morse":
            return self.play_morse(value)
        return super().write(property_name, value)
