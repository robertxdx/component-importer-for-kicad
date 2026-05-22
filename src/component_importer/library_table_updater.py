# Import Path for filesystem operations
from pathlib import Path

# Import os for normalized path containment checks
import os

# Import re for extracting simple KiCad table fields
import re


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


# Extract balanced (lib ...) blocks from a KiCad library table
def extract_library_table_blocks(content: str) -> list[str]:
    blocks = []
    search_position = 0

    while True:
        start = content.find("(lib", search_position)

        if start == -1:
            return blocks

        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(content)):
            char = content[index]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False

                continue

            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1

                if depth == 0:
                    blocks.append(content[start:index + 1])
                    search_position = index + 1
                    break
        else:
            return blocks


# Extract one quoted field value from a KiCad library table block
def extract_quoted_table_field(block: str, field_name: str) -> str | None:
    match = re.search(
        rf'\({re.escape(field_name)}\s+"([^"]*)"\)',
        block,
    )

    if not match:
        return None

    return match.group(1)


# Find the URI for a library nickname already registered in a table
def find_library_uri_in_table(
    table_path: str | Path,
    library_nickname: str,
) -> str | None:
    table_path = Path(table_path)

    if not table_path.exists():
        return None

    library_nickname = make_library_nickname(library_nickname)
    content = table_path.read_text(encoding="utf-8", errors="ignore")

    for block in extract_library_table_blocks(content):
        block_name = extract_quoted_table_field(block, "name")

        if block_name != library_nickname:
            continue

        return extract_quoted_table_field(block, "uri")

    return None


# Check whether a path stays inside the selected project root
def path_is_inside_project(project_root: str | Path, path: str | Path) -> bool:
    project_root = Path(project_root)
    path = Path(path)

    project_root_text = os.path.normcase(os.path.realpath(str(project_root)))
    path_text = os.path.normcase(os.path.realpath(str(path)))

    try:
        return os.path.commonpath([project_root_text, path_text]) == project_root_text
    except ValueError:
        return False


# Return True when two filesystem paths point to the same normalized location
def paths_are_same(left: str | Path, right: str | Path) -> bool:
    left_text = os.path.normcase(os.path.realpath(str(left)))
    right_text = os.path.normcase(os.path.realpath(str(right)))

    return left_text == right_text


# Convert a project-local filesystem path to a KiCad ${KIPRJMOD} URI
def make_project_relative_uri(project_root: str | Path, target_path: str | Path) -> str:
    if not path_is_inside_project(project_root, target_path):
        raise ValueError(f"Library path is outside project root: {target_path}")

    relative_path = os.path.relpath(str(target_path), str(project_root))
    relative_path = relative_path.replace("\\", "/")

    if relative_path == ".":
        return "${KIPRJMOD}"

    return f"${{KIPRJMOD}}/{relative_path}"


# Resolve a KiCad table URI only when it points inside the selected project
def resolve_project_local_library_uri(
    project_root: str | Path,
    uri: str,
) -> Path | None:
    project_root = Path(project_root)
    uri = uri.strip()

    if not uri:
        return None

    # Do not guess paths that use unknown KiCad variables or URI schemes
    if uri.startswith("${") and not uri.startswith("${KIPRJMOD}"):
        return None

    if "://" in uri:
        return None

    kiprjmod = "${KIPRJMOD}"

    if uri == kiprjmod:
        candidate = project_root
    elif uri.startswith(f"{kiprjmod}/") or uri.startswith(f"{kiprjmod}\\"):
        relative_path = uri[len(kiprjmod) + 1:].replace("\\", "/")
        candidate = project_root / relative_path
    else:
        candidate = Path(uri)

        if not candidate.is_absolute():
            candidate = project_root / uri

    if not path_is_inside_project(project_root, candidate):
        return None

    return candidate


# Find an already registered project-local library path for a nickname
def find_project_library_path_in_table(
    project_root: str | Path,
    table_name: str,
    library_nickname: str,
) -> Path | None:
    project_root = Path(project_root)
    table_path = project_root / table_name
    uri = find_library_uri_in_table(
        table_path=table_path,
        library_nickname=library_nickname,
    )

    if uri is None:
        return None

    resolved_path = resolve_project_local_library_uri(
        project_root=project_root,
        uri=uri,
    )

    if resolved_path is None:
        raise ValueError(
            "Library nickname already exists with a URI outside this project "
            f"or an unsupported variable: {library_nickname} -> {uri}"
        )

    return resolved_path


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

    # If this nickname already exists, it must point to the same library
    existing_uri = find_library_uri_in_table(
        table_path=table_path,
        library_nickname=library_nickname,
    )

    if existing_uri is not None:
        existing_path = resolve_project_local_library_uri(
            project_root=project_root,
            uri=existing_uri,
        )

        if existing_path is not None and paths_are_same(existing_path, footprint_library_path):
            return False

        raise ValueError(
            "Footprint library nickname already exists with a different URI: "
            f"{library_nickname} -> {existing_uri}"
        )

    # Convert footprint library path to project-relative KiCad path
    library_uri = make_project_relative_uri(project_root, footprint_library_path)

    # Build KiCad table entry
    entry = (
        f'  (lib '
        f'(name "{library_nickname}") '
        f'(type "KiCad") '
        f'(uri "{library_uri}") '
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

    # If this nickname already exists, it must point to the same library
    existing_uri = find_library_uri_in_table(
        table_path=table_path,
        library_nickname=library_nickname,
    )

    if existing_uri is not None:
        existing_path = resolve_project_local_library_uri(
            project_root=project_root,
            uri=existing_uri,
        )

        if existing_path is not None and paths_are_same(existing_path, symbol_library_path):
            return False

        raise ValueError(
            "Symbol library nickname already exists with a different URI: "
            f"{library_nickname} -> {existing_uri}"
        )

    # Convert symbol library path to project-relative KiCad path
    library_uri = make_project_relative_uri(project_root, symbol_library_path)

    # Build KiCad table entry
    entry = (
        f'  (lib '
        f'(name "{library_nickname}") '
        f'(type "KiCad") '
        f'(uri "{library_uri}") '
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
