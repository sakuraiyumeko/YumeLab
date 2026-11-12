
import os
import ubinascii
import json


class FileSystem:

    def __init__(self):
        self.write_state = None

    # --------------------------------------------------------
    # Path utilities
    # --------------------------------------------------------

    def normalize(self, path):
        if not path.startswith("/"):
            path = "/" + path

        parts = []

        for part in path.split("/"):
            if not part or part == ".":
                continue

            if part == "..":
                if parts:
                    parts.pop()
                continue

            parts.append(part)

        return "/" + "/".join(parts)

    def decode_path(self, value):
        path = ubinascii.a2b_base64(value).decode("utf-8")
        return self.normalize(path)

    def encode_data(self, data):
        return ubinascii.b2a_base64(data).strip().decode("ascii")

    def exists(self, path):
        try:
            os.stat(path)
            return True
        except OSError:
            return False

    def stat(self, path):
        info = os.stat(path)
        mode = info[0]

        return {
            "name": path.rsplit("/", 1)[-1] or "/",
            "type": "dir" if mode & 0x4000 else "file",
            "size": info[6]
        }

    # --------------------------------------------------------
    # Directory operations
    # --------------------------------------------------------

    def list_dir(self, path):
        entries = []

        for name in os.listdir(path):
            full_path = (
                path.rstrip("/") + "/" + name
                if path != "/"
                else "/" + name
            )

            info = self.stat(full_path)
            entries.append(info)

        entries.sort(
            key=lambda item: (
                item["type"] != "dir",
                item["name"].lower()
            )
        )

        return json.dumps(entries)

    def make_dir(self, path):
        if self.exists(path):
            raise OSError("Path already exists")

        os.mkdir(path)
        return "CREATED"

    def delete(self, path):
        info = self.stat(path)

        if info["type"] == "dir":
            raise OSError("Cannot delete directory with FS_DELETE")

        os.remove(path)
        return "DELETED"

    def rename(self, source, destination):
        if not self.exists(source):
            raise OSError("Source does not exist")

        if self.exists(destination):
            raise OSError("Destination already exists")

        os.rename(source, destination)
        return "RENAMED"

    # --------------------------------------------------------
    # File reading
    # --------------------------------------------------------

    def read_file(self, path, offset, size):
        info = self.stat(path)

        if info["type"] != "file":
            raise OSError("Not a file")

        if offset < 0 or size < 0 or size > 256:
            raise ValueError("Invalid read range")

        with open(path, "rb") as file:
            file.seek(offset)
            data = file.read(size)

        return self.encode_data(data)

    # --------------------------------------------------------
    # File writing
    # --------------------------------------------------------

    def write_begin(self, path, size):
        if self.write_state is not None:
            raise OSError("Another write is active")

        if size < 0:
            raise ValueError("Invalid file size")

        if self.exists(path):
            if self.stat(path)["type"] == "dir":
                raise OSError("Destination is a directory")

        temp_path = path + ".yume_tmp"

        if self.exists(temp_path):
            if self.stat(temp_path)["type"] == "dir":
                raise OSError("Temporary path is a directory")
            os.remove(temp_path)

        file = open(temp_path, "wb")

        self.write_state = {
            "path": path,
            "temp_path": temp_path,
            "size": size,
            "written": 0,
            "file": file
        }

        return "READY"

    def write_chunk(self, path, offset, encoded_data):
        state = self.write_state

        if state is None:
            raise OSError("No active write")

        if path != state["path"]:
            raise ValueError("Write path mismatch")

        if offset != state["written"]:
            raise ValueError("Invalid chunk offset")

        data = ubinascii.a2b_base64(encoded_data)

        if state["written"] + len(data) > state["size"]:
            raise ValueError("Chunk exceeds expected size")

        state["file"].write(data)
        state["written"] += len(data)

        return str(state["written"])

    def write_end(self, path):
        state = self.write_state

        if state is None or path != state["path"]:
            raise OSError("No matching active write")

        if state["written"] != state["size"]:
            raise ValueError("Incomplete file transfer")

        state["file"].close()

        destination = state["path"]
        temporary = state["temp_path"]

        try:
            if self.exists(destination):
                os.remove(destination)

            os.rename(temporary, destination)

        except Exception:
            self.write_state = None
            raise

        self.write_state = None

        return "WRITTEN"

    def write_abort(self, path):
        state = self.write_state

        if state is None:
            return "NO_ACTIVE_WRITE"

        if path != state["path"]:
            raise ValueError("Write path mismatch")

        state["file"].close()

        if self.exists(state["temp_path"]):
            os.remove(state["temp_path"])

        self.write_state = None

        return "ABORTED"

    # --------------------------------------------------------
    # Command dispatcher
    # --------------------------------------------------------

    def dispatch(self, command, args):

        if command == "FS_LIST":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            return "OK", self.list_dir(path)

        elif command == "FS_STAT":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            return "OK", json.dumps(self.stat(path))

        elif command == "FS_READ":
            if len(args) != 3:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            offset = int(args[1])
            size = int(args[2])

            return "OK", self.read_file(path, offset, size)

        elif command == "FS_WRITE_BEGIN":
            if len(args) != 2:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            size = int(args[1])

            return "OK", self.write_begin(path, size)

        elif command == "FS_WRITE_CHUNK":
            if len(args) != 3:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            offset = int(args[1])

            return "OK", self.write_chunk(
                path,
                offset,
                args[2]
            )

        elif command == "FS_WRITE_END":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            return "OK", self.write_end(path)

        elif command == "FS_WRITE_ABORT":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            return "OK", self.write_abort(path)

        elif command == "FS_MKDIR":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            return "OK", self.make_dir(path)

        elif command == "FS_DELETE":
            if len(args) != 1:
                raise ValueError("INVALID_ARGUMENT")

            path = self.decode_path(args[0])
            return "OK", self.delete(path)

        elif command == "FS_RENAME":
            if len(args) != 2:
                raise ValueError("INVALID_ARGUMENT")

            source = self.decode_path(args[0])
            destination = self.decode_path(args[1])

            return "OK", self.rename(source, destination)

        return None
