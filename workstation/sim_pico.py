"""
Simulated Pico Node & Transport for pure-software development and testing.

Reuses real YumeCore PICO modules (devices, sensors, actuators, events,
applications, services, controller, CommandDispatcher) backed by simulated
machine Pin/ADC/PWM objects so every protocol request executes the exact
YumeCore firmware logic without physical hardware.
"""

import importlib
import math
import os
import sys
import time
import types
from collections import deque
from pathlib import Path
from typing import Dict, Optional


PICO_DIR = Path(__file__).resolve().parent.parent / "YumeCore" / "PICO"
_CACHED_PICO_MODS: Optional[Dict[str, types.ModuleType]] = None


class _SimPin:
    IN = 0
    OUT = 1
    PULL_UP = 2
    PULL_DOWN = 3

    def __init__(self, pin_id, mode=OUT, pull=None):
        self.pin_id = pin_id
        self.mode = mode
        self.pull = pull
        self._val = 0

    def value(self, val=None):
        if val is not None:
            self._val = 1 if val else 0
        return self._val


class _SimPWM:
    def __init__(self, pin_obj):
        self.pin_obj = pin_obj
        self._freq = 1000
        self._duty_u16 = 0

    def freq(self, val=None):
        if val is not None:
            self._freq = int(val)
        return self._freq

    def duty_u16(self, val=None):
        if val is not None:
            self._duty_u16 = int(val)
        return self._duty_u16

    def deinit(self):
        pass


class _SimADC:
    def __init__(self, channel_or_pin, env_state: Dict[str, float]):
        self.channel_or_pin = channel_or_pin
        self.env_state = env_state

    def read_u16(self) -> int:
        # Internal RP2040 temperature sensor ADC(4)
        if self.channel_or_pin == 4:
            temp_c = self.env_state["ambient_temp_c"]
            voltage = 0.706 - (temp_c - 27.0) * 0.001721
            raw = int(voltage * 65535 / 3.3)
            return max(0, min(65535, raw))

        # External GPIO 26 light sensor ADC
        pin_id = getattr(self.channel_or_pin, "pin_id", self.channel_or_pin)
        if pin_id == 26:
            pct = max(0.0, min(100.0, self.env_state["ambient_light_pct"]))
            raw = int(1040 + (pct / 100.0) * (65535 - 1040))
            return max(0, min(65535, raw))

        return 32768


def _install_fake_machine(env_state: Dict[str, float]) -> None:
    """Installs or refreshes a simulated MicroPython `machine` module."""
    if "machine" in sys.modules and getattr(sys.modules["machine"], "_yumelab_sim", False):
        sys.modules["machine"].ADC = lambda ch: _SimADC(ch, env_state)
        return

    fake_machine = types.ModuleType("machine")
    fake_machine._yumelab_sim = True
    fake_machine.Pin = _SimPin
    fake_machine.PWM = _SimPWM
    fake_machine.ADC = lambda ch: _SimADC(ch, env_state)
    fake_machine.soft_reset = lambda: None
    sys.modules["machine"] = fake_machine


def _load_pico_modules() -> Dict[str, types.ModuleType]:
    """
    Loads YumeCore/PICO modules cleanly without colliding with YumeCore/PC
    `transport` or `protocol` entries already present in `sys.modules`.
    """
    global _CACHED_PICO_MODS
    if _CACHED_PICO_MODS is not None:
        return _CACHED_PICO_MODS

    pico_str = str(PICO_DIR)
    saved_modules = {}
    collide_names = (
        "transport",
        "protocol",
        "hardware",
        "devices",
        "sensors",
        "actuators",
        "buzzer",
        "events",
        "device_service",
        "app_service",
        "controller",
        "filesystem",
        "main",
        "applications",
        "applications.thermal",
        "applications.ambient_light",
    )
    for name in collide_names:
        if name in sys.modules:
            saved_modules[name] = sys.modules.pop(name)

    sys.path.insert(0, pico_str)
    try:
        mods = {
            "transport": importlib.import_module("transport"),
            "protocol": importlib.import_module("protocol"),
            "hardware": importlib.import_module("hardware"),
            "devices": importlib.import_module("devices"),
            "sensors": importlib.import_module("sensors"),
            "actuators": importlib.import_module("actuators"),
            "buzzer": importlib.import_module("buzzer"),
            "events": importlib.import_module("events"),
            "device_service": importlib.import_module("device_service"),
            "app_service": importlib.import_module("app_service"),
            "controller": importlib.import_module("controller"),
            "filesystem": importlib.import_module("filesystem"),
            "main": importlib.import_module("main"),
            "thermal": importlib.import_module("applications.thermal"),
            "ambient_light": importlib.import_module("applications.ambient_light"),
        }
        _CACHED_PICO_MODS = mods
        return mods
    finally:
        if sys.path and sys.path[0] == pico_str:
            sys.path.pop(0)
        # Restore PC modules if they were loaded prior to PICO import
        for name in collide_names:
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


class SimulatedPicoNode:
    """
    In-memory simulation of the Raspberry Pi Pico running YumeCore.
    Includes realistic ambient temperature & daylight waveforms that can also
    be manually overridden from the workstation UI or tests.
    """

    def __init__(self, initial_temp: float = 29.5, initial_light: float = 62.0):
        self.env_state: Dict[str, float] = {
            "ambient_temp_c": float(initial_temp),
            "ambient_light_pct": float(initial_light),
        }
        self._manual_override = False
        self._start_time = time.monotonic()

        _install_fake_machine(self.env_state)
        mods = _load_pico_modules()

        # Refresh ADC/Pin/PWM references inside hardware/sensors/actuators for this node's env_state
        fake_machine = sys.modules["machine"]
        mods["hardware"].ADC = fake_machine.ADC
        mods["hardware"].Pin = fake_machine.Pin
        mods["hardware"].PWM = fake_machine.PWM
        mods["actuators"].Pin = fake_machine.Pin
        mods["actuators"].PWM = fake_machine.PWM
        mods["sensors"].Pin = fake_machine.Pin

        self.hardware = mods["hardware"].HardwareManager()
        self.registry = mods["devices"].DeviceRegistry()
        self.events = mods["events"].EventBus()
        self.device_service = mods["device_service"].DeviceService(self.registry)
        self.app_service = mods["app_service"].AppService()
        self.filesystem = mods["filesystem"].FileSystem()
        self.controller = mods["controller"].Controller(
            registry=self.registry,
            events=self.events,
            update_interval_ms=500,
        )

        # Register simulated devices mirroring YumeCore/PICO/main.py
        self.led = mods["actuators"].LED(self.hardware, pin="LED", device_id="led", initial="OFF")
        self.registry.register(self.led)

        self.temp_sensor = mods["sensors"].TemperatureSensor(
            self.hardware,
            device_id="sensor.temperature",
            event_bus=self.events,
            deadband=0.1,
        )
        self.registry.register(self.temp_sensor)

        self.light_sensor = mods["sensors"].LightSensor(
            self.hardware,
            pin=26,
            device_id="sensor.light",
            event_bus=self.events,
            deadband=1.0,
        )
        self.registry.register(self.light_sensor)

        self.desk_lamp = mods["actuators"].PWMOutput(
            self.hardware,
            pin=15,
            device_id="actuator.desk_lamp",
            freq=1000,
            duty=0,
        )
        self.registry.register(self.desk_lamp)

        self.passive_buzzer = mods["buzzer"].PassiveBuzzer(
            self.hardware,
            pin=16,
            device_id="actuator.buzzer.passive",
        )
        self.registry.register(self.passive_buzzer)

        self.active_buzzer = mods["buzzer"].ActiveBuzzer(
            self.hardware,
            pin=17,
            device_id="actuator.buzzer.active",
            initial="OFF",
        )
        self.registry.register(self.active_buzzer)

        # Register applications
        self.thermal_app = mods["thermal"].ThermalButton(
            sensor=self.temp_sensor,
            events=self.events,
            threshold=45.0,
            hysteresis=1.0,
            debounce_ms=0,
            led_device=self.led,
        )
        self.app_service.register_app(self.thermal_app)
        self.controller.register_app(self.thermal_app)

        self.ambient_light_app = mods["ambient_light"].AmbientLightController(
            sensor=self.light_sensor,
            events=self.events,
            dark_threshold=35.0,
            hysteresis=5.0,
            debounce_ms=0,
            actuator_device=self.desk_lamp,
            target_brightness=60.0,
        )
        self.app_service.register_app(self.ambient_light_app)
        self.controller.register_app(self.ambient_light_app)

        self.dispatcher = mods["main"].CommandDispatcher(
            self.device_service,
            self.app_service,
            self.filesystem,
        )

    def set_environment(
        self,
        temp_c: Optional[float] = None,
        light_pct: Optional[float] = None,
        auto_wave: bool = False,
    ) -> Dict[str, float]:
        """Allows tests or UI simulation sliders to inject ambient conditions."""
        self._manual_override = not auto_wave
        if temp_c is not None:
            self.env_state["ambient_temp_c"] = float(temp_c)
        if light_pct is not None:
            self.env_state["ambient_light_pct"] = max(0.0, min(100.0, float(light_pct)))
        for dev in self.registry.all():
            dev.update()
        self.controller.tick()
        return dict(self.env_state)

    def step_simulation(self) -> None:
        """Advances simulated ambient drift and ticks the YumeCore controller."""
        if not self._manual_override:
            t = time.monotonic() - self._start_time
            self.env_state["ambient_temp_c"] = round(30.0 + 4.5 * math.sin(t * 0.25), 2)
            self.env_state["ambient_light_pct"] = round(50.0 + 35.0 * math.cos(t * 0.18), 1)
        self.controller.tick()

    def handle_line(self, line: str) -> str:
        """Processes one protocol request line and returns the response frame."""
        self.step_simulation()
        if line.strip().endswith("INFO"):
            req_id = line.strip().split()[0]
            if not hasattr(os, "uname"):
                return f"{req_id} OK MACHINE=Simulated-Pico-RP2040 RELEASE=sim-1.0\n"
        response, _do_reboot = self.dispatcher.dispatch(line)
        return response


class SimulatedTransport:
    """
    Drop-in replacement for YumeCore PC `SerialTransport`.
    Bridges `YumeCore` client calls directly to a `SimulatedPicoNode`.
    """

    def __init__(self, node: Optional[SimulatedPicoNode] = None):
        self.node = node or SimulatedPicoNode()
        self._rx_queue: deque = deque()
        self._open = True

    @property
    def is_open(self) -> bool:
        return self._open

    def write(self, data: str) -> None:
        if not self._open:
            raise ConnectionError("Simulated transport is closed")
        for line in data.splitlines(keepends=True):
            if line.strip():
                resp = self.node.handle_line(line)
                self._rx_queue.append(resp.strip())

    def readline(self, deadline: Optional[float] = None) -> Optional[str]:
        if not self._open:
            raise ConnectionError("Simulated transport is closed")
        if self._rx_queue:
            return self._rx_queue.popleft()
        return None

    def reset_input_buffer(self) -> None:
        self._rx_queue.clear()

    def close(self) -> None:
        self._open = False
