# Import Path for normal filesystem paths
# Import PurePosixPath for paths inside ZIP files
from pathlib import Path, PurePosixPath

# Import ZipFile to read ZIP archives
from zipfile import ZipFile

# Import re for portable filename cleanup
import re

# Import our shared data model and asset type enum
from component_importer.models import CadAsset, AssetType


# Maximum number of ZIP entries accepted before scanning stops
MAX_ZIP_ENTRIES = 2000

# Maximum size for one supported CAD asset inside the ZIP
MAX_SUPPORTED_ASSET_BYTES = 500 * 1024 * 1024

# Maximum total uncompressed size for supported CAD assets
MAX_TOTAL_SUPPORTED_ASSET_BYTES = 1024 * 1024 * 1024


# Make a portable filename from a ZIP member basename
def safe_member_filename(filename: str, fallback: str = "imported_asset") -> str:
    # Replace path separators and characters invalid on Windows
    filename = re.sub(r'[<>:"/\\|?*]+', "_", filename)

    # Remove control characters
    filename = "".join(
        char
        for char in filename
        if ord(char) >= 32
    )

    # Avoid awkward Windows trailing characters
    filename = filename.strip().strip(".")

    # Return fallback if empty after cleanup
    if not filename:
        return fallback

    # Avoid Windows device filenames
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    stem = Path(filename).stem.upper()

    if stem in reserved_names:
        filename = f"_{filename}"

    return filename


# Validate one ZIP member path before using it as an import source
def validate_zip_member_path(member_name: str) -> PurePosixPath:
    # ZIP paths should use POSIX separators; reject Windows separators directly
    if "\\" in member_name:
        raise ValueError(f"Unsafe ZIP member path contains backslashes: {member_name}")

    # Reject drive-relative and drive-absolute Windows paths
    if re.match(r"^[A-Za-z]:", member_name):
        raise ValueError(f"Unsafe ZIP member path contains a drive prefix: {member_name}")

    internal_path = PurePosixPath(member_name)

    # Reject absolute paths and parent traversal
    if internal_path.is_absolute() or ".." in internal_path.parts:
        raise ValueError(f"Unsafe ZIP member path: {member_name}")

    # Reject entries without a usable basename
    if not internal_path.name:
        raise ValueError(f"ZIP member path has no filename: {member_name}")

    return internal_path


# Validate one ZIP entry before importing it
def validate_supported_zip_entry(member_name: str, file_size: int, flag_bits: int) -> None:
    # Encrypted files cannot be imported safely without a password flow
    if flag_bits & 0x1:
        raise ValueError(f"Encrypted ZIP member is not supported: {member_name}")

    # Stop oversized supported assets before extraction or full text reads
    if file_size > MAX_SUPPORTED_ASSET_BYTES:
        raise ValueError(
            f"ZIP member is too large to import safely: {member_name}"
        )


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

    # Track total supported-asset size for zip-bomb protection
    total_supported_asset_size = 0

    # Open the ZIP file for reading
    with ZipFile(zip_path, "r") as zf:
        # Read central directory once
        zip_infos = zf.infolist()

        # Refuse extreme file counts before scanning
        if len(zip_infos) > MAX_ZIP_ENTRIES:
            raise ValueError(
                f"ZIP contains too many entries: {len(zip_infos)}"
            )

        # Loop through every file and folder name inside the ZIP
        for info in zip_infos:
            # Skip folders
            if info.is_dir():
                continue

            # Convert the internal ZIP path to a POSIX path for type detection
            raw_internal_path = PurePosixPath(info.filename)

            # Detect file type
            asset_type = detect_asset_type(raw_internal_path)

            # Skip unsupported files
            if asset_type == AssetType.UNKNOWN:
                continue

            # Validate supported paths before accepting them for import
            internal_path = validate_zip_member_path(info.filename)

            # Validate supported entry before accepting it for import
            validate_supported_zip_entry(
                member_name=info.filename,
                file_size=info.file_size,
                flag_bits=info.flag_bits,
            )

            total_supported_asset_size += info.file_size

            if total_supported_asset_size > MAX_TOTAL_SUPPORTED_ASSET_BYTES:
                raise ValueError("ZIP supported assets are too large to import safely.")

            # Store the detected asset
            assets.append(
                CadAsset(
                    asset_type=asset_type,
                    original_path=internal_path,
                    filename=safe_member_filename(internal_path.name),
                    extension=internal_path.suffix.lower(),
                )
            )

    # Return all supported files found in the ZIP
    return assets
