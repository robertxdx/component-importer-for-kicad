# Import widgets
from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QFormLayout
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QListWidget
from PyQt6.QtWidgets import QLabel

# Import signals, filesystem watcher, and timers
from PyQt6.QtCore import QFileSystemWatcher
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal

# Import Path
from pathlib import Path

# Import part name inference
from component_importer.gui_config_manager import infer_part_name_from_zip

# Import case-insensitive ZIP discovery helper
from component_importer.file_discovery import iter_zip_files


# Import tab
class ImportTab(QWidget):
    # Emitted when user requests ZIP import
    importRequested = pyqtSignal(str, str)

    # Log signal
    logMessage = pyqtSignal(str)

    # Create tab
    def __init__(self, config):
        # Initialize QWidget
        super().__init__()

        # Store config
        self.config = config

        # Store listed ZIP files
        self.zip_files = []
        self.loading_downloads_list = False

        # Build UI
        self.build_ui()

        # Keep downloads list up to date when the folder changes
        self.setup_downloads_watcher()

    # Update config
    def update_config(self, config) -> None:
        # Store config
        self.config = config

        # Rewatch the configured folder and refresh without noisy log output
        self.configure_downloads_watcher()
        self.refresh_downloads(show_log=False)

    # Setup event-driven downloads-list refresh
    def setup_downloads_watcher(self) -> None:
        # Refresh once after the tab is constructed
        QTimer.singleShot(0, lambda: self.refresh_downloads(show_log=False))

        # Watch the downloads folder for OS-reported changes
        self.downloads_watcher = QFileSystemWatcher(self)
        self.downloads_watcher.directoryChanged.connect(
            self.on_downloads_folder_changed
        )

        # Coalesce bursts of filesystem notifications into one refresh
        self.downloads_refresh_timer = QTimer(self)
        self.downloads_refresh_timer.setSingleShot(True)
        self.downloads_refresh_timer.setInterval(300)
        self.downloads_refresh_timer.timeout.connect(
            lambda: self.refresh_downloads(show_log=False)
        )

        # Watch the configured folder
        self.configure_downloads_watcher()

    # Watch the currently configured downloads folder
    def configure_downloads_watcher(self) -> None:
        watched_directories = self.downloads_watcher.directories()

        if watched_directories:
            self.downloads_watcher.removePaths(watched_directories)

        folder = Path(self.config.downloads_folder)

        if folder.exists():
            self.downloads_watcher.addPath(str(folder))

    # Build UI
    def build_ui(self) -> None:
        # Main layout
        main_layout = QVBoxLayout(self)

        # Help label
        help_label = QLabel(
            "Manual import uses the configured project root and shared libraries. "
            "The ZIP can be imported while KiCad is open. If KiCad caches a dialog, close and reopen only that dialog."
        )
        help_label.setWordWrap(True)

        # Form layout
        form_layout = QFormLayout()

        # ZIP row
        self.zip_path_edit = QLineEdit()
        self.zip_path_button = QPushButton("Browse")

        zip_row = QHBoxLayout()
        zip_row.addWidget(self.zip_path_edit)
        zip_row.addWidget(self.zip_path_button)

        # Add rows
        form_layout.addRow("Component ZIP:", zip_row)

        # Button row
        button_row = QHBoxLayout()
        self.import_button = QPushButton("Import ZIP")

        button_row.addWidget(self.import_button)
        button_row.addStretch()

        # ZIP list
        self.downloads_list = QListWidget()

        # Add widgets
        main_layout.addWidget(help_label)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)
        main_layout.addWidget(QLabel("Latest ZIP files in watch/downloads folder:"))
        main_layout.addWidget(self.downloads_list)

        # Connect signals
        self.zip_path_button.clicked.connect(self.browse_zip)
        self.import_button.clicked.connect(self.request_import)
        self.downloads_list.currentRowChanged.connect(self.select_zip_from_row)

    # Browse ZIP file
    def browse_zip(self) -> None:
        # Open file chooser
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select component ZIP file",
            self.config.downloads_folder,
            "ZIP files (*.zip);;All files (*.*)",
        )

        # Use selected file
        if file_path:
            self.zip_path_edit.setText(file_path)

    # Refresh downloads list after the watched folder changes
    def on_downloads_folder_changed(self, folder: str) -> None:
        # Some platforms drop the watch after changes; keep it attached
        if folder and folder not in self.downloads_watcher.directories():
            self.downloads_watcher.addPath(folder)

        self.downloads_refresh_timer.start()

    # Get latest ZIP files from configured downloads folder
    def get_latest_download_zips(self, show_log: bool) -> list[Path] | None:
        # Get downloads folder
        folder = Path(self.config.downloads_folder)

        # Validate folder
        if not folder.exists():
            if show_log:
                self.logMessage.emit(f"Downloads folder does not exist: {folder}")

            return None

        # Store ZIP file paths that can still be statted
        zip_file_rows = []

        for zip_file in iter_zip_files(folder):
            try:
                modified_time = zip_file.stat().st_mtime
            except OSError:
                continue

            zip_file_rows.append((modified_time, zip_file))

        # Return newest ZIP files first
        zip_file_rows.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            zip_file
            for _modified_time, zip_file in zip_file_rows[:20]
        ]

    # Replace downloads list contents while preserving selection when possible
    def populate_downloads_list(self, zip_files: list[Path]) -> None:
        # Remember selected item by path
        selected_path = None
        row = self.downloads_list.currentRow()

        if 0 <= row < len(self.zip_files):
            selected_path = str(self.zip_files[row])

        self.loading_downloads_list = True

        try:
            # Clear list
            self.downloads_list.clear()
            self.zip_files = zip_files

            # Fill list
            for zip_file in self.zip_files:
                self.downloads_list.addItem(str(zip_file))

            # Restore selection if that ZIP is still listed
            if selected_path is None:
                return

            for index, zip_file in enumerate(self.zip_files):
                if str(zip_file) == selected_path:
                    self.downloads_list.setCurrentRow(index)
                    return
        finally:
            self.loading_downloads_list = False

    # Refresh downloads list
    def refresh_downloads(self, show_log: bool = True) -> None:
        # Get latest ZIP files
        zip_files = self.get_latest_download_zips(show_log=show_log)

        # Stop if folder was invalid
        if zip_files is None:
            return

        # Avoid repainting the list when nothing changed
        old_paths = [str(zip_file) for zip_file in self.zip_files]
        new_paths = [str(zip_file) for zip_file in zip_files]

        if old_paths != new_paths:
            self.populate_downloads_list(zip_files)

        # Log message
        if show_log:
            self.logMessage.emit(f"Found {len(self.zip_files)} ZIP files.")

    # Put the selected ZIP in the Component ZIP field
    def select_zip_from_row(self, row: int) -> None:
        # Stop if invalid
        if row < 0 or row >= len(self.zip_files):
            return

        # Get ZIP path
        zip_path = self.zip_files[row]

        # Set ZIP path
        self.zip_path_edit.setText(str(zip_path))

        # Log only for user selection, not silent list refresh restores
        if not self.loading_downloads_list:
            self.logMessage.emit(f"Selected ZIP: {zip_path}")

    # Request import
    def request_import(self) -> None:
        # Get ZIP path
        zip_path = self.zip_path_edit.text().strip()

        # Stop if ZIP empty
        if not zip_path:
            self.logMessage.emit("ZIP path is empty.")
            return

        # Infer part name internally for metadata and import logs
        part_name = infer_part_name_from_zip(zip_path)

        # Emit import request
        self.importRequested.emit(zip_path, part_name)
