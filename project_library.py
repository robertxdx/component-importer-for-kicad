# Import Path for filesystem operations
from pathlib import Path


# Create an empty KiCad symbol library if it does not already exist
def create_empty_symbol_library(symbol_library_path: str | Path) -> None:
    # Convert input to Path object
    symbol_library_path = Path(symbol_library_path)

    # Do nothing if symbol library already exists
    if symbol_library_path.exists():
        return

    # Create parent folder if needed
    symbol_library_path.parent.mkdir(parents=True, exist_ok=True)

    # Write minimal KiCad symbol library file
    symbol_library_path.write_text(
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        '  (generator "component_importer")\n'
        '  (generator_version "0.1")\n'
        ")\n",
        encoding="utf-8",
    )


# Create the folder structure used by our KiCad project-local library
def create_project_library_structure(
    project_root: str | Path,
    library_name: str,
    symbol_library_name: str | None = None,
    footprint_library_name: str | None = None,
) -> dict[str, Path]:
    # Convert input to a Path object
    project_root = Path(project_root)

    # Use the same library name for symbols and footprints if specific names are not provided
    if symbol_library_name is None:
        symbol_library_name = library_name

    if footprint_library_name is None:
        footprint_library_name = library_name

    # Main folder where all local libraries will be stored
    libraries_dir = project_root / "libraries"

    # Main shared KiCad symbol library
    symbol_lib_path = libraries_dir / f"{symbol_library_name}.kicad_sym"

    # Folder where raw imported symbol libraries can be stored if needed later
    symbol_imports_dir = libraries_dir / "imported_symbols"

    # KiCad footprint library folder
    # KiCad footprint libraries use the .pretty folder extension
    footprint_lib_dir = libraries_dir / f"{footprint_library_name}.pretty"

    # Folder for STEP, STP, WRL, and STL 3D models
    models_dir = libraries_dir / "3dmodels"

    # Folder where original downloaded ZIP files are stored for traceability
    source_zips_dir = libraries_dir / "source_zips"

    # Folder for JSON metadata, PDFs, and other support files
    metadata_dir = libraries_dir / "metadata"

    # Create all folders
    libraries_dir.mkdir(parents=True, exist_ok=True)
    symbol_imports_dir.mkdir(parents=True, exist_ok=True)
    footprint_lib_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    source_zips_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    # Create the selected shared symbol library if missing
    create_empty_symbol_library(symbol_lib_path)

    # Return all important paths so other modules can use them
    return {
        "project_root": project_root,
        "libraries_dir": libraries_dir,
        "symbol_lib_path": symbol_lib_path,
        "symbol_imports_dir": symbol_imports_dir,
        "footprint_lib_dir": footprint_lib_dir,
        "models_dir": models_dir,
        "source_zips_dir": source_zips_dir,
        "metadata_dir": metadata_dir,
        "symbol_library_name": symbol_library_name,
        "footprint_library_name": footprint_library_name,
    }