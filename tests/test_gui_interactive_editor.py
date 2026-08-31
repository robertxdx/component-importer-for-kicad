import os
import tempfile
import unittest
from pathlib import Path

from component_importer.interactive_editor import EditorState, Slot, handle_key
from component_importer.interactive_strategy import (
    InteractiveReconstructionStrategy,
    PredeterminedLayoutStrategy,
    build_state_from_layout,
    build_state_from_symbol,
    layout_from_state,
)
from component_importer.key_source import Key, ScriptedKeySource


# A four-sided fixture symbol: left(1,2) right(3) bottom(4) top(5)
FOUR_SIDED_SYMBOL = """(symbol "FOUR" (pin_names (offset 0.254)) (in_bom yes) (on_board yes)
    (property "Reference" "U" (id 0) (at 0 2.54 0)
      (effects (font (size 1.27 1.27))))
    (property "Value" "FOUR" (id 1) (at 0 0 0)
      (effects (font (size 1.27 1.27))))
    (symbol "FOUR_0_1"
      (pin input line (at -17.78 5.08 0) (length 5.08)
        (name "SCL" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin input line (at -17.78 0 0) (length 5.08)
        (name "SDA" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
      (pin output line (at 17.78 5.08 180) (length 5.08)
        (name "OUT" (effects (font (size 1.27 1.27))))
        (number "3" (effects (font (size 1.27 1.27)))))
      (pin power_in line (at 5.08 -20.32 90) (length 5.08)
        (name "GND" (effects (font (size 1.27 1.27))))
        (number "4" (effects (font (size 1.27 1.27)))))
      (pin power_out line (at -5.08 20.32 270) (length 5.08)
        (name "VCC" (effects (font (size 1.27 1.27))))
        (number "5" (effects (font (size 1.27 1.27)))))))"""

LIBRARY = (
    "(kicad_symbol_lib (version 20211014) (generator kicad_symbol_editor)\n  "
    + FOUR_SIDED_SYMBOL
    + "\n)\n"
)


class _NullRenderer:
    def render(self, lines):
        return None


def snapshot(state: EditorState):
    return (
        {
            side: [(slot.is_blank, slot.number, slot.name) for slot in state.sides[side]]
            for side in state.sides
        },
        state.cursor_side,
        state.cursor_index,
        state.selected,
        state.pending,
    )


def fixture_state() -> EditorState:
    state = EditorState()
    state.sides["left"] = [Slot(name="A", number="1"), Slot(name="B", number="2")]
    state.sides["right"] = [Slot(name="C", number="3")]
    state.sides["top"] = [Slot(name="T", number="5")]
    state.sides["bottom"] = [Slot(name="G", number="4")]
    state.cursor_side = "left"
    state.cursor_index = 0
    return state


class LayoutTransferTest(unittest.TestCase):
    def test_layout_round_trip_preserves_arrangement(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        # Select left[0] and move it inbound to the right side, insert a blank
        handle_key(state, Key.SPACE)
        handle_key(state, Key.RIGHT)
        handle_key(state, Key.SPACE)
        handle_key(state, Key.SHIFT_SPACE)

        layout = layout_from_state(state)
        rebuilt = build_state_from_layout(FOUR_SIDED_SYMBOL, layout)

        self.assertEqual(snapshot(state)[0], snapshot(rebuilt)[0])

    def _byte_compare_for_moves(self, moves):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path_a = Path(temp_dir) / "a.kicad_sym"
            path_b = Path(temp_dir) / "b.kicad_sym"
            path_a.write_text(LIBRARY, encoding="utf-8")
            path_b.write_text(LIBRARY, encoding="utf-8")

            # Interactive strategy: replay moves then accept (Y, Y)
            source = ScriptedKeySource(list(moves) + [Key.Y, Key.Y])
            interactive = InteractiveReconstructionStrategy(
                key_source=source, renderer=_NullRenderer()
            )
            result_a = interactive.format_symbol_library_file(path_a, ["FOUR"])

            # Derive the layout the same moves produce, then apply it headless
            state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
            for move in moves:
                handle_key(state, move)

            predetermined = PredeterminedLayoutStrategy(
                {"FOUR": layout_from_state(state)}
            )
            result_b = predetermined.format_symbol_library_file(path_b, ["FOUR"])

            self.assertIsNotNone(result_a)
            self.assertIsNotNone(result_b)
            self.assertEqual(
                path_a.read_text(encoding="utf-8"),
                path_b.read_text(encoding="utf-8"),
            )

    def test_byte_identical_accept_no_moves(self):
        self._byte_compare_for_moves([])

    def test_byte_identical_after_inbound_move(self):
        # select left[0] (SCL), inbound RIGHT to the right side
        self._byte_compare_for_moves([Key.SPACE, Key.RIGHT])

    def test_byte_identical_after_blank_insert_and_move(self):
        self._byte_compare_for_moves(
            [Key.SHIFT_SPACE, Key.DOWN, Key.SPACE, Key.DOWN]
        )

    def test_from_states_matches_explicit_layout(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        handle_key(state, Key.SPACE)
        handle_key(state, Key.DOWN)

        by_states = PredeterminedLayoutStrategy.from_states({"FOUR": state})
        by_layout = PredeterminedLayoutStrategy({"FOUR": layout_from_state(state)})

        self.assertEqual(by_states.layouts, by_layout.layouts)

    def test_missing_layout_leaves_symbol_untouched(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "lib.kicad_sym"
            path.write_text(LIBRARY, encoding="utf-8")

            # No layout for FOUR -> mirrors a cancel, file unchanged, result None
            strategy = PredeterminedLayoutStrategy({"OTHER": {}})
            result = strategy.format_symbol_library_file(path, ["FOUR"])

            self.assertIsNone(result)
            self.assertEqual(path.read_text(encoding="utf-8"), LIBRARY)


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen",
    "GUI test requires QT_QPA_PLATFORM=offscreen",
)
class InteractiveDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _make_dialog(self):
        from component_importer.gui_interactive_editor import (
            InteractivePinLayoutDialog,
        )

        return InteractivePinLayoutDialog(fixture_state(), "FOUR")

    def _send(self, dialog, key: Key):
        # Map a logical Key to a Qt key event and route it through the dialog
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent

        mapping = {
            Key.UP: (Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier),
            Key.DOWN: (Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier),
            Key.LEFT: (Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier),
            Key.RIGHT: (Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier),
            Key.SPACE: (Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
            Key.SHIFT_SPACE: (
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.ShiftModifier,
            ),
            Key.DELETE: (Qt.Key.Key_D, Qt.KeyboardModifier.NoModifier),
            Key.Y: (Qt.Key.Key_Y, Qt.KeyboardModifier.NoModifier),
            Key.ESC: (Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
            Key.ENTER: (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
        }
        qt_key, modifier = mapping[key]
        event = QKeyEvent(QEvent.Type.KeyPress, qt_key, modifier)
        dialog.keyPressEvent(event)

    def _drive(self, dialog, keys):
        for key in keys:
            self._send(dialog, key)

    # Driving the dialog mutates its state exactly like the shared core
    def _assert_mirrors_core(self, keys):
        dialog = self._make_dialog()
        reference = fixture_state()

        for key in keys:
            self._send(dialog, key)
            handle_key(reference, key)

        self.assertEqual(snapshot(dialog.state), snapshot(reference))

    def test_key_mapping(self):
        from PyQt6.QtCore import Qt, QEvent
        from PyQt6.QtGui import QKeyEvent
        from component_importer.gui_interactive_editor import qt_key_event_to_key

        cases = {
            (Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier): Key.UP,
            (Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier): Key.SPACE,
            (Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier): Key.SHIFT_SPACE,
            (Qt.Key.Key_S, Qt.KeyboardModifier.NoModifier): Key.SHIFT_SPACE,
            (Qt.Key.Key_D, Qt.KeyboardModifier.NoModifier): Key.DELETE,
            (Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier): Key.DELETE,
            (Qt.Key.Key_Y, Qt.KeyboardModifier.NoModifier): Key.Y,
            (Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier): Key.ESC,
            (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier): Key.ENTER,
            (Qt.Key.Key_J, Qt.KeyboardModifier.NoModifier): Key.OTHER,
        }
        for (qt_key, modifier), expected in cases.items():
            event = QKeyEvent(QEvent.Type.KeyPress, qt_key, modifier)
            self.assertEqual(qt_key_event_to_key(event), expected)

    def test_navigate_mirrors_core(self):
        self._assert_mirrors_core([Key.DOWN, Key.DOWN, Key.UP])

    def test_select_and_move_mirrors_core(self):
        self._assert_mirrors_core([Key.SPACE, Key.RIGHT, Key.SPACE])

    def test_blank_insert_mirrors_core(self):
        self._assert_mirrors_core([Key.SHIFT_SPACE, Key.DOWN])

    def test_delete_blank_mirrors_core(self):
        self._assert_mirrors_core([Key.SHIFT_SPACE, Key.DELETE])

    def test_accept_path_sets_accepted_result(self):
        from PyQt6.QtWidgets import QDialog

        dialog = self._make_dialog()
        # Y opens the confirm prompt, second Y accepts
        self._drive(dialog, [Key.SPACE, Key.RIGHT, Key.Y, Key.Y])
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

        # The accepted state carries the moved pin so a layout can be captured
        # (left[0]="A" moved inbound to the right side)
        self.assertIn("A", [slot.name for slot in dialog.state.sides["right"]])

    def test_accept_prompt_resume_does_not_accept(self):
        from PyQt6.QtWidgets import QDialog

        dialog = self._make_dialog()
        # Y opens prompt, a non-Y key resumes editing without accepting
        self._drive(dialog, [Key.Y, Key.LEFT])
        self.assertIsNone(dialog.state.pending)
        # Dialog not yet accepted; still editable
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_cancel_path_sets_rejected_result(self):
        from PyQt6.QtWidgets import QDialog

        dialog = self._make_dialog()
        # Esc opens the exit prompt, Enter confirms cancel
        self._drive(dialog, [Key.ESC, Key.ENTER])
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

    def test_keyclick_drives_dialog(self):
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt

        dialog = self._make_dialog()
        before = snapshot(dialog.state)
        QTest.keyClick(dialog, Qt.Key.Key_Down)
        self.assertNotEqual(snapshot(dialog.state), before)

    def test_ok_button_accepts_bypassing_prompt(self):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox

        dialog = self._make_dialog()
        # Move left[0]="A" inbound to the right side, then click OK directly:
        # no two-step Y->Y prompt is needed.
        self._drive(dialog, [Key.SPACE, Key.RIGHT])
        dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        # State is left intact exactly like the Y path so layout extraction reads
        # the moved pin on the right side.
        self.assertIn("A", [slot.name for slot in dialog.state.sides["right"]])

    def test_ok_button_layout_byte_identical_to_terminal_accept(self):
        # End-to-end equivalence of the two accept paths on the same moves:
        # the GUI OK-button path the app actually uses
        # (build_state_from_symbol -> dialog -> OK -> layout_from_state ->
        # PredeterminedLayoutStrategy) must rewrite the library byte-for-byte
        # identically to the terminal editor's Y,Y accept.
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        from component_importer.gui_interactive_editor import (
            InteractivePinLayoutDialog,
        )

        moves = [Key.SPACE, Key.RIGHT]

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path_terminal = Path(temp_dir) / "terminal.kicad_sym"
            path_dialog = Path(temp_dir) / "dialog.kicad_sym"
            path_terminal.write_text(LIBRARY, encoding="utf-8")
            path_dialog.write_text(LIBRARY, encoding="utf-8")

            # Terminal editor: replay moves then accept with Y, Y
            source = ScriptedKeySource(list(moves) + [Key.Y, Key.Y])
            InteractiveReconstructionStrategy(
                key_source=source, renderer=_NullRenderer()
            ).format_symbol_library_file(path_terminal, ["FOUR"])

            # GUI dialog: same moves, accept by clicking OK (not the Y prompt)
            dialog = InteractivePinLayoutDialog(
                build_state_from_symbol(FOUR_SIDED_SYMBOL), "FOUR"
            )
            self._drive(dialog, moves)
            dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

            PredeterminedLayoutStrategy(
                {"FOUR": layout_from_state(dialog.state)}
            ).format_symbol_library_file(path_dialog, ["FOUR"])

            self.assertEqual(
                path_terminal.read_text(encoding="utf-8"),
                path_dialog.read_text(encoding="utf-8"),
            )

    def test_cancel_button_rejects(self):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox

        dialog = self._make_dialog()
        dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel).click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

    def test_buttons_never_take_keyboard_focus_or_default(self):
        from PyQt6.QtCore import Qt

        dialog = self._make_dialog()
        for button in dialog.button_box.buttons():
            self.assertEqual(button.focusPolicy(), Qt.FocusPolicy.NoFocus)
            self.assertFalse(button.autoDefault())
            self.assertFalse(button.isDefault())

    def test_enter_outside_prompt_does_not_trigger_ok(self):
        from PyQt6.QtWidgets import QDialog

        dialog = self._make_dialog()
        # Plain Enter is inert during editing; the OK button's default-button
        # behaviour must not hijack it into an accept.
        self._drive(dialog, [Key.ENTER])
        self.assertIsNone(dialog.state.pending)
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_enter_still_confirms_exit_prompt(self):
        from PyQt6.QtWidgets import QDialog

        dialog = self._make_dialog()
        # Esc opens the exit prompt; Enter must still mean "confirm cancel"
        # (reject), not fire the OK button.
        self._drive(dialog, [Key.ESC, Key.ENTER])
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen",
    "GUI test requires QT_QPA_PLATFORM=offscreen",
)
class CanvasCenteringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _canvas(self):
        from component_importer.gui_interactive_editor import _PinCanvas

        return _PinCanvas(fixture_state())

    def test_small_state_centered_on_large_canvas(self):
        canvas = self._canvas()
        canvas.resize(2000, 1400)

        body_w, body_h, left_ext, right_ext, top_ext, bottom_ext = (
            canvas._content_metrics()
        )
        bx, by = canvas._compute_origin()

        # The whole drawn chip (labels + stubs + body) is centred in the widget
        content_cx = (bx - left_ext) + (left_ext + body_w + right_ext) / 2
        content_cy = (by - top_ext) + (top_ext + body_h + bottom_ext) / 2
        self.assertAlmostEqual(content_cx, 1000, delta=1)
        self.assertAlmostEqual(content_cy, 700, delta=1)

    def test_oversize_chip_anchors_without_negative_origin(self):
        canvas = self._canvas()
        # Drop the minimum-size floor so the widget can be smaller than the chip
        canvas.setMinimumSize(0, 0)
        canvas.resize(40, 40)  # smaller than the chip in every dimension

        _, _, left_ext, _, top_ext, _ = canvas._content_metrics()
        bx, by = canvas._compute_origin()

        # Content is flush to the top-left edge, never pushed off-canvas
        self.assertEqual(bx - left_ext, 0)
        self.assertEqual(by - top_ext, 0)


if __name__ == "__main__":
    unittest.main()
