# Import Qt core helpers
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QRectF
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal

# Import drawing helpers
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QPen

# Import widgets
from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtWidgets import QColorDialog
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtWidgets import QDoubleSpinBox
from PyQt6.QtWidgets import QFormLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget

# Import config helpers
from component_importer.gui_config_manager import GuiConfig
from component_importer.gui_config_manager import save_gui_config
from component_importer.symbol_style import KICAD_DEFAULT_FILL_MODE
from component_importer.symbol_style import KICAD_DEFAULT_FILL_COLOR
from component_importer.symbol_style import KICAD_DENSE_SYMBOL_PIN_COUNT_THRESHOLD
from component_importer.symbol_style import KICAD_DENSE_SYMBOL_PIN_LENGTH_MM
from component_importer.symbol_style import KICAD_DEFAULT_PIN_LENGTH_MM
from component_importer.symbol_style import KICAD_DEFAULT_PIN_NUMBER_COLOR
from component_importer.symbol_style import KICAD_DEFAULT_TEXT_COLOR
from component_importer.symbol_style import normalize_fill_mode
from component_importer.symbol_style import normalize_hex_color


# Draw a basic schematic symbol preview from the configured style
class SymbolPreview(QWidget):
    # Create preview
    def __init__(self, config: GuiConfig):
        super().__init__()

        self.config = config
        self.setMinimumSize(460, 340)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

    # Update preview config
    def set_config(self, config: GuiConfig) -> None:
        self.config = config
        self.update()

    # Paint preview
    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            canvas = QRectF(self.rect()).adjusted(14, 14, -14, -14)
            painter.fillRect(canvas, QColor("#ffffff"))
            painter.setPen(QPen(QColor("#d0d0d0"), 1))
            painter.drawRoundedRect(canvas, 8, 8)

            content = canvas.adjusted(34, 30, -34, -30)
            center = content.center()
            scale = min(content.width() / 40.0, content.height() / 30.0)

            line_color = QColor(normalize_hex_color(self.config.symbol_line_color))
            line_width = max(1.0, self.config.symbol_line_width_mm * scale)
            line_pen = QPen(line_color, line_width)
            line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(line_pen)

            fill_mode = normalize_fill_mode(self.config.symbol_fill_mode)
            body = QRectF(
                self.point(center, scale, -10.0, 7.5),
                self.point(center, scale, 10.0, -8.0),
            ).normalized()

            if fill_mode == "kicad_default":
                painter.setBrush(QColor(KICAD_DEFAULT_FILL_COLOR))
            elif fill_mode == "color":
                painter.setBrush(QColor(normalize_hex_color(self.config.symbol_fill_color)))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.drawRect(body)

            self.draw_pins(
                painter=painter,
                center=center,
                scale=scale,
            )
            self.draw_symbol_text(
                painter=painter,
                center=center,
                scale=scale,
                fill_mode=fill_mode,
            )
        finally:
            painter.end()

    # Convert symbol coordinates to preview points
    def point(self, center: QPointF, scale: float, x: float, y: float) -> QPointF:
        return QPointF(center.x() + x * scale, center.y() - y * scale)

    # Draw preview pins and a few internal lines
    def draw_pins(
        self,
        painter: QPainter,
        center: QPointF,
        scale: float,
    ) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pin_line_color = QColor(KICAD_DEFAULT_PIN_NUMBER_COLOR)
        pin_pen = QPen(pin_line_color, max(1.0, 0.127 * scale))
        pin_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pin_pen)

        pin_rows = [
            (5.8, "IN1", "1", "OUT1", "14"),
            (3.9, "IN2", "2", "OUT2", "13"),
            (2.0, "IN3", "3", "OUT3", "12"),
            (0.1, "IN4", "4", "OUT4", "11"),
            (-1.8, "EN", "5", "READY", "10"),
            (-3.7, "VCC", "6", "FAULT", "9"),
            (-5.6, "GND", "7", "GND", "8"),
        ]
        body_left_x = -10.0
        body_right_x = 10.0
        pin_length = KICAD_DENSE_SYMBOL_PIN_LENGTH_MM

        if len(pin_rows) * 2 <= KICAD_DENSE_SYMBOL_PIN_COUNT_THRESHOLD:
            pin_length = KICAD_DEFAULT_PIN_LENGTH_MM

        left_pin_outer_x = body_left_x - pin_length
        right_pin_outer_x = body_right_x + pin_length

        pin_name_color = QColor(KICAD_DEFAULT_TEXT_COLOR)
        pin_number_color = QColor(KICAD_DEFAULT_PIN_NUMBER_COLOR)

        for y, left_name, left_number, right_name, right_number in pin_rows:
            painter.drawLine(
                self.point(center, scale, left_pin_outer_x, y),
                self.point(center, scale, body_left_x, y),
            )
            painter.drawLine(
                self.point(center, scale, body_right_x, y),
                self.point(center, scale, right_pin_outer_x, y),
            )

            self.draw_pin_label(
                painter,
                center,
                scale,
                body_left_x + 0.8,
                y,
                left_name,
                pin_name_color,
                Qt.AlignmentFlag.AlignLeft,
            )
            self.draw_pin_label(
                painter,
                center,
                scale,
                left_pin_outer_x - 1.05,
                y,
                left_number,
                pin_number_color,
                Qt.AlignmentFlag.AlignRight,
            )
            self.draw_pin_label(
                painter,
                center,
                scale,
                body_right_x - 0.8,
                y,
                right_name,
                pin_name_color,
                Qt.AlignmentFlag.AlignRight,
            )
            self.draw_pin_label(
                painter,
                center,
                scale,
                right_pin_outer_x + 1.05,
                y,
                right_number,
                pin_number_color,
                Qt.AlignmentFlag.AlignLeft,
            )

    # Draw a small pin label
    def draw_pin_label(
        self,
        painter: QPainter,
        center: QPointF,
        scale: float,
        x: float,
        y: float,
        text: str,
        color: QColor,
        alignment: Qt.AlignmentFlag,
    ) -> None:
        painter.save()
        painter.setPen(color)
        font = painter.font()
        font.setPixelSize(max(9, int(self.config.symbol_font_size_mm * scale * 0.72)))
        painter.setFont(font)

        anchor = self.point(center, scale, x, y)
        if alignment == Qt.AlignmentFlag.AlignRight:
            box = QRectF(anchor.x() - 54, anchor.y() - 11, 52, 22)
        else:
            box = QRectF(anchor.x() + 2, anchor.y() - 11, 54, 22)

        painter.drawText(
            box,
            alignment | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()

    # Draw reference and value text
    def draw_symbol_text(
        self,
        painter: QPainter,
        center: QPointF,
        scale: float,
        fill_mode: str,
    ) -> None:
        painter.save()

        text_color = QColor(KICAD_DEFAULT_TEXT_COLOR)

        font = QFont()
        font.setPixelSize(max(12, int(self.config.symbol_font_size_mm * scale * 0.9)))
        painter.setFont(font)
        painter.setPen(text_color)

        ref_box = QRectF(
            self.point(center, scale, -5.2, 12.8),
            self.point(center, scale, 5.2, 11.0),
        ).normalized()
        value_box = QRectF(
            self.point(center, scale, -12.0, 10.7),
            self.point(center, scale, 12.0, 8.8),
        ).normalized()

        painter.drawText(ref_box, Qt.AlignmentFlag.AlignCenter, "U1")
        painter.drawText(value_box, Qt.AlignmentFlag.AlignCenter, "GENERIC_IC")
        painter.restore()

    # Return True when a color needs light text for contrast
    def color_is_dark(self, color: QColor) -> bool:
        luminance = (
            0.299 * color.red()
            + 0.587 * color.green()
            + 0.114 * color.blue()
        )
        return luminance < 140


# Symbol style tab
class SymbolStyleTab(QWidget):
    # Emitted when config is saved
    configSaved = pyqtSignal(object, bool)

    # Emitted for log messages
    logMessage = pyqtSignal(str)

    # Create tab
    def __init__(self, config: GuiConfig):
        super().__init__()

        self.config = config
        self.loading_config = False
        self.committing_config = False
        self.symbol_line_color = config.symbol_line_color
        self.symbol_fill_color = config.symbol_fill_color

        self.build_ui()
        self.load_config_to_fields()
        self.setup_auto_save()

    # Update tab state from a config object
    def update_config(self, config: GuiConfig) -> None:
        if self.committing_config:
            self.config = config
            self.preview.set_config(config)
            return

        self.config = config
        self.load_config_to_fields()

    # Build UI
    def build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(18)

        controls_widget = QWidget()
        controls_widget.setMaximumWidth(520)
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        self.apply_formatting_checkbox = QCheckBox("Apply formatting")

        self.symbol_line_width_spin = QDoubleSpinBox()
        self.symbol_line_width_spin.setRange(0.0, 5.0)
        self.symbol_line_width_spin.setDecimals(3)
        self.symbol_line_width_spin.setSingleStep(0.025)
        self.symbol_line_width_spin.setSuffix(" mm")

        self.symbol_line_color_button = QPushButton()
        self.symbol_line_color_button.setMinimumWidth(120)

        self.symbol_fill_mode_combo = QComboBox()
        self.symbol_fill_mode_combo.addItem("Component default", "keep")
        self.symbol_fill_mode_combo.addItem("KiCad default", "kicad_default")
        self.symbol_fill_mode_combo.addItem("Custom", "color")

        self.symbol_fill_color_button = QPushButton()
        self.symbol_fill_color_button.setMinimumWidth(120)

        self.symbol_font_size_spin = QDoubleSpinBox()
        self.symbol_font_size_spin.setRange(0.1, 20.0)
        self.symbol_font_size_spin.setDecimals(3)
        self.symbol_font_size_spin.setSingleStep(0.05)
        self.symbol_font_size_spin.setSuffix(" mm")

        self.formatting_controls = [
            self.symbol_line_width_spin,
            self.symbol_line_color_button,
            self.symbol_fill_mode_combo,
            self.symbol_fill_color_button,
            self.symbol_font_size_spin,
        ]

        form_layout.addRow("", self.apply_formatting_checkbox)
        form_layout.addRow("Body line width:", self.symbol_line_width_spin)
        form_layout.addRow("Body line color:", self.symbol_line_color_button)
        form_layout.addRow("Fill:", self.symbol_fill_mode_combo)
        form_layout.addRow("Custom fill color:", self.symbol_fill_color_button)
        form_layout.addRow("Text size:", self.symbol_font_size_spin)

        controls_layout.addLayout(form_layout)
        controls_layout.addStretch()

        preview_column = QVBoxLayout()
        preview_label = QLabel("Preview")
        self.preview = SymbolPreview(self.config)
        preview_column.addWidget(preview_label)
        preview_column.addWidget(self.preview)

        main_layout.addWidget(controls_widget)
        main_layout.addLayout(preview_column, 1)

        self.symbol_line_color_button.clicked.connect(self.choose_symbol_line_color)
        self.symbol_fill_color_button.clicked.connect(self.choose_symbol_fill_color)

    # Connect changes to preview and autosave
    def setup_auto_save(self) -> None:
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.setInterval(700)
        self.auto_save_timer.timeout.connect(self.auto_save_config_from_fields)

        self.preview_update_timer = QTimer(self)
        self.preview_update_timer.setSingleShot(True)
        self.preview_update_timer.setInterval(35)
        self.preview_update_timer.timeout.connect(self.update_preview_from_fields)

        self.apply_formatting_checkbox.stateChanged.connect(self.on_style_changed)
        self.symbol_fill_mode_combo.currentIndexChanged.connect(self.on_style_changed)

        for spin_box in [
            self.symbol_line_width_spin,
            self.symbol_font_size_spin,
        ]:
            spin_box.valueChanged.connect(self.on_style_changed)

    # Load config into controls
    def load_config_to_fields(self) -> None:
        self.loading_config = True

        self.apply_formatting_checkbox.setChecked(self.config.symbol_style_enabled)
        self.symbol_line_width_spin.setValue(self.config.symbol_line_width_mm)
        self.set_symbol_line_color(self.config.symbol_line_color)
        self.set_symbol_fill_color(self.config.symbol_fill_color)

        fill_mode = normalize_fill_mode(self.config.symbol_fill_mode)
        fill_index = self.symbol_fill_mode_combo.findData(fill_mode)
        if fill_index >= 0:
            self.symbol_fill_mode_combo.setCurrentIndex(fill_index)
        else:
            self.symbol_fill_mode_combo.setCurrentIndex(0)

        self.symbol_font_size_spin.setValue(self.config.symbol_font_size_mm)

        self.loading_config = False
        self.update_formatting_controls_enabled()
        self.update_fill_color_enabled()
        self.update_preview_from_fields()

    # Handle field changes
    def on_style_changed(self, *args) -> None:
        if self.loading_config:
            return

        self.update_formatting_controls_enabled()
        self.update_fill_color_enabled()
        self.preview_update_timer.start()
        self.auto_save_timer.start()

    # Enable formatting controls only when formatting will be applied on import
    def update_formatting_controls_enabled(self) -> None:
        formatting_enabled = self.apply_formatting_checkbox.isChecked()

        for control in self.formatting_controls:
            control.setEnabled(formatting_enabled)

    # Set line color button state
    def set_symbol_line_color(self, color: str) -> None:
        self.symbol_line_color = normalize_hex_color(color)
        text_color = "#ffffff" if self.symbol_color_is_dark(self.symbol_line_color) else "#000000"
        self.symbol_line_color_button.setText(self.symbol_line_color)
        self.symbol_line_color_button.setStyleSheet(
            "QPushButton { "
            f"background-color: {self.symbol_line_color}; "
            f"color: {text_color}; "
            "}"
        )

    # Set fill color button state
    def set_symbol_fill_color(self, color: str) -> None:
        self.symbol_fill_color = normalize_hex_color(
            color,
            fallback=KICAD_DEFAULT_FILL_COLOR,
        )
        text_color = "#ffffff" if self.symbol_color_is_dark(self.symbol_fill_color) else "#000000"
        self.symbol_fill_color_button.setText(self.symbol_fill_color)
        self.symbol_fill_color_button.setStyleSheet(
            "QPushButton { "
            f"background-color: {self.symbol_fill_color}; "
            f"color: {text_color}; "
            "}"
        )

    # Apply a swatch-like style to a color button
    def apply_color_button_style(self, button: QPushButton, color: str) -> None:
        text_color = "#ffffff" if self.symbol_color_is_dark(color) else "#000000"
        button.setText(color)
        button.setStyleSheet(
            "QPushButton { "
            f"background-color: {color}; "
            f"color: {text_color}; "
            "}"
        )

    # Enable custom fill color only when it is used
    def update_fill_color_enabled(self) -> None:
        self.symbol_fill_color_button.setEnabled(
            self.apply_formatting_checkbox.isChecked()
            and self.symbol_fill_mode_combo.currentData() == "color"
        )

    # Choose line color
    def choose_symbol_line_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.symbol_line_color),
            self,
            "Select symbol line color",
        )

        if not color.isValid():
            return

        self.set_symbol_line_color(color.name())
        self.on_style_changed()

    # Choose fill color
    def choose_symbol_fill_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.symbol_fill_color),
            self,
            "Select symbol fill color",
        )

        if not color.isValid():
            return

        self.set_symbol_fill_color(color.name())
        self.on_style_changed()

    # Return True when a color needs light text for contrast
    def symbol_color_is_dark(self, color: str) -> bool:
        color = normalize_hex_color(color)
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
        luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
        return luminance < 140

    # Build config from current fields
    def build_config_from_fields(self) -> GuiConfig:
        return GuiConfig(
            project_root=self.config.project_root,
            library_name=self.config.library_name,
            symbol_library_name=self.config.symbol_library_name,
            footprint_library_name=self.config.footprint_library_name,
            downloads_folder=self.config.downloads_folder,
            create_backups=True,
            auto_import_enabled=self.config.auto_import_enabled,
            start_with_windows=self.config.start_with_windows,
            symbol_style_enabled=self.apply_formatting_checkbox.isChecked(),
            symbol_line_width_mm=self.symbol_line_width_spin.value(),
            symbol_line_color=self.symbol_line_color,
            symbol_fill_mode=(
                self.symbol_fill_mode_combo.currentData()
                or KICAD_DEFAULT_FILL_MODE
            ),
            symbol_fill_color=self.symbol_fill_color,
            symbol_font_size_mm=self.symbol_font_size_spin.value(),
        )

    # Update preview without saving
    def update_preview_from_fields(self) -> None:
        self.preview.set_config(self.build_config_from_fields())

    # Autosave style without noisy log messages
    def auto_save_config_from_fields(self) -> None:
        if hasattr(self, "preview_update_timer"):
            self.preview_update_timer.stop()
            self.update_preview_from_fields()

        self.commit_config_from_fields(show_log=False)

    # Save current fields and notify main window
    def commit_config_from_fields(self, show_log: bool = False) -> None:
        if self.committing_config:
            return

        config = self.build_config_from_fields()

        try:
            self.committing_config = True
            self.config = config
            save_gui_config(config)
            self.configSaved.emit(config, show_log)
        finally:
            self.committing_config = False

        if show_log:
            self.logMessage.emit("Symbol style saved.")
