# Import Qt core classes
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QThread
from PyQt6.QtCore import QTimer

# Import widgets
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QTabWidget
from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtWidgets import QSplitter
from PyQt6.QtWidgets import QSystemTrayIcon
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QStyle
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtWidgets import QLabel

# Import actions and icons
from PyQt6.QtGui import QAction
from PyQt6.QtGui import QIcon

# Import datetime for log timestamps
from datetime import datetime

# Import config helpers
from component_importer.gui_config_manager import load_gui_config
from component_importer.gui_config_manager import save_gui_config
from component_importer.gui_config_manager import infer_part_name_from_zip
from component_importer.gui_config_manager import RECOMMENDED_STABLE_ZIP_DELAY_SECONDS
from component_importer.gui_config_manager import validate_gui_config

# Import app path helpers
from component_importer.app_paths import APP_NAME
from component_importer.app_paths import runtime_icon_path

# Import library initializer
from component_importer.project_library_initializer import initialize_project_libraries

# Import tabs
from component_importer.gui_config_tab import ConfigTab
from component_importer.gui_search_tab import SearchTab
from component_importer.gui_import_tab import ImportTab
from component_importer.gui_how_to_use_tab import HowToUseTab

# Import worker classes
from component_importer.gui_import_worker import ImportComponentWorker

# Import folder watcher
from component_importer.gui_scan_watcher import ZipFolderWatcher


# Main GUI window
class MainWindow(QMainWindow):
    # Create main window
    def __init__(self):
        # Initialize QMainWindow
        super().__init__()

        # Set title
        self.setWindowTitle(APP_NAME)

        # Set application icon
        self.app_icon = QIcon(str(runtime_icon_path()))
        self.setWindowIcon(self.app_icon)

        # Set size
        self.resize(1200, 800)

        # Load config
        self.config = load_gui_config()

        # Worker state
        self.current_thread = None
        self.current_worker = None
        self.current_import_context = None
        self.import_busy = False
        self.import_queue = []
        self.active_popups = []

        # Build UI
        self.build_ui()

        # Build tray icon
        self.build_tray_icon()

        # Build folder watcher
        self.build_folder_watcher()

        # Start watcher if enabled
        self.restart_watcher()

        # Prepare project libraries for the loaded config if possible
        self.prepare_project_libraries(show_log=False)

    # Build UI
    def build_ui(self) -> None:
        # Main widget
        central_widget = QWidget()

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Tabs
        self.tabs = QTabWidget()
        self.config_tab = ConfigTab(self.config)
        self.import_tab = ImportTab(self.config)
        self.search_tab = SearchTab()
        self.how_to_use_tab = HowToUseTab()

        # Add tabs
        self.tabs.addTab(self.config_tab, "Configuration")
        self.tabs.addTab(self.import_tab, "Import ZIP")
        self.tabs.addTab(self.search_tab, "Search")
        self.tabs.addTab(self.how_to_use_tab, "How to use")

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        # Add to splitter
        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.log_output)
        self.splitter.setSizes([550, 250])

        # Add splitter
        main_layout.addWidget(self.splitter)

        # Subtle support link visible on every tab
        self.support_link_label = QLabel(
            'Support the app: '
            '<a href="https://buy.stripe.com/cNieVeg1c7xbalm0CEdnW00">'
            '<span style="color:#0067c0; text-decoration: underline;">'
            'Buy me a coffee'
            '</span>'
            '</a>'
        )
        self.support_link_label.setTextFormat(Qt.TextFormat.RichText)
        self.support_link_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.support_link_label.setOpenExternalLinks(True)
        self.support_link_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        main_layout.addWidget(
            self.support_link_label,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )

        # Set central widget
        self.setCentralWidget(central_widget)

        # Connect tab signals
        self.config_tab.configSaved.connect(self.on_config_saved)
        self.config_tab.logMessage.connect(self.log)
        self.search_tab.logMessage.connect(self.log)
        self.import_tab.logMessage.connect(self.log)
        self.import_tab.importRequested.connect(self.start_import)
        self.tabs.currentChanged.connect(self.update_log_visibility)

        # Apply initial log visibility for the selected tab
        self.update_log_visibility()

    # Hide the log panel on informational tabs
    def update_log_visibility(self, *args) -> None:
        # The help tab should read like a full page, without the operation log
        on_help_tab = self.tabs.currentWidget() == self.how_to_use_tab

        # Toggle log visibility
        self.log_output.setVisible(not on_help_tab)

        # Give the main tab area the full height when the log is hidden
        if on_help_tab:
            self.splitter.setSizes([800, 0])
        else:
            self.splitter.setSizes([550, 250])

    # Build tray icon
    def build_tray_icon(self) -> None:
        self.tray_icon = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        # Create tray icon
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)

        # Create menu
        menu = QMenu()

        # Show action
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_from_tray)

        # Exit action
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_app)

        # Add actions
        menu.addAction(show_action)
        menu.addAction(exit_action)

        # Set menu
        self.tray_icon.setContextMenu(menu)

        # Connect activation
        self.tray_icon.activated.connect(self.on_tray_activated)

        # Show tray icon
        self.tray_icon.show()

    # Build folder watcher
    def build_folder_watcher(self) -> None:
        # Create watcher
        self.watcher = ZipFolderWatcher(self)

        # Connect watcher
        self.watcher.zipDetected.connect(self.on_zip_detected)
        self.watcher.message.connect(self.log)

    # Restart watcher based on config
    def restart_watcher(self) -> None:
        # Stop old watcher
        self.watcher.stop()

        # Start only if enabled
        if not self.config.auto_import_enabled:
            self.log("Auto import watcher is disabled.")
            return

        # Start watcher
        self.watcher.start(
            folder=self.config.downloads_folder,
            stable_delay_seconds=RECOMMENDED_STABLE_ZIP_DELAY_SECONDS,
        )

    # Handle saved config
    def on_config_saved(self, config, show_log: bool = False) -> None:
        # Store old config so watcher restarts only when watcher settings changed
        old_config = self.config

        # Store config
        self.config = config

        # Save config
        save_gui_config(config)

        # Ensure libraries are created and registered as soon as config is valid
        self.prepare_project_libraries(show_log=show_log)

        # Update tabs
        self.import_tab.update_config(config)

        # Restart watcher only when relevant settings changed
        if self.watcher_settings_changed(old_config, config):
            self.restart_watcher()

    # Check whether a config change affects the ZIP watcher
    def watcher_settings_changed(self, old_config, new_config) -> bool:
        return (
            old_config.downloads_folder != new_config.downloads_folder
            or old_config.auto_import_enabled != new_config.auto_import_enabled
        )

    # Create/register configured project libraries early
    def prepare_project_libraries(self, show_log: bool = False) -> bool:
        # Only initialize when the config is valid enough to touch the project
        errors = validate_gui_config(self.config)

        if errors:
            return False

        try:
            result = initialize_project_libraries(
                project_root=self.config.project_root,
                library_name=self.config.library_name,
                symbol_library_name=self.config.symbol_library_name,
                footprint_library_name=self.config.footprint_library_name,
            )
        except Exception as error:
            if show_log:
                self.log(f"Library setup error: {error}")

            return False

        if show_log:
            table_update = result.get("table_update", {})
            footprint_updated = table_update.get("footprint_table_updated", False)
            symbol_updated = bool(table_update.get("symbol_tables_updated", []))

            if footprint_updated or symbol_updated:
                self.log("Project libraries registered.")
            else:
                self.log("Project libraries ready.")

        return True

    # Save current configuration fields without logging
    def save_current_config_silently(self) -> None:
        if not hasattr(self, "config_tab"):
            return

        # Stop any pending autosave and write the latest field values
        if hasattr(self.config_tab, "auto_save_timer"):
            self.config_tab.auto_save_timer.stop()

        self.config = self.config_tab.build_config_from_fields()
        save_gui_config(self.config)

    # Handle detected ZIP
    def on_zip_detected(self, zip_path: str) -> None:
        # Infer part name
        part_name = infer_part_name_from_zip(zip_path)

        # Log detection
        self.log(f"Auto import detected: {part_name}")

        # Start import
        self.start_import(zip_path, part_name, auto_import=True)

    # Validate config before operations
    def check_config_before_operation(self) -> bool:
        # Validate config
        errors = validate_gui_config(self.config)

        # Log errors
        for error in errors:
            self.log(f"Config error: {error}")

        # Return True if no errors
        return not errors

    # Start component import
    def start_import(self, zip_path: str, part_name: str, auto_import: bool = False) -> None:
        # Check config
        if not self.check_config_before_operation():
            return

        # Make sure libraries are present before importing files into them
        if not self.prepare_project_libraries(show_log=False):
            return

        # If import is busy, queue this one
        if self.import_busy:
            self.import_queue.append((zip_path, part_name, auto_import))
            self.log(f"Import busy. Queued: {part_name}")
            return

        # Mark busy
        self.import_busy = True

        # Log
        self.log(f"Import started: {part_name}")

        # Create thread and worker
        thread = QThread(self)
        worker = ImportComponentWorker(zip_path, part_name, self.config)

        # Move worker to thread
        worker.moveToThread(thread)

        # Connect thread start
        thread.started.connect(worker.run)

        # Connect worker signals
        worker.finished.connect(self.on_import_finished)
        worker.failed.connect(self.on_worker_failed)

        # Cleanup
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Store references
        self.current_thread = thread
        self.current_worker = worker
        library_label, library_word = self.get_import_library_label()
        self.current_import_context = {
            "auto_import": auto_import,
            "part_name": part_name,
            "zip_path": zip_path,
            "library_label": library_label,
            "library_word": library_word,
        }

        # Start thread
        thread.start()

    # Handle import finished
    def on_import_finished(self, result, validation, output: str) -> None:
        # Log output
        self.log(output)

        # Store and clear context for this completed import
        import_context = self.current_import_context or {}
        self.current_import_context = None

        # Mark not busy
        self.import_busy = False

        # Show a success popup for completed imports
        if validation.get("passed", False):
            component_name = self.get_imported_component_name(
                result=result,
                fallback=import_context.get("part_name", "Component"),
            )
            self.show_import_success_popup(
                component_name=component_name,
                library_label=import_context.get("library_label", "configured"),
                library_word=import_context.get("library_word", "library"),
            )

        # Process queue if any
        self.process_next_import_queue_item()

    # Process next queued import
    def process_next_import_queue_item(self) -> None:
        # Return if no queued imports
        if not self.import_queue:
            return

        # Get next item
        zip_path, part_name, auto_import = self.import_queue.pop(0)

        # Delay slightly so thread cleanup completes
        QTimer.singleShot(300, lambda: self.start_import(zip_path, part_name, auto_import))

    # Handle worker failure
    def on_worker_failed(self, error_text: str) -> None:
        # Log a concise user-facing error
        self.log(f"Error: {error_text}")

        # Clear context for failed import
        self.current_import_context = None

        # Mark not busy
        self.import_busy = False

        # Process queued import if needed
        self.process_next_import_queue_item()

    # Get a readable library label for import messages
    def get_import_library_label(self) -> tuple[str, str]:
        # Use the configured symbol and footprint libraries
        symbol_library = self.config.symbol_library_name.strip() or self.config.library_name.strip()
        footprint_library = self.config.footprint_library_name.strip() or self.config.library_name.strip()

        # Fallback for incomplete configuration
        if not symbol_library and not footprint_library:
            return "configured", "library"

        # If both asset types share a library name, use a singular message
        if symbol_library == footprint_library:
            return symbol_library, "library"

        # Otherwise name both libraries
        return f"{symbol_library} and {footprint_library}", "libraries"

    # Get the most accurate imported component name from the import result
    def get_imported_component_name(self, result: dict, fallback: str) -> str:
        # Prefer the symbol name that was linked to a footprint
        for link_result in result.get("symbol_footprint_link", []):
            symbol_name = link_result.get("symbol_name")
            if symbol_name:
                return symbol_name

        # Fall back to merged symbol names
        for merge_result in result.get("merged_symbols", []):
            merged_symbol_names = merge_result.get("merged_symbol_names", [])
            if merged_symbol_names:
                return merged_symbol_names[0]

        # Last fallback is the inferred part name
        return fallback

    # Show non-blocking popup after successful import
    def show_import_success_popup(
        self,
        component_name: str,
        library_label: str,
        library_word: str,
    ) -> None:
        # Build message requested for import completion
        message = (
            f"{component_name} has been successfully imported "
            f"to {library_label} {library_word}."
        )

        # Use a standalone popup if the main window is hidden to tray
        parent = self if self.isVisible() else None
        popup = QMessageBox(parent)
        popup.setWindowTitle("Component imported")
        popup.setIcon(QMessageBox.Icon.Information)
        popup.setText(message)
        popup.setStandardButtons(QMessageBox.StandardButton.Ok)
        popup.setModal(False)
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # Keep popup alive until the user closes it
        self.active_popups.append(popup)

        def remove_popup(_result=None) -> None:
            if popup in self.active_popups:
                self.active_popups.remove(popup)

        popup.finished.connect(remove_popup)
        popup.show()
        popup.raise_()
        popup.activateWindow()

    # Log message
    def log(self, message: str) -> None:
        # Build timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Append each line with timestamp
        for line in str(message).splitlines():
            self.log_output.append(f"[{timestamp}] {line}")

    # Handle minimize event
    def changeEvent(self, event) -> None:
        # Call parent implementation
        super().changeEvent(event)

        # Hide to tray when minimized
        if event.type().name == "WindowStateChange":
            if self.isMinimized():
                QTimer.singleShot(0, self.hide_to_tray)

    # Hide window to tray
    def hide_to_tray(self) -> None:
        if self.tray_icon is None or not self.tray_icon.isVisible():
            return

        # Hide window
        self.hide()

        # Show tray message
        self.tray_icon.showMessage(
            APP_NAME,
            "The app is still running in the background.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    # Show window from tray
    def show_from_tray(self) -> None:
        # Show normal window
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # Handle tray activation
    def on_tray_activated(self, reason) -> None:
        # Show on double click
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()

    # Exit app
    def exit_app(self) -> None:
        # Persist latest config values before quitting
        self.save_current_config_silently()

        # Stop watcher
        self.watcher.stop()

        # Hide tray icon
        if self.tray_icon is not None:
            self.tray_icon.hide()

        # Quit app
        QApplication.instance().quit()

    # Close event
    def closeEvent(self, event) -> None:
        # X button closes the app fully
        self.exit_app()

        # Accept event
        event.accept()
