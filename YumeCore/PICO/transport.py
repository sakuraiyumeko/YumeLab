"""
YumeCore Transport Layer for Raspberry Pi Pico (MicroPython).
Manages non-blocking USB CDC input/output, message buffering,
framing by newline, maximum message length, and buffer overflow detection.
"""

import sys
try:
    import uselect
except ImportError:
    uselect = None


class Transport:
    def __init__(self, max_length=256):
        self.max_length = max_length
        self._buffer = ""
        self._overflow = False
        if uselect and hasattr(uselect, "poll"):
            self._poller = uselect.poll()
            self._poller.register(sys.stdin, getattr(uselect, "POLLIN", 1))
        else:
            self._poller = None

    def read_line(self):
        """
        Polls for available characters on USB CDC stdin without blocking.
        
        Returns:
            (line, is_overflow): When a full line (ending with \n) is ready.
            None: When no complete line is ready yet.
        """
        reads_done = 0
        max_reads = self.max_length * 2

        while reads_done < max_reads and self._poller.poll(0):
            char = sys.stdin.read(1)
            reads_done += 1

            if not char:
                break

            if char == "\n":
                line = self._buffer
                is_overflow = self._overflow
                self._buffer = ""
                self._overflow = False
                return line, is_overflow
            elif char != "\r":
                if len(self._buffer) < self.max_length and not self._overflow:
                    self._buffer += char
                else:
                    self._overflow = True

        return None

    def write(self, data):
        """
        Writes data string to USB CDC stdout.
        """
        if data:
            sys.stdout.write(data)
            if hasattr(sys.stdout, "flush"):
                try:
                    sys.stdout.flush()
                except Exception:
                    pass

    def reset(self):
        """
        Clears the internal line buffer.
        """
        self._buffer = ""
        self._overflow = False
