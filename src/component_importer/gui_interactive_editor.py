# Qt (PyQt6) graphical front-end for the interactive symbol pin-layout editor.
#
# This is a thin view over the Qt-free editor core in interactive_editor.py: the
# dialog owns an EditorState, paints it, and routes every key press through the
# shared handle_key() so movement / blank / accept / cancel semantics stay
# identical to the terminal (TUI) editor. No editor logic is reimplemented here.
#
# Accept (handle_key returns True) -> dialog.accept(); cancel (returns False) ->
# dialog.reject(). Everything else keeps the dialog open and repaints.

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QDialog
from PyQt6.QtWidgets import QDialogButtonBox
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

from component_importer.interactive_editor import EditorState
from component_importer.interactive_editor import handle_key
from component_importer.key_source import Key


# Colours matching the TUI: cursor slot yellow, selected slot red
CURSOR_COLOR = QColor(220, 180, 0)
SELECTED_COLOR = QColor(210, 40, 40)
BODY_COLOR = QColor(120, 120, 120)
TEXT_COLOR = QColor(30, 30, 30)

# Pixel geometry (functional, not fine-tuned)
PIN_STUB = 22
MIN_BODY_W = 160
MIN_BODY_H = 120


# Translate a Qt key event into the editor's logical Key enum
def qt_key_event_to_key(event) -> Key:
    key = event.key()
    modifiers = event.modifiers()
    shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

    if key == Qt.Key.Key_Up:
        return Key.UP
    if key == Qt.Key.Key_Down:
        return Key.DOWN
    if key == Qt.Key.Key_Left:
        return Key.LEFT
    if key == Qt.Key.Key_Right:
        return Key.RIGHT

    if key == Qt.Key.Key_Space:
        # Shift+Space inserts a blank, plain Space toggles selection
        return Key.SHIFT_SPACE if shift else Key.SPACE

    # 'S' is the documented insert-blank key (matches the TUI's capital S)
    if key == Qt.Key.Key_S:
        return Key.SHIFT_SPACE

    if key in (Qt.Key.Key_D, Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
        return Key.DELETE

    if key == Qt.Key.Key_Y:
        return Key.Y

    if key == Qt.Key.Key_Escape:
        return Key.ESC

    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return Key.ENTER

    return Key.OTHER


# Widget that paints the chip body + pins on all four sides from an EditorState
class _PinCanvas(QWidget):
    def __init__(self, state: EditorState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setMinimumSize(600, 460)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self.setFont(font)

    # Colour for a slot given its cursor / selected status
    def _slot_color(self, is_cursor: bool, is_selected: bool):
        if is_selected:
            return SELECTED_COLOR
        if is_cursor:
            return CURSOR_COLOR
        return TEXT_COLOR

    # Label text drawn beside a slot (name plus optional pin number)
    def _label_text(self, slot) -> str:
        return f"{slot.display_name} ({slot.number})" if slot.number else slot.display_name

    # Widest label pixel width across a side (0 when the side is empty)
    def _max_label_width(self, fm, slots) -> int:
        return max(
            (fm.horizontalAdvance(self._label_text(slot)) for slot in slots),
            default=0,
        )

    # Chip geometry: body size plus how far drawn content (stub + label) reaches
    # beyond each body edge. Pure function of the state and current font metrics.
    def _content_metrics(self):
        state = self.state
        left = state.sides["left"]
        right = state.sides["right"]
        top = state.sides["top"]
        bottom = state.sides["bottom"]

        fm = QFontMetrics(self.font())
        pitch = fm.height() + 12

        n_v = max(len(left), len(right), 1)
        n_h = max(len(top), len(bottom), 1)

        body_w = max(n_h * pitch + pitch, MIN_BODY_W)
        body_h = max(n_v * pitch + pitch, MIN_BODY_H)

        # Stub length plus a small text gap, then the widest label on that side
        pad = PIN_STUB + 6
        left_ext = pad + self._max_label_width(fm, left)
        right_ext = pad + self._max_label_width(fm, right)
        top_ext = pad + self._max_label_width(fm, top)
        bottom_ext = pad + self._max_label_width(fm, bottom)

        return body_w, body_h, left_ext, right_ext, top_ext, bottom_ext

    # Body top-left (bx, by) that centres the whole drawn chip (body + stubs +
    # labels) in the widget's current size. Recomputed every paint so dialog
    # resizes stay centred. Padding is clamped so an oversized chip anchors with
    # its top-left labels flush to the widget edge (never off-canvas).
    def _compute_origin(self):
        body_w, body_h, left_ext, right_ext, top_ext, bottom_ext = self._content_metrics()

        content_w = left_ext + body_w + right_ext
        content_h = top_ext + body_h + bottom_ext

        bx = left_ext + max(0, (self.width() - content_w) // 2)
        by = top_ext + max(0, (self.height() - content_h) // 2)

        return bx, by

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        state = self.state
        left = state.sides["left"]
        right = state.sides["right"]
        top = state.sides["top"]
        bottom = state.sides["bottom"]
        cursor = (state.cursor_side, state.cursor_index)
        selected = state.selected

        body_w, body_h, *_ = self._content_metrics()
        bx, by = self._compute_origin()

        # Chip body rectangle
        painter.setPen(QPen(BODY_COLOR, 2))
        painter.drawRect(bx, by, body_w, body_h)

        # Left side: horizontal rows, names/numbers outside to the left
        for index, slot in enumerate(left):
            y = by + int((index + 0.5) * body_h / max(len(left), 1))
            is_cursor = cursor == ("left", index)
            color = self._slot_color(is_cursor, is_cursor and selected)
            self._draw_h_pin(painter, slot, bx, y, color, edge="left")

        # Right side: horizontal rows, names/numbers outside to the right
        for index, slot in enumerate(right):
            y = by + int((index + 0.5) * body_h / max(len(right), 1))
            is_cursor = cursor == ("right", index)
            color = self._slot_color(is_cursor, is_cursor and selected)
            self._draw_h_pin(painter, slot, bx + body_w, y, color, edge="right")

        # Top side: columns, names drawn vertically (rotated) above the body
        for index, slot in enumerate(top):
            x = bx + int((index + 0.5) * body_w / max(len(top), 1))
            is_cursor = cursor == ("top", index)
            color = self._slot_color(is_cursor, is_cursor and selected)
            self._draw_v_pin(painter, slot, x, by, color, edge="top")

        # Bottom side: columns, names drawn vertically below the body
        for index, slot in enumerate(bottom):
            x = bx + int((index + 0.5) * body_w / max(len(bottom), 1))
            is_cursor = cursor == ("bottom", index)
            color = self._slot_color(is_cursor, is_cursor and selected)
            self._draw_v_pin(painter, slot, x, by + body_h, color, edge="bottom")

        painter.end()

    # Draw a left/right pin: stub, edge marker, and a horizontal label
    def _draw_h_pin(self, painter, slot, edge_x, y, color, edge) -> None:
        direction = -1 if edge == "left" else 1
        stub_end = edge_x + direction * PIN_STUB

        painter.setPen(QPen(color, 2))
        painter.drawLine(edge_x, y, stub_end, y)
        # Edge marker (cursor/selected block)
        if color in (CURSOR_COLOR, SELECTED_COLOR):
            painter.fillRect(edge_x - 3, y - 3, 6, 6, color)

        text = f"{slot.display_name} ({slot.number})" if slot.number else slot.display_name
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)
        ty = y + fm.ascent() // 2

        if edge == "left":
            painter.drawText(stub_end - 6 - tw, ty, text)
        else:
            painter.drawText(stub_end + 6, ty, text)

    # Draw a top/bottom pin: stub, edge marker, and a vertical (rotated) label
    def _draw_v_pin(self, painter, slot, x, edge_y, color, edge) -> None:
        direction = -1 if edge == "top" else 1
        stub_end = edge_y + direction * PIN_STUB

        painter.setPen(QPen(color, 2))
        painter.drawLine(x, edge_y, x, stub_end)
        if color in (CURSOR_COLOR, SELECTED_COLOR):
            painter.fillRect(x - 3, edge_y - 3, 6, 6, color)

        text = f"{slot.display_name} ({slot.number})" if slot.number else slot.display_name
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)

        painter.save()
        if edge == "top":
            # Name climbs away from the body; rotate so it reads bottom-to-top
            painter.translate(x, stub_end - 6)
            painter.rotate(-90)
            painter.drawText(0, fm.ascent() // 2, text)
        else:
            painter.translate(x, stub_end + 6)
            painter.rotate(-90)
            painter.drawText(-tw, fm.ascent() // 2, text)
        painter.restore()


# Modal dialog that drives the shared editor core with keyboard input
class InteractivePinLayoutDialog(QDialog):
    def __init__(self, state: EditorState, symbol_name: str = "", parent=None):
        super().__init__(parent)

        self.state = state
        self.symbol_name = symbol_name

        title = "Interactive pin layout"
        if symbol_name:
            title = f"{title} - {symbol_name}"
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)

        heading = symbol_name or "symbol"
        self.header_label = QLabel(f"Arrange pins for {heading}")
        layout.addWidget(self.header_label)

        self.canvas = _PinCanvas(state, self)
        layout.addWidget(self.canvas, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # OK / Cancel are mouse shortcuts for the keyboard accept / cancel flows:
        # OK bypasses the two-step Y->Y prompt (dialog.accept()), Cancel bypasses
        # the Esc->Enter prompt (dialog.reject()). Downstream layout extraction
        # reads dialog.state, which OK leaves untouched exactly like the Y path.
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # The buttons must never intercept the editor's keys: NoFocus keeps arrow /
        # Space / S / D / Y / Esc / Enter flowing to keyPressEvent, and clearing
        # auto-default / default stops QDialog from firing OK when the user presses
        # Enter to confirm an exit prompt.
        for button in self.button_box.buttons():
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAutoDefault(False)
            button.setDefault(False)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self._refresh_status()

        # Ensure the dialog receives key events directly
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # Build the status / help line from the current editor state
    def _refresh_status(self) -> None:
        state = self.state

        if state.pending == "accept":
            text = "Accept this layout? Press Y to confirm, any other key to resume."
        elif state.pending == "exit":
            text = (
                "Exit without changes? Press Enter to cancel import, "
                "any other key to resume."
            )
        else:
            mode = "MOVE" if state.selected else "NAV"
            text = (
                f"[{mode}]  arrows: move   Space: select/deselect   "
                "S: insert blank   D/Del: delete blank   Y: accept   Esc: cancel"
            )

        if state.status:
            text = f"{text}\n{state.status}"

        self.status_label.setText(text)

    # All keyboard input flows through the shared editor core
    def keyPressEvent(self, event) -> None:
        key = qt_key_event_to_key(event)
        result = handle_key(self.state, key)

        self.canvas.update()
        self._refresh_status()
        event.accept()

        if result is True:
            self.accept()
        elif result is False:
            self.reject()
