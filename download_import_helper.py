# Import Path for filesystem operations
from pathlib import Path

# Import Optional for optional path typing
from typing import Optional

# Import the main CAD ZIP importer
from cad_zip_importer import import_cad_zip


# Get the default Windows Downloads folder for the current user
def get_default_downloads_folder() -> Path:
    # Build path like C:\Users\YourUser\Downloads
    downloads_folder = Path.home() / "Downloads"

    # Return the detected Downloads folder
    return downloads_folder


# List ZIP files inside a folder, newest first
def list_zip_files(
    folder: str | Path,
    max_results: int = 10,
) -> list[Path]:
    # Convert input to Path object
    folder = Path(folder)

    # Stop early if folder does not exist
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder.resolve()}")

    # Find all .zip files inside the folder
    zip_files = list(folder.glob("*.zip"))

    # Sort ZIP files by modification time, newest first
    zip_files = sorted(
        zip_files,
        key=lambda file_path: file_path.stat().st_mtime,
        reverse=True,
    )

    # Return only the requested number of results
    return zip_files[:max_results]


# Print the latest ZIP files from a folder
def print_latest_zips(
    folder: str | Path | None = None,
    max_results: int = 10,
) -> list[Path]:
    # Use default Downloads folder if no folder is provided
    if folder is None:
        folder = get_default_downloads_folder()

    # Get latest ZIP files
    zip_files = list_zip_files(
        folder=folder,
        max_results=max_results,
    )

    # Print folder being searched
    print(f"Searching ZIP files in: {Path(folder)}")
    print()

    # If no ZIP files are found, print clear message
    if not zip_files:
        print("No ZIP files found.")
        return []

    # Print ZIP files with index numbers
    for index, zip_file in enumerate(zip_files, start=1):
        print(f"{index}. {zip_file}")

    # Return ZIP file list so it can be reused
    return zip_files


# Get the newest ZIP file from a folder
def get_latest_zip(
    folder: str | Path | None = None,
) -> Path:
    # Use default Downloads folder if no folder is provided
    if folder is None:
        folder = get_default_downloads_folder()

    # Get latest ZIP files
    zip_files = list_zip_files(
        folder=folder,
        max_results=1,
    )

    # Stop if no ZIP files were found
    if not zip_files:
        raise FileNotFoundError(f"No ZIP files found in: {Path(folder).resolve()}")

    # Return newest ZIP file
    return zip_files[0]


# Import a selected ZIP from a list returned by print_latest_zips
def import_selected_downloaded_zip(
    zip_files: list[Path],
    index: int,
    project_root: str | Path,
    library_name: str,
    part_name: str,
    fix_3d_paths: bool = True,
    update_library_tables: bool = True,
) -> dict:
    # Check index range
    if index < 1 or index > len(zip_files):
        raise IndexError(f"Index must be between 1 and {len(zip_files)}.")

    # Select ZIP file by human-friendly index
    zip_path = zip_files[index - 1]

    # Import selected ZIP file
    result = import_cad_zip(
        zip_path=zip_path,
        project_root=project_root,
        library_name=library_name,
        part_name=part_name,
        fix_3d_paths=fix_3d_paths,
        update_library_tables=update_library_tables,
    )

    # Return import result
    return result


# Import the newest ZIP from Downloads or another folder
def import_latest_downloaded_zip(
    project_root: str | Path,
    library_name: str,
    part_name: str,
    downloads_folder: str | Path | None = None,
    fix_3d_paths: bool = True,
    update_library_tables: bool = True,
) -> dict:
    # Get newest ZIP file
    zip_path = get_latest_zip(downloads_folder)

    # Print ZIP file being imported
    print(f"Importing latest ZIP:")
    print(f"  {zip_path}")
    print()

    # Import ZIP file
    result = import_cad_zip(
        zip_path=zip_path,
        project_root=project_root,
        library_name=library_name,
        part_name=part_name,
        fix_3d_paths=fix_3d_paths,
        update_library_tables=update_library_tables,
    )

    # Return import result
    return result