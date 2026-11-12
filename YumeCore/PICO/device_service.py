"""
YumeCore Device Service.
Handles DEVICE_LIST, DEVICE_INFO, DEVICE_READ, DEVICE_WRITE protocol commands.
Provides backward-compatible support for legacy STATUS, LED, and HW_* commands.
Completely decouples protocol request handling from Controller and Device implementations.
"""

try:
    import ujson as json
except ImportError:
    import json


class DeviceService:
    HANDLED_COMMANDS = (
        "DEVICE_LIST",
        "DEVICE_INFO",
        "DEVICE_READ",
        "DEVICE_WRITE",
        "STATUS",
        "LED",
        "HW_LIST",
        "HW_GET",
        "HW_SET",
    )

    def __init__(self, registry):
        self.registry = registry

    def can_handle(self, command):
        return command in self.HANDLED_COMMANDS

    def handle(self, command, args):
        """
        Dispatches a device-related command.
        Returns: (status, payload_string)
        """
        try:
            # 1. Generic Device Commands
            if command == "DEVICE_LIST":
                if args:
                    return "ERROR", "INVALID_ARGUMENT"
                return "OK", json.dumps(self.registry.list())

            elif command == "DEVICE_INFO":
                if len(args) != 1:
                    return "ERROR", "INVALID_ARGUMENT"
                device = self.registry.get(args[0])
                return "OK", json.dumps(device.info())

            elif command == "DEVICE_READ":
                if len(args) != 2:
                    return "ERROR", "INVALID_ARGUMENT"
                device_id, prop = args[0], args[1]
                device = self.registry.get(device_id)
                val = device.read(prop)
                return "OK", json.dumps({
                    "device": device_id,
                    "property": prop,
                    "value": val,
                })

            elif command == "DEVICE_WRITE":
                if len(args) < 3:
                    return "ERROR", "INVALID_ARGUMENT"
                device_id, prop = args[0], args[1]
                val = " ".join(args[2:])
                device = self.registry.get(device_id)
                new_val = device.write(prop, val)
                return "OK", json.dumps({
                    "device": device_id,
                    "property": prop,
                    "value": new_val,
                })

            # 2. Backward compatibility aliases
            elif command == "STATUS":
                if args:
                    return "ERROR", "INVALID_ARGUMENT"
                led_state = "UNKNOWN"
                if self.registry.has("led"):
                    led_state = self.registry.get("led").read("state")
                return "OK", "LED={}".format(led_state)

            elif command == "LED":
                if len(args) != 1:
                    return "ERROR", "INVALID_ARGUMENT"
                if not self.registry.has("led"):
                    return "ERROR", "DEVICE_NOT_FOUND"
                state = self.registry.get("led").write("state", args[0])
                return "OK", "LED={}".format(state)

            elif command == "HW_LIST":
                if args:
                    return "ERROR", "INVALID_ARGUMENT"
                # Legacy HW_LIST returned name, type, writable
                devices = []
                for dev in self.registry.all():
                    has_writable = any(p.get("writable", False) for p in dev.properties.values())
                    devices.append({
                        "name": dev.device_id,
                        "type": dev.device_type,
                        "writable": has_writable,
                    })
                return "OK", json.dumps(devices)

            elif command == "HW_GET":
                if len(args) != 1:
                    return "ERROR", "INVALID_ARGUMENT"
                device = self.registry.get(args[0])
                # Default property to read
                prop = "state" if "state" in device.properties else list(device.properties.keys())[0]
                val = device.read(prop)
                # If reading digital state, return 1/0 for backward compatibility
                if prop == "state":
                    val = 1 if str(val).upper() == "ON" else 0
                return "OK", json.dumps({
                    "name": device.device_id,
                    "value": val,
                })

            elif command == "HW_SET":
                if len(args) != 2:
                    return "ERROR", "INVALID_ARGUMENT"
                device = self.registry.get(args[0])
                prop = "state" if "state" in device.properties else list(device.properties.keys())[0]
                val = device.write(prop, args[1])
                if prop == "state":
                    val = 1 if str(val).upper() == "ON" else 0
                return "OK", json.dumps({
                    "name": device.device_id,
                    "value": val,
                })

        except ValueError as exc:
            err_msg = str(exc)
            if ":" in err_msg:
                err_msg = err_msg.split(":", 1)[0].strip()
            return "ERROR", err_msg or "VALUE_ERROR"
        except Exception as exc:
            return "ERROR", str(exc) or "OPERATION_FAILED"

        return "ERROR", "UNKNOWN_COMMAND"
