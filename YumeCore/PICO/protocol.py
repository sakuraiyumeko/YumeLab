
PROTOCOL_VERSION = "0.3"

ID_LENGTH = 4

COMMANDS = {
    "PING", "INFO", "STATUS", "LED", "REBOOT", "UPTIME",

    "HW_LIST", "HW_GET", "HW_SET",
    "TEMP", "AUTO", "AUTO_SET",

    "FS_LIST", "FS_STAT", "FS_READ",
    "FS_WRITE_BEGIN", "FS_WRITE_CHUNK",
    "FS_WRITE_END", "FS_WRITE_ABORT",
    "FS_MKDIR", "FS_DELETE", "FS_RENAME",
}


def valid_id(request_id):
    return (
        isinstance(request_id, str)
        and len(request_id) == ID_LENGTH
        and request_id.isdigit()
    )


def make_request(request_id, command, *args):
    if not valid_id(request_id):
        raise ValueError("Invalid request ID")

    command = command.upper()

    if command not in COMMANDS:
        raise ValueError("Unknown command")

    parts = [request_id, command]
    parts.extend(str(arg) for arg in args)

    return " ".join(parts) + "\n"


def parse_request(message):
    parts = message.strip().split()

    if not parts:
        return None, None, [], "EMPTY_REQUEST"

    request_id = parts[0]

    if not valid_id(request_id):
        return None, None, [], "INVALID_ID"

    if len(parts) < 2:
        return request_id, None, [], "INVALID_COMMAND"

    command = parts[1].upper()
    args = parts[2:]

    if command not in COMMANDS:
        return request_id, command, args, "UNKNOWN_COMMAND"

    return request_id, command, args, None


def make_response(request_id, status, payload=""):
    if not valid_id(request_id):
        raise ValueError("Invalid response ID")

    status = status.upper()

    if status not in ("OK", "ERROR"):
        raise ValueError("Invalid response status")

    parts = [request_id, status]

    if payload:
        parts.append(str(payload))

    return " ".join(parts) + "\n"


def parse_response(message):
    parts = message.strip().split(" ", 2)

    if len(parts) < 2:
        raise ValueError("Malformed response")

    request_id, status = parts[:2]

    if not valid_id(request_id):
        raise ValueError("Invalid response ID")

    if status not in ("OK", "ERROR"):
        raise ValueError("Invalid response status")

    payload = parts[2] if len(parts) == 3 else ""

    return request_id, status, payload
