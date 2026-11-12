"""
YumeCore Controller & Runtime.
Responsible for task scheduling, periodic device updates,
and application lifecycle management.
Does NOT directly depend on hardware pins or communication protocols.
"""

try:
    import time
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
except AttributeError:
    import time
    ticks_ms = lambda: int(time.monotonic() * 1000)
    ticks_diff = lambda a, b: a - b


class Controller:
    def __init__(self, registry=None, events=None, update_interval_ms=1000):
        self.registry = registry
        self.events = events
        self.update_interval_ms = update_interval_ms

        self.running = True
        self._tasks = {}  # name -> {"callback": cb, "interval_ms": int, "last_run": int}
        self._apps = []
        self._last_device_update = None
        self.last_error = None
        self.error_count = 0

    def register_task(self, name, callback, interval_ms):
        if not callable(callback):
            raise TypeError("Task callback must be callable")
        self._tasks[name] = {
            "callback": callback,
            "interval_ms": max(1, int(interval_ms)),
            "last_run": None,
        }

    def unregister_task(self, name):
        if name in self._tasks:
            del self._tasks[name]

    def register_app(self, app):
        if app not in self._apps:
            self._apps.append(app)

    def unregister_app(self, app):
        if app in self._apps:
            self._apps.remove(app)

    def tick(self):
        """
        Runs one iteration of non-blocking scheduling:
        - Periodic device updates
        - Registered applications updates
        - Custom periodic tasks
        """
        if not self.running:
            return False

        now = ticks_ms()
        activity = False

        # 1. Periodic device updates
        if self.registry is not None:
            if self._last_device_update is None or ticks_diff(now, self._last_device_update) >= self.update_interval_ms:
                self._last_device_update = now
                activity = True
                for dev in self.registry.all():
                    try:
                        dev.update()
                    except Exception as exc:
                        self.last_error = str(exc)
                        self.error_count += 1

        # 2. Application updates (e.g. debounce servicing)
        for app in self._apps:
            if hasattr(app, "update") and callable(app.update):
                try:
                    app.update()
                except Exception as exc:
                    self.last_error = str(exc)
                    self.error_count += 1

        # 3. Scheduled custom tasks
        for name, task in list(self._tasks.items()):
            last_run = task["last_run"]
            if last_run is None or ticks_diff(now, last_run) >= task["interval_ms"]:
                task["last_run"] = now
                activity = True
                try:
                    task["callback"]()
                except Exception as exc:
                    self.last_error = str(exc)
                    self.error_count += 1

        return activity

    def stop(self):
        self.running = False

    def start(self):
        self.running = True
