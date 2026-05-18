# Import helper to resolve assets in source and packaged runs
from app_paths import resource_path


# Accent color used across the GUI
ACCENT_COLOR = "#0067c0"

# Green check used for checked checkbox indicators
CHECK_GREEN_COLOR = "#107c10"

# Small SVG assets used by the stylesheet
CHECK_ICON = resource_path("gui_assets/check_green.svg")
CHEVRON_ICON = resource_path("gui_assets/chevron_down.svg")
CHEVRON_UP_ICON = resource_path("gui_assets/chevron_up.svg")


# Build the application-wide Qt stylesheet
def build_app_stylesheet() -> str:
    # Qt stylesheets prefer forward slashes in URLs on Windows
    check_icon_url = CHECK_ICON.as_posix()
    chevron_icon_url = CHEVRON_ICON.as_posix()
    chevron_up_icon_url = CHEVRON_UP_ICON.as_posix()

    return f"""
    QWidget {{
        background: #f3f3f3;
        color: #1f1f1f;
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 10pt;
    }}

    QMainWindow {{
        background: #f3f3f3;
    }}

    QLabel {{
        background: transparent;
        color: #323130;
        border: none;
        line-height: 1.35;
    }}

    QTabWidget::pane {{
        border: 1px solid #d0d0d0;
        border-radius: 8px;
        background: #ffffff;
        top: -1px;
    }}

    QTabBar::tab {{
        background: #eeeeee;
        color: #323130;
        border: 1px solid #d0d0d0;
        border-bottom: none;
        padding: 9px 16px;
        margin-right: 4px;
        min-width: 96px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}

    QTabBar::tab:selected {{
        background: #ffffff;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-top: 3px solid {ACCENT_COLOR};
        border-bottom: 1px solid #ffffff;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        font-weight: 600;
    }}

    QTabBar::tab:hover:!selected {{
        color: #1f1f1f;
        background: #f8f8f8;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}

    QGroupBox {{
        background: #ffffff;
        border: 1px solid #dcdcdc;
        border-radius: 8px;
    }}

    QGroupBox::title {{
        background: transparent;
        color: #323130;
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}

    QLineEdit,
    QSpinBox,
    QTextEdit,
    QTextBrowser,
    QListWidget {{
        background: #ffffff;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-radius: 6px;
        padding: 7px 9px;
        selection-background-color: {ACCENT_COLOR};
        selection-color: #ffffff;
    }}

    QComboBox {{
        background: #ffffff;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-radius: 6px;
        padding: 7px 36px 7px 9px;
        min-height: 20px;
        selection-background-color: {ACCENT_COLOR};
        selection-color: #ffffff;
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 30px;
        border-left: 1px solid #d0d0d0;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
        background: #f9f9f9;
    }}

    QComboBox::drop-down:hover {{
        background: #eeeeee;
    }}

    QComboBox::down-arrow {{
        image: url("{chevron_icon_url}");
        width: 14px;
        height: 14px;
    }}

    QSpinBox {{
        background: #ffffff;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-radius: 6px;
        padding: 7px 34px 7px 9px;
        min-height: 20px;
        selection-background-color: {ACCENT_COLOR};
        selection-color: #ffffff;
    }}

    QSpinBox::up-button,
    QSpinBox::down-button {{
        subcontrol-origin: border;
        width: 28px;
        border-left: 1px solid #d0d0d0;
        background: #f9f9f9;
    }}

    QSpinBox::up-button {{
        subcontrol-position: top right;
        border-top-right-radius: 6px;
    }}

    QSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: 6px;
    }}

    QSpinBox::up-button:hover,
    QSpinBox::down-button:hover {{
        background: #eeeeee;
    }}

    QSpinBox::up-arrow {{
        image: url("{chevron_up_icon_url}");
        width: 14px;
        height: 14px;
    }}

    QSpinBox::down-arrow {{
        image: url("{chevron_icon_url}");
        width: 14px;
        height: 14px;
    }}

    QComboBox QAbstractItemView {{
        background: #ffffff;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-radius: 6px;
        padding: 4px;
        outline: 0;
        selection-background-color: #e5f1fb;
        selection-color: #1f1f1f;
    }}

    QLineEdit:hover,
    QComboBox:hover,
    QSpinBox:hover,
    QTextEdit:hover,
    QTextBrowser:hover,
    QListWidget:hover {{
        border-color: #8a8a8a;
    }}

    QLineEdit:focus,
    QComboBox:focus,
    QSpinBox:focus,
    QTextEdit:focus,
    QTextBrowser:focus,
    QListWidget:focus {{
        border: 1px solid {ACCENT_COLOR};
    }}

    QPushButton {{
        background: #fbfbfb;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-radius: 6px;
        padding: 8px 14px;
        min-height: 20px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        border-color: #8a8a8a;
        color: #1f1f1f;
        background: #f6f6f6;
    }}

    QPushButton:pressed {{
        background: #e5e5e5;
        border-color: #8a8a8a;
    }}

    QPushButton:focus {{
        border-color: {ACCENT_COLOR};
    }}

    QPushButton:disabled {{
        color: #9a9a9a;
        background: #f0f0f0;
        border-color: #dddddd;
    }}

    QCheckBox {{
        background: transparent;
        spacing: 8px;
        color: #323130;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid #8a8a8a;
        border-radius: 4px;
        background: #ffffff;
    }}

    QCheckBox::indicator:checked {{
        background: #ffffff;
        border: 2px solid {CHECK_GREEN_COLOR};
        image: url("{check_icon_url}");
    }}

    QCheckBox::indicator:hover {{
        border-color: {CHECK_GREEN_COLOR};
    }}

    QListWidget::item {{
        padding: 7px 8px;
        border-radius: 5px;
    }}

    QListWidget::item:selected {{
        background: #e5f1fb;
        color: #1f1f1f;
    }}

    QListWidget::item:hover {{
        background: #f4f4f4;
    }}

    QSplitter::handle {{
        background: #dcdcdc;
    }}

    QSplitter::handle:hover {{
        background: {ACCENT_COLOR};
    }}

    QScrollBar:vertical {{
        background: #f3f3f3;
        width: 12px;
        margin: 0;
        border-radius: 6px;
    }}

    QScrollBar::handle:vertical {{
        background: #cfcfcf;
        border-radius: 6px;
        min-height: 28px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #a8a8a8;
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QToolTip {{
        background: #ffffff;
        color: #1f1f1f;
        border: 1px solid #c8c8c8;
        border-radius: 4px;
        padding: 6px;
    }}
    """
