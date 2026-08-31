# Adversarial / independent test suite for the interactive symbol pin-layout
# editor. These tests were written to try to BREAK the feature: long movement
# chains around every corner, prompt state machines, rendering-overlap
# invariants, and (when kicad-cli is available) validation that the regenerated
# libraries actually parse in real KiCad plus a full CLI-level import.

import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import component_importer.interactive_editor as ie
from component_importer.interactive_editor import (
    ANSI_RED,
    ANSI_YELLOW,
    CURSOR_BLOCK,
    EditorState,
    Slot,
    handle_key,
    make_blank,
    render_screen,
    run_editor,
)
from component_importer.interactive_strategy import (
    InteractiveReconstructionStrategy,
    build_state_from_symbol,
    compute_geometry,
    regenerate_symbol_block,
)
from component_importer.key_source import Key, KeySource, ScriptedKeySource
from component_importer.symbol_footprint_linker import find_symbol_blocks
from component_importer.symbol_style import (
    find_list_blocks,
    find_list_blocks_at_depth,
    parse_pin_at_block,
    parse_pin_length_block,
)


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


class _NullRenderer:
    def render(self, lines):
        pass


class AlwaysAcceptKeySource(KeySource):
    """Feeds Key.Y forever: every symbol is accepted (Y sets the prompt, the
    next Y confirms it), so a run with any number of symbols terminates."""

    def read_key(self):
        return Key.Y


# ---------------------------------------------------------------------------
# 1. Adversarial movement sequences
# ---------------------------------------------------------------------------


class CircumnavigationTest(unittest.TestCase):
    def _single(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="X", number="1")]
        st.cursor_side = "left"
        st.cursor_index = 0
        return st

    def test_single_pin_clockwise_returns_to_start(self):
        st = self._single()
        handle_key(st, Key.SPACE)  # select X
        # left.first -> top -> right -> bottom -> left, all via corners
        handle_key(st, Key.UP)     # left.first -> top.first
        self.assertEqual(cursor(st), ("top", 0))
        self.assertEqual(names(st)["top"], ["X"])
        handle_key(st, Key.RIGHT)  # top.last -> right.first
        self.assertEqual(cursor(st), ("right", 0))
        handle_key(st, Key.DOWN)   # right.last -> bottom.last
        self.assertEqual(cursor(st), ("bottom", 0))
        handle_key(st, Key.LEFT)   # bottom.first -> left.last
        self.assertEqual(cursor(st), ("left", 0))
        self.assertEqual(names(st), {"left": ["X"], "right": [], "top": [], "bottom": []})
        self.assertTrue(st.selected)  # move-mode is retained through transport

    def test_single_pin_counterclockwise_returns_to_start(self):
        st = self._single()
        handle_key(st, Key.SPACE)
        handle_key(st, Key.DOWN)   # left.last -> bottom.first
        self.assertEqual(cursor(st), ("bottom", 0))
        handle_key(st, Key.RIGHT)  # bottom.last -> right.last
        self.assertEqual(cursor(st), ("right", 0))
        handle_key(st, Key.UP)     # right.first -> top.last
        self.assertEqual(cursor(st), ("top", 0))
        handle_key(st, Key.LEFT)   # top.first -> left.first
        self.assertEqual(cursor(st), ("left", 0))
        self.assertEqual(names(st), {"left": ["X"], "right": [], "top": [], "bottom": []})

    def test_multi_pin_full_loop_hand_computed(self):
        # Take A around the whole chip, hand-computing the expected layout.
        st = sample_state()  # left[A,B,C] right[D,E] top[T1] bottom[BM]
        handle_key(st, Key.SPACE)   # select A (left,0)
        handle_key(st, Key.UP)      # left.first -> top.first : top=[A,T1]
        self.assertEqual(names(st)["top"], ["A", "T1"])
        handle_key(st, Key.RIGHT)   # within top: swap -> top=[T1,A], (top,1)
        self.assertEqual(names(st)["top"], ["T1", "A"])
        handle_key(st, Key.RIGHT)   # top.last -> right.first : right=[A,D,E]
        self.assertEqual(names(st)["right"], ["A", "D", "E"])
        handle_key(st, Key.DOWN)    # within right -> [D,A,E]
        handle_key(st, Key.DOWN)    # within right -> [D,E,A]
        self.assertEqual(names(st)["right"], ["D", "E", "A"])
        handle_key(st, Key.DOWN)    # right.last -> bottom.last : bottom=[BM,A]
        self.assertEqual(names(st)["bottom"], ["BM", "A"])
        handle_key(st, Key.LEFT)    # within bottom -> [A,BM]
        handle_key(st, Key.LEFT)    # bottom.first -> left.last : left=[B,C,A]
        self.assertEqual(
            names(st),
            {"left": ["B", "C", "A"], "right": ["D", "E"], "top": ["T1"], "bottom": ["BM"]},
        )
        self.assertEqual(cursor(st), ("left", 2))


class CornerInvolutionTest(unittest.TestCase):
    # Each corner transport must be reversible (an involution) in both
    # directions: pushing a slot across a corner then pushing it straight back
    # must restore the exact starting layout.
    CORNERS = [
        # (from_side, index_setter, out_key, back_key)
        ("left", 0, Key.UP, Key.LEFT),     # top-left  : left.first <-> top.first
        ("left", -1, Key.DOWN, Key.LEFT),  # bot-left  : left.last  <-> bottom.first
        ("right", 0, Key.UP, Key.RIGHT),   # top-right : right.first<-> top.last
        ("right", -1, Key.DOWN, Key.RIGHT),# bot-right : right.last <-> bottom.last
        ("top", 0, Key.LEFT, Key.UP),      # top.first -> left.first ; reverse UP
        ("top", -1, Key.RIGHT, Key.UP),    # top.last -> right.first ; reverse UP
        ("bottom", 0, Key.LEFT, Key.DOWN), # bottom.first -> left.last ; reverse DOWN
        ("bottom", -1, Key.RIGHT, Key.DOWN),  # bottom.last -> right.last ; reverse DOWN
    ]

    def test_every_corner_is_reversible(self):
        for side, idx, out_key, back_key in self.CORNERS:
            st = sample_state()
            # make sure the chosen side has a slot to move
            if not st.sides[side]:
                continue
            st.cursor_side = side
            st.cursor_index = idx % len(st.sides[side])
            before = names(st)
            handle_key(st, Key.SPACE)   # select
            handle_key(st, out_key)     # transport across the corner
            self.assertNotEqual(names(st), before, f"{side}:{idx} did not transport")
            handle_key(st, back_key)    # push straight back
            self.assertEqual(
                names(st), before, f"{side}:{idx} corner not reversible via {out_key}/{back_key}"
            )


class InboundClampTest(unittest.TestCase):
    def test_inbound_index_zero(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="A"), Slot(name="B")]
        st.sides["right"] = [Slot(name="C"), Slot(name="D")]
        st.cursor_side = "left"
        st.cursor_index = 0
        handle_key(st, Key.SPACE)
        handle_key(st, Key.RIGHT)  # inbound at 0 -> right insert at 0
        self.assertEqual(names(st)["right"], ["A", "C", "D"])
        self.assertEqual(cursor(st), ("right", 0))

    def test_inbound_middle(self):
        st = sample_state()
        st.cursor_index = 1  # B
        handle_key(st, Key.SPACE)
        handle_key(st, Key.RIGHT)
        self.assertEqual(names(st)["right"], ["D", "B", "E"])
        self.assertEqual(cursor(st), ("right", 1))

    def test_inbound_beyond_opposite_length_clamps_to_append(self):
        st = EditorState()
        st.sides["left"] = [Slot(name=n) for n in ("A", "B", "C", "D")]
        st.sides["right"] = [Slot(name="E")]  # length 1
        st.cursor_side = "left"
        st.cursor_index = 3  # D, far beyond right's length
        handle_key(st, Key.SPACE)
        handle_key(st, Key.RIGHT)
        self.assertEqual(names(st)["right"], ["E", "D"])  # clamped to append
        self.assertEqual(cursor(st), ("right", 1))

    def test_inbound_top_to_bottom_and_back(self):
        st = sample_state()
        st.cursor_side = "top"
        st.cursor_index = 0
        handle_key(st, Key.SPACE)
        handle_key(st, Key.DOWN)   # top -> bottom (inbound)
        self.assertEqual(names(st)["top"], [])
        self.assertEqual(names(st)["bottom"], ["T1", "BM"])
        handle_key(st, Key.UP)     # bottom -> top (inbound back), clamped to index 0
        self.assertEqual(names(st)["top"], ["T1"])


class BlankMovementTest(unittest.TestCase):
    def test_blank_transports_through_corner(self):
        st = sample_state()
        st.cursor_side = "left"
        st.cursor_index = 0
        handle_key(st, Key.SHIFT_SPACE)  # blank at left[0]
        self.assertTrue(st.sides["left"][0].is_blank)
        handle_key(st, Key.SPACE)        # select the blank
        handle_key(st, Key.UP)           # left.first -> top.first
        self.assertEqual(cursor(st), ("top", 0))
        self.assertTrue(st.sides["top"][0].is_blank)
        self.assertEqual(st.sides["top"][0].display_name, "[blank]")

    def test_blank_inbound_move(self):
        st = sample_state()
        st.cursor_side = "left"
        st.cursor_index = 0
        handle_key(st, Key.SHIFT_SPACE)  # blank at left[0]
        handle_key(st, Key.SPACE)
        handle_key(st, Key.RIGHT)        # inbound to right
        self.assertTrue(st.sides["right"][0].is_blank)


class SingleAndOneSidedTest(unittest.TestCase):
    def test_single_pin_symbol_regenerates_and_is_on_grid(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="P", number="1")]
        st.cursor_side = "left"
        geo = compute_geometry(st, 2.54)
        self.assertEqual(len(geo["pins"]), 1)
        _assert_pins_on_edge_and_grid_state(self, geo)

    def test_all_pins_on_one_side(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="N%d" % i, number=str(i)) for i in range(6)]
        st.cursor_side = "left"
        geo = compute_geometry(st, 2.54)
        self.assertEqual(len(geo["pins"]), 6)
        _assert_pins_on_edge_and_grid_state(self, geo)
        # all six on the left edge, angle 0
        self.assertTrue(all(angle == 0 for _, _, _, angle in geo["pins"]))

    def test_empty_side_receives_first_slot_via_transport(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="A")]  # everything else empty
        st.cursor_side = "left"
        handle_key(st, Key.SPACE)
        handle_key(st, Key.UP)  # into empty top
        self.assertEqual(names(st)["top"], ["A"])
        self.assertEqual(names(st)["left"], [])


class DeleteAndInsertTest(unittest.TestCase):
    def test_delete_refuses_every_real_pin(self):
        st = sample_state()
        for side in ("left", "right", "top", "bottom"):
            st.cursor_side = side
            st.cursor_index = 0
            before = list(st.sides[side])
            handle_key(st, Key.DELETE)
            self.assertEqual(st.sides[side], before)
            self.assertIn("Refused", st.status)

    def test_delete_blank_at_side_ends(self):
        st = sample_state()
        # blank at the FIRST position
        st.cursor_side = "left"
        st.cursor_index = 0
        handle_key(st, Key.SHIFT_SPACE)
        handle_key(st, Key.DELETE)
        self.assertEqual(names(st)["left"], ["A", "B", "C"])
        # blank at the LAST position
        st.sides["left"].append(make_blank())
        st.cursor_index = len(st.sides["left"]) - 1
        handle_key(st, Key.DELETE)
        self.assertEqual(names(st)["left"], ["A", "B", "C"])

    def test_shift_space_inserts_on_each_side(self):
        for side in ("left", "right", "top", "bottom"):
            st = sample_state()
            st.cursor_side = side
            st.cursor_index = 0
            n_before = len(st.sides[side])
            handle_key(st, Key.SHIFT_SPACE)
            self.assertEqual(len(st.sides[side]), n_before + 1)
            self.assertTrue(st.sides[side][0].is_blank)
            self.assertEqual(cursor(st), (side, 0))

    def test_shift_space_ignored_in_move_mode(self):
        st = sample_state()
        handle_key(st, Key.SPACE)  # move mode
        n_before = len(st.sides["left"])
        handle_key(st, Key.SHIFT_SPACE)
        self.assertEqual(len(st.sides["left"]), n_before)


class NoCrashTest(unittest.TestCase):
    def test_empty_state_all_keys_survive(self):
        st = EditorState()
        for key in (Key.DOWN, Key.UP, Key.LEFT, Key.RIGHT, Key.SPACE,
                    Key.SHIFT_SPACE, Key.DELETE):
            handle_key(st, key)  # must not raise
        self.assertFalse(st.selected)

    def test_navigate_from_stale_cursor_index(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="A"), Slot(name="B")]
        st.cursor_side = "left"
        st.cursor_index = 99
        handle_key(st, Key.DOWN)
        self.assertIn(cursor(st), [("left", 0), ("left", 1)])


# ---------------------------------------------------------------------------
# 2. Prompt state machines
# ---------------------------------------------------------------------------


class PromptStateMachineTest(unittest.TestCase):
    def test_accept_needs_two_ys_intervening_key_resumes(self):
        st = sample_state()
        # Y (arm accept) -> OTHER (resume) -> Y -> Y (accept)
        src = ScriptedKeySource([Key.Y, Key.OTHER, Key.Y, Key.Y])
        self.assertTrue(run_editor(st, src))

    def test_single_y_then_other_stays_in_editor(self):
        st = sample_state()
        handle_key(st, Key.Y)
        self.assertEqual(st.pending, "accept")
        self.assertIsNone(handle_key(st, Key.OTHER))
        self.assertIsNone(st.pending)
        self.assertIn("Cancelled accept", st.status)

    def test_cancel_needs_esc_then_enter(self):
        st = sample_state()
        src = ScriptedKeySource([Key.ESC, Key.OTHER, Key.ESC, Key.ENTER])
        self.assertFalse(run_editor(st, src))

    def test_esc_then_non_enter_resumes(self):
        st = sample_state()
        handle_key(st, Key.ESC)
        self.assertEqual(st.pending, "exit")
        self.assertIsNone(handle_key(st, Key.Y))  # any non-Enter resumes
        self.assertIsNone(st.pending)
        self.assertIn("Resumed", st.status)

    def test_prompts_interleaved_with_moves(self):
        st = sample_state()
        # move, arm-accept then bail, move again, finally accept
        src = ScriptedKeySource(
            [Key.SPACE, Key.DOWN, Key.SPACE, Key.Y, Key.OTHER, Key.DOWN, Key.Y, Key.Y]
        )
        self.assertTrue(run_editor(st, src))
        # after moving A down once (B,A,C) then navigating, A/B swapped stays
        self.assertEqual(names(st)["left"], ["B", "A", "C"])

    def test_cancel_leaves_file_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lib.kicad_sym"
            path.write_text(LIBRARY, encoding="utf-8")
            before = hashlib.sha256(path.read_bytes()).hexdigest()

            strat = InteractiveReconstructionStrategy(
                key_source=ScriptedKeySource([Key.ESC, Key.ENTER]),
                renderer=_NullRenderer(),
            )
            result = strat.format_symbol_library_file(path, ["FOUR"])

            self.assertIsNone(result)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(before, after)

    def test_move_then_cancel_still_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lib.kicad_sym"
            path.write_text(LIBRARY, encoding="utf-8")
            before = path.read_bytes()

            # lots of movement, then cancel: file must be untouched
            keys = [Key.SPACE, Key.DOWN, Key.UP, Key.RIGHT, Key.SPACE, Key.ESC, Key.ENTER]
            strat = InteractiveReconstructionStrategy(
                key_source=ScriptedKeySource(keys), renderer=_NullRenderer()
            )
            result = strat.format_symbol_library_file(path, ["FOUR"])
            self.assertIsNone(result)
            self.assertEqual(path.read_bytes(), before)


# ---------------------------------------------------------------------------
# 3. Rendering invariants
# ---------------------------------------------------------------------------


class RenderingInvariantTest(unittest.TestCase):
    def _long_state(self):
        st = EditorState()
        st.sides["left"] = [Slot(name="LEFT_TWENTYCHAR_NAME_%02d" % i, number=str(i)) for i in range(3)]
        st.sides["right"] = [Slot(name="RIGHT_TWENTYCHAR_NAME_%02d" % i, number=str(10 + i)) for i in range(2)]
        st.sides["top"] = [Slot(name="TOP_TWENTYCHAR_NAME_%02d" % i, number=str(20 + i)) for i in range(4)]
        st.sides["bottom"] = [Slot(name="BOTTOM_TWENTYCHAR_%02d" % i, number=str(30 + i)) for i in range(4)]
        st.cursor_side = "left"
        st.cursor_index = 0
        return st

    def test_no_text_overlaps_with_long_names_on_all_sides(self):
        st = self._long_state()
        collisions = []
        writes = {}
        original = ie._Canvas.put

        def spy(self, row, col, text, color=None):
            for offset, char in enumerate(text):
                key = (row, col + offset)
                prev = writes.get(key)
                # the cursor block deliberately overwrites the border glyph
                if (
                    prev is not None
                    and prev not in (" ", "|", "-", "+")
                    and char not in (" ", "|", "-", "+", CURSOR_BLOCK)
                    and prev != char
                ):
                    collisions.append((key, prev, char))
                writes[key] = char
            return original(self, row, col, text, color)

        ie._Canvas.put = spy
        try:
            render_screen(st)
        finally:
            ie._Canvas.put = original

        self.assertEqual(collisions, [], f"text glyphs overlapped: {collisions}")

    def test_top_bottom_names_are_vertical(self):
        st = build_state_from_symbol(FOUR_SIDED_SYMBOL)
        chip = [re.sub(r"\x1b\[[0-9]+m", "", ln) for ln in render_screen(st)]
        chip = chip[: chip.index("")]
        # no horizontal run of a top/bottom name
        self.assertFalse(any("VCC" in ln for ln in chip))
        self.assertFalse(any("GND" in ln for ln in chip))
        # VCC stacked down a single column
        rows_with_v = [r for r, ln in enumerate(chip) if "V" in ln]
        self.assertTrue(rows_with_v)
        v_row = rows_with_v[0]
        v_col = chip[v_row].index("V")
        stacked = "".join(chip[v_row + o][v_col] for o in range(3))
        self.assertEqual(stacked, "VCC")

    def test_cursor_block_present_exactly_once(self):
        st = self._long_state()
        joined = "\n".join(render_screen(st))
        self.assertEqual(joined.count(CURSOR_BLOCK), 1)

    def test_nav_mode_has_yellow_no_red(self):
        st = self._long_state()
        joined = "\n".join(render_screen(st))
        self.assertIn(ANSI_YELLOW, joined)
        self.assertNotIn(ANSI_RED, joined)

    def test_move_mode_has_red_no_yellow(self):
        st = self._long_state()
        handle_key(st, Key.SPACE)  # select cursor slot
        joined = "\n".join(render_screen(st))
        self.assertIn(ANSI_RED, joined)
        # the selected slot is red, so the cursor colour is never yellow
        self.assertNotIn(ANSI_YELLOW, joined)

    def test_cursor_on_each_side_still_one_block(self):
        for side in ("left", "right", "top", "bottom"):
            st = self._long_state()
            st.cursor_side = side
            st.cursor_index = 0
            joined = "\n".join(render_screen(st))
            self.assertEqual(joined.count(CURSOR_BLOCK), 1, f"side {side}")


# ---------------------------------------------------------------------------
# geometry helpers shared by the geometry / kicad tests
# ---------------------------------------------------------------------------


def _pins_from_block(block_text):
    result = []
    for pb in find_list_blocks(block_text, "pin"):
        at = find_list_blocks_at_depth(pb["text"], "at", 1)[0]["text"]
        length = find_list_blocks_at_depth(pb["text"], "length", 1)[0]["text"]
        x, y, angle = parse_pin_at_block(at)
        L = parse_pin_length_block(length)
        result.append((x, y, angle, L))
    return result


def _body_rect(block_text):
    rect = find_list_blocks(block_text, "rectangle")[0]["text"]
    sx, sy = map(float, re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", rect).groups())
    ex, ey = map(float, re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", rect).groups())
    return min(sx, ex), max(sx, ex), min(sy, ey), max(sy, ey)


def _assert_pins_on_edge_and_grid_state(test, geo):
    min_x, max_x, min_y, max_y = geo["min_x"], geo["max_x"], geo["min_y"], geo["max_y"]
    for slot, x, y, angle in geo["pins"]:
        dx = round(math.cos(math.radians(angle)))
        dy = round(math.sin(math.radians(angle)))
        ix, iy = x + dx * geo["pin_length"], y + dy * geo["pin_length"]
        on_edge = (
            (abs(ix - min_x) < 1e-6 and dx == 1)
            or (abs(ix - max_x) < 1e-6 and dx == -1)
            or (abs(iy - min_y) < 1e-6 and dy == 1)
            or (abs(iy - max_y) < 1e-6 and dy == -1)
        )
        test.assertTrue(on_edge, f"pin inner ({ix},{iy}) not on body edge")
        for value in (x, y):
            test.assertAlmostEqual(value / 2.54, round(value / 2.54), places=6)
    for value in (min_x, max_x, min_y, max_y):
        test.assertAlmostEqual(value / 2.54, round(value / 2.54), places=6)


def _assert_block_on_edge_and_grid(test, block_text):
    min_x, max_x, min_y, max_y = _body_rect(block_text)
    for x, y, angle, length in _pins_from_block(block_text):
        dx = round(math.cos(math.radians(angle)))
        dy = round(math.sin(math.radians(angle)))
        ix, iy = x + dx * length, y + dy * length
        on_edge = (
            (abs(ix - min_x) < 1e-6 and dx == 1)
            or (abs(ix - max_x) < 1e-6 and dx == -1)
            or (abs(iy - min_y) < 1e-6 and dy == 1)
            or (abs(iy - max_y) < 1e-6 and dy == -1)
        )
        test.assertTrue(on_edge, f"pin ({x},{y},{angle}) inner ({ix},{iy}) not on edge")
        for value in (x, y):
            test.assertAlmostEqual(value / 2.54, round(value / 2.54), places=6)
    for value in (min_x, max_x, min_y, max_y):
        test.assertAlmostEqual(value / 2.54, round(value / 2.54), places=6)


class RegenerationPreservationTest(unittest.TestCase):
    def test_properties_and_alternates_preserved(self):
        sym = (
            '(symbol "WIDGET" (pin_names (offset 0.254)) (in_bom yes) (on_board yes)\n'
            '    (property "Reference" "U" (id 0) (at 0 2.54 0) (effects (font (size 1.27 1.27))))\n'
            '    (property "Value" "WIDGET" (id 1) (at 0 0 0) (effects (font (size 1.27 1.27))))\n'
            '    (property "Footprint" "MyParts:SOT23" (id 2) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            '    (symbol "WIDGET_0_1"\n'
            '      (pin input line (at -10.16 0 0) (length 5.08)\n'
            '        (name "IN" (effects (font (size 1.27 1.27))))\n'
            '        (number "1" (effects (font (size 1.27 1.27))))\n'
            '        (alternate "ALT" input line))\n'
            '      (pin output line (at 10.16 0 180) (length 5.08)\n'
            '        (name "OUT" (effects (font (size 1.27 1.27))))\n'
            '        (number "2" (effects (font (size 1.27 1.27)))))))'
        )
        state = build_state_from_symbol(sym)
        out = regenerate_symbol_block(sym, "WIDGET", state)
        self.assertIn('"Reference" "U"', out)
        self.assertIn("MyParts:SOT23", out)
        self.assertIn('(alternate "ALT" input line)', out)
        self.assertEqual(out.count("("), out.count(")"))
        _assert_block_on_edge_and_grid(self, out)


# ---------------------------------------------------------------------------
# 4. Real-KiCad validation (kicad-cli)
# ---------------------------------------------------------------------------


def _find_kicad_cli():
    for candidate in ("/usr/bin/kicad-cli", "kicad-cli"):
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    return None


KICAD_CLI = _find_kicad_cli()


def _regen_library(keys):
    """Return the LIBRARY text after driving the strategy over an in-memory copy."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "lib.kicad_sym"
        path.write_text(LIBRARY, encoding="utf-8")
        strat = InteractiveReconstructionStrategy(
            key_source=ScriptedKeySource(list(keys)), renderer=_NullRenderer()
        )
        strat.format_symbol_library_file(path, ["FOUR"])
        return path.read_text(encoding="utf-8")


@unittest.skipUnless(KICAD_CLI, "kicad-cli not available")
class KicadCliValidationTest(unittest.TestCase):
    def _validate(self, lib_text):
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / "out.kicad_sym"
            lib.write_text(lib_text, encoding="utf-8")
            out_dir = Path(tmp) / "svg"
            out_dir.mkdir()
            proc = subprocess.run(
                [KICAD_CLI, "sym", "export", "svg", str(lib), "-o", str(out_dir)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                proc.returncode, 0, f"kicad-cli failed: {proc.stdout}\n{proc.stderr}"
            )
            # a copy also survives the format upgrader
            upg = Path(tmp) / "upg.kicad_sym"
            upg.write_text(lib_text, encoding="utf-8")
            proc2 = subprocess.run(
                [KICAD_CLI, "sym", "upgrade", "--force", str(upg)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc2.returncode, 0, f"upgrade failed: {proc2.stderr}")

    def test_four_sided_edited_parses(self):
        # move SCL inbound to the right side, then accept
        self._validate(_regen_library([Key.SPACE, Key.RIGHT, Key.Y, Key.Y]))

    def test_symbol_with_blanks_parses(self):
        self._validate(
            _regen_library([Key.SHIFT_SPACE, Key.DOWN, Key.DOWN, Key.SHIFT_SPACE, Key.Y, Key.Y])
        )

    def test_untouched_after_cancel_parses(self):
        # cancel leaves the merged library; it must still be valid KiCad
        text = _regen_library([Key.ESC, Key.ENTER])
        self.assertEqual(text, LIBRARY)
        self._validate(text)


# ---------------------------------------------------------------------------
# 5. Full-pipeline e2e (real import_cad_zip through the interactive strategy)
# ---------------------------------------------------------------------------

_ZIP_DIR = Path("/home/ux/kicad-importer")
_PDU_SRC = _ZIP_DIR / "PrinterWorks" / "PDU20V"
_E2E_ZIPS = ["ul_TPS631000DRLR.zip", "ul_BQ28Z610DRZR.zip"]
_E2E_READY = (
    KICAD_CLI is not None
    and _PDU_SRC.is_dir()
    and all((_ZIP_DIR / z).exists() for z in _E2E_ZIPS)
)


@unittest.skipUnless(_E2E_READY, "e2e fixtures / kicad-cli not available")
class FullPipelineE2ETest(unittest.TestCase):
    def test_interactive_import_into_scratch_project(self):
        from component_importer.cad_zip_importer import import_cad_zip

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "PDU20V"
            shutil.copytree(_PDU_SRC, root)

            for zip_name, part in zip(_E2E_ZIPS, ("TPS631000DRLR", "BQ28Z610DRZR")):
                strat = InteractiveReconstructionStrategy(
                    key_source=AlwaysAcceptKeySource(), renderer=_NullRenderer()
                )
                result = import_cad_zip(
                    _ZIP_DIR / zip_name,
                    root,
                    "MyParts",
                    part,
                    formatting_strategy=strat,
                )
                style = result.get("symbol_style_update")
                self.assertIsNotNone(style, "interactive strategy did not run")
                self.assertIn(part, style["reconstructed_symbol_names"])

            # the regenerated library must parse in real KiCad and be on-grid
            lib = root / "libraries" / "MyParts.kicad_sym"
            self.assertTrue(lib.exists())
            out_dir = Path(tmp) / "svg"
            out_dir.mkdir()
            proc = subprocess.run(
                [KICAD_CLI, "sym", "export", "svg", str(lib), "-o", str(out_dir)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, f"{proc.stdout}\n{proc.stderr}")

            content = lib.read_text(encoding="utf-8")
            for block in find_symbol_blocks(content):
                if block.get("name") in ("TPS631000DRLR", "BQ28Z610DRZR"):
                    _assert_block_on_edge_and_grid(self, block["text"])


if __name__ == "__main__":
    unittest.main()
