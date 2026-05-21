# Import datetime to record when an import was done
from datetime import datetime

# Import Path for filesystem paths
from pathlib import Path

# Import ZipFile to read ZIP files
from zipfile import ZipFile

# Import json to save import metadata
import json

# Import shutil to copy files
import shutil

# Import our asset type enum
from component_importer.models import AssetType

# Import function that creates the local KiCad library structure
from component_importer.project_library import create_project_library_structure

# Import function that scans ZIP contents
from component_importer.zip_scanner import scan_cad_zip

# Import function that fixes 3D model paths inside imported footprints
from component_importer.footprint_3d_fixer import fix_3d_paths_for_imported_footprints

# Import function that updates KiCad project library tables
from component_importer.library_table_updater import update_kicad_library_tables

# Import function that links symbols to imported footprint options
from component_importer.symbol_footprint_linker import link_symbol_library_to_footprints

# Import symbol library merge helper
from component_importer.symbol_library_manager import merge_symbol_library_content_into_target

# Import backup helpers
from component_importer.backup_helper import get_backup_timestamp, backup_file_if_exists


# Make a string safe to use as a filename across supported platforms
def safe_filename(name: str) -> str:
    # Use the strict Windows set so names also travel cleanly between platforms
    invalid_chars = '<>:"/\\|?*'

    # Replace each invalid character with an underscore
    for char in invalid_chars:
        name = name.replace(char, "_")

    # Remove leading and trailing whitespace
    return name.strip()


# Build a safe target path that avoids overwriting existing files unless overwrite is enabled
def build_target_path(
    folder: Path,
    filename: str,
    overwrite_existing: bool,
) -> Path:
    # Build initial target path
    target = folder / filename

    # If overwriting is allowed, return the direct target
    if overwrite_existing:
        return target

    # If file does not exist, return the direct target
    if not target.exists():
        return target

    # Extract file stem and extension
    stem = target.stem
    suffix = target.suffix

    # Start numbering duplicate files
    counter = 2

    # Loop until an unused filename is found
    while True:
        # Build numbered target filename
        numbered_target = folder / f"{stem}_{counter}{suffix}"

        # Return numbered path if unused
        if not numbered_target.exists():
            return numbered_target

        # Increment counter
        counter += 1


# Copy one file from a ZIP into a target path with optional backup
def extract_zip_file_to_target(
    zf: ZipFile,
    source_inside_zip: str,
    target: Path,
    project_root: Path,
    backup_timestamp: str,
    create_backup: bool,
) -> str | None:
    # Prepare backup result
    backup_path = None

    # Backup existing file before overwriting
    if create_backup:
        backup_path = backup_file_if_exists(
            project_root=project_root,
            target_file=target,
            backup_timestamp=backup_timestamp,
        )

    # Create target parent folder if needed
    target.parent.mkdir(parents=True, exist_ok=True)

    # Extract selected file from ZIP and copy it to target
    with zf.open(source_inside_zip) as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)

    # Return backup path if one was created
    return backup_path


# Decide if the default footprint should also be included in ki_fp_filters
def should_include_default_footprint_in_filters(footprint_files: list[str]) -> bool:
    # Always include the default footprint in ki_fp_filters.
    # KiCad uses this property to filter the footprint chooser, so omitting the
    # default can make the assigned footprint hard to find after import.
    return True


# Import a CAD ZIP file into a selected KiCad project-local library
def import_cad_zip(
    zip_path: str | Path,
    project_root: str | Path,
    library_name: str,
    part_name: str,
    symbol_library_name: str | None = None,
    footprint_library_name: str | None = None,
    fix_3d_paths: bool = True,
    update_library_tables: bool = True,
    link_symbol_footprints: bool = True,
    default_footprint_name: str | None = None,
    footprint_filter_mode: str = "exact",
    overwrite_existing: bool = True,
    create_backups: bool = True,
    merge_symbols_into_selected_library: bool = True,
    replace_existing_symbols: bool = True,
) -> dict:
    # Convert input paths to Path objects
    zip_path = Path(zip_path)
    project_root = Path(project_root)

    # Clean part name so it can safely be used in filenames
    part_name = safe_filename(part_name)

    # Use same library name for symbols and footprints if specific names are not provided
    if symbol_library_name is None:
        symbol_library_name = library_name

    if footprint_library_name is None:
        footprint_library_name = library_name

    # Stop early if ZIP file does not exist
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path.resolve()}")

    # Create backup timestamp for this import operation
    backup_timestamp = get_backup_timestamp()

    # Create the selected KiCad library folders and files
    paths = create_project_library_structure(
        project_root=project_root,
        library_name=library_name,
        symbol_library_name=symbol_library_name,
        footprint_library_name=footprint_library_name,
    )

    # Scan ZIP file and detect supported CAD assets
    assets = scan_cad_zip(zip_path)

    # Prepare result dictionary
    imported = {
        "selected_symbol_library": str(paths["symbol_lib_path"]),
        "selected_footprint_library": str(paths["footprint_lib_dir"]),
        "symbol_libraries": [],
        "source_symbol_libraries": [],
        "merged_symbols": [],
        "footprints": [],
        "models_3d": [],
        "datasheets": [],
        "source_zip": None,
        "metadata": None,
        "3d_path_fix": None,
        "library_table_update": None,
        "symbol_footprint_link": [],
        "backups": [],
    }

    # Build target path for original source ZIP copy
    source_zip_target = build_target_path(
        folder=paths["source_zips_dir"],
        filename=f"{part_name}_{zip_path.name}",
        overwrite_existing=overwrite_existing,
    )

    # Backup old source ZIP copy if it exists
    if create_backups:
        backup_path = backup_file_if_exists(
            project_root=project_root,
            target_file=source_zip_target,
            backup_timestamp=backup_timestamp,
        )

        # Store backup path if created
        if backup_path:
            imported["backups"].append(backup_path)

    # Copy source ZIP for traceability
    shutil.copy2(zip_path, source_zip_target)

    # Store source ZIP path
    imported["source_zip"] = str(source_zip_target)

    # Store whether selected symbol library was used
    selected_symbol_library_used = False

    # Open ZIP file for extracting selected files
    with ZipFile(zip_path, "r") as zf:
        # Loop through all detected CAD assets
        for asset in assets:
            # Convert internal ZIP path to POSIX string
            source_inside_zip = asset.original_path.as_posix()

            # Symbol libraries are merged into the selected shared symbol library
            if asset.asset_type == AssetType.SYMBOL_LIB:
                # Store source symbol library path inside ZIP
                imported["source_symbol_libraries"].append(source_inside_zip)

                # Read source symbol library content from ZIP
                with zf.open(source_inside_zip) as src:
                    source_symbol_content = src.read().decode("utf-8", errors="ignore")

                # Backup selected symbol library before merge
                if create_backups:
                    backup_path = backup_file_if_exists(
                        project_root=project_root,
                        target_file=paths["symbol_lib_path"],
                        backup_timestamp=backup_timestamp,
                    )

                    # Store backup path if created
                    if backup_path:
                        imported["backups"].append(backup_path)

                # Merge source symbols into selected symbol library
                if merge_symbols_into_selected_library:
                    merge_result = merge_symbol_library_content_into_target(
                        target_symbol_library_path=paths["symbol_lib_path"],
                        source_symbol_library_content=source_symbol_content,
                        replace_existing_symbols=replace_existing_symbols,
                    )

                    # Store merge result
                    imported["merged_symbols"].append(merge_result)

                    # Mark selected symbol library as used
                    selected_symbol_library_used = True

                # Skip normal extraction because symbol was merged
                continue

            # Footprints are copied into the selected .pretty footprint library
            elif asset.asset_type == AssetType.FOOTPRINT:
                # Keep original footprint filename because this is the actual KiCad footprint name
                target = build_target_path(
                    folder=paths["footprint_lib_dir"],
                    filename=asset.filename,
                    overwrite_existing=overwrite_existing,
                )

            # 3D models are copied into the project 3dmodels folder
            elif asset.asset_type in [
                AssetType.STEP_MODEL,
                AssetType.WRL_MODEL,
                AssetType.STL_MODEL,
            ]:
                # Keep original 3D model filename
                target = build_target_path(
                    folder=paths["models_dir"],
                    filename=asset.filename,
                    overwrite_existing=overwrite_existing,
                )

            # Datasheets are copied into metadata
            elif asset.asset_type == AssetType.DATASHEET:
                # Keep original datasheet filename
                target = build_target_path(
                    folder=paths["metadata_dir"],
                    filename=asset.filename,
                    overwrite_existing=overwrite_existing,
                )

            # Ignore anything else
            else:
                continue

            # Extract selected file and backup old target first if needed
            backup_path = extract_zip_file_to_target(
                zf=zf,
                source_inside_zip=source_inside_zip,
                target=target,
                project_root=project_root,
                backup_timestamp=backup_timestamp,
                create_backup=create_backups,
            )

            # Store backup path if one was created
            if backup_path:
                imported["backups"].append(backup_path)

            # Store imported footprint path
            if asset.asset_type == AssetType.FOOTPRINT:
                imported["footprints"].append(str(target))

            # Store imported 3D model path
            elif asset.asset_type in [
                AssetType.STEP_MODEL,
                AssetType.WRL_MODEL,
                AssetType.STL_MODEL,
            ]:
                imported["models_3d"].append(str(target))

            # Store imported datasheet path
            elif asset.asset_type == AssetType.DATASHEET:
                imported["datasheets"].append(str(target))

    # If symbols were merged, the selected symbol library is the imported symbol library
    if selected_symbol_library_used:
        imported["symbol_libraries"].append(str(paths["symbol_lib_path"]))

    # Link newly merged symbols to imported footprints if enabled
    if link_symbol_footprints and imported["symbol_libraries"] and imported["footprints"]:
        # Decide if default footprint should be included in ki_fp_filters
        include_default_in_filters = should_include_default_footprint_in_filters(
            footprint_files=imported["footprints"],
        )

        # Loop through merge results
        for merge_result in imported["merged_symbols"]:
            # Loop through each newly merged symbol name
            for merged_symbol_name in merge_result.get("merged_symbol_names", []):
                # Backup selected symbol library before editing links
                if create_backups:
                    backup_path = backup_file_if_exists(
                        project_root=project_root,
                        target_file=paths["symbol_lib_path"],
                        backup_timestamp=backup_timestamp,
                    )

                    # Store backup path if one was created
                    if backup_path:
                        imported["backups"].append(backup_path)

                # Link selected symbol to imported footprint options
                link_result = link_symbol_library_to_footprints(
                    symbol_library_path=paths["symbol_lib_path"],
                    footprint_files=imported["footprints"],
                    library_name=footprint_library_name,
                    default_footprint_name=default_footprint_name,
                    symbol_name=merged_symbol_name,
                    filter_mode=footprint_filter_mode,
                    include_default_in_filters=include_default_in_filters,
                )

                # Store link result
                imported["symbol_footprint_link"].append(link_result)

    # Fix 3D model paths in imported footprints if enabled
    if fix_3d_paths:
        # Backup footprints before modifying 3D paths
        if create_backups:
            for footprint_file in imported["footprints"]:
                backup_path = backup_file_if_exists(
                    project_root=project_root,
                    target_file=footprint_file,
                    backup_timestamp=backup_timestamp,
                )

                # Store backup path if one was created
                if backup_path:
                    imported["backups"].append(backup_path)

        # Fix 3D paths
        imported["3d_path_fix"] = fix_3d_paths_for_imported_footprints(
            footprint_files=imported["footprints"],
            model_files=imported["models_3d"],
        )

    # Backup library tables before updating them
    if update_library_tables and create_backups:
        for table_name in ["fp-lib-table", "sym-lib-table"]:
            # Build table path
            table_path = project_root / table_name

            # Backup table if it already exists
            backup_path = backup_file_if_exists(
                project_root=project_root,
                target_file=table_path,
                backup_timestamp=backup_timestamp,
            )

            # Store backup path if one was created
            if backup_path:
                imported["backups"].append(backup_path)

    # Update KiCad project library tables if enabled
    if update_library_tables:
        imported["library_table_update"] = update_kicad_library_tables(
            project_root=project_root,
            library_name=footprint_library_name,
            footprint_library_path=paths["footprint_lib_dir"],
            symbol_library_paths=imported["symbol_libraries"],
        )

    # Create metadata about this import
    metadata = {
        "part_name": part_name,
        "library_name": library_name,
        "symbol_library_name": symbol_library_name,
        "footprint_library_name": footprint_library_name,
        "project_root": str(project_root),
        "source_zip": str(zip_path),
        "imported_at": datetime.now().isoformat(timespec="seconds"),
        "imported_assets": imported,
    }

    # Decide where to save metadata JSON
    metadata_path = paths["metadata_dir"] / f"{part_name}_import_metadata.json"

    # Backup old metadata if it exists
    if create_backups:
        backup_path = backup_file_if_exists(
            project_root=project_root,
            target_file=metadata_path,
            backup_timestamp=backup_timestamp,
        )

        # Store backup path if one was created
        if backup_path:
            imported["backups"].append(backup_path)

    # Write metadata JSON
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # Store metadata path in result
    imported["metadata"] = str(metadata_path)

    # Return import summary
    return imported
