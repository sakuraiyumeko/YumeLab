"""
YumeCore Application Service.
Handles APP_LIST, APP_INFO, APP_READ, APP_WRITE protocol commands.
Provides backward-compatible support for legacy AUTO, AUTO_SET, and TEMP commands.
Completely decouples protocol request handling from Controller and Application implementations.
"""

try:
    import ujson as json
except ImportError:
    import json


class AppService:
    HANDLED_COMMANDS = (
        "APP_LIST",
        "APP_INFO",
        "APP_READ",
        "APP_WRITE",
        "AUTO",
        "AUTO_SET",
        "TEMP",
    )

    def __init__(self):
        self._apps = {}

    def register_app(self, app):
        if not hasattr(app, "name") or not app.name:
            raise ValueError("INVALID_APP: App must have a non-empty 'name'")
        self._apps[app.name] = app
        return app

    def unregister_app(self, app_name):
        if app_name in self._apps:
            app = self._apps[app_name]
            if hasattr(app, "deinit"):
                try:
                    app.deinit()
                except Exception:
                    pass
            del self._apps[app_name]

    def get_app(self, app_name):
        app = self._apps.get(app_name)
        if app is None:
            raise ValueError("APP_NOT_FOUND: {}".format(app_name))
        return app

    def has_app(self, app_name):
        return app_name in self._apps

    def list_apps(self):
        return [app.info() for app in self._apps.values()]

    def can_handle(self, command):
        return command in self.HANDLED_COMMANDS

    def handle(self, command, args):
        """
        Dispatches application-related commands.
        Returns: (status, payload_string)
        """
        try:
            # 1. Generic App Commands
            if command == "APP_LIST":
                if args:
                    return "ERROR", "INVALID_ARGUMENT"
                return "OK", json.dumps(self.list_apps())

            elif command == "APP_INFO":
                if len(args) != 1:
                    return "ERROR", "INVALID_ARGUMENT"
                app = self.get_app(args[0])
                return "OK", json.dumps(app.info())

            elif command == "APP_READ":
                if len(args) != 2:
                    return "ERROR", "INVALID_ARGUMENT"
                app_name, prop = args[0], args[1]
                app = self.get_app(app_name)
                val = app.read(prop)
                return "OK", json.dumps({
                    "app": app_name,
                    "property": prop,
                    "value": val,
                })

            elif command == "APP_WRITE":
                if len(args) < 3:
                    return "ERROR", "INVALID_ARGUMENT"
                app_name, prop = args[0], args[1]
                val = " ".join(args[2:])
                app = self.get_app(app_name)
                new_val = app.write(prop, val)
                return "OK", json.dumps({
                    "app": app_name,
                    "property": prop,
                    "value": new_val,
                })

            # 2. Backward compatibility aliases
            elif command == "TEMP":
                if args:
                    return "ERROR", "INVALID_ARGUMENT"
                if self.has_app("thermal"):
                    temp = self.get_app("thermal").read("last_temp")
                    if temp is not None:
                        return "OK", "TEMP={:.1f}C".format(temp)
                return "OK", "TEMP=UNAVAILABLE"

            elif command == "AUTO":
                if len(args) != 1:
                    return "ERROR", "INVALID_ARGUMENT"
                state = args[0].upper()
                if state not in ("ON", "OFF"):
                    return "ERROR", "INVALID_AUTO_STATE"
                if not self.has_app("thermal"):
                    return "ERROR", "APP_NOT_FOUND"
                self.get_app("thermal").write("enabled", state == "ON")
                return "OK", "AUTO={}".format(state)

            elif command == "AUTO_SET":
                if len(args) != 1:
                    return "ERROR", "INVALID_ARGUMENT"
                if not self.has_app("thermal"):
                    return "ERROR", "APP_NOT_FOUND"
                thresh = float(args[0])
                self.get_app("thermal").write("threshold", thresh)
                return "OK", "THRESHOLD={:.1f}C".format(thresh)

        except ValueError as exc:
            err_msg = str(exc)
            if ":" in err_msg:
                err_msg = err_msg.split(":", 1)[0].strip()
            return "ERROR", err_msg or "VALUE_ERROR"
        except Exception as exc:
            return "ERROR", str(exc) or "OPERATION_FAILED"

        return "ERROR", "UNKNOWN_COMMAND"
