"""
YumeCore Device Layer.
Defines the Device abstract interface and DeviceRegistry.
Completely decoupled from specific communication protocols and controllers.
"""

try:
    import ujson as json
except ImportError:
    import json


class Device:
    """
    Base class for all hardware devices and sensors.
    """
    device_id = "generic"
    device_type = "generic"
    # Dictionary describing properties: {prop_name: {"readable": bool, "writable": bool}}
    properties = {}

    def info(self):
        """Returns metadata describing the device and its capabilities."""
        return {
            "id": self.device_id,
            "type": self.device_type,
            "properties": self.properties,
        }

    def read(self, property_name):
        """Reads a property value. Subclasses must implement."""
        raise NotImplementedError("Property read not implemented")

    def write(self, property_name, value):
        """Writes a property value. Subclasses must implement for writable properties."""
        raise NotImplementedError("Property write not implemented")

    def update(self):
        """Optional periodic update called by controller (e.g. sensor sampling)."""
        pass

    def deinit(self):
        """Optional resource cleanup when device is unregistered."""
        pass


class DeviceRegistry:
    """
    Central registry for devices.
    """
    def __init__(self):
        self._devices = {}

    def register(self, device):
        if not isinstance(device, Device):
            raise TypeError("INVALID_DEVICE: Must inherit from Device")

        if not device.device_id:
            raise ValueError("INVALID_DEVICE_ID: Missing device_id")

        if device.device_id in self._devices:
            raise ValueError(
                "DEVICE_ALREADY_REGISTERED: Device {} already registered".format(
                    device.device_id
                )
            )

        self._devices[device.device_id] = device
        return device

    def unregister(self, device_id):
        device = self._devices.get(device_id)
        if device is None:
            raise ValueError("DEVICE_NOT_FOUND: {}".format(device_id))

        try:
            device.deinit()
        except Exception:
            pass

        del self._devices[device_id]
        return device

    def get(self, device_id):
        device = self._devices.get(device_id)
        if device is None:
            raise ValueError("DEVICE_NOT_FOUND: {}".format(device_id))
        return device

    def has(self, device_id):
        return device_id in self._devices

    def list(self):
        """Returns metadata of all registered devices."""
        return [dev.info() for dev in self._devices.values()]

    def all(self):
        """Returns all registered device instances."""
        return list(self._devices.values())
