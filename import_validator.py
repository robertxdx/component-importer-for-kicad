# Import Path for filesystem operations
from pathlib import Path

# Import fnmatch to check wildcard footprint filters
import fnmatch

# Import re for extracting KiCad properties from symbol files
import re

# Import helper used to make library names match KiCad table nicknames
from library_table_updater import make_library_nickname

# Import helper used to read 3D model paths from footprint files
from footprint_3d_fixer import find_3d_models_in_footprint

# Import helper used to find symbol blocks inside .kicad_sym files
from symbol_footprint_linker import find_symbol_blocks


# Add one validation check to the result dictionary
def add_check(
    validation: dict,
    category: str,
    check: str,
    passed: bool,
    message: str,
    severity: str = "error",
) -> None:
    # Create category list if it does not exist
    if category not in validation["checks"]:
        validation["checks"][category] = []

    # Store this check
    validation["checks"][category].append(
        {
            "check": check,
            "passed": passed,
            "message": message,
            "severity": severity,
        }
    )

    # A failed error check means full validation failed
    if not passed and severity == "error":
        validation["passed"] = False

    # A failed warning check does not fail full validation
    if not passed and severity == "warning":
        validation["warnings"].append(message)


# Read a text file safely
def read_text_file(path: str | Path) -> str:
    # Convert input to Path object
    path = Path(path)

    # Return empty string if file does not exist
    if not path.exists():
        return ""

    # Read file content
    return path.read_text(encoding="utf-8", errors="ignore")


# Convert a path to a KiCad project-relative URI
def make_kiprojmod_uri(project_root: str | Path, target_path: str | Path) -> str:
    # Convert inputs to Path objects
    project_root = Path(project_root)
    target_path = Path(target_path)

    # Convert target path to relative path
    relative_path = target_path.relative_to(project_root).as_posix()

    # Return KiCad project-relative URI
    return f"${{KIPRJMOD}}/{relative_path}"


# Check if a library nickname exists in a KiCad library table
def table_contains_library_name(table_content: str, library_name: str) -> bool:
    # Clean nickname
    library_name = make_library_nickname(library_name)

    # Check quoted library name format
    return f'(name "{library_name}")' in table_content


# Check if a library URI exists in a KiCad library table
def table_contains_uri(table_content: str, uri: str) -> bool:
    # Check quoted URI
    return f'(uri "{uri}")' in table_content


# Extract KiCad symbol properties from one symbol block
def extract_symbol_properties(symbol_block: str) -> dict[str, str]:
    # Find all simple property declarations in this symbol block
    property_matches = re.findall(
        r'\(property\s+"([^"]+)"\s+"([^"]*)"',
        symbol_block,
    )

    # Return dictionary where later duplicate properties overwrite older ones
    return {name: value for name, value in property_matches}


# Check if old fp_filters blocks still exist
def has_old_fp_filters_block(symbol_block: str) -> bool:
    # Return True if old fp_filters block exists
    return "(fp_filters" in symbol_block


# Check if a footprint reference has library prefix
def is_qualified_footprint_reference(footprint_reference: str) -> bool:
    # A qualified KiCad footprint reference looks like LibraryName:FootprintName
    return ":" in footprint_reference and not footprint_reference.startswith(":")


# Split ki_fp_filters string into individual filters
def split_ki_fp_filters(value: str) -> list[str]:
    # KiCad stores ki_fp_filters as a space-separated string
    return [item.strip() for item in value.split() if item.strip()]


# Build full footprint references from imported footprint files
def build_available_footprint_references(
    library_name: str,
    footprint_files: list[str | Path],
) -> list[str]:
    # Clean library nickname
    library_name = make_library_nickname(library_name)

    # Build LibraryName:FootprintName for every footprint file
    return [
        f"{library_name}:{Path(footprint_file).stem}"
        for footprint_file in footprint_files
    ]


# Check if a footprint filter matches at least one available footprint
def footprint_filter_matches_available_footprint(
    footprint_filter: str,
    available_footprints: list[str],
) -> bool:
    # Check exact or wildcard match against available footprint references
    for footprint_reference in available_footprints:
        if fnmatch.fnmatchcase(footprint_reference, footprint_filter):
            return True

    # Return False if nothing matched
    return False


# Resolve a KiCad model path to a real filesystem path
def resolve_kicad_model_path(
    project_root: str | Path,
    footprint_path: str | Path,
    model_path: str,
) -> Path:
    # Convert inputs to Path objects
    project_root = Path(project_root)
    footprint_path = Path(footprint_path)

    # Handle KiCad project variable
    if model_path.startswith("${KIPRJMOD}/"):
        # Remove variable prefix
        relative_path = model_path.replace("${KIPRJMOD}/", "", 1)

        # Resolve against project root
        return project_root / relative_path

    # Handle absolute Windows or Linux paths
    possible_path = Path(model_path)

    # If absolute, return it directly
    if possible_path.is_absolute():
        return possible_path

    # Fallback: resolve relative to the footprint folder
    return footprint_path.parent / model_path


# Get symbol names that were modified by this import result
def get_expected_symbol_names_from_result(result: dict) -> list[str]:
    # Store symbol names
    symbol_names = []

    # Get symbol-to-footprint link results
    link_results = result.get("symbol_footprint_link", [])

    # Extract symbol names from link results
    for link_result in link_results:
        symbol_name = link_result.get("symbol_name")

        # Store symbol name if present
        if symbol_name:
            symbol_names.append(symbol_name)

    # Remove duplicates while preserving order
    symbol_names = list(dict.fromkeys(symbol_names))

    # Return symbol names
    return symbol_names


# Get symbol blocks that should be validated
def get_symbol_blocks_to_validate(
    symbol_content: str,
    expected_symbol_names: list[str],
) -> list[dict]:
    # Find all symbol blocks in the library
    symbol_blocks = find_symbol_blocks(symbol_content)

    # If no specific expected symbols exist, return all symbol blocks
    if not expected_symbol_names:
        return symbol_blocks

    # Store matching symbol blocks
    matching_blocks = []

    # Loop through all symbols
    for symbol_block in symbol_blocks:
        # Store block if symbol name is expected
        if symbol_block.get("name") in expected_symbol_names:
            matching_blocks.append(symbol_block)

    # Return only expected symbol blocks
    return matching_blocks


# Validate one symbol block
def validate_one_symbol_block(
    validation: dict,
    symbol_library: Path,
    symbol_block: dict,
    available_footprints: list[str],
    multiple_footprints_available: bool,
) -> None:
    # Get symbol name
    symbol_name = symbol_block.get("name", "Unknown")

    # Get symbol block text
    symbol_text = symbol_block.get("text", "")

    # Extract symbol properties
    properties = extract_symbol_properties(symbol_text)

    # Get Footprint property
    footprint_property = properties.get("Footprint", "")

    # Check Footprint property exists
    add_check(
        validation=validation,
        category="symbols",
        check="footprint_property_exists",
        passed=bool(footprint_property),
        message=f"{symbol_library.name} / {symbol_name}: Footprint = {footprint_property or 'missing'}",
    )

    # Check Footprint property has library prefix
    add_check(
        validation=validation,
        category="symbols",
        check="footprint_property_qualified",
        passed=is_qualified_footprint_reference(footprint_property),
        message=f"{symbol_library.name} / {symbol_name}: Footprint property is {footprint_property}",
    )

    # Check Footprint property points to imported footprint
    add_check(
        validation=validation,
        category="symbols",
        check="default_footprint_exists",
        passed=footprint_property in available_footprints,
        message=f"{symbol_library.name} / {symbol_name}: {footprint_property} should exist in imported footprint library.",
    )

    # Get ki_fp_filters property
    ki_fp_filters = properties.get("ki_fp_filters", "")

    # Split filters
    footprint_filters = split_ki_fp_filters(ki_fp_filters)

    # Footprint filters are only required when there is more than one compatible footprint
    if multiple_footprints_available:
        # Check ki_fp_filters exists when multiple footprints exist
        add_check(
            validation=validation,
            category="symbols",
            check="ki_fp_filters_exists_for_multiple_footprints",
            passed=bool(footprint_filters),
            message=f"{symbol_library.name} / {symbol_name}: {len(footprint_filters)} footprint filter(s) found.",
            severity="warning",
        )

    # If only one footprint exists, missing filters are fine
    else:
        add_check(
            validation=validation,
            category="symbols",
            check="ki_fp_filters_not_required_for_single_footprint",
            passed=True,
            message=f"{symbol_library.name} / {symbol_name}: only one footprint exists, so ki_fp_filters is not required.",
            severity="warning",
        )

    # Check every filter if filters exist
    for footprint_filter in footprint_filters:
        # Check every filter is qualified
        add_check(
            validation=validation,
            category="symbols",
            check="ki_fp_filter_qualified",
            passed=is_qualified_footprint_reference(footprint_filter),
            message=f"{symbol_library.name} / {symbol_name}: Filter = {footprint_filter}",
        )

        # Check every filter matches at least one available footprint
        add_check(
            validation=validation,
            category="symbols",
            check="ki_fp_filter_matches",
            passed=footprint_filter_matches_available_footprint(
                footprint_filter=footprint_filter,
                available_footprints=available_footprints,
            ),
            message=f"{symbol_library.name} / {symbol_name}: Filter {footprint_filter} should match an imported footprint.",
        )

    # If filters exist, the assigned default footprint should be included too
    if footprint_filters:
        add_check(
            validation=validation,
            category="symbols",
            check="default_footprint_in_filters",
            passed=footprint_property in footprint_filters,
            message=f"{symbol_library.name} / {symbol_name}: default footprint {footprint_property} should be included in ki_fp_filters.",
        )

    # Check old fp_filters blocks are gone
    add_check(
        validation=validation,
        category="symbols",
        check="no_old_fp_filters_block",
        passed=not has_old_fp_filters_block(symbol_text),
        message=f"{symbol_library.name} / {symbol_name}: old fp_filters block should not exist.",
    )


# Validate symbol library files
def validate_symbol_libraries(
    validation: dict,
    project_root: str | Path,
    result: dict,
    library_name: str,
) -> None:
    # Convert project root to Path object
    project_root = Path(project_root)

    # Get imported or selected symbol libraries
    symbol_libraries = result.get("symbol_libraries", [])

    # Get imported footprints for this import
    footprint_files = result.get("footprints", [])

    # Determine if multiple footprints exist
    multiple_footprints_available = len(footprint_files) > 1

    # Build available footprint references
    available_footprints = build_available_footprint_references(
        library_name=library_name,
        footprint_files=footprint_files,
    )

    # Get expected symbol names from this import
    expected_symbol_names = get_expected_symbol_names_from_result(result)

    # Check if at least one symbol library exists
    add_check(
        validation=validation,
        category="symbols",
        check="symbol_libraries_present",
        passed=bool(symbol_libraries),
        message=f"Found {len(symbol_libraries)} imported or selected symbol library file(s).",
    )

    # Loop through symbol libraries
    for symbol_library in symbol_libraries:
        # Convert to Path object
        symbol_library = Path(symbol_library)

        # Check file exists
        add_check(
            validation=validation,
            category="symbols",
            check="symbol_library_exists",
            passed=symbol_library.exists(),
            message=str(symbol_library),
        )

        # Skip deeper checks if file does not exist
        if not symbol_library.exists():
            continue

        # Read symbol content
        symbol_content = read_text_file(symbol_library)

        # Find symbol blocks to validate
        symbol_blocks_to_validate = get_symbol_blocks_to_validate(
            symbol_content=symbol_content,
            expected_symbol_names=expected_symbol_names,
        )

        # Check that expected symbols were found
        if expected_symbol_names:
            found_names = [
                symbol_block.get("name")
                for symbol_block in symbol_blocks_to_validate
            ]

            for expected_symbol_name in expected_symbol_names:
                add_check(
                    validation=validation,
                    category="symbols",
                    check="expected_symbol_found",
                    passed=expected_symbol_name in found_names,
                    message=f"{symbol_library.name}: expected symbol {expected_symbol_name}",
                )

        # Validate every relevant symbol block
        for symbol_block in symbol_blocks_to_validate:
            validate_one_symbol_block(
                validation=validation,
                symbol_library=symbol_library,
                symbol_block=symbol_block,
                available_footprints=available_footprints,
                multiple_footprints_available=multiple_footprints_available,
            )


# Validate footprint files and 3D model links
def validate_footprints_and_3d_models(
    validation: dict,
    project_root: str | Path,
    result: dict,
) -> None:
    # Convert project root to Path object
    project_root = Path(project_root)

    # Get imported footprints
    footprint_files = result.get("footprints", [])

    # Get imported 3D models
    model_files = result.get("models_3d", [])

    # Check footprints exist
    add_check(
        validation=validation,
        category="footprints",
        check="footprints_present",
        passed=bool(footprint_files),
        message=f"Found {len(footprint_files)} imported footprint file(s).",
    )

    # Check every footprint file exists
    for footprint_file in footprint_files:
        # Convert to Path object
        footprint_file = Path(footprint_file)

        # Check footprint exists
        add_check(
            validation=validation,
            category="footprints",
            check="footprint_file_exists",
            passed=footprint_file.exists(),
            message=str(footprint_file),
        )

        # Skip 3D checks if footprint does not exist
        if not footprint_file.exists():
            continue

        # Find 3D model paths referenced inside footprint
        model_paths = find_3d_models_in_footprint(footprint_file)

        # Check footprint has at least one model path if models were imported
        add_check(
            validation=validation,
            category="3d_models",
            check="footprint_has_model_path",
            passed=bool(model_paths) if model_files else True,
            message=f"{footprint_file.name}: {len(model_paths)} model path(s) found.",
            severity="warning" if not model_files else "error",
        )

        # Validate every model path
        for model_path in model_paths:
            # Resolve KiCad model path to filesystem path
            resolved_path = resolve_kicad_model_path(
                project_root=project_root,
                footprint_path=footprint_file,
                model_path=model_path,
            )

            # Check resolved path exists
            add_check(
                validation=validation,
                category="3d_models",
                check="model_path_exists",
                passed=resolved_path.exists(),
                message=f"{footprint_file.name}: {model_path} -> {resolved_path}",
            )

            # Check model path uses KIPRJMOD
            add_check(
                validation=validation,
                category="3d_models",
                check="model_path_uses_kiprojmod",
                passed=model_path.startswith("${KIPRJMOD}/"),
                message=f"{footprint_file.name}: {model_path}",
                severity="warning",
            )

    # Check imported model files exist
    for model_file in model_files:
        # Convert to Path object
        model_file = Path(model_file)

        # Check model exists
        add_check(
            validation=validation,
            category="3d_models",
            check="imported_model_file_exists",
            passed=model_file.exists(),
            message=str(model_file),
        )


# Get selected footprint library path from result or fallback
def get_selected_footprint_library_path(
    project_root: str | Path,
    result: dict,
    library_name: str,
) -> Path:
    # Convert project root to Path object
    project_root = Path(project_root)

    # Use selected footprint library if available
    selected_footprint_library = result.get("selected_footprint_library")

    # Return selected footprint library if present
    if selected_footprint_library:
        return Path(selected_footprint_library)

    # Fallback to old expected location
    return project_root / "libraries" / f"{make_library_nickname(library_name)}.pretty"


# Validate KiCad project library tables
def validate_library_tables(
    validation: dict,
    project_root: str | Path,
    result: dict,
    library_name: str,
) -> None:
    # Convert project root to Path object
    project_root = Path(project_root)

    # Define table paths
    sym_table_path = project_root / "sym-lib-table"
    fp_table_path = project_root / "fp-lib-table"

    # Check sym-lib-table exists
    add_check(
        validation=validation,
        category="library_tables",
        check="sym_lib_table_exists",
        passed=sym_table_path.exists(),
        message=str(sym_table_path),
    )

    # Check fp-lib-table exists
    add_check(
        validation=validation,
        category="library_tables",
        check="fp_lib_table_exists",
        passed=fp_table_path.exists(),
        message=str(fp_table_path),
    )

    # Read table content
    sym_table_content = read_text_file(sym_table_path)
    fp_table_content = read_text_file(fp_table_path)

    # Check footprint library nickname is registered
    add_check(
        validation=validation,
        category="library_tables",
        check="footprint_library_registered",
        passed=table_contains_library_name(fp_table_content, library_name),
        message=f"Footprint library nickname: {make_library_nickname(library_name)}",
    )

    # Get selected footprint library path
    footprint_library_path = get_selected_footprint_library_path(
        project_root=project_root,
        result=result,
        library_name=library_name,
    )

    # Build expected footprint library URI
    footprint_library_uri = make_kiprojmod_uri(project_root, footprint_library_path)

    # Check footprint library URI is registered
    add_check(
        validation=validation,
        category="library_tables",
        check="footprint_library_uri_registered",
        passed=table_contains_uri(fp_table_content, footprint_library_uri),
        message=footprint_library_uri,
    )

    # Check each imported or selected symbol library is registered
    for symbol_library in result.get("symbol_libraries", []):
        # Convert to Path object
        symbol_library = Path(symbol_library)

        # Expected symbol library nickname
        symbol_nickname = make_library_nickname(symbol_library.stem)

        # Expected URI
        symbol_uri = make_kiprojmod_uri(project_root, symbol_library)

        # Check symbol nickname registered
        add_check(
            validation=validation,
            category="library_tables",
            check="symbol_library_registered",
            passed=table_contains_library_name(sym_table_content, symbol_nickname),
            message=f"Symbol library nickname: {symbol_nickname}",
        )

        # Check symbol URI registered
        add_check(
            validation=validation,
            category="library_tables",
            check="symbol_library_uri_registered",
            passed=table_contains_uri(sym_table_content, symbol_uri),
            message=symbol_uri,
        )


# Validate one imported CAD ZIP result
def validate_imported_part(
    project_root: str | Path,
    result: dict,
    library_name: str,
) -> dict:
    # Prepare validation dictionary
    validation = {
        "passed": True,
        "warnings": [],
        "checks": {},
    }

    # Validate symbol libraries and symbol footprint properties
    validate_symbol_libraries(
        validation=validation,
        project_root=project_root,
        result=result,
        library_name=library_name,
    )

    # Validate footprints and 3D model paths
    validate_footprints_and_3d_models(
        validation=validation,
        project_root=project_root,
        result=result,
    )

    # Validate KiCad project library tables
    validate_library_tables(
        validation=validation,
        project_root=project_root,
        result=result,
        library_name=library_name,
    )

    # Return validation result
    return validation


# Print validation summary
def print_validation_summary(validation: dict, show_passed_checks: bool = False) -> None:
    # Print global result
    print(f"Validation passed: {validation.get('passed', False)}")
    print()

    # Print warning count
    warnings = validation.get("warnings", [])
    print(f"Warnings: {len(warnings)}")

    # Print warnings if any exist
    for warning in warnings:
        print(f"  {warning}")

    # Add empty line
    print()

    # Loop through validation categories
    for category, checks in validation.get("checks", {}).items():
        # Print category title
        print(f"{category}:")

        # Track if anything was printed in this category
        printed_anything = False

        # Loop through checks
        for check in checks:
            # Skip passed checks unless requested
            if check["passed"] and not show_passed_checks:
                continue

            # Build status text
            status = "PASS" if check["passed"] else "FAIL"

            # Build severity text
            severity = check.get("severity", "error")

            # Print check
            print(f"  [{status}] {check['check']} ({severity})")
            print(f"    {check['message']}")

            # Mark that something was printed
            printed_anything = True

        # If no failed checks were printed, show a compact OK line
        if not printed_anything and not show_passed_checks:
            print("  OK")

        # Add empty line after category
        print()
