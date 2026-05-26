# Import dataclass for simple config storage
from dataclasses import dataclass

# Import asdict to convert dataclass to dictionary
from dataclasses import asdict

# Import fields to ignore stale keys from older config files
from dataclasses import fields

# Import field for dynamic default values
from dataclasses import field

# Import Path for filesystem paths
from pathlib import Path

# Import ZipFile to inspect downloaded ZIP symbol names when available
from zipfile import BadZipFile
from zipfile import ZipFile

# Import json for reading and writing config files
import json

# Import re for extracting part names from ZIP filenames
import re

# Import app path helper
from component_importer.app_paths import default_downloads_dir
from component_importer.app_paths import gui_config_file_path
from component_importer.library_table_updater import make_library_nickname
from component_importer.models import AssetType
from component_importer.symbol_footprint_linker import find_symbol_blocks
from component_importer.symbol_style import KICAD_DEFAULT_BODY_LINE_WIDTH_MM
from component_importer.symbol_style import KICAD_DEFAULT_BODY_COLOR
from component_importer.symbol_style import KICAD_DEFAULT_FILL_MODE
from component_importer.symbol_style import KICAD_DEFAULT_FILL_COLOR
from component_importer.symbol_style import SymbolStyle
from component_importer.symbol_style import normalize_fill_mode
from component_importer.symbol_style import normalize_float
from component_importer.symbol_style import normalize_hex_color
from component_importer.zip_scanner import scan_cad_zip


# Default config file
CONFIG_FILE = gui_config_file_path()

# Built-in ZIP stability delay used by the auto importer
RECOMMENDED_STABLE_ZIP_DELAY_SECONDS = 4


# Normalize user-entered text values from config files and fields
def clean_config_text(value: object) -> str:
    if value is None:
        return ""

    return str(value).strip()


# Store GUI configuration
@dataclass
class GuiConfig:
    # KiCad project root folder, this must contain the .kicad_pro file
    project_root: str = ""

    # Shared library name used for generated symbol and footprint libraries
    library_name: str = "Project_Components"

    # Backward-compatible config field, always normalized to library_name
    symbol_library_name: str = "Project_Components"

    # Backward-compatible config field, always normalized to library_name
    footprint_library_name: str = "Project_Components"

    # Folder watched for newly downloaded ZIP files
    downloads_folder: str = field(
        default_factory=lambda: str(default_downloads_dir())
    )

    # Create backups before overwriting files
    create_backups: bool = True

    # Automatically import new ZIP files detected in downloads folder
    auto_import_enabled: bool = False

    # Start the app automatically when the user signs in, where supported
    start_with_windows: bool = False

    # Apply formatting to imported KiCad symbols
    symbol_style_enabled: bool = True

    # Imported symbol graphic line width in millimeters
    symbol_line_width_mm: float = KICAD_DEFAULT_BODY_LINE_WIDTH_MM

    # Imported symbol graphic stroke color
    symbol_line_color: str = KICAD_DEFAULT_BODY_COLOR

    # Imported symbol fill mode: keep, kicad_default, or color
    symbol_fill_mode: str = KICAD_DEFAULT_FILL_MODE

    # Imported symbol custom fill color, used when symbol_fill_mode is color
    symbol_fill_color: str = KICAD_DEFAULT_FILL_COLOR

    # Imported symbol text height/width in millimeters
    symbol_font_size_mm: float = 1.27

    # Keep one user-facing library name for both symbol and footprint libraries
    def __post_init__(self) -> None:
        shared_library_name = (
            clean_config_text(self.library_name)
            or clean_config_text(self.symbol_library_name)
            or clean_config_text(self.footprint_library_name)
        )

        if shared_library_name:
            shared_library_name = make_library_nickname(shared_library_name)

        self.library_name = shared_library_name
        self.symbol_library_name = shared_library_name
        self.footprint_library_name = shared_library_name
        self.symbol_style_enabled = bool(self.symbol_style_enabled)
        self.symbol_line_width_mm = normalize_float(
            self.symbol_line_width_mm,
            fallback=KICAD_DEFAULT_BODY_LINE_WIDTH_MM,
            minimum=0.0,
            maximum=5.0,
        )
        self.symbol_line_color = normalize_hex_color(self.symbol_line_color)
        self.symbol_fill_mode = normalize_fill_mode(
            self.symbol_fill_mode,
            fallback=KICAD_DEFAULT_FILL_MODE,
        )
        self.symbol_fill_color = normalize_hex_color(
            self.symbol_fill_color,
            fallback=KICAD_DEFAULT_FILL_COLOR,
        )
        self.symbol_font_size_mm = normalize_float(
            self.symbol_font_size_mm,
            fallback=1.27,
            minimum=0.1,
            maximum=20.0,
        )


# Convert a dictionary to GuiConfig with safe defaults
def config_from_dict(data: dict) -> GuiConfig:
    # Create default config
    default_config = GuiConfig()

    # Convert default config to dictionary
    default_data = asdict(default_config)

    # Update defaults with loaded data
    default_data.update(data)

    # Use the platform default when older or hand-edited configs leave this blank
    if not str(default_data.get("downloads_folder", "")).strip():
        default_data["downloads_folder"] = str(default_downloads_dir())

    # Migrate older split-name configs to one shared library name
    shared_library_name = (
        clean_config_text(data.get("library_name"))
        or clean_config_text(data.get("symbol_library_name"))
        or clean_config_text(data.get("footprint_library_name"))
        or clean_config_text(default_data.get("library_name"))
    )

    if shared_library_name:
        shared_library_name = make_library_nickname(shared_library_name)

    default_data["library_name"] = shared_library_name
    default_data["symbol_library_name"] = shared_library_name
    default_data["footprint_library_name"] = shared_library_name

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

    # Read config file, falling back to defaults if it is damaged
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GuiConfig()

    # Ignore invalid top-level config shapes
    if not isinstance(data, dict):
        return GuiConfig()

    # Convert dictionary to config object
    return config_from_dict(data)


# Save GUI config to disk
def save_gui_config(config: GuiConfig, config_path: str | Path = CONFIG_FILE) -> None:
    # Convert config path to Path object
    config_path = Path(config_path)

    # Create parent folder if needed
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalize legacy split library fields before writing
    config = GuiConfig(**asdict(config))

    # Backups are intentionally always enabled
    data = asdict(config)
    data["create_backups"] = True

    # Write formatted JSON atomically to avoid half-written config files
    temp_path = config_path.with_name(f"{config_path.name}.tmp")
    temp_path.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(config_path)


# Convert GUI style settings to the backend symbol style object
def build_symbol_style_from_config(config: GuiConfig) -> SymbolStyle | None:
    if not config.symbol_style_enabled:
        return None

    return SymbolStyle(
        line_width_mm=config.symbol_line_width_mm,
        line_color=config.symbol_line_color,
        fill_mode=config.symbol_fill_mode,
        fill_color=config.symbol_fill_color,
        font_size_mm=config.symbol_font_size_mm,
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


# Try to infer the part name from the KiCad symbol name inside a ZIP
def infer_part_name_from_zip_symbols(zip_path: str | Path) -> str:
    zip_path = Path(zip_path)

    try:
        assets = scan_cad_zip(zip_path)

        with ZipFile(zip_path, "r") as zf:
            for asset in assets:
                if asset.asset_type != AssetType.SYMBOL_LIB:
                    continue

                with zf.open(asset.original_path.as_posix()) as src:
                    content = src.read().decode("utf-8", errors="ignore")

                for block in find_symbol_blocks(content):
                    symbol_name = clean_config_text(block.get("name", ""))

                    if symbol_name:
                        return safe_name(symbol_name)

    except (BadZipFile, KeyError, OSError, ValueError):
        return ""

    return ""


# Infer a useful part name from a ZIP filename without splitting on part dots
def infer_part_name_from_zip_filename(zip_path: str | Path) -> str:
    zip_path = Path(zip_path)
    stem = zip_path.stem.strip()

    # Drop browser duplicate suffixes like " (1)" before cleanup
    stem = re.sub(r"\s+\(\d+\)$", "", stem).strip()

    generic_word = (
        r"lib|ul|kicad|ki[-_\s]*cad|cad|model|models|symbol|symbols|"
        r"footprint|footprints|download|export"
    )

    # Strip common provider prefixes while preserving dots and dashes in parts
    while True:
        cleaned = re.sub(
            rf"(?i)^(?:{generic_word})[\s_.-]+",
            "",
            stem,
        ).strip()

        if cleaned == stem:
            break

        stem = cleaned

    # Strip common provider suffixes if a vendor adds them after the part name
    while True:
        cleaned = re.sub(
            rf"(?i)[\s_.-]+(?:{generic_word})$",
            "",
            stem,
        ).strip()

        if cleaned == stem:
            break

        stem = cleaned

    return safe_name(stem)


# Infer part name from a downloaded ZIP
def infer_part_name_from_zip(zip_path: str | Path) -> str:
    symbol_name = infer_part_name_from_zip_symbols(zip_path)

    if symbol_name:
        return symbol_name

    return infer_part_name_from_zip_filename(zip_path)


# Validate basic config values
def validate_gui_config(config: GuiConfig) -> list[str]:
    # Store validation messages
    errors = []

    # Check project root
    if not config.project_root:
        errors.append("Project root is empty.")
    elif not Path(config.project_root).exists():
        errors.append(f"Project root does not exist: {config.project_root}")
    elif not Path(config.project_root).is_dir():
        errors.append(f"Project root is not a folder: {config.project_root}")
    else:
        project_files = list(Path(config.project_root).glob("*.kicad_pro"))

        if not project_files:
            errors.append("Project root does not contain a .kicad_pro file.")

    # Check downloads folder
    if not config.downloads_folder:
        errors.append("Downloads folder is empty.")
    elif not Path(config.downloads_folder).exists():
        errors.append(f"Downloads folder does not exist: {config.downloads_folder}")
    elif not Path(config.downloads_folder).is_dir():
        errors.append(f"Downloads folder is not a folder: {config.downloads_folder}")

    # Check shared library name
    if not config.library_name.strip():
        errors.append("Library name is empty.")

    # Return validation errors
    return errors
