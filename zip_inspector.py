# Import Counter to count file extensions and asset types
from collections import Counter

# Import Path for normal filesystem paths
# Import PurePosixPath for paths inside ZIP files
from pathlib import Path, PurePosixPath

# Import ZipFile to read ZIP archives
from zipfile import ZipFile

# Import detect_asset_type to reuse our existing CAD asset detection logic
from zip_scanner import detect_asset_type

# Import AssetType so we can compare detected file types
from models import AssetType


# Inspect all files inside a ZIP file
def inspect_zip_contents(zip_path: str | Path) -> dict:
    # Convert input to Path object
    zip_path = Path(zip_path)

    # Stop early if the ZIP file does not exist
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path.resolve()}")

    # Prepare list of all files found inside the ZIP
    all_files = []

    # Prepare counter for file extensions
    extension_counter = Counter()

    # Prepare counter for detected asset types
    asset_type_counter = Counter()

    # Open ZIP file for reading
    with ZipFile(zip_path, "r") as zf:
        # Loop through all ZIP entries
        for info in zf.infolist():
            # Skip folders
            if info.is_dir():
                continue

            # Convert ZIP internal path to POSIX path
            internal_path = PurePosixPath(info.filename)

            # Detect asset type using our scanner logic
            asset_type = detect_asset_type(internal_path)

            # Get lowercase extension
            extension = internal_path.suffix.lower()

            # Count extension
            extension_counter[extension if extension else "[no extension]"] += 1

            # Count asset type
            asset_type_counter[asset_type.value] += 1

            # Store file details
            all_files.append(
                {
                    "path": internal_path.as_posix(),
                    "filename": internal_path.name,
                    "extension": extension,
                    "asset_type": asset_type.value,
                    "size_bytes": info.file_size,
                    "compressed_size_bytes": info.compress_size,
                }
            )

    # Return full inspection result
    return {
        "zip_path": str(zip_path),
        "file_count": len(all_files),
        "extension_counts": dict(extension_counter),
        "asset_type_counts": dict(asset_type_counter),
        "files": all_files,
    }


# Print a readable summary of ZIP contents
def print_zip_inspection_summary(inspection: dict) -> None:
    # Print ZIP path
    print("ZIP Inspection:")
    print(f"  {inspection.get('zip_path', 'Unknown')}")
    print()

    # Print total file count
    print(f"Total files: {inspection.get('file_count', 0)}")
    print()

    # Print file extension counts
    print("File extensions:")

    # Get extension counts
    extension_counts = inspection.get("extension_counts", {})

    # Print each extension count
    for extension, count in sorted(extension_counts.items()):
        print(f"  {extension}: {count}")

    # Add empty line
    print()

    # Print detected asset type counts
    print("Detected asset types:")

    # Get asset type counts
    asset_type_counts = inspection.get("asset_type_counts", {})

    # Print each asset type count
    for asset_type, count in sorted(asset_type_counts.items()):
        print(f"  {asset_type}: {count}")

    # Add empty line
    print()


# Print all files inside a ZIP
def print_all_zip_files(inspection: dict) -> None:
    # Print section title
    print("All files:")

    # Loop through files
    for file_info in inspection.get("files", []):
        # Print path, type, and size
        print(
            f"  {file_info['path']} "
            f"| type: {file_info['asset_type']} "
            f"| size: {file_info['size_bytes']} bytes"
        )

    # Add empty line
    print()


# Print only unsupported or unknown files
def print_unknown_zip_files(inspection: dict) -> None:
    # Print section title
    print("Unknown or unsupported files:")

    # Track whether anything was printed
    found_unknown = False

    # Loop through files
    for file_info in inspection.get("files", []):
        # Print only unknown files
        if file_info["asset_type"] == AssetType.UNKNOWN.value:
            print(
                f"  {file_info['path']} "
                f"| extension: {file_info['extension']} "
                f"| size: {file_info['size_bytes']} bytes"
            )

            # Mark that at least one unknown file was found
            found_unknown = True

    # Print clear message if no unknown files exist
    if not found_unknown:
        print("  None")

    # Add empty line
    print()


# Inspect a ZIP and print summary in one call
def inspect_and_print_zip(zip_path: str | Path, show_all_files: bool = False) -> dict:
    # Inspect ZIP
    inspection = inspect_zip_contents(zip_path)

    # Print summary
    print_zip_inspection_summary(inspection)

    # Print unknown files
    print_unknown_zip_files(inspection)

    # Optionally print all files
    if show_all_files:
        print_all_zip_files(inspection)

    # Return inspection data for further use
    return inspection