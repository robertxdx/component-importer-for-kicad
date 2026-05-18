# Import dataclass to create simple data containers without writing boilerplate classes
from dataclasses import dataclass

# Import Enum so we can define fixed asset type values
from enum import Enum

# Import PurePosixPath because paths inside ZIP files always use "/" separators
# even when running on Windows
from pathlib import PurePosixPath


# Define all CAD asset types that our scanner can recognize
class AssetType(str, Enum):
    # KiCad symbol library file, usually ending in .kicad_sym
    SYMBOL_LIB = "symbol_library"

    # KiCad footprint file, usually ending in .kicad_mod
    FOOTPRINT = "footprint"

    # 3D model in STEP format
    STEP_MODEL = "step_model"

    # 3D model in WRL format
    WRL_MODEL = "wrl_model"

    # 3D model in STL format
    STL_MODEL = "stl_model"

    # Datasheet or documentation PDF
    DATASHEET = "datasheet"

    # Any file type we do not currently handle
    UNKNOWN = "unknown"


# Store information about one detected CAD asset inside a ZIP file
@dataclass
class CadAsset:
    # Type of asset, for example symbol, footprint, STEP model, PDF
    asset_type: AssetType

    # Full internal path inside the ZIP file
    original_path: PurePosixPath

    # Filename only, without folders
    filename: str

    # File extension, for example .kicad_mod, .step, .pdf
    extension: str