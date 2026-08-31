# Pure editor core for the interactive symbol-reconstruction TUI.
#
# This module is Qt-free and, except for the optional terminal driver at the very
# bottom, side-effect free. The editor state, all movement rules and the screen
# renderer are pure functions of the state so they can be snapshot-tested with a
# ScriptedKeySource. Colours are emitted as raw ANSI escape codes embedded in the
# rendered lines.
#
# Geometry vocabulary
# -------------------
# The chip has four sides: two vertical (left, right) and two horizontal
# (top, bottom). Each side holds an ordered list of slots. A slot is either a
# real pin or a blank spacer; both are the same Slot type so movement code never
# special-cases blanks. Side reading order matches the source extraction order:
#   left  : top -> bottom
#   right : top -> bottom
#   top   : left -> right
#   bottom: left -> right

import re
from dataclasses import dataclass, field

from component_importer.key_source import Key, KeySource


# Matches SGR (colour) escape sequences so the visible width of a rendered line
# can be measured without counting the invisible escape bytes.
_ANSI_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")


# ANSI colour codes used by the renderer
ANSI_RESET = "\x1b[0m"
ANSI_YELLOW = "\x1b[33m"
ANSI_RED = "\x1b[31m"

# Character drawn on the chip edge at the cursor slot
CURSOR_BLOCK = "█"  # solid block

# Rendered name of a blank slot
BLANK_NAME = "[blank]"

# The four sides and their orientation
VERTICAL_SIDES = ("left", "right")
HORIZONTAL_SIDES = ("top", "bottom")
ALL_SIDES = ("left", "right", "top", "bottom")

# Cyclic order used for plain navigation across sides
NAV_CYCLE = ("left", "top", "right", "bottom")

# Corner-transport mapping. When a selected slot is pushed past the first/last
# position of its side it crosses the shared corner into the neighbouring,
# perpendicular side. The mapping is the geometrically continuous one: a slot
# leaving a side re-enters the adjacent side at the very corner they share.
#
#   left.first  <-> top.first      (top-left corner)
#   left.last   <-> bottom.first   (bottom-left corner)
#   right.first <-> top.last        (top-right corner)
#   right.last  <-> bottom.last     (bottom-right corner)
#
# "first" inserts at index 0; "last" appends to the end of the target side.
CORNER_TRANSPORT = {
    ("left", "first"): ("top", "first"),
    ("left", "last"): ("bottom", "first"),
    ("right", "first"): ("top", "last"),
    ("right", "last"): ("bottom", "last"),
    ("top", "first"): ("left", "first"),
    ("top", "last"): ("right", "first"),
    ("bottom", "first"): ("left", "last"),
    ("bottom", "last"): ("right", "last"),
}


# One slot on a side: a real pin or a blank spacer
@dataclass
class Slot:
    is_blank: bool = False
    number: str = ""
    name: str = ""
    etype: str = "passive"
    length: float = 2.54
    # Verbatim source pin text, kept so regeneration can preserve alternates/effects
    source_text: str = ""

    # Text shown for this slot in the editor
    @property
    def display_name(self) -> str:
        return BLANK_NAME if self.is_blank else self.name


# Build a blank slot
def make_blank() -> Slot:
    return Slot(is_blank=True, name=BLANK_NAME)


# Full mutable editor state
@dataclass
class EditorState:
    sides: dict = field(default_factory=lambda: {side: [] for side in ALL_SIDES})
    cursor_side: str = "left"
    cursor_index: int = 0
    # True when a slot is selected and move-mode arrow semantics apply
    selected: bool = False
    # None, "accept" or "exit" while a confirmation prompt is showing
    pending: str | None = None
    # Transient status line message
    status: str = ""

    # The list of slots on the side under the cursor
    def current_side_slots(self) -> list:
        return self.sides[self.cursor_side]

    # The slot under the cursor, or None when the side is empty
    def current_slot(self):
        slots = self.current_side_slots()

        if 0 <= self.cursor_index < len(slots):
            return slots[self.cursor_index]

        return None


# ---------------------------------------------------------------------------
# Cursor placement helpers
# ---------------------------------------------------------------------------


# Clamp the cursor index into the current side's valid range
def _clamp_cursor(state: EditorState) -> None:
    slots = state.current_side_slots()

    if not slots:
        state.cursor_index = 0
        return

    state.cursor_index = max(0, min(state.cursor_index, len(slots) - 1))


# Move the cursor to the first non-empty side, used when the current side empties
def _ensure_cursor_on_nonempty_side(state: EditorState) -> None:
    if state.current_side_slots():
        return

    for side in NAV_CYCLE:
        if state.sides[side]:
            state.cursor_side = side
            state.cursor_index = 0
            return

    # Everything is empty: keep the cursor where it is
    state.cursor_index = 0


# ---------------------------------------------------------------------------
# Navigation mode (no slot selected)
# ---------------------------------------------------------------------------


# Flatten all slots into one addressable sequence following NAV_CYCLE order
def _flat_positions(state: EditorState) -> list:
    positions = []

    for side in NAV_CYCLE:
        for index in range(len(state.sides[side])):
            positions.append((side, index))

    return positions


# Move the cursor one step through the flattened slot sequence
def _navigate(state: EditorState, key: Key) -> None:
    positions = _flat_positions(state)

    if not positions:
        return

    try:
        current = positions.index((state.cursor_side, state.cursor_index))
    except ValueError:
        current = 0

    # DOWN/RIGHT advance, UP/LEFT retreat, both wrapping around the perimeter
    if key in (Key.DOWN, Key.RIGHT):
        current = (current + 1) % len(positions)
    elif key in (Key.UP, Key.LEFT):
        current = (current - 1) % len(positions)

    state.cursor_side, state.cursor_index = positions[current]


# ---------------------------------------------------------------------------
# Move mode (a slot is selected)
# ---------------------------------------------------------------------------


# Classify an arrow for the selected slot's current side
def _arrow_role(side: str, key: Key) -> str:
    # Returns one of: "back", "forward", "inbound", "outbound"
    if side in VERTICAL_SIDES:
        if key == Key.UP:
            return "back"
        if key == Key.DOWN:
            return "forward"
        # Inbound points into the body: RIGHT on left side, LEFT on right side
        if (side == "left" and key == Key.RIGHT) or (side == "right" and key == Key.LEFT):
            return "inbound"
        return "outbound"

    # Horizontal sides
    if key == Key.LEFT:
        return "back"
    if key == Key.RIGHT:
        return "forward"
    # Inbound: DOWN on top side, UP on bottom side
    if (side == "top" and key == Key.DOWN) or (side == "bottom" and key == Key.UP):
        return "inbound"
    return "outbound"


# The side opposite a given side (left<->right, top<->bottom)
def _opposite_side(side: str) -> str:
    return {
        "left": "right",
        "right": "left",
        "top": "bottom",
        "bottom": "top",
    }[side]


# Swap the selected slot with its neighbour inside the same side
def _shift_within_side(state: EditorState, direction: int) -> None:
    slots = state.current_side_slots()
    index = state.cursor_index
    neighbour = index + direction

    slots[index], slots[neighbour] = slots[neighbour], slots[index]
    state.cursor_index = neighbour


# Transport the selected slot across a corner into the adjacent side
def _transport_corner(state: EditorState, end: str) -> None:
    from_side = state.cursor_side
    to_side, position = CORNER_TRANSPORT[(from_side, end)]

    slot = state.current_side_slots().pop(state.cursor_index)
    target = state.sides[to_side]

    if position == "first":
        target.insert(0, slot)
        new_index = 0
    else:
        target.append(slot)
        new_index = len(target) - 1

    state.cursor_side = to_side
    state.cursor_index = new_index
    _ensure_cursor_on_nonempty_side(state)


# Move the selected slot straight across the body to the opposite side
def _move_inbound(state: EditorState) -> None:
    from_side = state.cursor_side
    to_side = _opposite_side(from_side)
    index = state.cursor_index

    slot = state.current_side_slots().pop(index)
    target = state.sides[to_side]

    # Same positional index, clamped into the opposite side, shifting as needed
    insert_index = min(index, len(target))
    target.insert(insert_index, slot)

    state.cursor_side = to_side
    state.cursor_index = insert_index
    _ensure_cursor_on_nonempty_side(state)


# Apply move-mode semantics for the selected slot
def _move_selected(state: EditorState, key: Key) -> None:
    slots = state.current_side_slots()

    if not slots:
        return

    side = state.cursor_side
    index = state.cursor_index
    role = _arrow_role(side, key)

    if role == "outbound":
        # Arrow pointing out of the body is a deliberate no-op
        return

    if role == "inbound":
        _move_inbound(state)
        return

    if role == "back":
        if index > 0:
            _shift_within_side(state, -1)
        else:
            _transport_corner(state, "first")
        return

    if role == "forward":
        if index < len(slots) - 1:
            _shift_within_side(state, +1)
        else:
            _transport_corner(state, "last")
        return


# ---------------------------------------------------------------------------
# Blank insert / delete
# ---------------------------------------------------------------------------


# Insert a new blank slot at the cursor position
def _insert_blank(state: EditorState) -> None:
    slots = state.current_side_slots()
    index = state.cursor_index if slots else 0
    slots.insert(index, make_blank())
    state.cursor_index = index
    state.status = "Inserted blank."


# Delete a blank under the cursor; refuse to delete real pins
def _delete_blank(state: EditorState) -> None:
    slot = state.current_slot()

    if slot is None:
        return

    if not slot.is_blank:
        state.status = "Refused: only blanks can be deleted."
        return

    state.current_side_slots().pop(state.cursor_index)
    _clamp_cursor(state)
    _ensure_cursor_on_nonempty_side(state)
    state.status = "Deleted blank."


# ---------------------------------------------------------------------------
# Key handling / run loop
# ---------------------------------------------------------------------------


# Handle one key. Returns True on accept, False on cancel, None to keep editing.
def handle_key(state: EditorState, key: Key) -> bool | None:
    # Confirmation prompts intercept the next key first
    if state.pending == "accept":
        if key == Key.Y:
            return True
        state.pending = None
        state.status = "Cancelled accept."
        return None

    if state.pending == "exit":
        if key == Key.ENTER:
            return False
        state.pending = None
        state.status = "Resumed editing."
        return None

    state.status = ""

    if key == Key.Y:
        state.pending = "accept"
        return None

    if key == Key.ESC:
        state.pending = "exit"
        return None

    if key == Key.SPACE:
        # Toggle move mode, but only if there is a slot to select
        if state.current_slot() is not None:
            state.selected = not state.selected
        return None

    if key == Key.SHIFT_SPACE:
        # Inserting a blank only makes sense in navigation mode
        if not state.selected:
            _insert_blank(state)
        return None

    if key == Key.DELETE:
        if not state.selected:
            _delete_blank(state)
        return None

    if key in (Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT):
        if state.selected:
            _move_selected(state, key)
        else:
            _navigate(state, key)
        return None

    return None


# Run the editor loop against a key source and optional render callback.
# Returns True when the layout was accepted, False when cancelled.
def run_editor(state: EditorState, key_source: KeySource, on_render=None) -> bool:
    while True:
        if on_render is not None:
            on_render(render_screen(state))

        key = key_source.read_key()
        result = handle_key(state, key)

        if result is not None:
            return result


# ---------------------------------------------------------------------------
# Rendering (pure function of state -> list[str])
# ---------------------------------------------------------------------------


# Colour a run of text unless colour is None
def _colorize(text: str, color: str | None) -> str:
    if color is None:
        return text

    return f"{color}{text}{ANSI_RESET}"


# Decide the colour for a slot given whether it is the cursor / selected slot
def _slot_color(is_cursor: bool, is_selected: bool) -> str | None:
    if is_selected:
        return ANSI_RED
    if is_cursor:
        return ANSI_YELLOW
    return None


# A tiny mutable character canvas addressed by (row, col)
class _Canvas:
    def __init__(self):
        self._cells: dict = {}
        self.max_row = 0
        self.max_col = 0

    # Place already-formatted text starting at (row, col); one cell per char
    def put(self, row: int, col: int, text: str, color: str | None = None) -> None:
        for offset, char in enumerate(text):
            self._cells[(row, col + offset)] = _colorize(char, color)
            self.max_col = max(self.max_col, col + offset)

        self.max_row = max(self.max_row, row)

    # Render the canvas into a list of strings
    def to_lines(self) -> list[str]:
        lines = []

        for row in range(self.max_row + 1):
            chars = []

            for col in range(self.max_col + 1):
                chars.append(self._cells.get((row, col), " "))

            lines.append("".join(chars).rstrip())

        return lines


# Max display-name length across a list of slots (0 for an empty side)
def _max_name_len(slots: list) -> int:
    return max((len(slot.display_name) for slot in slots), default=0)


# Max pin-number length across a list of slots
def _max_number_len(slots: list) -> int:
    return max((len(slot.number) for slot in slots), default=0)


# Render the whole editor screen as a list of strings (with ANSI colour codes)
def render_screen(state: EditorState) -> list[str]:
    sides = state.sides
    left, right = sides["left"], sides["right"]
    top, bottom = sides["top"], sides["bottom"]

    # Layout metrics -------------------------------------------------------
    left_name_w = _max_name_len(left)
    right_name_w = _max_name_len(right)
    left_num_w = _max_number_len(left)
    right_num_w = _max_number_len(right)

    top_name_h = _max_name_len(top)
    bottom_name_h = _max_name_len(bottom)

    # Column width for a single top/bottom slot (holds its vertical name + number)
    tb_slots = top + bottom
    col_w = max(1, _max_number_len(tb_slots))
    col_gap = 1

    n_mid_cols = max(len(top), len(bottom))
    mid_w = n_mid_cols * col_w + max(0, n_mid_cols - 1) * col_gap

    zone_gap = 2
    interior_w = left_name_w + zone_gap + mid_w + zone_gap + right_name_w
    interior_w = max(interior_w, mid_w, 4)

    n_mid_rows = max(len(left), len(right))
    zone_gap_row = 1
    interior_h = top_name_h + zone_gap_row + n_mid_rows + zone_gap_row + bottom_name_h
    interior_h = max(interior_h, n_mid_rows, 2)

    # Absolute canvas coordinates -----------------------------------------
    # Columns: [left numbers][border][interior][border][right numbers]
    left_num_col = 0
    left_border_col = left_num_w + 1
    interior_col0 = left_border_col + 1
    right_border_col = interior_col0 + interior_w
    right_num_col = right_border_col + 1

    # Rows: [top numbers][border][interior][border][bottom numbers]
    top_num_row = 0
    top_border_row = 1
    interior_row0 = top_border_row + 1
    bottom_border_row = interior_row0 + interior_h
    bottom_num_row = bottom_border_row + 1

    canvas = _Canvas()

    # Draw the body rectangle border --------------------------------------
    for col in range(interior_col0, right_border_col):
        canvas.put(top_border_row, col, "-")
        canvas.put(bottom_border_row, col, "-")

    for row in range(interior_row0, bottom_border_row):
        canvas.put(row, left_border_col, "|")
        canvas.put(row, right_border_col, "|")

    canvas.put(top_border_row, left_border_col, "+")
    canvas.put(top_border_row, right_border_col, "+")
    canvas.put(bottom_border_row, left_border_col, "+")
    canvas.put(bottom_border_row, right_border_col, "+")

    cursor = (state.cursor_side, state.cursor_index)

    # Left side -----------------------------------------------------------
    for index, slot in enumerate(left):
        row = interior_row0 + top_name_h + zone_gap_row + index
        is_cursor = cursor == ("left", index)
        color = _slot_color(is_cursor, is_cursor and state.selected)

        # Name inside the edge (left-aligned in the left name zone)
        canvas.put(row, interior_col0, slot.display_name, color)

        # Number outside the edge (right-aligned in the left number zone)
        if slot.number:
            num = slot.number.rjust(left_num_w)
            canvas.put(row, left_num_col, num, color)

        # Cursor marks the edge with a solid block
        if is_cursor:
            canvas.put(row, left_border_col, CURSOR_BLOCK, color)

    # Right side ----------------------------------------------------------
    for index, slot in enumerate(right):
        row = interior_row0 + top_name_h + zone_gap_row + index
        is_cursor = cursor == ("right", index)
        color = _slot_color(is_cursor, is_cursor and state.selected)

        # Name inside the edge (right-aligned against the right border)
        name = slot.display_name
        canvas.put(row, right_border_col - len(name), name, color)

        # Number outside the edge (left-aligned in the right number zone)
        if slot.number:
            canvas.put(row, right_num_col, slot.number, color)

        if is_cursor:
            canvas.put(row, right_border_col, CURSOR_BLOCK, color)

    # Middle-column origin for top/bottom slots
    mid_col0 = interior_col0 + left_name_w + zone_gap

    # Top side (vertical names hanging down from the top edge) -------------
    for index, slot in enumerate(top):
        col = mid_col0 + index * (col_w + col_gap)
        is_cursor = cursor == ("top", index)
        color = _slot_color(is_cursor, is_cursor and state.selected)

        # Vertical name: one character per row, top -> down, inside the body
        name = slot.display_name
        for char_index, char in enumerate(name):
            canvas.put(interior_row0 + char_index, col, char, color)

        # Number horizontally above the top edge (outside)
        if slot.number:
            canvas.put(top_num_row, col, slot.number, color)

        if is_cursor:
            canvas.put(top_border_row, col, CURSOR_BLOCK, color)

    # Bottom side (vertical names rising toward the bottom edge) -----------
    for index, slot in enumerate(bottom):
        col = mid_col0 + index * (col_w + col_gap)
        is_cursor = cursor == ("bottom", index)
        color = _slot_color(is_cursor, is_cursor and state.selected)

        name = slot.display_name
        # Place the name so its last character sits just above the bottom edge
        name_start = bottom_border_row - len(name)
        for char_index, char in enumerate(name):
            canvas.put(name_start + char_index, col, char, color)

        # Number horizontally below the bottom edge (outside)
        if slot.number:
            canvas.put(bottom_num_row, col, slot.number, color)

        if is_cursor:
            canvas.put(bottom_border_row, col, CURSOR_BLOCK, color)

    lines = canvas.to_lines()

    # Status / help footer ------------------------------------------------
    lines.append("")

    if state.pending == "accept":
        lines.append("Accept this layout? press Y to confirm, any other key to resume.")
    elif state.pending == "exit":
        lines.append("Exit without changes? press Enter to cancel import, any other key to resume.")
    else:
        mode = "MOVE" if state.selected else "NAV"
        lines.append(
            f"[{mode}] arrows: move  space: select/deselect  "
            "S: insert blank  d: delete blank  y: accept  Esc: cancel"
        )

    if state.status:
        lines.append(state.status)

    return lines


# Visible width of a rendered line, ignoring ANSI colour escape sequences
def _visible_len(line: str) -> int:
    return len(_ANSI_SGR_RE.sub("", line))


# Centre the editor screen within a (width, height) character grid. render_screen
# stays a tight-bounding-box producer; centring is a pure, separately testable
# transform applied just before drawing.
#
# The chip is centred horizontally on its own width (uniform leading spaces), so
# the much wider help/status footer never drags it off-centre. The footer stays
# full-width at column 0 below the chip (matching the Qt editor, whose help text
# is a separate label under the canvas). The whole block is centred vertically by
# prepending blank rows. Every pad is clamped at 0, so content larger than the
# grid anchors top-left and never gets negative padding.
def center_lines(
    chip_lines: list[str], footer_lines: list[str], width: int, height: int
) -> list[str]:
    if not chip_lines and not footer_lines:
        return []

    chip_width = max((_visible_len(line) for line in chip_lines), default=0)
    left_pad = max(0, (width - chip_width) // 2)

    pad = " " * left_pad
    shifted_chip = [pad + line if line else "" for line in chip_lines]

    block = shifted_chip + list(footer_lines)
    top_pad = max(0, (height - len(block)) // 2)

    return [""] * top_pad + block


# Split render_screen output into its chip lines and the help/status footer. The
# footer is the trailing blank separator plus the (always non-empty) help/status
# lines, so the split is the LAST blank line -- an internal blank chip row (e.g.
# an empty top-number row) must not be mistaken for the separator.
def split_chip_and_footer(lines: list[str]) -> tuple[list[str], list[str]]:
    for offset, line in enumerate(reversed(lines)):
        if line == "":
            sep = len(lines) - 1 - offset
            return lines[:sep], lines[sep:]

    return lines, []


# ---------------------------------------------------------------------------
# Terminal driver (the only part that touches the real screen)
# ---------------------------------------------------------------------------


# Draw the rendered lines on the alternate screen buffer with the cursor hidden,
# restoring the terminal cleanly even if an exception propagates.
class TerminalRenderer:
    def __init__(self, stream=None):
        import sys

        self._stream = stream if stream is not None else sys.stdout
        self._entered = False

    # Enter the alternate screen buffer and hide the cursor
    def __enter__(self):
        self._stream.write("\x1b[?1049h\x1b[?25l")
        self._stream.flush()
        self._entered = True
        return self

    # Restore the primary screen buffer and the cursor
    def __exit__(self, exc_type, exc_value, traceback):
        if self._entered:
            self._stream.write("\x1b[?25h\x1b[?1049l")
            self._stream.flush()
            self._entered = False

        return False

    # Clear the screen and paint the given lines, centred in the terminal.
    # The size is re-queried every frame so a resized window re-centres.
    def render(self, lines: list[str]) -> None:
        import shutil

        size = shutil.get_terminal_size()
        chip, footer = split_chip_and_footer(lines)
        lines = center_lines(chip, footer, size.columns, size.lines)

        self._stream.write("\x1b[2J\x1b[H")
        self._stream.write("\r\n".join(lines))
        self._stream.write("\r\n")
        self._stream.flush()
