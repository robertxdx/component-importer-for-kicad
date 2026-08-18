# Import QObject and signals for threaded work
from PyQt6.QtCore import QObject
from PyQt6.QtCore import pyqtSignal

# Import Path for paths
from pathlib import Path

# Import component ZIP importer
from component_importer.cad_zip_importer import import_cad_zip

# Import symbol style helper
from component_importer.gui_config_manager import build_symbol_style_from_config

# Import import validator
from component_importer.import_validator import validate_imported_part
from component_importer.library_table_updater import update_global_kicad_library_tables


# Return one failed validation check for a category, if any
def first_failed_error(validation: dict, category: str) -> dict | None:
    # Loop through checks in this category
    for check in validation.get("checks", {}).get(category, []):
        if not check.get("passed", False) and check.get("severity", "error") == "error":
            return check

    # No failed error found
    return None


# Keep error lines readable in the GUI log
def compact_error_message(message: str, max_length: int = 180) -> str:
    # Normalize whitespace
    message = " ".join(str(message).split())

    # Return short messages unchanged
    if len(message) <= max_length:
        return message

    # Truncate long paths/details
    return f"{message[:max_length - 3]}..."


# Build one compact status line
def build_status_line(
    label: str,
    validation: dict,
    validation_category: str,
) -> str:
    # Check for an error in this validation category
    failed_check = first_failed_error(validation, validation_category)

    # Return error line if needed
    if failed_check:
        message = compact_error_message(failed_check.get("message", "Unknown error"))
        return f"{label}: ERROR - {message}"

    # Return compact OK line
    return f"{label}: OK"


# Build a short GUI log summary for one import
def build_compact_import_log(
    result: dict,
    validation: dict,
    part_name: str,
) -> str:
    # Build compact lines
    lines = [
        f"Import: {part_name}",
        build_status_line("Symbol import", validation, "symbols"),
        build_status_line("Footprint import", validation, "footprints"),
        build_status_line("3D model import", validation, "3d_models"),
    ]

    # Surface library table errors without adding normal OK clutter
    library_table_error = first_failed_error(validation, "library_tables")
    if library_table_error:
        message = compact_error_message(library_table_error.get("message", "Unknown error"))
        lines.append(f"KiCad library table: ERROR - {message}")

    # Return summary text
    return "\n".join(lines)

# Worker used for importing one component ZIP
class ImportComponentWorker(QObject):
    # Emitted when import finishes successfully
    finished = pyqtSignal(object, object, str)

    # Emitted when import fails
    failed = pyqtSignal(str)

    # Create worker
    def __init__(self, zip_path: str, part_name: str, config):
        # Initialize QObject
        super().__init__()

        # Store ZIP path
        self.zip_path = zip_path

        # Store part name
        self.part_name = part_name

        # Store GUI config
        self.config = config

    # Run import operation
    def run(self) -> None:
        try:
            # Convert project root to Path
            project_root = Path(self.config.project_root)

            # Run backend import
            result = import_cad_zip(
                zip_path=self.zip_path,
                project_root=project_root,
                library_name=self.config.library_name,
                symbol_library_name=self.config.library_name,
                footprint_library_name=self.config.library_name,
                part_name=self.part_name,
                footprint_filter_mode="exact",
                create_backups=True,
                skip_existing_components=True,
                symbol_style=build_symbol_style_from_config(self.config),
            )

            # Existing components are intentionally skipped to avoid duplicates
            if result.get("skipped_existing", False):
                validation = {
                    "passed": True,
                    "warnings": [],
                    "checks": {},
                    "skipped_existing": True,
                }
                skipped_message = (
                    "Component already exists in the configured library. Import skipped."
                )

                if result.get("symbol_style_update"):
                    skipped_message += "\nSymbol style refreshed."

                if not self.config.import_to_global_library:
                    output = f"Import: {self.part_name}\n{skipped_message}"
                    self.finished.emit(result, validation, output)
                    return

            else:
                # Run validation for a project import that changed files.
                validation = validate_imported_part(
                    project_root=project_root,
                    result=result,
                    library_name=self.config.library_name,
                )

            # Optionally repeat the import into persistent libraries registered
            # in KiCad's per-user global library tables.
            if self.config.import_to_global_library:
                global_root = (
                    Path(self.config.global_library_root).expanduser().resolve()
                )
                global_result = import_cad_zip(
                    zip_path=self.zip_path,
                    project_root=global_root,
                    library_name=self.config.global_library_name,
                    symbol_library_name=self.config.global_library_name,
                    footprint_library_name=self.config.global_library_name,
                    part_name=self.part_name,
                    footprint_filter_mode="exact",
                    create_backups=True,
                    skip_existing_components=True,
                    symbol_style=build_symbol_style_from_config(self.config),
                    update_library_tables=False,
                    library_layout="external",
                )

                global_result["library_table_update"] = (
                    update_global_kicad_library_tables(
                        kicad_config_dir=self.config.kicad_config_dir,
                        library_name=self.config.global_library_name,
                        footprint_library_path=global_result[
                            "selected_footprint_library"
                        ],
                        symbol_library_paths=[
                            global_result["selected_symbol_library"]
                        ],
                    )
                )
                result["global_import"] = global_result

                if global_result.get("skipped_existing", False):
                    global_validation = {
                        "passed": True,
                        "warnings": [],
                        "checks": {},
                        "skipped_existing": True,
                    }
                else:
                    global_validation = validate_imported_part(
                        project_root=global_root,
                        result=global_result,
                        library_name=self.config.global_library_name,
                        table_root=self.config.kicad_config_dir,
                        global_tables=True,
                    )

                validation["global"] = global_validation
                validation["passed"] = (
                    validation.get("passed", False)
                    and global_validation.get("passed", False)
                )

            # Build compact GUI log output
            output = build_compact_import_log(
                result=result,
                validation=validation,
                part_name=self.part_name,
            )

            if result.get("skipped_existing", False):
                output = (
                    f"Import: {self.part_name}\n"
                    "Project library: already present"
                )

            if self.config.import_to_global_library:
                global_result = result.get("global_import", {})
                global_validation = validation.get("global", {})

                if global_result.get("skipped_existing", False):
                    output += "\nGlobal library: already present"
                elif global_validation.get("passed", False):
                    output += "\nGlobal library: OK"
                else:
                    output += "\nGlobal library: ERROR"

            # Emit result
            self.finished.emit(result, validation, output)

        except Exception as error:
            # Emit a concise user-facing error
            self.failed.emit(f"{type(error).__name__}: {error}")
