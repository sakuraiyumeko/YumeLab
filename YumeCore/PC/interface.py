import os
import json
import base64
import shlex
import posixpath

from host import YumeCore


# ============================================================
# Configuration
# ============================================================

PORT = "COM7"
CHUNK_SIZE = 96


# ============================================================
# CLI Command Definitions
# ============================================================

COMMANDS = {
    "help": {
        "usage": "help",
        "description": "Show available commands"
    },
    "ls": {
        "usage": "ls [path]",
        "description": "List directory contents"
    },
    "cd": {
        "usage": "cd <path>",
        "description": "Change remote directory"
    },
    "pwd": {
        "usage": "pwd",
        "description": "Show current remote directory"
    },
    "cat": {
        "usage": "cat <file>",
        "description": "Display a remote text file"
    },
    "put": {
        "usage": "put <local> [remote]",
        "description": "Upload a local file"
    },
    "get": {
        "usage": "get <remote> [local]",
        "description": "Download a remote file"
    },
    "mkdir": {
        "usage": "mkdir <path>",
        "description": "Create a directory"
    },
    "rm": {
        "usage": "rm <path>",
        "description": "Delete a file"
    },
    "mv": {
        "usage": "mv <source> <destination>",
        "description": "Rename or move a file"
    },
    "reboot": {
        "usage": "reboot",
        "description": "Reboot the Pico and disconnect"
    },
    "exit": {
        "usage": "exit",
        "description": "Disconnect"
    },
    "send": {
        "usage": "send <command> [args...]",
        "description": "Send a raw protocol command to Pico"
    },
}


# ============================================================
# Pico Filesystem Interface
# ============================================================

class PicoInterface:

    def __init__(self, port):
        self.core = YumeCore(port)
        self.cwd = "/"

    # --------------------------------------------------------
    # Basic utilities
    # --------------------------------------------------------

    @staticmethod
    def encode(value):
        return base64.b64encode(
            value.encode("utf-8")
        ).decode("ascii")

    @staticmethod
    def decode(value):
        return base64.b64decode(value)

    def remote_path(self, path):
        if path.startswith("/"):
            return posixpath.normpath(path)

        return posixpath.normpath(
            posixpath.join(self.cwd, path)
        )

    def request(self, command, *args):
        return self.core._send(command, *args)

    # --------------------------------------------------------
    # Filesystem operations
    # --------------------------------------------------------

    def list_dir(self, path="."):
        path = self.remote_path(path)

        result = self.request(
            "FS_LIST",
            self.encode(path)
        )

        return json.loads(result)

    def read_file(self, path):
        path = self.remote_path(path)

        info = json.loads(
            self.request("FS_STAT", self.encode(path))
        )

        size = info["size"]
        data = bytearray()

        for offset in range(0, size, CHUNK_SIZE):
            chunk_size = min(CHUNK_SIZE, size - offset)

            result = self.request(
                "FS_READ",
                self.encode(path),
                offset,
                chunk_size
            )

            data.extend(self.decode(result))

        return bytes(data)

    def write_file(self, local_path, remote_path):
        with open(local_path, "rb") as file:
            data = file.read()

        remote_path = self.remote_path(remote_path)
        encoded_path = self.encode(remote_path)

        self.request(
            "FS_WRITE_BEGIN",
            encoded_path,
            len(data)
        )

        try:
            for offset in range(0, len(data), CHUNK_SIZE):
                chunk = data[offset:offset + CHUNK_SIZE]

                self.request(
                    "FS_WRITE_CHUNK",
                    encoded_path,
                    offset,
                    base64.b64encode(chunk).decode("ascii")
                )

            self.request(
                "FS_WRITE_END",
                encoded_path
            )

        except Exception:
            try:
                self.request("FS_WRITE_ABORT", encoded_path)
            except Exception:
                pass
            raise

    def mkdir(self, path):
        self.request(
            "FS_MKDIR",
            self.encode(self.remote_path(path))
        )

    def remove(self, path):
        self.request(
            "FS_DELETE",
            self.encode(self.remote_path(path))
        )

    def rename(self, source, destination):
        self.request(
            "FS_RENAME",
            self.encode(self.remote_path(source)),
            self.encode(self.remote_path(destination))
        )

    # --------------------------------------------------------
    # CLI commands
    # --------------------------------------------------------

    def cmd_help(self, args):
        for name, info in COMMANDS.items():
            print("{:<8} {:<25} {}".format(
                name,
                info["usage"],
                info["description"]
            ))

    def cmd_ls(self, args):
        path = args[0] if args else "."

        entries = self.list_dir(path)

        for entry in entries:
            name = entry["name"]
            kind = entry["type"]

            if kind == "dir":
                print("[DIR]  " + name)
            else:
                print("{:>8}  {}".format(
                    entry.get("size", 0),
                    name
                ))

    def cmd_cd(self, args):
        if not args:
            print("Usage:", COMMANDS["cd"]["usage"])
            return

        target = self.remote_path(args[0])

        # Verify that the target exists and is a directory.
        info = json.loads(
            self.request("FS_STAT", self.encode(target))
        )

        if info["type"] != "dir":
            print("Not a directory:", target)
            return

        self.cwd = target

    def cmd_pwd(self, args):
        print(self.cwd)

    def cmd_cat(self, args):
        if not args:
            print("Usage:", COMMANDS["cat"]["usage"])
            return

        data = self.read_file(args[0])
        print(data.decode("utf-8", errors="replace"))

    def cmd_put(self, args):
        if not args:
            print("Usage:", COMMANDS["put"]["usage"])
            return

        local = args[0]
        remote = args[1] if len(args) > 1 else os.path.basename(local)

        self.write_file(local, remote)
        print("Uploaded:", remote)

    def cmd_get(self, args):
        if not args:
            print("Usage:", COMMANDS["get"]["usage"])
            return

        remote = args[0]
        local = args[1] if len(args) > 1 else os.path.basename(remote)

        data = self.read_file(remote)

        with open(local, "wb") as file:
            file.write(data)

        print("Downloaded:", local)

    def cmd_mkdir(self, args):
        if not args:
            print("Usage:", COMMANDS["mkdir"]["usage"])
            return

        self.mkdir(args[0])
        print("Directory created.")

    def cmd_rm(self, args):
        if not args:
            print("Usage:", COMMANDS["rm"]["usage"])
            return

        self.remove(args[0])
        print("Deleted.")

    def cmd_mv(self, args):
        if len(args) != 2:
            print("Usage:", COMMANDS["mv"]["usage"])
            return

        self.rename(args[0], args[1])
        print("Moved.")
        
    def cmd_reboot(self, args):
        self.core.reboot()
        print("Rebooting Pico...")
        return "exit"

    def cmd_send(self, args):
        if not args:
            print("Usage:", COMMANDS["send"]["usage"])
            return

        result = self.request(*args)
        print(result)

    # --------------------------------------------------------
    # Main CLI loop
    # --------------------------------------------------------

    def run(self):
        print("YumeCore Pico Filesystem Interface")
        print("Type 'help' for commands.\n")

        handlers = {
            "help": self.cmd_help,
            "ls": self.cmd_ls,
            "cd": self.cmd_cd,
            "pwd": self.cmd_pwd,
            "cat": self.cmd_cat,
            "put": self.cmd_put,
            "get": self.cmd_get,
            "mkdir": self.cmd_mkdir,
            "rm": self.cmd_rm,
            "mv": self.cmd_mv,
            "reboot": self.cmd_reboot,
            "send": self.cmd_send,
        }

        try:
            while True:
                try:
                    command_line = input(
                        "Pico:{} $ ".format(self.cwd)
                    )

                    if not command_line.strip():
                        continue

                    parts = shlex.split(command_line)
                    command = parts[0].lower()
                    args = parts[1:]

                    if command == "exit":
                        break

                    if command not in COMMANDS:
                        print("Unknown command:", command)
                        continue

                    if handlers[command](args) == "exit":
                        break

                except (ValueError, RuntimeError, OSError) as exc:
                    print("Error:", exc)

        finally:
            self.core.close()
            print("Disconnected.")


if __name__ == "__main__":
    PicoInterface(PORT).run()
