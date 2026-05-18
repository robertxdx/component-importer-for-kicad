# Import Path for filesystem operations
from pathlib import Path


# Make a KiCad-safe library nickname
def make_library_nickname(name: str) -> str:
    # Characters that are annoying or unsafe inside KiCad library nicknames
    invalid_chars = '<>:"/\\|?* '

    # Replace invalid characters with underscore
    for char in invalid_chars:
        name = name.replace(char, "_")

    # Remove repeated underscores
    while "__" in name:
        name = name.replace("__", "_")

    # Remove leading and trailing underscores
    name = name.strip("_")

    # Return fallback name if the result is empty
    if not name:
        return "Imported_Library"

    # Return cleaned nickname
    return name


# Create a basic KiCad fp-lib-table if it does not exist
def create_empty_fp_lib_table(table_path: str | Path) -> None:
    # Convert input to Path object
    table_path = Path(table_path)

    # Do nothing if file already exists
    if table_path.exists():
        return

    # Create parent folder if needed
    table_path.parent.mkdir(parents=True, exist_ok=True)

    # Write empty footprint library table
    table_path.write_text(
        "(fp_lib_table\n"
        ")\n",
        encoding="utf-8",
    )


# Create a basic KiCad sym-lib-table if it does not exist
def create_empty_sym_lib_table(table_path: str | Path) -> None:
    # Convert input to Path object
    table_path = Path(table_path)

    # Do nothing if file already exists
    if table_path.exists():
        return

    # Create parent folder if needed
    table_path.parent.mkdir(parents=True, exist_ok=True)

    # Write empty symbol library table
    table_path.write_text(
        "(sym_lib_table\n"
        ")\n",
        encoding="utf-8",
    )


# Add a footprint library entry to the project fp-lib-table
def add_footprint_library_to_table(
    project_root: str | Path,
    library_nickname: str,
    footprint_library_path: str | Path,
) -> bool:
    # Convert paths to Path objects
    project_root = Path(project_root)
    footprint_library_path = Path(footprint_library_path)

    # Define project-local fp-lib-table path
    table_path = project_root / "fp-lib-table"

    # Create table if missing
    create_empty_fp_lib_table(table_path)

    # Clean nickname
    library_nickname = make_library_nickname(library_nickname)

    # Read existing table content
    content = table_path.read_text(encoding="utf-8", errors="ignore")

    # If this nickname already exists, do not add duplicate entry
    if f'(name "{library_nickname}")' in content:
        return False

    # Convert footprint library path to project-relative KiCad path
    relative_path = footprint_library_path.relative_to(project_root).as_posix()

    # Build KiCad table entry
    entry = (
        f'  (lib '
        f'(name "{library_nickname}") '
        f'(type "KiCad") '
        f'(uri "${{KIPRJMOD}}/{relative_path}") '
        f'(options "") '
        f'(descr "Project local footprint library")'
        f')\n'
    )

    # Insert entry before final closing parenthesis
    insert_position = content.rfind(")")

    # Stop if table is invalid
    if insert_position == -1:
        raise ValueError(f"Invalid fp-lib-table file: {table_path}")

    # Create updated content
    updated_content = content[:insert_position] + entry + content[insert_position:]

    # Write updated table
    table_path.write_text(updated_content, encoding="utf-8")

    # Return True because file changed
    return True


# Add a symbol library entry to the project sym-lib-table
def add_symbol_library_to_table(
    project_root: str | Path,
    library_nickname: str,
    symbol_library_path: str | Path,
) -> bool:
    # Convert paths to Path objects
    project_root = Path(project_root)
    symbol_library_path = Path(symbol_library_path)

    # Define project-local sym-lib-table path
    table_path = project_root / "sym-lib-table"

    # Create table if missing
    create_empty_sym_lib_table(table_path)

    # Clean nickname
    library_nickname = make_library_nickname(library_nickname)

    # Read existing table content
    content = table_path.read_text(encoding="utf-8", errors="ignore")

    # If this nickname already exists, do not add duplicate entry
    if f'(name "{library_nickname}")' in content:
        return False

    # Convert symbol library path to project-relative KiCad path
    relative_path = symbol_library_path.relative_to(project_root).as_posix()

    # Build KiCad table entry
    entry = (
        f'  (lib '
        f'(name "{library_nickname}") '
        f'(type "KiCad") '
        f'(uri "${{KIPRJMOD}}/{relative_path}") '
        f'(options "") '
        f'(descr "Imported symbol library")'
        f')\n'
    )

    # Insert entry before final closing parenthesis
    insert_position = content.rfind(")")

    # Stop if table is invalid
    if insert_position == -1:
        raise ValueError(f"Invalid sym-lib-table file: {table_path}")

    # Create updated content
    updated_content = content[:insert_position] + entry + content[insert_position:]

    # Write updated table
    table_path.write_text(updated_content, encoding="utf-8")

    # Return True because file changed
    return True


# Register imported footprint and symbol libraries in KiCad project tables
def update_kicad_library_tables(
    project_root: str | Path,
    library_name: str,
    footprint_library_path: str | Path,
    symbol_library_paths: list[str | Path],
) -> dict:
    # Convert project root to Path object
    project_root = Path(project_root)

    # Prepare result dictionary
    result = {
        "footprint_table_updated": False,
        "symbol_tables_updated": [],
        "symbol_tables_skipped": [],
    }

    # Add footprint library to fp-lib-table
    result["footprint_table_updated"] = add_footprint_library_to_table(
        project_root=project_root,
        library_nickname=library_name,
        footprint_library_path=footprint_library_path,
    )

    # Add every imported symbol library to sym-lib-table
    for symbol_library_path in symbol_library_paths:
        # Convert to Path object
        symbol_library_path = Path(symbol_library_path)

        # Create nickname from symbol library filename
        symbol_nickname = make_library_nickname(symbol_library_path.stem)

        # Add symbol library entry
        changed = add_symbol_library_to_table(
            project_root=project_root,
            library_nickname=symbol_nickname,
            symbol_library_path=symbol_library_path,
        )

        # Store result
        if changed:
            result["symbol_tables_updated"].append(str(symbol_library_path))
        else:
            result["symbol_tables_skipped"].append(str(symbol_library_path))

    # Return summary
    return result