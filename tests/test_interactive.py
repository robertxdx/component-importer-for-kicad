import math
import re
import tempfile
import unittest
from pathlib import Path

from component_importer.interactive_editor import (
    ANSI_RED,
    ANSI_RESET,
    ANSI_YELLOW,
    CURSOR_BLOCK,
    EditorState,
    Slot,
    center_lines,
    handle_key,
    make_blank,
    render_screen,
    run_editor,
    split_chip_and_footer,
)
from component_importer.interactive_strategy import (
    CHAR_WIDTH_MM,
    NAME_ZONE_GAP_MM,
    InteractiveReconstructionStrategy,
    build_state_from_symbol,
    compute_geometry,
    regenerate_symbol_block,
)
from component_importer.key_source import Key, ScriptedKeySource
from component_importer.symbol_footprint_linker import (
    find_matching_paren,
    find_symbol_blocks,
)
from component_importer.symbol_style import (
    find_list_blocks,
    find_list_blocks_at_depth,
    parse_pin_at_block,
    parse_pin_length_block,
)


# A four-sided fixture symbol: left(1,2) right(3) top(5) bottom(4)
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


def names(state):
    return {side: [slot.name for slot in state.sides[side]] for side in state.sides}


def cursor(state):
    return (state.cursor_side, state.cursor_index)


def sample_state():
    state = EditorState()
    state.sides["left"] = [Slot(name="A", number="1"), Slot(name="B", number="2"), Slot(name="C", number="3")]
    state.sides["right"] = [Slot(name="D", number="4"), Slot(name="E", number="5")]
    state.sides["top"] = [Slot(name="T1", number="6")]
    state.sides["bottom"] = [Slot(name="BM", number="7")]
    state.cursor_side = "left"
    state.cursor_index = 0
    return state


class ExtractionTest(unittest.TestCase):
    def test_sides_and_order(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        # left top->bottom, right top->bottom, top left->right, bottom left->right
        self.assertEqual(names(state)["left"], ["SCL", "SDA"])
        self.assertEqual(names(state)["right"], ["OUT"])
        self.assertEqual(names(state)["top"], ["VCC"])
        self.assertEqual(names(state)["bottom"], ["GND"])

    def test_electrical_types_and_numbers_preserved(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        self.assertEqual(state.sides["left"][0].etype, "input")
        self.assertEqual(state.sides["top"][0].etype, "power_out")
        self.assertEqual(state.sides["bottom"][0].number, "4")

    def test_left_order_is_top_to_bottom_by_y(self):
        # SCL at y=5.08 must come before SDA at y=0
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        self.assertEqual([s.number for s in state.sides["left"]], ["1", "2"])


class NavigationTest(unittest.TestCase):
    def test_nav_moves_through_flat_sequence(self):
        state = sample_state()
        # NAV cycle order: left, top, right, bottom
        handle_key(state, Key.DOWN)
        self.assertEqual(cursor(state), ("left", 1))
        handle_key(state, Key.UP)
        self.assertEqual(cursor(state), ("left", 0))

    def test_nav_wraps_backward_to_last_slot(self):
        state = sample_state()
        handle_key(state, Key.UP)
        # Previous of first slot wraps to the last slot in the cycle (bottom)
        self.assertEqual(cursor(state), ("bottom", 0))

    def test_nav_crosses_sides_forward(self):
        state = sample_state()
        # advance past the 3 left slots -> top side
        for _ in range(3):
            handle_key(state, Key.DOWN)
        self.assertEqual(cursor(state), ("top", 0))


class MoveReorderTest(unittest.TestCase):
    def test_space_enters_and_leaves_move_mode(self):
        state = sample_state()
        handle_key(state, Key.SPACE)
        self.assertTrue(state.selected)
        handle_key(state, Key.SPACE)
        self.assertFalse(state.selected)

    def test_shift_within_side(self):
        state = sample_state()
        handle_key(state, Key.SPACE)
        handle_key(state, Key.DOWN)
        self.assertEqual(names(state)["left"], ["B", "A", "C"])
        self.assertEqual(cursor(state), ("left", 1))


class CornerTransportTest(unittest.TestCase):
    def test_left_first_up_goes_to_top_first(self):
        state = sample_state()
        handle_key(state, Key.SPACE)
        handle_key(state, Key.UP)
        self.assertEqual(names(state)["top"], ["A", "T1"])
        self.assertEqual(cursor(state), ("top", 0))

    def test_left_last_down_goes_to_bottom_first(self):
        state = sample_state()
        state.cursor_index = 2
        handle_key(state, Key.SPACE)
        handle_key(state, Key.DOWN)
        self.assertEqual(names(state)["bottom"], ["C", "BM"])
        self.assertEqual(cursor(state), ("bottom", 0))

    def test_right_first_up_appends_to_top(self):
        state = sample_state()
        state.cursor_side = "right"
        state.cursor_index = 0
        handle_key(state, Key.SPACE)
        handle_key(state, Key.UP)
        self.assertEqual(names(state)["top"], ["T1", "D"])
        self.assertEqual(cursor(state), ("top", 1))

    def test_top_right_appends_to_right_first(self):
        state = sample_state()
        state.cursor_side = "top"
        state.cursor_index = 0
        handle_key(state, Key.SPACE)
        handle_key(state, Key.RIGHT)
        self.assertEqual(names(state)["right"], ["T1", "D", "E"])

    def test_bottom_left_appends_to_left_last(self):
        state = sample_state()
        state.cursor_side = "bottom"
        state.cursor_index = 0
        handle_key(state, Key.SPACE)
        handle_key(state, Key.LEFT)
        self.assertEqual(names(state)["left"], ["A", "B", "C", "BM"])


class InboundMoveTest(unittest.TestCase):
    def test_inbound_left_to_right_same_index(self):
        state = sample_state()
        state.cursor_index = 1
        handle_key(state, Key.SPACE)
        handle_key(state, Key.RIGHT)
        self.assertEqual(names(state)["left"], ["A", "C"])
        self.assertEqual(names(state)["right"], ["D", "B", "E"])
        self.assertEqual(cursor(state), ("right", 1))

    def test_inbound_top_to_bottom(self):
        state = sample_state()
        state.cursor_side = "top"
        state.cursor_index = 0
        handle_key(state, Key.SPACE)
        handle_key(state, Key.DOWN)
        self.assertEqual(names(state)["bottom"], ["T1", "BM"])
        self.assertEqual(names(state)["top"], [])

    def test_inbound_clamps_to_opposite_length(self):
        state = sample_state()
        # right side has only 2 slots; move left[2] (index 2) inbound to right
        state.cursor_index = 2
        handle_key(state, Key.SPACE)
        handle_key(state, Key.RIGHT)
        # index 2 clamps to append (len(right)==2)
        self.assertEqual(names(state)["right"], ["D", "E", "C"])
        self.assertEqual(cursor(state), ("right", 2))


class OutboundNoOpTest(unittest.TestCase):
    def test_outbound_arrows_are_noops(self):
        cases = [("left", Key.LEFT), ("right", Key.RIGHT), ("top", Key.UP), ("bottom", Key.DOWN)]
        for side, key in cases:
            state = sample_state()
            state.cursor_side = side
            state.cursor_index = 0
            before = names(state)
            handle_key(state, Key.SPACE)
            handle_key(state, key)
            self.assertEqual(names(state), before, f"{side} {key} should be a no-op")
            self.assertEqual(cursor(state), (side, 0))


class BlankTest(unittest.TestCase):
    def test_insert_blank_at_cursor(self):
        state = sample_state()
        handle_key(state, Key.SHIFT_SPACE)
        self.assertTrue(state.sides["left"][0].is_blank)
        self.assertEqual(state.sides["left"][0].display_name, "[blank]")
        self.assertEqual(cursor(state), ("left", 0))

    def test_delete_blank(self):
        state = sample_state()
        state.sides["left"].insert(0, make_blank())
        state.cursor_index = 0
        handle_key(state, Key.DELETE)
        self.assertEqual(names(state)["left"], ["A", "B", "C"])

    def test_delete_refuses_real_pin(self):
        state = sample_state()
        handle_key(state, Key.DELETE)
        self.assertEqual(names(state)["left"], ["A", "B", "C"])
        self.assertIn("Refused", state.status)

    def test_blank_obeys_movement_rules(self):
        state = sample_state()
        handle_key(state, Key.SHIFT_SPACE)  # blank at left[0]
        handle_key(state, Key.SPACE)  # select it
        handle_key(state, Key.DOWN)  # shift down like any slot
        self.assertEqual(names(state)["left"][1], "[blank]")


class AcceptCancelFlowTest(unittest.TestCase):
    def test_accept_yy(self):
        state = sample_state()
        source = ScriptedKeySource([Key.Y, Key.Y])
        self.assertTrue(run_editor(state, source))

    def test_cancel_y_then_other(self):
        state = sample_state()
        source = ScriptedKeySource([Key.Y, Key.OTHER, Key.ESC, Key.ENTER])
        # Y then non-Y resumes editing; then Esc,Enter cancels
        self.assertFalse(run_editor(state, source))

    def test_cancel_esc_enter(self):
        state = sample_state()
        source = ScriptedKeySource([Key.ESC, Key.ENTER])
        self.assertFalse(run_editor(state, source))

    def test_esc_other_resumes(self):
        state = sample_state()
        # Esc then non-Enter resumes editing (does not cancel); then accept
        resume_state = sample_state()
        handle_key(resume_state, Key.ESC)
        handle_key(resume_state, Key.OTHER)
        self.assertIsNone(resume_state.pending)
        self.assertIn("Resumed", resume_state.status)

        source = ScriptedKeySource([Key.ESC, Key.OTHER, Key.Y, Key.Y])
        self.assertTrue(run_editor(state, source))


class RenderSnapshotTest(unittest.TestCase):
    def test_cursor_is_yellow_with_block(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        lines = render_screen(state)
        joined = "\n".join(lines)
        self.assertIn(ANSI_YELLOW, joined)
        self.assertIn(CURSOR_BLOCK, joined)

    def test_selected_is_red(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        handle_key(state, Key.SPACE)
        joined = "\n".join(render_screen(state))
        self.assertIn(ANSI_RED, joined)

    def test_top_bottom_names_render_vertically(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        all_lines = [re.sub(r"\x1b\[[0-9]+m", "", line) for line in render_screen(state)]
        # Only inspect the chip canvas (everything before the footer separator)
        chip = all_lines[: all_lines.index("")]
        # Top name "VCC" and bottom name "GND" must be stacked (never a horizontal run)
        self.assertFalse(any("VCC" in line for line in chip))
        self.assertFalse(any("GND" in line for line in chip))
        # "VCC" must stack down one column across three consecutive rows.
        v_row = next(r for r, line in enumerate(chip) if "V" in line)
        v_col = chip[v_row].index("V")
        stacked = "".join(
            chip[v_row + offset][v_col]
            for offset in range(3)
            if v_col < len(chip[v_row + offset])
        )
        self.assertEqual(stacked, "VCC")

    def test_accept_prompt_rendered(self):
        state = sample_state()
        handle_key(state, Key.Y)
        lines = render_screen(state)
        self.assertTrue(any("press Y to confirm" in line for line in lines))

    def test_exit_prompt_rendered(self):
        state = sample_state()
        handle_key(state, Key.ESC)
        lines = render_screen(state)
        self.assertTrue(any("press Enter to cancel" in line for line in lines))


class CenterLinesTest(unittest.TestCase):
    def test_centers_chip_horizontally_and_vertically(self):
        chip = ["abc", "de"]  # width 3, height 2
        out = center_lines(chip, [], width=11, height=6)
        # top_pad = (6 - 2) // 2 = 2 blank rows prepended
        self.assertEqual(out[:2], ["", ""])
        # left_pad = (11 - 3) // 2 = 4 leading spaces on each chip line
        self.assertEqual(out[2], "    abc")
        self.assertEqual(out[3], "    de")

    def test_left_pad_uses_widest_chip_line(self):
        # The widest chip line drives the uniform horizontal shift
        chip = ["short", "a longer line"]  # width 13
        out = center_lines(chip, [], width=33, height=2)  # left_pad = (33-13)//2 = 10
        self.assertTrue(out[0].startswith(" " * 10 + "short"))
        self.assertTrue(out[1].startswith(" " * 10 + "a longer line"))

    def test_footer_stays_full_width_below_chip(self):
        # The chip is centred on its own width; a wider footer is NOT counted
        # for horizontal centring and stays at column 0.
        chip = ["chip"]  # width 4
        footer = ["", "a very wide help footer line"]  # width 28
        out = center_lines(chip, footer, width=20, height=3)
        # left_pad from the chip only: (20 - 4) // 2 = 8
        self.assertEqual(out[0], " " * 8 + "chip")
        # Footer keeps its blank separator and full-width (col 0) help line
        self.assertEqual(out[1], "")
        self.assertEqual(out[2], "a very wide help footer line")

    def test_vertical_centering_counts_footer_height(self):
        chip = ["chip"]
        footer = ["", "help"]  # block height = 1 + 2 = 3
        out = center_lines(chip, footer, width=40, height=9)  # top_pad = (9-3)//2 = 3
        self.assertEqual(out[:3], ["", "", ""])
        self.assertEqual(len(out), 6)

    def test_ansi_codes_ignored_when_measuring_width(self):
        # Colour escapes must not count toward the visible chip width
        colored = f"{ANSI_YELLOW}ab{ANSI_RESET}"  # visible width 2
        out = center_lines([colored], [], width=12, height=1)  # left_pad = (12-2)//2 = 5
        self.assertEqual(out[0], " " * 5 + colored)

    def test_internal_blank_chip_line_stays_blank(self):
        # A blank row inside the chip keeps blank (no trailing spaces)
        out = center_lines(["", "xx"], [], width=8, height=2)  # left_pad = (8-2)//2 = 3
        self.assertEqual(out[0], "")
        self.assertEqual(out[1], "   xx")

    def test_oversize_chip_has_no_negative_padding(self):
        chip = ["a" * 40, "b" * 40, "c" * 40]  # wider and taller than the grid
        out = center_lines(chip, [], width=10, height=1)
        # No blank top rows, no leading spaces: anchored top-left
        self.assertEqual(out, chip)

    def test_empty_input_returns_empty(self):
        self.assertEqual(center_lines([], [], width=80, height=24), [])


class SplitChipAndFooterTest(unittest.TestCase):
    def test_splits_on_last_blank_not_internal_blank(self):
        # render_screen may emit an internal blank chip row (empty top-number
        # row); the split must land on the trailing separator, not that row.
        state = EditorState()
        state.sides["left"] = [Slot(name="A", number="1")]
        state.sides["right"] = [Slot(name="C", number="3")]
        lines = render_screen(state)
        chip, footer = split_chip_and_footer(lines)

        # The help line lives in the footer, never in the chip
        self.assertTrue(any("arrows: move" in line for line in footer))
        self.assertFalse(any("arrows: move" in line for line in chip))
        # Footer begins with the blank separator
        self.assertEqual(footer[0], "")
        # The leading internal blank row is preserved in the chip
        self.assertEqual(chip[0], "")

    def test_no_blank_returns_all_as_chip(self):
        chip, footer = split_chip_and_footer(["a", "b"])
        self.assertEqual(chip, ["a", "b"])
        self.assertEqual(footer, [])


def pins_from_block(block_text):
    result = []
    for pb in find_list_blocks(block_text, "pin"):
        at = find_list_blocks_at_depth(pb["text"], "at", 1)[0]["text"]
        length = find_list_blocks_at_depth(pb["text"], "length", 1)[0]["text"]
        x, y, angle = parse_pin_at_block(at)
        L = parse_pin_length_block(length)
        result.append((x, y, angle, L))
    return result


def body_rect(block_text):
    rect = find_list_blocks(block_text, "rectangle")[0]["text"]
    sx, sy = map(float, re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", rect).groups())
    ex, ey = map(float, re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", rect).groups())
    return min(sx, ex), max(sx, ex), min(sy, ey), max(sy, ey)


class RegenerationGeometryTest(unittest.TestCase):
    def _assert_pins_on_edge_and_grid(self, block_text):
        min_x, max_x, min_y, max_y = body_rect(block_text)
        for x, y, angle, length in pins_from_block(block_text):
            dx = round(math.cos(math.radians(angle)))
            dy = round(math.sin(math.radians(angle)))
            ix, iy = x + dx * length, y + dy * length
            on_edge = (
                (abs(ix - min_x) < 1e-6 and dx == 1)
                or (abs(ix - max_x) < 1e-6 and dx == -1)
                or (abs(iy - min_y) < 1e-6 and dy == 1)
                or (abs(iy - max_y) < 1e-6 and dy == -1)
            )
            self.assertTrue(on_edge, f"pin ({x},{y},{angle}) inner ({ix},{iy}) not on edge")
            for value in (x, y):
                self.assertAlmostEqual(value / 2.54, round(value / 2.54), places=6)
        # body edges themselves are on grid
        for value in (min_x, max_x, min_y, max_y):
            self.assertAlmostEqual(value / 2.54, round(value / 2.54), places=6)

    def test_four_sided_geometry(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        block = regenerate_symbol_block(FOUR_SIDED_SYMBOL, "FOUR", state)
        self._assert_pins_on_edge_and_grid(block)

    def test_nasty_long_names_no_intersection(self):
        # A brutal fixture: very long names on every side.
        state = EditorState()
        state.sides["left"] = [Slot(name="VERY_LONG_LEFT_NAME_A", number="1")]
        state.sides["right"] = [Slot(name="VERY_LONG_RIGHT_NAME_B", number="2")]
        state.sides["top"] = [Slot(name="VERY_LONG_TOP_NAME_C", number="3")]
        state.sides["bottom"] = [Slot(name="VERY_LONG_BOTTOM_NAME_D", number="4")]
        geo = compute_geometry(state, 2.54)
        width = geo["max_x"] - geo["min_x"]
        height = geo["max_y"] - geo["min_y"]
        # Horizontal names must fit across the width without touching
        left_len = len("VERY_LONG_LEFT_NAME_A")
        right_len = len("VERY_LONG_RIGHT_NAME_B")
        self.assertGreaterEqual(
            width, (left_len + right_len) * CHAR_WIDTH_MM + NAME_ZONE_GAP_MM - 1e-6
        )
        # Vertical top/bottom names must fit down the height without touching
        top_len = len("VERY_LONG_TOP_NAME_C")
        bottom_len = len("VERY_LONG_BOTTOM_NAME_D")
        self.assertGreaterEqual(
            height, (top_len + bottom_len) * CHAR_WIDTH_MM + NAME_ZONE_GAP_MM - 1e-6
        )
        block = regenerate_symbol_block(
            FOUR_SIDED_SYMBOL.replace('"FOUR"', '"NASTY"'), "NASTY", state
        )
        # generated block must be paren-balanced
        self.assertEqual(block.count("("), block.count(")"))

    def test_blanks_produce_no_pins_but_spacing(self):
        state = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        # insert a blank at the top of the left column
        state.cursor_side = "left"
        state.cursor_index = 0
        handle_key(state, Key.SHIFT_SPACE)
        block = regenerate_symbol_block(FOUR_SIDED_SYMBOL, "FOUR", state)
        # still 5 pins (blank emits nothing)
        self.assertEqual(len(pins_from_block(block)), 5)
        self._assert_pins_on_edge_and_grid(block)


class StrategyRoundTripTest(unittest.TestCase):
    def test_accept_round_trip_rewrites_file(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "lib.kicad_sym"
            path.write_text(LIBRARY, encoding="utf-8")

            source = ScriptedKeySource([Key.Y, Key.Y])
            strategy = InteractiveReconstructionStrategy(
                key_source=source, renderer=_NullRenderer()
            )
            result = strategy.format_symbol_library_file(path, ["FOUR"])

            self.assertIsNotNone(result)
            self.assertTrue(result["updated"])
            self.assertEqual(result["reconstructed_symbol_names"], ["FOUR"])

            content = path.read_text(encoding="utf-8")
            # file still parses and contains our regenerated units
            self.assertEqual(content.count("("), content.count(")"))
            self.assertIn('"FOUR_0_1"', content)
            self.assertIn('"FOUR_1_1"', content)
            block = find_symbol_blocks(content)[0]
            self.assertEqual(find_matching_paren(content, block["start"]), block["end"])

    def test_cancel_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "lib.kicad_sym"
            path.write_text(LIBRARY, encoding="utf-8")

            source = ScriptedKeySource([Key.ESC, Key.ENTER])
            strategy = InteractiveReconstructionStrategy(
                key_source=source, renderer=_NullRenderer()
            )
            result = strategy.format_symbol_library_file(path, ["FOUR"])

            self.assertIsNone(result)
            self.assertEqual(path.read_text(encoding="utf-8"), LIBRARY)

    def test_move_one_pin_then_accept(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "lib.kicad_sym"
            path.write_text(LIBRARY, encoding="utf-8")

            # select left[0] (SCL), inbound RIGHT to the right side, then accept
            source = ScriptedKeySource([Key.SPACE, Key.RIGHT, Key.Y, Key.Y])
            strategy = InteractiveReconstructionStrategy(
                key_source=source, renderer=_NullRenderer()
            )
            result = strategy.format_symbol_library_file(path, ["FOUR"])
            self.assertIsNotNone(result)

            content = path.read_text(encoding="utf-8")
            block = find_symbol_blocks(content)[0]["text"]
            # SCL should now be a right-side pin (angle 180)
            scl = [pb for pb in find_list_blocks(block, "pin") if '"SCL"' in pb["text"]][0]
            at = find_list_blocks_at_depth(scl["text"], "at", 1)[0]["text"]
            _, _, angle = parse_pin_at_block(at)
            self.assertEqual(int(angle), 180)


class _NullRenderer:
    def render(self, lines):
        pass


if __name__ == "__main__":
    unittest.main()
