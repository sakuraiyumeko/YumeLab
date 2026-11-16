"""
YumeCore Main Entry Point for Raspberry Pi Pico.
Assembles the system layers and executes the fair scheduling loop.
"""

import sys
import os
import time

try:
    import machine
except ImportError:
    machine = None

from transport import Transport
from protocol import parse_request, make_response
from hardware import HardwareManager
from devices import DeviceRegistry
from sensors import TemperatureSensor, LightSensor
from actuators import LED, PWMOutput
from buzzer import PassiveBuzzer, ActiveBuzzer
from events import EventBus
from applications.thermal import ThermalButton
from applications.ambient_light import AmbientLightController
from device_service import DeviceService
from app_service import AppService
from filesystem import FileSystem
from controller import Controller


class CommandDispatcher:
    """
    Routes parsed protocol requests to appropriate domain services.
    """
    def __init__(self, device_service, app_service, filesystem):
        self.device_service = device_service
        self.app_service = app_service
        self.filesystem = filesystem

    def dispatch(self, message):
        request_id, command, args, error = parse_request(message)

        if error:
            return make_response(
                request_id or "0000",
                "ERROR",
                error
            ), False

        try:
            # 1. System Level Commands
            if command == "PING":
                if args:
                    return make_response(request_id, "ERROR", "INVALID_ARGUMENT"), False
                return make_response(request_id, "OK", "PONG"), False

            elif command == "INFO":
                if args:
                    return make_response(request_id, "ERROR", "INVALID_ARGUMENT"), False
                info = os.uname()
                return make_response(
                    request_id,
                    "OK",
                    "MACHINE={} RELEASE={}".format(info.machine, info.release)
                ), False

            elif command == "REBOOT":
                if args:
                    return make_response(request_id, "ERROR", "INVALID_ARGUMENT"), False
                return make_response(request_id, "OK", "REBOOTING"), True

            # 2. Device Service (DEVICE_LIST, DEVICE_INFO, DEVICE_READ, DEVICE_WRITE, STATUS, LED, HW_*)
            elif self.device_service and self.device_service.can_handle(command):
                status, payload = self.device_service.handle(command, args)
                return make_response(request_id, status, payload), False

            # 3. Application Service (APP_LIST, APP_INFO, APP_READ, APP_WRITE, AUTO, AUTO_SET, TEMP)
            elif self.app_service and self.app_service.can_handle(command):
                status, payload = self.app_service.handle(command, args)
                return make_response(request_id, status, payload), False

            # 4. FileSystem Service (FS_*)
            elif command.startswith("FS_") and self.filesystem:
                result = self.filesystem.dispatch(command, args)
                if result is None:
                    return make_response(request_id, "ERROR", "UNKNOWN_COMMAND"), False
                status, payload = result
                return make_response(request_id, status, payload), False

            return make_response(request_id, "ERROR", "UNKNOWN_COMMAND"), False

        except Exception as exc:
            return make_response(request_id, "ERROR", str(exc) or "OPERATION_FAILED"), False


def main():
    # 1. Initialize Subsystems
    hardware = HardwareManager()
    registry = DeviceRegistry()
    events = EventBus()
    transport = Transport()

    device_service = DeviceService(registry)
    app_service = AppService()
    filesystem = FileSystem()

    controller = Controller(registry=registry, events=events, update_interval_ms=100)

    # 2. Register Standard Hardware Devices
    try:
        led = LED(hardware, pin="LED", device_id="led", initial="OFF")
        registry.register(led)
    except Exception as exc:
        print("[WARN] Failed to register LED:", exc)
        led = None

    try:
        temp_sensor = TemperatureSensor(
            hardware,
            device_id="sensor.temperature",
            event_bus=events,
            deadband=0.1
        )
        registry.register(temp_sensor)
    except Exception as exc:
        print("[WARN] Failed to register TemperatureSensor:", exc)
        temp_sensor = None
        
    try:
        light_sensor = LightSensor(
            hardware,
            pin=26,
            device_id="sensor.light",
            event_bus=events,
            deadband=1.0
        )
        registry.register(light_sensor)
    except Exception as exc:
        print("[WARN] Failed to register LightSensor:", exc)
        light_sensor = None

    try:
        desk_lamp = PWMOutput(hardware, pin=15, device_id="actuator.desk_lamp", freq=1000, duty=0)
        registry.register(desk_lamp)
    except Exception as exc:
        print("[WARN] Failed to register DeskLamp:", exc)
        desk_lamp = None

    try:
        passive_buzzer = PassiveBuzzer(hardware, pin=16, device_id="actuator.buzzer.passive")
        registry.register(passive_buzzer)
    except Exception as exc:
        print("[WARN] Failed to register PassiveBuzzer:", exc)
        passive_buzzer = None

    try:
        active_buzzer = ActiveBuzzer(hardware, pin=17, device_id="actuator.buzzer.active", initial="OFF")
        registry.register(active_buzzer)
    except Exception as exc:
        print("[WARN] Failed to register ActiveBuzzer:", exc)
        active_buzzer = None

    # 3. Register Applications
    if temp_sensor is not None:
        thermal_app = ThermalButton(
            sensor=temp_sensor,
            events=events,
            threshold=45.0,
            hysteresis=1.0,
            debounce_ms=100,
            led_device=led
        )
        app_service.register_app(thermal_app)
        controller.register_app(thermal_app)

    if light_sensor is not None:
        ambient_light_app = AmbientLightController(
            sensor=light_sensor,
            events=events,
            dark_threshold=35.0,
            hysteresis=5.0,
            debounce_ms=200,
            actuator_device=desk_lamp,
            target_brightness=60.0,
        )
        app_service.register_app(ambient_light_app)
        controller.register_app(ambient_light_app)

    # 4. Build Dispatcher
    dispatcher = CommandDispatcher(device_service, app_service, filesystem)

    # 5. Main Fair Scheduling Loop
    while True:
        # Rate-limited serial input processing (at most 1 message per iteration)
        res = transport.read_line()
        if res is not None:
            line, is_overflow = res
            if is_overflow:
                transport.write(make_response("0000", "ERROR", "LINE_TOO_LONG"))
            else:
                response, do_reboot = dispatcher.dispatch(line)
                transport.write(response)
                if do_reboot:
                    time.sleep_ms(100)
                    if machine and hasattr(machine, "soft_reset"):
                        machine.soft_reset()

        # Unconditional continuous execution of periodic scheduler (prevents starvation)
        controller.tick()

        # Brief yield
        time.sleep_ms(1)


if __name__ == "__main__":
    main()
