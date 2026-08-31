# Adversarial tests for CROSS-side text overlap in the interactive symbol editor.
#
# When names come from different sides they must never collide: left/right names
# are drawn horizontally along their pin rows, top/bottom names are drawn
# vertically down/up their pin columns. A long vertical name can otherwise reach
# into a horizontal name's row (and vice-versa). These tests:
#
#   1. model every rendered name as an axis-aligned box in mm-space (using the
#      same coarse CHAR_WIDTH_MM metric the sizing rule itself uses) and assert
#      no two boxes from different sides intersect, and every box is inside the
#      body rectangle;
#   2. drive the real strategy end-to-end (auto-accept) and re-check the output;
#   3. assert the body actually enlarged where that is the only possible fix;
#   4. instrument the TUI canvas so no cell is written by two different texts;
#   5. (when kicad-cli is present) validate every fixture exports cleanly.

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import component_importer.interactive_editor as ie
from component_importer.interactive_editor import (
    CURSOR_BLOCK,
    EditorState,
    Slot,
    render_screen,
)
from component_importer.interactive_strategy import (
    CHAR_WIDTH_MM,
    GRID_MM,
    MIN_BODY_HALF_MM,
    NAME_ZONE_GAP_MM,
    PIN_EDGE_MARGIN_MM,
    InteractiveReconstructionStrategy,
    build_state_from_symbol,
    compute_geometry,
)
from component_importer.key_source import Key, ScriptedKeySource
from component_importer.symbol_footprint_linker import find_symbol_blocks
from component_importer.symbol_style import ceil_to_grid


# ---------------------------------------------------------------------------
# mm-space collision model (coarse, matching the sizing rule's own metric)
# ---------------------------------------------------------------------------

_HALF_CHAR = CHAR_WIDTH_MM / 2.0
_ANGLE_SIDE = {0: "left", 180: "right", 270: "top", 90: "bottom"}


# Bounding box (x0, x1, y0, y1) of each rendered name, tagged with its side.
def name_boxes(geo):
    min_x, max_x = geo["min_x"], geo["max_x"]
    min_y, max_y = geo["min_y"], geo["max_y"]
    boxes = []

    for slot, x, y, angle in geo["pins"]:
        if slot.is_blank or not slot.name:
            continue

        span = len(slot.name) * CHAR_WIDTH_MM
        side = _ANGLE_SIDE[angle]

        if side == "left":
            box = (min_x, min_x + span, y - _HALF_CHAR, y + _HALF_CHAR)
        elif side == "right":
            box = (max_x - span, max_x, y - _HALF_CHAR, y + _HALF_CHAR)
        elif side == "top":
            box = (x - _HALF_CHAR, x + _HALF_CHAR, max_y - span, max_y)
        else:  # bottom
            box = (x - _HALF_CHAR, x + _HALF_CHAR, min_y, min_y + span)

        boxes.append((side, slot.name, box))

    return boxes


def _overlap(a, b, tol=1e-6):
    ix = min(a[1], b[1]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[2], b[2])
    return ix > tol and iy > tol


class _CrossCheckMixin:
    def assert_no_cross_overlap(self, geo, label=""):
        min_x, max_x = geo["min_x"], geo["max_x"]
        min_y, max_y = geo["min_y"], geo["max_y"]
        boxes = name_boxes(geo)

        for side, name, box in boxes:
            self.assertTrue(
                box[0] >= min_x - 1e-6
                and box[1] <= max_x + 1e-6
                and box[2] >= min_y - 1e-6
                and box[3] <= max_y + 1e-6,
                f"{label}: {side} name {name!r} box {box} escapes body "
                f"[{min_x},{max_x}]x[{min_y},{max_y}]",
            )

        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                s1, n1, b1 = boxes[i]
                s2, n2, b2 = boxes[j]
                if s1 != s2:
                    self.assertFalse(
                        _overlap(b1, b2),
                        f"{label}: cross overlap {s1}:{n1!r}{b1} vs {s2}:{n2!r}{b2}",
                    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_state(left=None, right=None, top=None, bottom=None):
    state = EditorState()

    def slots(names):
        return [Slot(name=nm, number=str(i + 1)) for i, nm in enumerate(names or [])]

    state.sides["left"] = slots(left)
    state.sides["right"] = slots(right)
    state.sides["top"] = slots(top)
    state.sides["bottom"] = slots(bottom)

    for side in ie.ALL_SIDES:
        if state.sides[side]:
            state.cursor_side = side
            state.cursor_index = 0
            break

    return state


# Each fixture is a documented adversarial cross-side layout.
CASES = {
    # (a)/(d): a very long top name reaching down into the first left pin's row
    "long_top_over_center_left": dict(left=["LEFTNAME8"], top=["T" * 30]),
    # (a): single top pin above a single (centred) long left pin
    "single_top_over_single_left": dict(left=["LEFTPIN_LONG"], top=["TOPPIN_ALSO_LONG"]),
    # left pins spread over several rows, one long top name over all of them
    "three_left_pins_long_top": dict(
        left=["AAAAAAAA", "BBBBBBBB", "CCCCCCCC"], top=["T" * 20]
    ),
    # multiple top columns, one wide left name underneath them
    "many_top_wide_left": dict(left=["LEFTLEFTLEFT"], top=["T" * 15, "U" * 15, "V" * 15]),
    # top name reaching a RIGHT pin's row
    "long_top_over_right": dict(right=["RIGHTNAME8"], top=["T" * 30]),
    # (c)-ish: a long bottom name rising into a left pin's row
    "long_bottom_over_left": dict(left=["LEFTNAME8"], bottom=["B" * 30]),
    # asymmetric: two tiny left names + one huge top name (no overlap expected)
    "asym_two_tiny_left_huge_top": dict(left=["A", "B"], top=["T" * 30]),
    # (b): left vs right at the same row must clear horizontally
    "left_right_same_row": dict(left=["L" * 20], right=["R" * 20]),
    # (c): top vs bottom meeting mid-body on a short chip
    "top_vs_bottom_short_chip": dict(top=["T" * 12], bottom=["B" * 12], left=["X"]),
    # (e): empty left with huge top/bottom names
    "empty_left_huge_top_bottom": dict(top=["T" * 20], bottom=["B" * 20]),
    # all four sides long simultaneously
    "four_sided_long": dict(
        left=["SCLLONG", "SDA"],
        right=["OUTPUTPIN"],
        top=["VCCLONGNAME"],
        bottom=["GNDLONGNAME"],
    ),
}


# ---------------------------------------------------------------------------
# 1. Geometry-level cross-overlap invariant
# ---------------------------------------------------------------------------


class CrossOverlapGeometryTest(_CrossCheckMixin, unittest.TestCase):
    def test_no_cross_overlap_for_all_cases(self):
        for name, kw in CASES.items():
            geo = compute_geometry(make_state(**kw), 2.54)
            self.assert_no_cross_overlap(geo, label=name)

    def test_body_enlarged_when_cross_term_is_only_fix(self):
        # A single centred left pin + a 30-char top name: the naive rule (which
        # only stacks top+bottom for the height) leaves the top name descending
        # straight through the left name's row. The cross term must enlarge the
        # body beyond that naive minimum.
        kw = CASES["long_top_over_center_left"]
        state = make_state(**kw)
        geo = compute_geometry(state, 2.54)
        actual_half_h = (geo["max_y"] - geo["min_y"]) / 2.0

        # Reconstruct the naive minimum half-height (height terms without cross).
        max_top = len(kw["top"][0])
        name_height = max_top * CHAR_WIDTH_MM + NAME_ZONE_GAP_MM
        v_extent = 0.0  # single left pin sits at y=0
        naive_half_h = ceil_to_grid(
            max(v_extent + PIN_EDGE_MARGIN_MM, name_height / 2, MIN_BODY_HALF_MM),
            GRID_MM,
        )

        self.assertGreater(
            actual_half_h,
            naive_half_h,
            "cross term must enlarge the body beyond the naive minimum",
        )
        self.assert_no_cross_overlap(geo, label="enlargement")


# ---------------------------------------------------------------------------
# 2. End-to-end through the real strategy (auto-accept), re-checked
# ---------------------------------------------------------------------------


class _Null:
    def render(self, lines):
        pass


_SIDE_ANGLE = {"left": 0, "right": 180, "top": 270, "bottom": 90}


def _make_pin(side, idx, name, num):
    angle = _SIDE_ANGLE[side]

    if side in ("left", "right"):
        x = -25.4 if side == "left" else 25.4
        y = 2.54 * idx
    else:
        y = 25.4 if side == "top" else -25.4
        x = 2.54 * idx

    return (
        f'      (pin passive line (at {x} {y} {angle}) (length 5.08)\n'
        f'        (name "{name}" (effects (font (size 1.27 1.27))))\n'
        f'        (number "{num}" (effects (font (size 1.27 1.27)))))'
    )


def make_library(name, sides):
    pins = []
    num = 1

    for side, names in sides.items():
        for idx, nm in enumerate(names):
            pins.append(_make_pin(side, idx, nm, str(num)))
            num += 1

    body = "\n".join(pins)
    symbol = (
        f'(symbol "{name}" (pin_names (offset 0.254)) (in_bom yes) (on_board yes)\n'
        f'    (property "Reference" "U" (id 0) (at 0 2.54 0)'
        f' (effects (font (size 1.27 1.27))))\n'
        f'    (property "Value" "{name}" (id 1) (at 0 0 0)'
        f' (effects (font (size 1.27 1.27))))\n'
        f'    (symbol "{name}_0_1"\n{body}))'
    )

    return f"(kicad_symbol_lib (version 20211014) (generator test)\n  {symbol}\n)\n"


class CrossOverlapStrategyTest(_CrossCheckMixin, unittest.TestCase):
    def test_strategy_output_has_no_cross_overlap(self):
        for name, sides in CASES.items():
            safe_name = "S_" + re.sub(r"\W", "_", name)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{safe_name}.kicad_sym"
                path.write_text(make_library(safe_name, sides), encoding="utf-8")

                strategy = InteractiveReconstructionStrategy(
                    key_source=ScriptedKeySource([Key.Y, Key.Y]), renderer=_Null()
                )
                result = strategy.format_symbol_library_file(path, [safe_name])
                self.assertIsNotNone(result)

                block = find_symbol_blocks(path.read_text(encoding="utf-8"))[0]["text"]
                geo = compute_geometry(build_state_from_symbol(block), 2.54)
                self.assert_no_cross_overlap(geo, label=name)


# ---------------------------------------------------------------------------
# 3. TUI canvas: no cell written by two different texts
# ---------------------------------------------------------------------------


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_BORDER = set("+-|")


class _RecordingCanvas(ie._Canvas):
    def __init__(self):
        super().__init__()
        self.collisions = []

    def put(self, row, col, text, color=None):
        for offset, char in enumerate(text):
            key = (row, col + offset)
            prev = self._cells.get(key)
            prev_char = _ANSI.sub("", prev) if prev is not None else " "

            if prev_char != " " and prev_char != char:
                # The only legitimate overwrite is the cursor block on a border.
                if not (char == CURSOR_BLOCK and prev_char in _BORDER):
                    self.collisions.append((key, prev_char, char))

        super().put(row, col, text, color)


class CrossOverlapRenderTest(unittest.TestCase):
    def _render_collisions(self, state):
        holder = {}
        real_init = _RecordingCanvas.__init__

        def spy(self):
            real_init(self)
            holder["canvas"] = self

        original = ie._Canvas
        ie._Canvas = _RecordingCanvas
        _RecordingCanvas.__init__ = spy
        try:
            render_screen(state)
        finally:
            ie._Canvas = original
            _RecordingCanvas.__init__ = real_init

        return holder["canvas"].collisions

    def test_tui_has_no_cell_collisions(self):
        for name, kw in CASES.items():
            collisions = self._render_collisions(make_state(**kw))
            self.assertEqual(collisions, [], f"{name}: TUI cell collisions {collisions}")


# ---------------------------------------------------------------------------
# 4. kicad-cli validation (skipped when kicad-cli is absent)
# ---------------------------------------------------------------------------


def _find_kicad_cli():
    for candidate in ("/usr/bin/kicad-cli", "kicad-cli"):
        found = shutil.which(candidate) or (
            candidate if Path(candidate).exists() else None
        )
        if found:
            return found
    return None


KICAD_CLI = _find_kicad_cli()


@unittest.skipUnless(KICAD_CLI, "kicad-cli not available")
class CrossOverlapKicadCliTest(unittest.TestCase):
    def test_all_fixtures_export_svg(self):
        for name, sides in CASES.items():
            safe_name = "S_" + re.sub(r"\W", "_", name)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{safe_name}.kicad_sym"
                path.write_text(make_library(safe_name, sides), encoding="utf-8")

                strategy = InteractiveReconstructionStrategy(
                    key_source=ScriptedKeySource([Key.Y, Key.Y]), renderer=_Null()
                )
                strategy.format_symbol_library_file(path, [safe_name])

                out_dir = Path(tmp) / "svg"
                out_dir.mkdir()
                proc = subprocess.run(
                    [KICAD_CLI, "sym", "export", "svg", str(path), "-o", str(out_dir)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"{name}: kicad-cli failed: {proc.stdout}\n{proc.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
