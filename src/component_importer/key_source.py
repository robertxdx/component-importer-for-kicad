# Input abstraction for the interactive symbol editor.
# This module is Qt-free. Only TerminalKeySource ever touches the real terminal;
# ScriptedKeySource exists so the editor core can be driven head-less in tests.

from abc import ABC, abstractmethod
from enum import Enum


# The small set of logical keys the editor understands
class Key(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    SPACE = "space"
    SHIFT_SPACE = "shift_space"
    DELETE = "delete"
    Y = "y"
    ESC = "esc"
    ENTER = "enter"
    OTHER = "other"


# Base interface: a source of logical key presses
class KeySource(ABC):
    @abstractmethod
    def read_key(self) -> Key:
        """Return the next logical key press."""
        raise NotImplementedError


# Deterministic key source backed by a pre-built list, for tests
class ScriptedKeySource(KeySource):
    def __init__(self, keys: list[Key] | None = None):
        # Store a mutable queue of pending keys
        self._keys: list[Key] = list(keys or [])

    # Append more keys to the queue
    def feed(self, keys: list[Key]) -> None:
        self._keys.extend(keys)

    # Replace the queued keys
    def set_keys(self, keys: list[Key]) -> None:
        self._keys = list(keys)

    # Pop and return the next queued key
    def read_key(self) -> Key:
        if not self._keys:
            # Running dry means a test forgot to terminate the editor session.
            raise IndexError("ScriptedKeySource exhausted before the editor finished.")

        return self._keys.pop(0)


# Real terminal key source using stdin raw-mode reads (cbreak via termios/tty)
class TerminalKeySource(KeySource):
    def __init__(self, stream=None):
        import sys

        # Default to the process standard input
        self._stream = stream if stream is not None else sys.stdin

    # Read one logical key from the terminal, decoding CSI arrow sequences
    def read_key(self) -> Key:
        import termios
        import tty

        fd = self._stream.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            # Switch to cbreak so single keystrokes arrive without Enter.
            # TCSANOW keeps queued input; the default TCSAFLUSH would drop
            # keys that arrived between two read_key calls.
            tty.setcbreak(fd, termios.TCSANOW)
            char = self._read_byte(fd)

            # Escape may start a CSI arrow sequence or be a bare Esc press
            if char == "\x1b":
                return self._read_escape_sequence(fd)

            return self._classify_char(char)
        finally:
            # Always restore the previous terminal mode
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Read one byte straight from the descriptor. Python's buffered stdin
    # would slurp a whole escape sequence into its internal buffer, making
    # the select() probe below miss the bytes that already arrived.
    def _read_byte(self, fd) -> str:
        import os

        return os.read(fd, 1).decode("utf-8", "replace")

    # Decode the bytes following an initial Esc byte
    def _read_escape_sequence(self, fd) -> Key:
        import select

        # A lone Esc arrives with no immediately-following bytes
        following, _, _ = select.select([fd], [], [], 0.05)

        if not following:
            return Key.ESC

        # Arrows arrive as CSI (Esc [) or SS3 (Esc O) sequences
        bracket = self._read_byte(fd)

        if bracket not in ("[", "O"):
            return Key.ESC

        final = self._read_byte(fd)

        return {
            "A": Key.UP,
            "B": Key.DOWN,
            "C": Key.RIGHT,
            "D": Key.LEFT,
        }.get(final, Key.OTHER)

    # Map a single ordinary character to a logical key
    def _classify_char(self, char: str) -> Key:
        if char in ("\r", "\n"):
            return Key.ENTER

        if char == " ":
            return Key.SPACE

        # Capital S is treated as the shift-space equivalent (insert blank)
        if char == "S":
            return Key.SHIFT_SPACE

        if char in ("d", "D", "\x7f", "\x08"):
            return Key.DELETE

        if char in ("y", "Y"):
            return Key.Y

        return Key.OTHER
