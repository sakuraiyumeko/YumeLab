import time
from host import YumeCore

tone = {
    "C": 262,
    "C#": 277,
    "D": 294,
    "D#": 311,
    "E": 330,
    "F": 349,
    "F#": 370,
    "G": 392,
    "G#": 415,
    "A": 440,
    "A#": 466,
    "B": 494
}

def get_tone(note):
    name = note[:-1]
    octave = int(note[-1])

    return int(tone[name] * (2 ** (octave - 4)))


with YumeCore(port="COM7") as core:
    # 随手弹一段
    melody = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]

    for note in melody:
        freq = get_tone(note)
        core.devices.write("actuator.buzzer.passive", "tone", freq)
        time.sleep(0.2)

    # 停音
    core.devices.write("actuator.buzzer.passive", "tone", 0)
