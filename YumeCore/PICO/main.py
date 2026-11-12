
import sys
import os
import time
import machine
import uselect

from controller import Controller
from protocol import parse_request, make_response
from filesystem import FileSystem


controller = Controller()
filesystem = FileSystem()


def dispatch(command, args):
    if command == "PING":
        if args:
            return "ERROR", "INVALID_ARGUMENT"
        return "OK", "PONG"

    elif command == "INFO":
        if args:
            return "ERROR", "INVALID_ARGUMENT"

        info = os.uname()

        return "OK", "MACHINE={} RELEASE={}".format(
            info.machine,
            info.release
        )

    elif command == "REBOOT":
        if args:
            return "ERROR", "INVALID_ARGUMENT"
        return "OK", "REBOOTING"

    elif command in (
        "STATUS",
        "TEMP",
        "AUTO",
        "AUTO_SET",
        "LED",
        "HW_LIST",
        "HW_GET",
        "HW_SET",
    ):
        payload = controller.dispatch(command, args)
        return "OK", payload

    elif command.startswith("FS_"):
        result = filesystem.dispatch(command, args)

        if result is None:
            return "ERROR", "UNKNOWN_COMMAND"

        return result

    return "ERROR", "UNKNOWN_COMMAND"


def process_message(message):
    request_id, command, args, error = parse_request(message)

    if error:
        return make_response(
            request_id or "0000",
            "ERROR",
            error
        ), False

    try:
        status, payload = dispatch(command, args)

    except Exception as exc:
        status = "ERROR"
        payload = str(exc) or "OPERATION_FAILED"

    do_reboot = command == "REBOOT" and status == "OK"

    return make_response(request_id, status, payload), do_reboot


# Non-blocking USB CDC input
poller = uselect.poll()
poller.register(sys.stdin, uselect.POLLIN)

line_buffer = ""
overflow = False

while True:
    # Run the hardware control cycle independently.
    controller.tick()

    events = poller.poll(0)

    if events:
        char = sys.stdin.read(1)

        if char:
            if char == "\n":
                if overflow:
                    response = make_response(
                        "0000",
                        "ERROR",
                        "LINE_TOO_LONG"
                    )
                    do_reboot = False
                else:
                    response, do_reboot = process_message(
                        line_buffer + "\n"
                    )

                line_buffer = ""
                overflow = False

                sys.stdout.write(response)

                if do_reboot:
                    time.sleep_ms(100)
                    machine.soft_reset()

            elif char != "\r":
                if len(line_buffer) < 256 and not overflow:
                    line_buffer += char
                else:
                    overflow = True

    else:
        time.sleep_ms(5)
