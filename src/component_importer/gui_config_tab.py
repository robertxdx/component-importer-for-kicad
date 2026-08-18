# Import widgets
from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QFormLayout
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtWidgets import QLabel

# Import signals and timers
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal

# Import config helpers
from component_importer.gui_config_manager import GuiConfig
from component_importer.gui_config_manager import save_gui_config
from component_importer.gui_config_manager import validate_gui_config
from component_importer.startup_manager import startup_supported


# Configuration tab
class ConfigTab(QWidget):
    # Emitted when config is saved
    configSaved = pyqtSignal(object, bool)

    # Emitted for log messages
    logMessage = pyqtSignal(str)

    # Create tab
    def __init__(self, config: GuiConfig):
        # Initialize QWidget
        super().__init__()

        # Store config
        self.config = config

        # Track when fields are being populated programmatically
        self.loading_config = False

        # Build UI
        self.build_ui()

        # Load config into fields
        self.load_config_to_fields()

        # Autosave config when fields are edited
        self.setup_auto_save()

    # Update tab state from a config object
    def update_config(self, config: GuiConfig) -> None:
        self.config = config
        self.load_config_to_fields()

    # Build UI widgets
    def build_ui(self) -> None:
        # Main layout
        main_layout = QVBoxLayout(self)

        # Form layout
        form_layout = QFormLayout()

        # Project root field
        self.project_root_edit = QLineEdit()
        self.project_root_edit.setPlaceholderText(
            "Folder containing the .kicad_pro file"
        )
        self.project_root_button = QPushButton("Browse")

        # Project root row
        project_row = QHBoxLayout()
        project_row.addWidget(self.project_root_edit)
        project_row.addWidget(self.project_root_button)

        # Downloads folder field
        self.downloads_folder_edit = QLineEdit()
        self.downloads_folder_edit.setPlaceholderText(
            "Folder where component ZIP files are downloaded"
        )
        self.downloads_folder_button = QPushButton("Browse")

        # Downloads row
        downloads_row = QHBoxLayout()
        downloads_row.addWidget(self.downloads_folder_edit)
        downloads_row.addWidget(self.downloads_folder_button)

        # Library fields
        self.library_name_edit = QLineEdit()
        self.library_name_edit.setPlaceholderText("Example: Project_Components")

        # Optional global-library destination
        self.import_to_global_checkbox = QCheckBox(
            "Also import components into a KiCad global library"
        )
        self.global_library_root_edit = QLineEdit()
        self.global_library_root_edit.setPlaceholderText(
            "External folder that will contain the global library"
        )
        self.global_library_root_button = QPushButton("Browse")
        global_library_row = QHBoxLayout()
        global_library_row.addWidget(self.global_library_root_edit)
        global_library_row.addWidget(self.global_library_root_button)

        self.global_library_name_edit = QLineEdit()
        self.global_library_name_edit.setPlaceholderText(
            "Example: My_Global_Library"
        )

        self.kicad_config_dir_edit = QLineEdit()
        self.kicad_config_dir_edit.setPlaceholderText(
            "KiCad version folder containing sym-lib-table and fp-lib-table"
        )
        self.kicad_config_dir_button = QPushButton("Browse")
        kicad_config_row = QHBoxLayout()
        kicad_config_row.addWidget(self.kicad_config_dir_edit)
        kicad_config_row.addWidget(self.kicad_config_dir_button)

        # Auto import checkbox
        self.auto_import_checkbox = QCheckBox("Automatically import new ZIP files from watched folder")

        # Startup checkbox
        self.start_with_windows_checkbox = QCheckBox(
            "Start automatically on login"
        )
        self.start_with_windows_checkbox.setEnabled(startup_supported())
        self.start_with_windows_checkbox.setToolTip(
            "When started automatically, the app opens minimized to the tray "
            "when a system tray is available."
        )

        # Add rows
        form_layout.addRow("KiCad project root:", project_row)
        form_layout.addRow("Downloads/watch folder:", downloads_row)
        form_layout.addRow("Library name:", self.library_name_edit)
        form_layout.addRow("", self.import_to_global_checkbox)
        form_layout.addRow("Global library folder:", global_library_row)
        form_layout.addRow("Global library name:", self.global_library_name_edit)
        form_layout.addRow("KiCad global config folder:", kicad_config_row)
        form_layout.addRow("", self.auto_import_checkbox)
        form_layout.addRow("", self.start_with_windows_checkbox)

        # Help label
        help_label = QLabel(
            "Use the folder that contains the .kicad_pro file as project root. "
            "Global imports are stored separately and registered in the selected "
            "KiCad version's user library tables."
        )
        help_label.setWordWrap(True)

        # Buttons
        button_row = QHBoxLayout()
        self.save_button = QPushButton("Save Configuration")
        button_row.addWidget(self.save_button)
        button_row.addStretch()

        # Add layouts
        main_layout.addWidget(help_label)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_row)
        main_layout.addStretch()

        # Connect buttons
        self.project_root_button.clicked.connect(self.browse_project_root)
        self.downloads_folder_button.clicked.connect(self.browse_downloads_folder)
        self.global_library_root_button.clicked.connect(self.browse_global_library_root)
        self.kicad_config_dir_button.clicked.connect(self.browse_kicad_config_dir)
        self.save_button.clicked.connect(self.save_config_from_fields)
        self.import_to_global_checkbox.stateChanged.connect(
            self.update_global_fields_enabled
        )

    # Connect field changes to a short autosave timer
    def setup_auto_save(self) -> None:
        # Timer coalesces rapid edits into one save
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.setInterval(300)
        self.auto_save_timer.timeout.connect(self.auto_save_config_from_fields)

        # Text fields save after editing is finished
        for line_edit in [
            self.project_root_edit,
            self.downloads_folder_edit,
            self.library_name_edit,
            self.global_library_root_edit,
            self.global_library_name_edit,
            self.kicad_config_dir_edit,
        ]:
            line_edit.editingFinished.connect(self.schedule_auto_save)

        # Discrete controls save shortly after changing
        self.auto_import_checkbox.stateChanged.connect(self.schedule_auto_save)
        self.start_with_windows_checkbox.stateChanged.connect(self.schedule_auto_save)
        self.import_to_global_checkbox.stateChanged.connect(self.schedule_auto_save)

    # Start autosave unless fields are being loaded
    def schedule_auto_save(self, *args) -> None:
        if self.loading_config:
            return

        self.auto_save_timer.start()

    # Load config values into fields
    def load_config_to_fields(self) -> None:
        # Avoid autosaving while applying loaded config values
        self.loading_config = True

        # Set text fields
        self.project_root_edit.setText(self.config.project_root)
        self.downloads_folder_edit.setText(self.config.downloads_folder)
        self.library_name_edit.setText(self.config.library_name)
        self.global_library_root_edit.setText(self.config.global_library_root)
        self.global_library_name_edit.setText(self.config.global_library_name)
        self.kicad_config_dir_edit.setText(self.config.kicad_config_dir)

        # Set checkboxes
        self.auto_import_checkbox.setChecked(self.config.auto_import_enabled)
        self.start_with_windows_checkbox.setChecked(self.config.start_with_windows)
        self.import_to_global_checkbox.setChecked(
            self.config.import_to_global_library
        )
        self.update_global_fields_enabled()

        # Field population is complete
        self.loading_config = False

    # Browse project root
    def browse_project_root(self) -> None:
        # Open folder chooser
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select KiCad project root",
            self.project_root_edit.text(),
        )

        # Store folder if selected
        if folder:
            self.project_root_edit.setText(folder)
            self.schedule_auto_save()

    # Browse downloads folder
    def browse_downloads_folder(self) -> None:
        # Open folder chooser
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select downloads/watch folder",
            self.downloads_folder_edit.text(),
        )

        # Store folder if selected
        if folder:
            self.downloads_folder_edit.setText(folder)
            self.schedule_auto_save()

    # Browse persistent global library storage folder
    def browse_global_library_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select global library storage folder",
            self.global_library_root_edit.text(),
        )

        if folder:
            self.global_library_root_edit.setText(folder)
            self.schedule_auto_save()

    # Browse the versioned KiCad folder containing global library tables
    def browse_kicad_config_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select KiCad global configuration folder",
            self.kicad_config_dir_edit.text(),
        )

        if folder:
            self.kicad_config_dir_edit.setText(folder)
            self.schedule_auto_save()

    # Keep global-only path controls quiet when the feature is disabled
    def update_global_fields_enabled(self, *args) -> None:
        enabled = self.import_to_global_checkbox.isChecked()

        for widget in [
            self.global_library_root_edit,
            self.global_library_root_button,
            self.global_library_name_edit,
            self.kicad_config_dir_edit,
            self.kicad_config_dir_button,
        ]:
            widget.setEnabled(enabled)

    # Build a config object from current field values
    def build_config_from_fields(self) -> GuiConfig:
        library_name = self.library_name_edit.text().strip()

        return GuiConfig(
            project_root=self.project_root_edit.text().strip(),
            library_name=library_name,
            symbol_library_name=library_name,
            footprint_library_name=library_name,
            downloads_folder=self.downloads_folder_edit.text().strip(),
            import_to_global_library=self.import_to_global_checkbox.isChecked(),
            global_library_root=self.global_library_root_edit.text().strip(),
            global_library_name=self.global_library_name_edit.text().strip(),
            kicad_config_dir=self.kicad_config_dir_edit.text().strip(),
            create_backups=True,
            auto_import_enabled=self.auto_import_checkbox.isChecked(),
            start_with_windows=self.start_with_windows_checkbox.isChecked(),
            symbol_style_enabled=self.config.symbol_style_enabled,
            symbol_style_preset=self.config.symbol_style_preset,
            symbol_line_width_mm=self.config.symbol_line_width_mm,
            symbol_line_color=self.config.symbol_line_color,
            symbol_fill_mode=self.config.symbol_fill_mode,
            symbol_fill_color=self.config.symbol_fill_color,
            symbol_font_size_mm=self.config.symbol_font_size_mm,
        )

    # Save config from fields
    def save_config_from_fields(self) -> None:
        self.commit_config_from_fields(show_log=True)

    # Autosave config without noisy log messages
    def auto_save_config_from_fields(self) -> None:
        self.commit_config_from_fields(show_log=False)

    # Save current fields and notify the main window
    def commit_config_from_fields(self, show_log: bool = False) -> None:
        # Build config
        config = self.build_config_from_fields()

        # Reflect normalized values, such as safe library-name cleanup
        self.loading_config = True
        self.library_name_edit.setText(config.library_name)
        self.loading_config = False

        # Validate config
        errors = validate_gui_config(config)

        # Log warnings or success
        if show_log:
            if errors:
                for error in errors:
                    self.logMessage.emit(f"Config warning: {error}")
            else:
                self.logMessage.emit("Configuration looks valid.")

        # Save config
        save_gui_config(config)

        # Store config
        self.config = config

        # Emit config
        self.configSaved.emit(config, show_log)

        # Log message
        if show_log:
            self.logMessage.emit("Configuration saved.")
