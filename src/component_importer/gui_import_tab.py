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

# Import signals
from PyQt6.QtCore import pyqtSignal

# Import Path
from pathlib import Path

# Import part name inference
from component_importer.gui_config_manager import infer_part_name_from_zip


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

        # Build UI
        self.build_ui()

    # Update config
    def update_config(self, config) -> None:
        # Store config
        self.config = config

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
        self.refresh_downloads_button = QPushButton("Refresh Downloads")
        self.use_selected_zip_button = QPushButton("Use Selected ZIP")

        button_row.addWidget(self.import_button)
        button_row.addWidget(self.refresh_downloads_button)
        button_row.addWidget(self.use_selected_zip_button)
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
        self.refresh_downloads_button.clicked.connect(self.refresh_downloads)
        self.use_selected_zip_button.clicked.connect(self.use_selected_zip)
        self.downloads_list.itemDoubleClicked.connect(self.use_selected_zip)

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

    # Refresh downloads list
    def refresh_downloads(self) -> None:
        # Clear list
        self.downloads_list.clear()
        self.zip_files = []

        # Get downloads folder
        folder = Path(self.config.downloads_folder)

        # Validate folder
        if not folder.exists():
            self.logMessage.emit(f"Downloads folder does not exist: {folder}")
            return

        # Get latest ZIP files
        self.zip_files = sorted(
            folder.glob("*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:20]

        # Fill list
        for zip_file in self.zip_files:
            self.downloads_list.addItem(str(zip_file))

        # Log message
        self.logMessage.emit(f"Found {len(self.zip_files)} ZIP files.")

    # Use selected ZIP
    def use_selected_zip(self) -> None:
        # Get selected row
        row = self.downloads_list.currentRow()

        # Stop if invalid
        if row < 0 or row >= len(self.zip_files):
            self.logMessage.emit("No ZIP selected.")
            return

        # Get ZIP path
        zip_path = self.zip_files[row]

        # Set ZIP path
        self.zip_path_edit.setText(str(zip_path))

        # Log
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
