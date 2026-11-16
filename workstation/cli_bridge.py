"""
YumeLab Web CLI Bridge.
Wraps PicoInterface commands to execute directly through WorkstationHub
without opening a separate serial port or conflicting with background polling.
"""

import base64
import json
import os
import posixpath
import shlex
from typing import Any, Dict, List, Optional

from workstation.hub import WorkstationHub

CHUNK_SIZE = 96


class WebCLIBridge:
    """
    Executes full YumeCore PC interface.py CLI commands (ls, cat, put, get,
    mkdir, rm, mv, devices, device, apps, app, ping, info, send, reboot)
    reusing the active WorkstationHub connection inside hub._io_lock to guarantee
    exclusive, collision-free serial request/response framing against background polling.
    """

    def __init__(self, hub: WorkstationHub):
        self.hub = hub
        self.cwd = "/"

    @staticmethod
    def encode(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    @staticmethod
    def decode(value: str) -> bytes:
        return base64.b64decode(value)

    def remote_path(self, path: str) -> str:
        if path.startswith("/"):
            return posixpath.normpath(path)
        return posixpath.normpath(posixpath.join(self.cwd, path))

    def request(self, command: str, *args: Any) -> str:
        with self.hub._io_lock:
            if self.hub.core is None:
                raise RuntimeError("Hardware node is not connected.")
            return self.hub.core.send_request(command, *args)

    def execute_line(self, line: str) -> Dict[str, Any]:
        raw = line.strip()
        if not raw:
            return {"ok": True, "output": "", "cwd": self.cwd}

        parts = shlex.split(raw)
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "help":
                output = (
                    "Available YumeCore CLI Commands:\n"
                    "  help                        Show this command manual\n"
                    "  ping                        Test connection to Pico\n"
                    "  info                        Show Pico system information\n"
                    "  devices                     List all registered devices\n"
                    "  device info <id>            Inspect device properties\n"
                    "  device read <id> <prop>     Read device property\n"
                    "  device write <id> <p> <v>   Write device property\n"
                    "  apps                        List registered applications\n"
                    "  app info <name>             Inspect application properties\n"
                    "  app read <name> <prop>      Read application property\n"
                    "  app write <name> <p> <v>    Write application property\n"
                    "  auto <on|off|set <temp>>    Quick thermal auto control\n"
                    "  piano <ls|play <name>|pause|resume|stop>  Buzzer sheet player\n"
                    "  ls [path]                   List remote directory\n"
                    "  cd <path>                   Change remote directory\n"
                    "  pwd                         Show current remote directory\n"
                    "  cat <file>                  Display a remote text file\n"
                    "  put <local> [remote]        Upload a local file to Pico\n"
                    "  get <remote> [local]        Download a remote file from Pico\n"
                    "  mkdir <path>                Create a remote directory\n"
                    "  rm <path>                   Delete a remote file\n"
                    "  mv <src> <dst>              Rename or move a remote file\n"
                    "  reboot                      Reboot Pico (software reset)\n"
                    "  send <cmd> [args...]        Send raw protocol frame\n"
                    "  clear                       Clear terminal output\n"
                    "\nTip: You can also type natural language commands directly!"
                )
                return {"ok": True, "output": output, "cwd": self.cwd}

            elif cmd == "pwd":
                return {"ok": True, "output": self.cwd, "cwd": self.cwd}

            elif cmd == "ping":
                with self.hub._io_lock:
                    ok = self.hub.core.ping() if self.hub.core else False
                return {"ok": True, "output": "PONG" if ok else "PING failed", "cwd": self.cwd}

            elif cmd == "info":
                with self.hub._io_lock:
                    info = self.hub.core.info() if self.hub.core else "Not connected"
                return {"ok": True, "output": info, "cwd": self.cwd}

            elif cmd == "devices":
                with self.hub._io_lock:
                    devs = self.hub.core.devices.list()
                lines = [f"{'DEVICE ID':<24} {'TYPE':<20} PROPERTIES", "-" * 68]
                for dev in devs:
                    props = ", ".join(dev.get("properties", {}).keys())
                    lines.append(f"{dev['id']:<24} {dev['type']:<20} {props}")
                return {"ok": True, "output": "\n".join(lines), "cwd": self.cwd}

            elif cmd == "device":
                if not args:
                    return {"ok": False, "output": "Usage: device <info|read|write> <id> [prop] [val]", "cwd": self.cwd}
                action = args[0].lower()
                if action == "info":
                    if len(args) != 2:
                        return {"ok": False, "output": "Usage: device info <device_id>", "cwd": self.cwd}
                    with self.hub._io_lock:
                        data = self.hub.core.devices.info(args[1])
                    return {"ok": True, "output": json.dumps(data, indent=2), "cwd": self.cwd}
                elif action == "read":
                    if len(args) != 3:
                        return {"ok": False, "output": "Usage: device read <device_id> <property>", "cwd": self.cwd}
                    with self.hub._io_lock:
                        val = self.hub.core.devices.read(args[1], args[2])
                    return {"ok": True, "output": f"{args[1]}.{args[2]} = {val}", "cwd": self.cwd}
                elif action == "write":
                    if len(args) < 4:
                        return {"ok": False, "output": "Usage: device write <device_id> <property> <value>", "cwd": self.cwd}
                    val = " ".join(args[3:])
                    res = self.hub.write_device(args[1], args[2], val)
                    return {"ok": True, "output": f"{args[1]}.{args[2]} -> {res.get('value')}", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                return {"ok": False, "output": f"Unknown device action: {action}", "cwd": self.cwd}

            elif cmd == "apps":
                with self.hub._io_lock:
                    apps = self.hub.core.apps.list()
                lines = [f"{'APP NAME':<16} {'DESCRIPTION':<32} PROPERTIES", "-" * 75]
                for app in apps:
                    props = ", ".join(app.get("properties", {}).keys())
                    lines.append(f"{app['name']:<16} {app.get('description', '')[:30]:<32} {props}")
                return {"ok": True, "output": "\n".join(lines), "cwd": self.cwd}

            elif cmd == "app":
                if not args:
                    return {"ok": False, "output": "Usage: app <info|read|write> <name> [prop] [val]", "cwd": self.cwd}
                action = args[0].lower()
                if action == "info":
                    if len(args) != 2:
                        return {"ok": False, "output": "Usage: app info <app_name>", "cwd": self.cwd}
                    with self.hub._io_lock:
                        data = self.hub.core.apps.info(args[1])
                    return {"ok": True, "output": json.dumps(data, indent=2), "cwd": self.cwd}
                elif action == "read":
                    if len(args) != 3:
                        return {"ok": False, "output": "Usage: app read <app_name> <property>", "cwd": self.cwd}
                    with self.hub._io_lock:
                        val = self.hub.core.apps.read(args[1], args[2])
                    return {"ok": True, "output": f"{args[1]}.{args[2]} = {val}", "cwd": self.cwd}
                elif action == "write":
                    if len(args) < 4:
                        return {"ok": False, "output": "Usage: app write <app_name> <property> <value>", "cwd": self.cwd}
                    val = " ".join(args[3:])
                    res = self.hub.write_app(args[1], args[2], val)
                    return {"ok": True, "output": f"{args[1]}.{args[2]} -> {res.get('value')}", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                return {"ok": False, "output": f"Unknown app action: {action}", "cwd": self.cwd}

            elif cmd == "auto":
                if not args:
                    return {"ok": False, "output": "Usage: auto <on|off|set <threshold>>", "cwd": self.cwd}
                subcmd = args[0].lower()
                if subcmd == "on":
                    res = self.hub.write_app("thermal", "enabled", True)
                    return {"ok": True, "output": "Thermal auto mode: ON", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                elif subcmd == "off":
                    res = self.hub.write_app("thermal", "enabled", False)
                    return {"ok": True, "output": "Thermal auto mode: OFF", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                elif subcmd == "set":
                    if len(args) != 2:
                        return {"ok": False, "output": "Usage: auto set <threshold>", "cwd": self.cwd}
                    thresh = float(args[1])
                    res = self.hub.write_app("thermal", "threshold", thresh)
                    return {"ok": True, "output": f"Thermal threshold set to: {thresh}°C", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                return {"ok": False, "output": f"Unknown auto action: {subcmd}", "cwd": self.cwd}

            elif cmd == "piano":
                if not args:
                    st = self.hub.get_piano_status()
                    return {"ok": True, "output": json.dumps(st, ensure_ascii=False, indent=2), "cwd": self.cwd}
                sub = args[0].lower()
                if sub in ("ls", "list"):
                    sheets = self.hub.get_piano_sheets()
                    if not sheets:
                        return {"ok": True, "output": "(no sheets found)", "cwd": self.cwd}
                    lines = [f"{i}. {s['id']} — {s['title']} (BPM={s['bpm']}, {s['notes']} notes)" for i, s in enumerate(sheets, 1)]
                    return {"ok": True, "output": "\n".join(lines), "cwd": self.cwd}
                elif sub == "play":
                    if len(args) < 2:
                        return {"ok": False, "output": "Usage: piano play <index|name>", "cwd": self.cwd}
                    res = self.hub.play_piano_sheet(" ".join(args[1:]))
                    p = res["player"]
                    return {"ok": True, "output": f"Playing: {p.get('title')} (BPM={p.get('bpm')})", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                elif sub == "pause":
                    res = self.hub.pause_piano()
                    return {"ok": True, "output": f"Player state: {res['player'].get('state')}", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                elif sub == "resume":
                    res = self.hub.resume_piano()
                    return {"ok": True, "output": f"Player state: {res['player'].get('state')}", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                elif sub == "stop":
                    res = self.hub.stop_piano()
                    return {"ok": True, "output": f"Player state: {res['player'].get('state')}", "cwd": self.cwd, "snapshot": res.get("snapshot")}
                return {"ok": False, "output": "Usage: piano <ls|play <name>|pause|resume|stop>", "cwd": self.cwd}

            # Remote Filesystem Operations
            elif cmd == "ls":
                target = self.remote_path(args[0] if args else ".")
                res = self.request("FS_LIST", self.encode(target))
                entries = json.loads(res)
                lines = []
                for entry in entries:
                    if entry.get("type") == "dir":
                        lines.append(f"[DIR]  {entry['name']}")
                    else:
                        lines.append(f"{entry.get('size', 0):>8}  {entry['name']}")
                return {"ok": True, "output": "\n".join(lines) if lines else "(empty directory)", "cwd": self.cwd}

            elif cmd == "cd":
                if not args:
                    return {"ok": False, "output": "Usage: cd <path>", "cwd": self.cwd}
                target = self.remote_path(args[0])
                stat = json.loads(self.request("FS_STAT", self.encode(target)))
                if stat.get("type") != "dir":
                    return {"ok": False, "output": f"Not a directory: {target}", "cwd": self.cwd}
                self.cwd = target
                return {"ok": True, "output": f"Directory changed to: {self.cwd}", "cwd": self.cwd}

            elif cmd == "cat":
                if not args:
                    return {"ok": False, "output": "Usage: cat <file>", "cwd": self.cwd}
                target = self.remote_path(args[0])
                info = json.loads(self.request("FS_STAT", self.encode(target)))
                size = info["size"]
                buf = bytearray()
                for offset in range(0, size, CHUNK_SIZE):
                    chunk_size = min(CHUNK_SIZE, size - offset)
                    chunk_res = self.request("FS_READ", self.encode(target), offset, chunk_size)
                    buf.extend(self.decode(chunk_res))
                return {"ok": True, "output": bytes(buf).decode("utf-8", errors="replace"), "cwd": self.cwd}

            elif cmd == "mkdir":
                if not args:
                    return {"ok": False, "output": "Usage: mkdir <path>", "cwd": self.cwd}
                self.request("FS_MKDIR", self.encode(self.remote_path(args[0])))
                return {"ok": True, "output": "Directory created.", "cwd": self.cwd}

            elif cmd == "rm":
                if not args:
                    return {"ok": False, "output": "Usage: rm <path>", "cwd": self.cwd}
                self.request("FS_DELETE", self.encode(self.remote_path(args[0])))
                return {"ok": True, "output": "Deleted.", "cwd": self.cwd}

            elif cmd == "mv":
                if len(args) != 2:
                    return {"ok": False, "output": "Usage: mv <source> <destination>", "cwd": self.cwd}
                self.request("FS_RENAME", self.encode(self.remote_path(args[0])), self.encode(self.remote_path(args[1])))
                return {"ok": True, "output": "Moved.", "cwd": self.cwd}

            elif cmd == "reboot":
                with self.hub._io_lock:
                    if self.hub.core:
                        self.hub.core.reboot()
                return {"ok": True, "output": "Reboot command sent to Pico.", "cwd": self.cwd}

            elif cmd == "send":
                if not args:
                    return {"ok": False, "output": "Usage: send <command> [args...]", "cwd": self.cwd}
                res = self.request(*args)
                return {"ok": True, "output": res, "cwd": self.cwd}

            # Fallback to WorkstationCommander Natural Language
            from workstation.commander import WorkstationCommander
            commander = WorkstationCommander(self.hub)
            nl_res = commander.interpret_and_execute(raw)
            return {"ok": nl_res.get("ok", True), "output": nl_res.get("reply", ""), "cwd": self.cwd, "snapshot": nl_res.get("snapshot")}

        except Exception as exc:
            return {"ok": False, "output": f"Error: {exc}", "cwd": self.cwd}
