# Import Path for filesystem paths
from pathlib import Path

# Import project library helpers
from project_library import create_project_library_structure
from library_table_updater import update_kicad_library_tables


# Ensure the configured project-local libraries exist and are registered
def initialize_project_libraries(
    project_root: str | Path,
    library_name: str,
    symbol_library_name: str,
    footprint_library_name: str,
) -> dict:
    # Convert project root to Path
    project_root = Path(project_root)

    # Create empty project-local libraries and folders if needed
    paths = create_project_library_structure(
        project_root=project_root,
        library_name=library_name,
        symbol_library_name=symbol_library_name,
        footprint_library_name=footprint_library_name,
    )

    # Register the empty libraries in KiCad project tables immediately
    table_update = update_kicad_library_tables(
        project_root=project_root,
        library_name=footprint_library_name,
        footprint_library_path=paths["footprint_lib_dir"],
        symbol_library_paths=[paths["symbol_lib_path"]],
    )

    # Return useful status for logging/debugging
    return {
        "symbol_library": str(paths["symbol_lib_path"]),
        "footprint_library": str(paths["footprint_lib_dir"]),
        "table_update": table_update,
    }
