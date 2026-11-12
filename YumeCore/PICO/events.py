"""
YumeCore Event System.
Provides a lightweight in-process publish/subscribe event bus.
Decoupled from communication protocols, hardware, and transports.
Guarantees subscriber exception isolation so that one faulty handler
never disrupts the rest of the event pipeline.
"""


class EventBus:
    def __init__(self):
        # Maps event_name (str) -> list of callback callables
        self._subscribers = {}

    def subscribe(self, event_name, callback):
        """
        Subscribes a callback to an event.
        callback signature: callback(data: dict)
        """
        if not callable(callback):
            raise TypeError("Subscriber must be callable")

        if event_name not in self._subscribers:
            self._subscribers[event_name] = []

        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        """
        Unsubscribes a callback from an event.
        """
        if event_name in self._subscribers:
            if callback in self._subscribers[event_name]:
                self._subscribers[event_name].remove(callback)
            if not self._subscribers[event_name]:
                del self._subscribers[event_name]

    def publish(self, event_name, data=None):
        """
        Publishes an event to all registered subscribers.
        Isolates subscriber exceptions to prevent halting the system.
        Returns the number of subscribers that were successfully invoked.
        """
        if event_name not in self._subscribers:
            return 0

        if data is None:
            data = {}

        success_count = 0
        # Iterate over a copy of the list in case a subscriber unsubscribes itself during callback
        for callback in list(self._subscribers[event_name]):
            try:
                callback(data)
                success_count += 1
            except Exception as exc:
                # In MicroPython we avoid logging bloat, but isolate the failure
                # Optionally print or store last error if needed
                pass

        return success_count

    def has_subscribers(self, event_name):
        return event_name in self._subscribers and len(self._subscribers[event_name]) > 0

    def clear(self):
        self._subscribers.clear()
