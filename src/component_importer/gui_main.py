# Import sys for command line args
import sys

# Import QApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QSystemTrayIcon

# Import app path helpers
from component_importer.app_paths import APP_NAME
from component_importer.app_paths import runtime_icon_path

# Import icon class
from PyQt6.QtGui import QIcon

# Import main window
from component_importer.gui_main_window import MainWindow

# Import application stylesheet
from component_importer.gui_style import build_app_stylesheet


# Run a quick non-GUI check for packaged smoke tests
def run_self_test() -> None:
    # Build stylesheet to verify bundled assets can be resolved
    build_app_stylesheet()

    # Import window class to verify GUI modules can load
    from component_importer.gui_main_window import MainWindow  # noqa: F401


# Main entry point
def main() -> None:
    # Packaging smoke test, avoids opening the GUI
    if "--self-test" in sys.argv:
        run_self_test()
        return

    # Create app
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(runtime_icon_path())))

    # Apply clean white app theme
    app.setStyleSheet(build_app_stylesheet())

    # Keep app alive when window is hidden to tray, when the platform has a tray
    app.setQuitOnLastWindowClosed(not QSystemTrayIcon.isSystemTrayAvailable())

    # Create window
    window = MainWindow()

    # Show window
    window.show()

    # Run event loop
    sys.exit(app.exec())


# Run app
if __name__ == "__main__":
    main()
