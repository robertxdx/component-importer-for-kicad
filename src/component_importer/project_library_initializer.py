# Import Path for filesystem paths
from pathlib import Path

# Import project library helpers
from component_importer.project_library import create_project_library_structure
from component_importer.library_table_updater import update_kicad_library_tables
from component_importer.library_table_updater import update_global_kicad_library_tables
from component_importer.library_table_updater import find_library_uri_in_table
from component_importer.backup_helper import backup_file_if_exists
from component_importer.backup_helper import get_backup_timestamp


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


# Ensure persistent global libraries exist and are registered with one KiCad version
def initialize_global_libraries(
    global_library_root: str | Path,
    kicad_config_dir: str | Path,
    library_name: str,
) -> dict:
    global_library_root = Path(global_library_root).expanduser().resolve()
    kicad_config_dir = Path(kicad_config_dir).expanduser().resolve()
    paths = create_project_library_structure(
        project_root=global_library_root,
        library_name=library_name,
        symbol_library_name=library_name,
        footprint_library_name=library_name,
        layout="external",
    )

    backup_timestamp = get_backup_timestamp()
    backups = []

    for table_name in ["fp-lib-table", "sym-lib-table"]:
        table_path = kicad_config_dir / table_name

        # Avoid making a new backup on every app start when registration is ready.
        existing_uri = find_library_uri_in_table(table_path, library_name)

        if existing_uri is not None:
            continue

        backup_path = backup_file_if_exists(
            project_root=global_library_root,
            target_file=table_path,
            backup_timestamp=backup_timestamp,
        )

        if backup_path:
            backups.append(backup_path)

    table_update = update_global_kicad_library_tables(
        kicad_config_dir=kicad_config_dir,
        library_name=library_name,
        footprint_library_path=paths["footprint_lib_dir"],
        symbol_library_paths=[paths["symbol_lib_path"]],
    )

    return {
        "symbol_library": str(paths["symbol_lib_path"]),
        "footprint_library": str(paths["footprint_lib_dir"]),
        "table_update": table_update,
        "backups": backups,
    }
