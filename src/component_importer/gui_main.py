# Import sys for command line args
import sys

# Import QApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMessageBox
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

# Import single-instance lock
from component_importer.single_instance import SingleInstanceLock

# Import startup launch helpers
from component_importer.startup_manager import START_MINIMIZED_TO_TRAY_ARG
from component_importer.startup_manager import start_minimized_to_tray_requested


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

    # Remove app-specific flags before handing argv to Qt
    start_minimized_to_tray = start_minimized_to_tray_requested()
    qt_args = [
        argument
        for argument in sys.argv
        if argument != START_MINIMIZED_TO_TRAY_ARG
    ]

    # Create app
    app = QApplication(qt_args)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(runtime_icon_path())))

    # Apply clean white app theme
    app.setStyleSheet(build_app_stylesheet())

    # Keep only one GUI instance running
    instance_lock = SingleInstanceLock()

    if not instance_lock.acquire():
        QMessageBox.warning(None, APP_NAME, "App already running.")
        return

    exit_code = 1

    try:
        # Keep app alive when window is hidden to tray, when the platform has a tray
        app.setQuitOnLastWindowClosed(not QSystemTrayIcon.isSystemTrayAvailable())

        # Create window
        window = MainWindow()

        # OS startup launches quietly into the tray when possible
        if start_minimized_to_tray and window.can_hide_to_tray():
            window.hide_to_tray(show_message=False)
        else:
            window.show()

        # Run event loop
        exit_code = app.exec()
    finally:
        instance_lock.release()

    sys.exit(exit_code)


# Run app
if __name__ == "__main__":
    main()
