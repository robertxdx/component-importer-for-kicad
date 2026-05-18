# Import Path for filesystem operations
from pathlib import Path

# Import parser helpers from the existing symbol footprint linker
from component_importer.symbol_footprint_linker import find_symbol_blocks, remove_blocks_from_text


# Create an empty KiCad symbol library if needed
def create_empty_symbol_library(symbol_library_path: str | Path) -> None:
    # Convert input to Path object
    symbol_library_path = Path(symbol_library_path)

    # Do nothing if file already exists
    if symbol_library_path.exists():
        return

    # Create parent folder if needed
    symbol_library_path.parent.mkdir(parents=True, exist_ok=True)

    # Write minimal KiCad symbol library
    symbol_library_path.write_text(
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        '  (generator "component_importer")\n'
        '  (generator_version "0.1")\n'
        ")\n",
        encoding="utf-8",
    )


# Find the final closing parenthesis of a KiCad symbol library
def find_symbol_library_insert_position(content: str) -> int:
    # Find last closing parenthesis
    insert_position = content.rfind(")")

    # Stop if file is invalid
    if insert_position == -1:
        raise ValueError("Invalid KiCad symbol library. No final closing parenthesis found.")

    # Return insert position
    return insert_position


# Remove existing symbols from target content if their names match imported symbols
def remove_existing_symbols_by_name(
    target_content: str,
    symbol_names_to_replace: list[str],
) -> str:
    # Find existing symbol blocks in target library
    existing_symbol_blocks = find_symbol_blocks(target_content)

    # Store blocks to remove
    blocks_to_remove = []

    # Loop through existing symbols
    for block in existing_symbol_blocks:
        # If symbol name matches one of the imported symbols, mark it for removal
        if block.get("name") in symbol_names_to_replace:
            blocks_to_remove.append(block)

    # Remove matching blocks
    cleaned_content = remove_blocks_from_text(
        text=target_content,
        blocks=blocks_to_remove,
    )

    # Return cleaned content
    return cleaned_content


# Merge symbol blocks from source content into one target KiCad symbol library
def merge_symbol_library_content_into_target(
    target_symbol_library_path: str | Path,
    source_symbol_library_content: str,
    replace_existing_symbols: bool = True,
) -> dict:
    # Convert target path to Path object
    target_symbol_library_path = Path(target_symbol_library_path)

    # Create target symbol library if missing
    create_empty_symbol_library(target_symbol_library_path)

    # Read current target symbol library
    target_content = target_symbol_library_path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    # Find symbol blocks inside source symbol library
    source_symbol_blocks = find_symbol_blocks(source_symbol_library_content)

    # Stop if no symbols were found
    if not source_symbol_blocks:
        return {
            "target_symbol_library": str(target_symbol_library_path),
            "merged_symbol_names": [],
            "replaced_existing_symbols": [],
            "updated": False,
            "message": "No symbol blocks found in source symbol library.",
        }

    # Get imported symbol names
    imported_symbol_names = [
        block.get("name", "Unknown")
        for block in source_symbol_blocks
    ]

    # Store replaced symbol names
    replaced_existing_symbols = []

    # Replace existing symbols with the same name if enabled
    if replace_existing_symbols:
        # Find existing symbol names before removal
        existing_symbol_names = [
            block.get("name", "Unknown")
            for block in find_symbol_blocks(target_content)
        ]

        # Store which symbols will be replaced
        replaced_existing_symbols = [
            symbol_name
            for symbol_name in imported_symbol_names
            if symbol_name in existing_symbol_names
        ]

        # Remove existing symbols with matching names
        target_content = remove_existing_symbols_by_name(
            target_content=target_content,
            symbol_names_to_replace=imported_symbol_names,
        )

    # Build text to insert
    symbols_to_insert = ""

    # Add each source symbol block
    for block in source_symbol_blocks:
        symbols_to_insert += "\n"
        symbols_to_insert += block["text"]
        symbols_to_insert += "\n"

    # Find insert position before final closing parenthesis
    insert_position = find_symbol_library_insert_position(target_content)

    # Insert symbols into target library
    updated_content = (
        target_content[:insert_position]
        + symbols_to_insert
        + target_content[insert_position:]
    )

    # Check if target file changed
    updated = updated_content != target_content

    # Write updated target library
    target_symbol_library_path.write_text(updated_content, encoding="utf-8")

    # Return merge summary
    return {
        "target_symbol_library": str(target_symbol_library_path),
        "merged_symbol_names": imported_symbol_names,
        "replaced_existing_symbols": replaced_existing_symbols,
        "updated": updated,
        "message": f"Merged {len(imported_symbol_names)} symbol(s).",
    }


# Merge a symbol library file into a target KiCad symbol library
def merge_symbol_library_file_into_target(
    target_symbol_library_path: str | Path,
    source_symbol_library_path: str | Path,
    replace_existing_symbols: bool = True,
) -> dict:
    # Convert source path to Path object
    source_symbol_library_path = Path(source_symbol_library_path)

    # Stop if source file does not exist
    if not source_symbol_library_path.exists():
        raise FileNotFoundError(
            f"Source symbol library not found: {source_symbol_library_path.resolve()}"
        )

    # Read source symbol library content
    source_content = source_symbol_library_path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    # Merge source content into target library
    return merge_symbol_library_content_into_target(
        target_symbol_library_path=target_symbol_library_path,
        source_symbol_library_content=source_content,
        replace_existing_symbols=replace_existing_symbols,
    )