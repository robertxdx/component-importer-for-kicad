# Import Path for normal filesystem paths
# Import PurePosixPath for paths inside ZIP files
from pathlib import Path, PurePosixPath

# Import ZipFile to read ZIP archives
from zipfile import ZipFile

# Import our shared data model and asset type enum
from models import CadAsset, AssetType


# Detect what kind of CAD asset a file is based on its extension
def detect_asset_type(path: PurePosixPath) -> AssetType:
    # Convert file extension to lowercase so detection is case-insensitive
    suffix = path.suffix.lower()

    # KiCad symbol library
    if suffix == ".kicad_sym":
        return AssetType.SYMBOL_LIB

    # KiCad footprint file
    if suffix == ".kicad_mod":
        return AssetType.FOOTPRINT

    # STEP 3D model
    if suffix in [".step", ".stp"]:
        return AssetType.STEP_MODEL

    # WRL 3D model
    if suffix == ".wrl":
        return AssetType.WRL_MODEL

    # STL 3D model
    if suffix == ".stl":
        return AssetType.STL_MODEL

    # PDF datasheet or documentation
    if suffix == ".pdf":
        return AssetType.DATASHEET

    # File type not supported yet
    return AssetType.UNKNOWN


# Scan a CAD ZIP file and return all supported CAD assets found inside it
def scan_cad_zip(zip_path: str | Path) -> list[CadAsset]:
    # Convert input to a Path object
    zip_path = Path(zip_path)

    # Stop early if the ZIP file does not exist
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path.resolve()}")

    # This list will store all detected CAD assets
    assets: list[CadAsset] = []

    # Open the ZIP file for reading
    with ZipFile(zip_path, "r") as zf:
        # Loop through every file and folder name inside the ZIP
        for name in zf.namelist():
            # Skip folders
            if name.endswith("/"):
                continue

            # Convert the internal ZIP path to a POSIX path
            # ZIP archives always use "/" internally
            internal_path = PurePosixPath(name)

            # Detect file type
            asset_type = detect_asset_type(internal_path)

            # Skip unsupported files
            if asset_type == AssetType.UNKNOWN:
                continue

            # Store the detected asset
            assets.append(
                CadAsset(
                    asset_type=asset_type,
                    original_path=internal_path,
                    filename=internal_path.name,
                    extension=internal_path.suffix.lower(),
                )
            )

    # Return all supported files found in the ZIP
    return assets