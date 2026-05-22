# Import Path for filesystem operations
from pathlib import Path

# Import helpers for reusing existing project-local library table entries
from component_importer.library_table_updater import find_project_library_path_in_table
from component_importer.library_table_updater import make_library_nickname


# Return True when a candidate is below a folder that should not be reused
def is_ignored_library_search_path(path: Path) -> bool:
    ignored_parts = {
        ".git",
        "__pycache__",
        "backups",
        "source_zips",
    }

    return any(part in ignored_parts for part in path.parts)


# Find one exact same-named project library already stored under the project root
def find_unique_project_library_by_name(
    project_root: Path,
    library_filename: str,
    must_be_dir: bool,
) -> Path | None:
    matches = []

    try:
        candidates = project_root.rglob(library_filename)

        for candidate in candidates:
            if is_ignored_library_search_path(candidate):
                continue

            if must_be_dir and not candidate.is_dir():
                continue

            if not must_be_dir and not candidate.is_file():
                continue

            matches.append(candidate)
    except OSError:
        return None

    if len(matches) != 1:
        return None

    return matches[0]


# Resolve the symbol library path, preferring existing project-local libraries
def resolve_symbol_library_path(
    project_root: Path,
    libraries_dir: Path,
    symbol_library_name: str,
) -> Path:
    existing_table_path = find_project_library_path_in_table(
        project_root=project_root,
        table_name="sym-lib-table",
        library_nickname=symbol_library_name,
    )

    if existing_table_path is not None and existing_table_path.suffix == ".kicad_sym":
        return existing_table_path

    library_filename = f"{symbol_library_name}.kicad_sym"
    existing_file_path = find_unique_project_library_by_name(
        project_root=project_root,
        library_filename=library_filename,
        must_be_dir=False,
    )

    if existing_file_path is not None:
        return existing_file_path

    return libraries_dir / library_filename


# Resolve the footprint library path, preferring existing project-local libraries
def resolve_footprint_library_dir(
    project_root: Path,
    libraries_dir: Path,
    footprint_library_name: str,
) -> Path:
    existing_table_path = find_project_library_path_in_table(
        project_root=project_root,
        table_name="fp-lib-table",
        library_nickname=footprint_library_name,
    )

    if existing_table_path is not None and existing_table_path.suffix == ".pretty":
        return existing_table_path

    library_filename = f"{footprint_library_name}.pretty"
    existing_dir_path = find_unique_project_library_by_name(
        project_root=project_root,
        library_filename=library_filename,
        must_be_dir=True,
    )

    if existing_dir_path is not None:
        return existing_dir_path

    return libraries_dir / library_filename


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

    # Use KiCad-safe names for filesystem library names and table nicknames
    symbol_library_name = make_library_nickname(symbol_library_name)
    footprint_library_name = make_library_nickname(footprint_library_name)

    # Main folder where all local libraries will be stored
    libraries_dir = project_root / "libraries"

    # Main shared KiCad symbol library
    symbol_lib_path = resolve_symbol_library_path(
        project_root=project_root,
        libraries_dir=libraries_dir,
        symbol_library_name=symbol_library_name,
    )

    # Folder where raw imported symbol libraries can be stored if needed later
    symbol_imports_dir = libraries_dir / "imported_symbols"

    # KiCad footprint library folder
    # KiCad footprint libraries use the .pretty folder extension
    footprint_lib_dir = resolve_footprint_library_dir(
        project_root=project_root,
        libraries_dir=libraries_dir,
        footprint_library_name=footprint_library_name,
    )

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
