import os
import sys
import unittest

from component_importer.key_source import Key, TerminalKeySource


@unittest.skipUnless(sys.platform.startswith("linux"), "requires a POSIX pty")
class TerminalKeySourceTests(unittest.TestCase):
    def read_keys_from_pty(self, payload: bytes, count: int) -> list[Key]:
        master_fd, slave_fd = os.openpty()

        try:
            os.write(master_fd, payload)
            stream = os.fdopen(slave_fd, "r", closefd=False)
            source = TerminalKeySource(stream)
            return [source.read_key() for _ in range(count)]
        finally:
            os.close(master_fd)
            os.close(slave_fd)

    def test_csi_arrow_sequences_decode_as_single_keys(self):
        # The whole sequence arrives in one write, like a terminal sends it;
        # buffered reads used to split it into ESC + two OTHER keys
        keys = self.read_keys_from_pty(b"\x1b[A\x1b[B\x1b[C\x1b[D", 4)
        self.assertEqual(keys, [Key.UP, Key.DOWN, Key.RIGHT, Key.LEFT])

    def test_ss3_arrow_sequences_decode_as_single_keys(self):
        keys = self.read_keys_from_pty(b"\x1bOA\x1bOB", 2)
        self.assertEqual(keys, [Key.UP, Key.DOWN])

    def test_plain_characters_between_arrows(self):
        keys = self.read_keys_from_pty(b"\x1b[B Sy\x1b[A", 5)
        self.assertEqual(
            keys,
            [Key.DOWN, Key.SPACE, Key.SHIFT_SPACE, Key.Y, Key.UP],
        )

    def test_lone_escape_is_esc(self):
        keys = self.read_keys_from_pty(b"\x1b", 1)
        self.assertEqual(keys, [Key.ESC])


if __name__ == "__main__":
    unittest.main()
