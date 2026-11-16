import re
import time
import tomllib
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional
from host import YumeCore

tone = {
    "C": 262, "C#": 277, "D": 294, "D#": 311,
    "E": 330, "F": 349, "F#": 370, "G": 392,
    "G#": 415, "A": 440, "A#": 466, "B": 494,
}


def get_tone(note, bpm):
    if note.startswith("R"):
        match = re.fullmatch(r"R(?::(\d+))?(\.)?", note)
        if not match:
            raise ValueError(f"Invalid rest: {note}")
        duration = int(match.group(1) or 4)
        seconds = 60 / bpm * 4 / duration
        return 0, (seconds * 1.5 if match.group(2) else seconds)

    match = re.fullmatch(r"([A-G]#?)([0-8])(?::(\d+))?(\.)?", note)
    if not match:
        raise ValueError(f"Invalid note: {note}")
    name, octave, duration, dotted = match.groups()
    freq = int(tone[name] * (2 ** (int(octave) - 4)))
    seconds = 60 / bpm * 4 / int(duration or 4)
    return freq, (seconds * 1.5 if dotted else seconds)


class State(Enum):
    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()


class BuzzerPlayer:
    def __init__(
        self,
        core,
        io_lock=None,
        sheets_dir: Optional[Path] = None,
        on_state_change: Optional[Callable[[dict], None]] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self.core = core
        self.lock = io_lock if io_lock is not None else threading.RLock()
        self.sheets_dir = Path(sheets_dir) if sheets_dir is not None else (Path(__file__).parent / "sheets")
        self.on_state_change = on_state_change
        self.log_fn = log_fn if log_fn is not None else print
        self.state = State.IDLE
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # set = 不暂停
        self.thread = None
        self.current_title = None
        self.current_sheet = None
        self.current_bpm = 120
        self.current_index = 0
        self.total_notes = 0
        self._sfx_seq = 0

    def _emit_log(self, msg: str):
        if self.log_fn:
            self.log_fn(msg)

    def _notify_change(self):
        if self.on_state_change:
            try:
                self.on_state_change(self.status())
            except Exception:
                pass

    def _write_tone(self, freq):
        with self.lock:
            if self.core is None:
                return
            self.core.devices.write("actuator.buzzer.passive", "tone", freq)

    def status(self) -> dict:
        return {
            "state": self.state.name,
            "title": self.current_title,
            "sheet": self.current_sheet,
            "bpm": self.current_bpm,
            "progress": self.current_index,
            "total": self.total_notes,
        }

    def list_sheets(self):
        files = get_sheets(self.sheets_dir)
        result = []
        for p in files:
            meta = {"id": p.stem, "filename": p.name, "title": p.stem, "bpm": 120, "notes": 0}
            try:
                with open(p, "rb") as f:
                    song = tomllib.load(f)
                meta["title"] = song.get("title", p.stem)
                meta["bpm"] = song.get("bpm", 120)
                meta["notes"] = len(song.get("melody", []))
            except Exception:
                pass
            result.append(meta)
        return result

    def resolve_sheet(self, sheet_ref) -> Path:
        files = get_sheets(self.sheets_dir)
        if not files:
            raise FileNotFoundError("没有找到任何乐谱文件")
        ref = str(sheet_ref).strip()
        if ref.isdigit():
            idx = int(ref) - 1
            if 0 <= idx < len(files):
                return files[idx]
            raise ValueError(f"序号超出范围啦 (1~{len(files)})")
        name = ref if ref.endswith(".toml") else f"{ref}.toml"
        direct = self.sheets_dir / name
        if direct.exists():
            return direct
        lower_ref = ref.lower()
        for p in files:
            if p.stem.lower() == lower_ref or p.name.lower() == lower_ref:
                return p
            try:
                with open(p, "rb") as f:
                    title = str(tomllib.load(f).get("title", "")).lower()
                if lower_ref and lower_ref in title:
                    return p
            except Exception:
                pass
        raise FileNotFoundError(f"找不到乐谱: {ref}")

    def play(self, toml_path):
        toml_path = Path(toml_path)
        self.stop()  # 先停掉上一首
        with open(toml_path, "rb") as f:
            song = tomllib.load(f)

        self.current_title = song.get("title", toml_path.stem)
        self.current_sheet = toml_path.stem
        bpm = song.get("bpm", 120)
        gate = song.get("gate", 0.98)
        melody = song["melody"]
        self.current_bpm = bpm
        self.current_index = 0
        self.total_notes = len(melody)

        self.stop_event.clear()
        self.pause_event.set()
        self.state = State.PLAYING
        self._notify_change()

        def _sleep_until(target_time: float) -> bool:
            """Sleep until target monotonic time, returning False if stopped or paused."""
            while True:
                if self.stop_event.is_set() or not self.pause_event.is_set():
                    return False
                remaining = target_time - time.monotonic()
                if remaining <= 0:
                    return True
                time.sleep(min(remaining, 0.005))

        def _worker():
            try:
                next_deadline = None
                prev_freq = None
                for idx, note in enumerate(melody, 1):
                    if self.stop_event.is_set():
                        break
                    if not self.pause_event.is_set():
                        self.pause_event.wait()
                        if self.stop_event.is_set():
                            break
                        next_deadline = None
                        prev_freq = None

                    self.current_index = idx
                    freq, dur = get_tone(note, bpm)

                    # 发送音符指令
                    if freq > 0:
                        self._write_tone(freq)
                    elif prev_freq != 0:
                        self._write_tone(0)
                    prev_freq = freq

                    # 关键修复：以音符成功在硬件/驱动生效的时刻（即 write_tone 之后）作为当前音符发声起点
                    now = time.monotonic()
                    if next_deadline is None or next_deadline < now - 0.15:
                        start_time = now
                    else:
                        start_time = next_deadline

                    sound_end = start_time + dur * gate
                    note_end = start_time + dur

                    if not _sleep_until(sound_end):
                        if self.stop_event.is_set():
                            break
                        self._write_tone(0)
                        prev_freq = 0
                        self.pause_event.wait()
                        if self.stop_event.is_set():
                            break
                        next_deadline = None
                        continue

                    if gate < 1.0 and freq > 0:
                        self._write_tone(0)
                        prev_freq = 0
                        if not _sleep_until(note_end):
                            if self.stop_event.is_set():
                                break
                            self._write_tone(0)
                            prev_freq = 0
                            self.pause_event.wait()
                            if self.stop_event.is_set():
                                break
                            next_deadline = None
                            continue

                    next_deadline = note_end
            finally:
                try:
                    if prev_freq != 0:
                        self._write_tone(0)
                except Exception:
                    pass
                was_stopped = self.stop_event.is_set()
                if self.state != State.IDLE:
                    self.state = State.IDLE
                    self.current_index = 0
                    self._notify_change()
                    if not was_stopped:
                        self._emit_log(f"[播放结束] {self.current_title}")

        self.thread = threading.Thread(target=_worker, daemon=True)
        self.thread.start()
        self._emit_log(f"开始演奏: {self.current_title} (BPM={bpm})")
        return self.status()

    def pause(self):
        if self.state == State.PLAYING:
            self.pause_event.clear()
            self.state = State.PAUSED
            self._write_tone(0)
            self._notify_change()
            self._emit_log("已暂停")
        else:
            self._emit_log("当前没有在播放哦")
        return self.status()

    def resume(self):
        if self.state == State.PAUSED:
            self.state = State.PLAYING
            self.pause_event.set()
            self._notify_change()
            self._emit_log("继续演奏～")
        else:
            self._emit_log("当前不在暂停状态哦")
        return self.status()

    def stop(self):
        if self.state != State.IDLE:
            self.stop_event.set()
            self.pause_event.set()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.5)
            self.state = State.IDLE
            self.current_index = 0
            try:
                self._write_tone(0)
            except Exception:
                pass
            self._notify_change()
            self._emit_log("已停止播放")
        return self.status()

    def play_sequence(self, sequence, title="SFX", bpm=120, gate=0.95):
        """
        Plays a list of (freq_hz, duration_ms) tuples using the BuzzerPlayer engine
        with exact monotonic clock tracking, interruption of previous songs/sfx, and no serial collisions.
        """
        self.stop()
        self.current_title = title
        self.current_sheet = title
        self.current_bpm = bpm
        self.current_index = 0
        self.total_notes = len(sequence)

        self.stop_event.clear()
        self.pause_event.set()
        self.state = State.PLAYING
        self._notify_change()

        def _sleep_until(target_time: float) -> bool:
            while True:
                if self.stop_event.is_set() or not self.pause_event.is_set():
                    return False
                remaining = target_time - time.monotonic()
                if remaining <= 0:
                    return True
                time.sleep(min(remaining, 0.005))

        def _worker():
            try:
                next_deadline = None
                prev_freq = None
                for idx, (freq, dur_ms) in enumerate(sequence, 1):
                    if self.stop_event.is_set():
                        break
                    if not self.pause_event.is_set():
                        self.pause_event.wait()
                        if self.stop_event.is_set():
                            break
                        next_deadline = None
                        prev_freq = None

                    self.current_index = idx
                    dur = dur_ms / 1000.0

                    if freq > 0:
                        self._write_tone(freq)
                    elif prev_freq != 0:
                        self._write_tone(0)
                    prev_freq = freq

                    now = time.monotonic()
                    if next_deadline is None or next_deadline < now - 0.15:
                        start_time = now
                    else:
                        start_time = next_deadline

                    sound_end = start_time + dur * gate
                    note_end = start_time + dur

                    if not _sleep_until(sound_end):
                        if self.stop_event.is_set():
                            break
                        self._write_tone(0)
                        prev_freq = 0
                        self.pause_event.wait()
                        if self.stop_event.is_set():
                            break
                        next_deadline = None
                        continue

                    if gate < 1.0 and freq > 0:
                        self._write_tone(0)
                        prev_freq = 0
                        if not _sleep_until(note_end):
                            if self.stop_event.is_set():
                                break
                            self._write_tone(0)
                            prev_freq = 0
                            self.pause_event.wait()
                            if self.stop_event.is_set():
                                break
                            next_deadline = None
                            continue

                    next_deadline = note_end
            finally:
                try:
                    if prev_freq != 0:
                        self._write_tone(0)
                except Exception:
                    pass
                was_stopped = self.stop_event.is_set()
                if self.state != State.IDLE:
                    self.state = State.IDLE
                    self.current_index = 0
                    self._notify_change()
                    if not was_stopped:
                        self._emit_log(f"[播放结束] {self.current_title}")

        self.thread = threading.Thread(target=_worker, daemon=True)
        self.thread.start()
        return self.status()

    def play_sfx(self, preset_name: str):
        """Plays an SFX preset through the robust BuzzerPlayer scheduling engine."""
        presets = {
            "click": [(1800, 20)],
            "beep": [(2400, 80)],
            "tone_up": [(1047, 50), (1319, 60), (1568, 100)],
            "tone_down": [(1568, 50), (1319, 60), (1047, 100)],
            "stark_boot": [(523, 70), (659, 70), (784, 90), (1047, 200)],
            "alert": [(2000, 90), (0, 50), (2000, 90), (0, 50), (2000, 140)],
            "victory": [(523, 90), (659, 90), (784, 90), (1047, 260)],
        }
        name = str(preset_name).lower().strip()
        if name in ("mute", "stop", "off"):
            self.stop()
            return name
        seq = presets.get(name)
        if seq:
            self.play_sequence(seq, title=f"SFX_{name}")
            return name
        return name

    def play_sfx_async(self, preset_name: str) -> None:
        """Alias to play_sfx for compatibility."""
        self.play_sfx(preset_name)


def get_sheets(sheets_dir):
    if not sheets_dir.exists():
        return []
    return sorted(sheets_dir.glob("*.toml"))


def main():
    sheets_dir = Path(__file__).parent / "sheets"
    print("正在连接 YumeCore (COM7)...")

    with YumeCore(port="COM7") as core:
        player = BuzzerPlayer(
            core,
            log_fn=lambda m: print(f"\n{m}\nyume> ", end="", flush=True) if m.startswith("[播放结束]") else print(m),
        )
        print("连接成功！输入 help 查看指令，输入 quit 退出。")
        try:
            while True:
                try:
                    cmd_line = input(f"[{player.state.name}] yume> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not cmd_line:
                    continue

                parts = cmd_line.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""

                if cmd in ("quit", "exit", "q"):
                    player.stop()
                    break
                elif cmd in ("list", "ls"):
                    files = get_sheets(sheets_dir)
                    if not files:
                        print("可用乐谱: (空)")
                    else:
                        print("可用乐谱:")
                        for idx, p in enumerate(files, 1):
                            print(f"  {idx}. {p.stem}")
                elif cmd == "play":
                    if not arg:
                        print("用法: play <序号或歌名>")
                        continue
                    files = get_sheets(sheets_dir)
                    if arg.isdigit():
                        idx = int(arg) - 1
                        if 0 <= idx < len(files):
                            player.play(files[idx])
                        else:
                            print(f"序号超出范围啦 (1~{len(files)})")
                    else:
                        name = arg if arg.endswith(".toml") else f"{arg}.toml"
                        path = sheets_dir / name
                        if not path.exists():
                            print(f"找不到乐谱: {path}")
                        else:
                            player.play(path)
                elif cmd == "pause":
                    player.pause()
                elif cmd == "resume":
                    player.resume()
                elif cmd == "stop":
                    player.stop()
                elif cmd == "help":
                    print("指令: ls | play <序号/歌名> | pause | resume | stop | quit")
                else:
                    print(f"未知指令: {cmd} (输入 help 查看)")
        finally:
            player.stop()
            core.devices.write("actuator.buzzer.passive", "tone", 0)

    print("再见啦～")


if __name__ == "__main__":
    main()