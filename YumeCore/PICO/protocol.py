"""
YumeCore Protocol Layer.
Handles message framing, request/response encoding and decoding.
Decoupled from specific commands and devices.
"""

PROTOCOL_VERSION = "1.0"
ID_LENGTH = 4

# Standard command constants (for reference/convenience, not used as a whitelist)
CMD_PING = "PING"
CMD_INFO = "INFO"
CMD_REBOOT = "REBOOT"

# Generic Device commands
CMD_DEVICE_LIST = "DEVICE_LIST"
CMD_DEVICE_INFO = "DEVICE_INFO"
CMD_DEVICE_READ = "DEVICE_READ"
CMD_DEVICE_WRITE = "DEVICE_WRITE"

# Generic Application commands
CMD_APP_LIST = "APP_LIST"
CMD_APP_INFO = "APP_INFO"
CMD_APP_READ = "APP_READ"
CMD_APP_WRITE = "APP_WRITE"


def valid_id(request_id):
    """Validates that a request ID is a 4-digit string."""
    return (
        isinstance(request_id, str)
        and len(request_id) == ID_LENGTH
        and request_id.isdigit()
    )


def make_request(request_id, command, *args):
    """
    Encodes a request: ID COMMAND [ARGS...]\n
    Does not restrict commands against a whitelist.
    """
    if not valid_id(request_id):
        raise ValueError("Invalid request ID")

    if not command or not isinstance(command, str):
        raise ValueError("Invalid command")

    command = command.upper().strip()
    parts = [request_id, command]
    parts.extend(str(arg) for arg in args)

    return " ".join(parts) + "\n"


def parse_request(message):
    """
    Decodes a request string.
    Returns: (request_id, command, args, error)
    """
    if not message:
        return None, None, [], "EMPTY_REQUEST"

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

    return request_id, command, args, None


def make_response(request_id, status, payload=""):
    """
    Encodes a response: ID STATUS [PAYLOAD]\n
    """
    if not valid_id(request_id):
        raise ValueError("Invalid response ID")

    status = status.upper().strip()

    if status not in ("OK", "ERROR"):
        raise ValueError("Invalid response status")

    parts = [request_id, status]

    if payload is not None and str(payload) != "":
        parts.append(str(payload))

    return " ".join(parts) + "\n"


def parse_response(message):
    """
    Decodes a response string: ID STATUS [PAYLOAD]
    Returns: (request_id, status, payload)
    """
    if not message:
        raise ValueError("Empty response")

    parts = message.strip().split(" ", 2)

    if len(parts) < 2:
        raise ValueError("Malformed response")

    request_id, status = parts[:2]

    if not valid_id(request_id):
        raise ValueError("Invalid response ID")

    status = status.upper()

    if status not in ("OK", "ERROR"):
        raise ValueError("Invalid response status")

    payload = parts[2] if len(parts) == 3 else ""

    return request_id, status, payload
