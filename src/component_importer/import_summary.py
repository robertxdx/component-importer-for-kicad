# Import Path to handle file paths cleanly
from pathlib import Path


# Convert a list of file paths into a clean printable list
def format_file_list(files: list[str]) -> list[str]:
    # If the list is empty, return a clear placeholder
    if not files:
        return ["None"]

    # Convert every file path to a string
    return [str(Path(file)) for file in files]


# Print one section of the import summary
def print_summary_section(title: str, files: list[str]) -> None:
    # Print section title
    print(title)

    # Print every file under this section
    for file in format_file_list(files):
        print(f"  {file}")

    # Add an empty line for readability
    print()


# Print selected target libraries
def print_selected_libraries(result: dict) -> None:
    # Print selected libraries section
    print("Selected Libraries:")

    # Print selected symbol library
    print(f"  Symbol library: {result.get('selected_symbol_library', 'None')}")

    # Print selected footprint library
    print(f"  Footprint library: {result.get('selected_footprint_library', 'None')}")

    # Add empty line
    print()


# Print symbol merge results
def print_merged_symbols_summary(merge_results: list[dict]) -> None:
    # Print section title
    print("Merged Symbols:")

    # If nothing was merged, print None
    if not merge_results:
        print("  None")
        print()
        return

    # Loop through merge results
    for merge_result in merge_results:
        # Print target symbol library
        print(f"  Target library: {merge_result.get('target_symbol_library', 'Unknown')}")

        # Print whether file changed
        print(f"  Updated: {merge_result.get('updated', False)}")

        # Print message
        print(f"  Message: {merge_result.get('message', '')}")

        # Print merged symbol names
        print("  Merged symbol names:")

        # Get merged names
        merged_names = merge_result.get("merged_symbol_names", [])

        # Print merged names or None
        if merged_names:
            for symbol_name in merged_names:
                print(f"    {symbol_name}")
        else:
            print("    None")

        # Print replaced existing symbols
        print("  Replaced existing symbols:")

        # Get replaced symbols
        replaced_symbols = merge_result.get("replaced_existing_symbols", [])

        # Print replaced symbols or None
        if replaced_symbols:
            for symbol_name in replaced_symbols:
                print(f"    {symbol_name}")
        else:
            print("    None")

        # Add empty line
        print()


# Print symbol-to-footprint linking details
def print_symbol_footprint_link_summary(link_results: list[dict]) -> None:
    # Print section title
    print("Symbol Footprint Links:")

    # If no link results exist, print None
    if not link_results:
        print("  None")
        print()
        return

    # Loop through link results
    for link_result in link_results:
        # Print symbol library path
        print(f"  Symbol library: {link_result.get('symbol_library', 'Unknown')}")

        # Print updated status
        print(f"  Updated: {link_result.get('updated', False)}")

        # Print symbol name
        print(f"  Symbol name: {link_result.get('symbol_name', 'Unknown')}")

        # Print default footprint
        print(f"  Default footprint: {link_result.get('default_footprint', 'None')}")

        # Print filter mode
        print(f"  Filter mode: {link_result.get('filter_mode', 'Unknown')}")

        # Print whether the default footprint is also included in the filter list
        print(
            "  Include default in filters: "
            f"{link_result.get('include_default_in_filters', False)}"
        )

        # Print footprint filters
        print("  Footprint filters:")

        # Get footprint filters
        footprint_filters = link_result.get("footprint_filters", [])

        # Print footprint filters or None
        if footprint_filters:
            for footprint_filter in footprint_filters:
                print(f"    {footprint_filter}")
        else:
            print("    None")

        # Print ki_fp_filters raw property value if available
        ki_fp_filters_value = link_result.get("ki_fp_filters_value")

        # Show KiCad property value used for footprint filters
        if ki_fp_filters_value is not None:
            print("  ki_fp_filters value:")
            print(f"    {ki_fp_filters_value}")

        # Add empty line between link results
        print()


# Print model matching details from the 3D path fixer
def print_model_matches(path_fix: dict) -> None:
    # Get model match list from path fix result
    model_matches = path_fix.get("model_matches", [])

    # If there are no model matches, print nothing extra
    if not model_matches:
        return

    # Print section title
    print("  Model matches:")

    # Print every footprint-to-model match
    for match in model_matches:
        # Get footprint filename
        footprint = Path(match.get("footprint", "Unknown")).name

        # Get model filename
        model = Path(match.get("model", "Unknown")).name

        # Get score from 0 to 100
        score = match.get("score", 0)

        # Print one match line
        print(f"    {footprint} -> {model} | score: {score}/100")


# Print KiCad library table update details
def print_library_table_update(table_update: dict | None) -> None:
    # Print section title
    print("KiCad Library Table Update:")

    # If no table update data exists, print None
    if not table_update:
        print("  None")
        print()
        return

    # Get footprint table update status
    footprint_updated = table_update.get("footprint_table_updated", False)

    # Show whether fp-lib-table changed
    if footprint_updated:
        print("  fp-lib-table: updated")
    else:
        print("  fp-lib-table: already contained this library or was not changed")

    # Get updated symbol libraries
    updated_symbols = table_update.get("symbol_tables_updated", [])

    # Get skipped symbol libraries
    skipped_symbols = table_update.get("symbol_tables_skipped", [])

    # Print updated symbol libraries
    print("  sym-lib-table updated libraries:")

    # Print updated symbol libraries or None
    if updated_symbols:
        for symbol_library in updated_symbols:
            print(f"    {symbol_library}")
    else:
        print("    None")

    # Print skipped symbol libraries
    print("  sym-lib-table skipped libraries:")

    # Print skipped symbol libraries or None
    if skipped_symbols:
        for symbol_library in skipped_symbols:
            print(f"    {symbol_library}")
    else:
        print("    None")

    # Add empty line for readability
    print()


# Print created backup files
def print_backup_summary(backups: list[str]) -> None:
    # Print section title
    print("Backups:")

    # If no backups were created, print None
    if not backups:
        print("  None")
        print()
        return

    # Print every backup path
    for backup in backups:
        print(f"  {backup}")

    # Add empty line
    print()


# Print a clean summary after importing a CAD ZIP
def print_import_summary(result: dict, part_name: str | None = None) -> None:
    # Print imported part name if provided
    if part_name:
        print(f"Imported part: {part_name}")
        print()

    # Print selected target libraries
    print_selected_libraries(result)

    # Print merged symbol results
    print_merged_symbols_summary(
        merge_results=result.get("merged_symbols", []),
    )

    # Print imported symbol libraries
    print_summary_section(
        title="Symbol Libraries Registered:",
        files=result.get("symbol_libraries", []),
    )

    # Print source symbol libraries from ZIP
    print_summary_section(
        title="Source Symbol Libraries From ZIP:",
        files=result.get("source_symbol_libraries", []),
    )

    # Print imported footprints
    print_summary_section(
        title="Footprints:",
        files=result.get("footprints", []),
    )

    # Print imported 3D models
    print_summary_section(
        title="3D Models:",
        files=result.get("models_3d", []),
    )

    # Print imported datasheets
    print_summary_section(
        title="Datasheets:",
        files=result.get("datasheets", []),
    )

    # Print source ZIP path
    print("Source ZIP:")
    print(f"  {result.get('source_zip', 'None')}")
    print()

    # Print metadata JSON path
    print("Metadata:")
    print(f"  {result.get('metadata', 'None')}")
    print()

    # Print symbol-to-footprint link summary
    print_symbol_footprint_link_summary(
        link_results=result.get("symbol_footprint_link", []),
    )

    # Get 3D path fix result
    path_fix = result.get("3d_path_fix")

    # Print 3D path fix summary
    print("3D Path Fix:")

    # If no 3D fix data exists, print None
    if not path_fix:
        print("  None")
        print()
    else:
        # Count updated footprints
        updated_count = len(path_fix.get("updated_footprints", []))

        # Count skipped footprints
        skipped_count = len(path_fix.get("skipped_footprints", []))

        # Print counts
        print(f"  Updated footprints: {updated_count}")
        print(f"  Skipped footprints: {skipped_count}")

        # Print available 3D models used by the fixer
        print("  Available models:")

        # Print each available model
        available_models = path_fix.get("available_models", [])

        # Print models or None
        if available_models:
            for model in available_models:
                print(f"    {model}")
        else:
            print("    None")

        # Print model matching details
        print_model_matches(path_fix)

        # Add empty line after 3D path section
        print()

    # Print backup summary
    print_backup_summary(result.get("backups", []))

    # Print KiCad library table update summary
    print_library_table_update(result.get("library_table_update"))