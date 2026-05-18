# Import dataclass for simple config storage
from dataclasses import dataclass

# Import asdict to convert dataclass to dictionary
from dataclasses import asdict

# Import fields to ignore stale keys from older config files
from dataclasses import fields

# Import Path for filesystem paths
from pathlib import Path

# Import json for reading and writing config files
import json

# Import re for extracting part names from ZIP filenames
import re

# Import app path helper
from component_importer.app_paths import gui_config_file_path


# Default config file
CONFIG_FILE = gui_config_file_path()

# Built-in ZIP stability delay used by the auto importer
RECOMMENDED_STABLE_ZIP_DELAY_SECONDS = 4


# Store GUI configuration
@dataclass
class GuiConfig:
    # KiCad project root folder, this must contain the .kicad_pro file
    project_root: str = ""

    # Main library name used as fallback
    library_name: str = "Project_Components"

    # Symbol library name without .kicad_sym
    symbol_library_name: str = "Project_Components"

    # Footprint library name without .pretty
    footprint_library_name: str = "Project_Components"

    # Folder watched for newly downloaded ZIP files
    downloads_folder: str = str(Path.home() / "Downloads")

    # Create backups before overwriting files
    create_backups: bool = True

    # Automatically import new ZIP files detected in downloads folder
    auto_import_enabled: bool = False


# Convert a dictionary to GuiConfig with safe defaults
def config_from_dict(data: dict) -> GuiConfig:
    # Create default config
    default_config = GuiConfig()

    # Convert default config to dictionary
    default_data = asdict(default_config)

    # Update defaults with loaded data
    default_data.update(data)

    # Backups are intentionally always enabled, even for older config files
    default_data["create_backups"] = True

    # Ignore keys from older versions of the GUI config
    allowed_keys = {field.name for field in fields(GuiConfig)}
    default_data = {
        key: value
        for key, value in default_data.items()
        if key in allowed_keys
    }

    # Return config object
    return GuiConfig(**default_data)


# Load GUI config from disk
def load_gui_config(config_path: str | Path = CONFIG_FILE) -> GuiConfig:
    # Convert config path to Path object
    config_path = Path(config_path)

    # Return defaults if config file does not exist
    if not config_path.exists():
        return GuiConfig()

    # Read config file
    data = json.loads(config_path.read_text(encoding="utf-8"))

    # Convert dictionary to config object
    return config_from_dict(data)


# Save GUI config to disk
def save_gui_config(config: GuiConfig, config_path: str | Path = CONFIG_FILE) -> None:
    # Convert config path to Path object
    config_path = Path(config_path)

    # Create parent folder if needed
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Backups are intentionally always enabled
    data = asdict(config)
    data["create_backups"] = True

    # Write formatted JSON
    config_path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


# Make a string safe for filenames and simple part names
def safe_name(value: str) -> str:
    # Replace invalid characters with underscore
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)

    # Remove leading and trailing whitespace and underscores
    value = value.strip().strip("_")

    # Return fallback if empty
    if not value:
        return "UnknownPart"

    # Return cleaned name
    return value


# Infer part name from a downloaded ZIP filename
def infer_part_name_from_zip(zip_path: str | Path) -> str:
    # Convert path to Path object
    zip_path = Path(zip_path)

    # Get filename without extension
    stem = zip_path.stem

    # Split filename into tokens
    tokens = re.split(r"[^A-Za-z0-9]+", stem)

    # Ignore generic provider/file tokens
    ignored_tokens = {
        "LIB",
        "UL",
        "KICAD",
        "KI",
        "CAD",
        "MODEL",
        "MODELS",
        "SYMBOL",
        "FOOTPRINT",
        "FOOTPRINTS",
        "DOWNLOAD",
        "EXPORT",
    }

    # Keep useful tokens
    candidates = [
        token
        for token in tokens
        if len(token) >= 4 and token.upper() not in ignored_tokens
    ]

    # Prefer the last useful token
    if candidates:
        return safe_name(candidates[-1])

    # Fallback to cleaned filename stem
    return safe_name(stem)


# Validate basic config values
def validate_gui_config(config: GuiConfig) -> list[str]:
    # Store validation messages
    errors = []

    # Check project root
    if not config.project_root:
        errors.append("Project root is empty.")
    elif not Path(config.project_root).exists():
        errors.append(f"Project root does not exist: {config.project_root}")
    else:
        project_files = list(Path(config.project_root).glob("*.kicad_pro"))

        if not project_files:
            errors.append("Project root does not contain a .kicad_pro file.")

    # Check downloads folder
    if not config.downloads_folder:
        errors.append("Downloads folder is empty.")
    elif not Path(config.downloads_folder).exists():
        errors.append(f"Downloads folder does not exist: {config.downloads_folder}")

    # Check library names
    if not config.symbol_library_name.strip():
        errors.append("Symbol library name is empty.")

    if not config.footprint_library_name.strip():
        errors.append("Footprint library name is empty.")

    # Return validation errors
    return errors
