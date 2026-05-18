# Import Path for filesystem operations
from pathlib import Path

# Import re for text matching and string cleanup
import re

# Import make_library_nickname so the footprint library name matches fp-lib-table
from component_importer.library_table_updater import make_library_nickname


# Check if a quote character is escaped
def is_escaped(text: str, index: int) -> bool:
    # Count backslashes before the quote character
    backslash_count = 0

    # Start from the character before the quote
    i = index - 1

    # Count continuous backslashes before the quote
    while i >= 0 and text[i] == "\\":
        backslash_count += 1
        i -= 1

    # Odd number of backslashes means the quote is escaped
    return backslash_count % 2 == 1


# Find the closing parenthesis that matches an opening parenthesis
def find_matching_paren(text: str, open_index: int) -> int:
    # Make sure the provided index points to an opening parenthesis
    if text[open_index] != "(":
        raise ValueError("open_index must point to an opening parenthesis.")

    # Track nested parentheses
    depth = 0

    # Track whether parser is inside a quoted string
    in_string = False

    # Scan from the opening parenthesis to the end of the text
    for index in range(open_index, len(text)):
        # Get current character
        char = text[index]

        # Toggle string state when finding an unescaped quote
        if char == '"' and not is_escaped(text, index):
            in_string = not in_string
            continue

        # Ignore parentheses inside quoted strings
        if in_string:
            continue

        # Increase depth for opening parenthesis
        if char == "(":
            depth += 1

        # Decrease depth for closing parenthesis
        elif char == ")":
            depth -= 1

            # Matching closing parenthesis found
            if depth == 0:
                return index

    # No matching parenthesis found
    raise ValueError("No matching closing parenthesis found.")


# Check if text at a given index starts with a specific KiCad list name
def starts_with_list_name(text: str, index: int, list_name: str) -> bool:
    # Build expected prefix
    prefix = f"({list_name}"

    # Return False if the text does not start with the expected prefix
    if not text.startswith(prefix, index):
        return False

    # Get the position after the prefix
    after_index = index + len(prefix)

    # Accept if the prefix reaches the end of text
    if after_index >= len(text):
        return True

    # KiCad list name should be followed by whitespace or closing parenthesis
    return text[after_index].isspace() or text[after_index] == ")"


# Find S-expression list blocks at a specific nesting depth
def find_list_blocks_at_depth(
    text: str,
    list_name: str,
    target_depth: int,
) -> list[dict]:
    # Store detected blocks
    blocks = []

    # Track nested parentheses
    depth = 0

    # Track whether parser is inside a quoted string
    in_string = False

    # Current scan index
    index = 0

    # Scan the text
    while index < len(text):
        # Get current character
        char = text[index]

        # Toggle string state when finding an unescaped quote
        if char == '"' and not is_escaped(text, index):
            in_string = not in_string
            index += 1
            continue

        # Ignore structural parsing inside quoted strings
        if in_string:
            index += 1
            continue

        # Handle opening parenthesis
        if char == "(":
            # Check if this is the requested list at the requested depth
            if depth == target_depth and starts_with_list_name(text, index, list_name):
                # Find full list block end
                end_index = find_matching_paren(text, index)

                # Store block
                blocks.append(
                    {
                        "start": index,
                        "end": end_index,
                        "text": text[index:end_index + 1],
                    }
                )

                # Jump after the detected block
                index = end_index + 1
                continue

            # Increase depth for a normal opening parenthesis
            depth += 1

        # Handle closing parenthesis
        elif char == ")":
            # Decrease depth
            depth -= 1

        # Move to next character
        index += 1

    # Return all detected blocks
    return blocks


# Remove selected blocks from text
def remove_blocks_from_text(text: str, blocks: list[dict]) -> str:
    # Remove blocks from end to beginning so indexes remain valid
    for block in sorted(blocks, key=lambda item: item["start"], reverse=True):
        # Remove block
        text = text[:block["start"]] + text[block["end"] + 1:]

    # Return cleaned text
    return text


# Extract symbol name from a symbol block
def extract_symbol_name(symbol_block: str) -> str:
    # Match symbol declaration like:
    # (symbol "AP63203WU-7"
    match = re.search(r'\(symbol\s+"([^"]+)"', symbol_block)

    # Return symbol name if found
    if match:
        return match.group(1)

    # Return fallback if not found
    return "Unknown"


# Extract property name from a property block
def extract_property_name(property_block: str) -> str | None:
    # Match property declaration like:
    # (property "Footprint" "..."
    match = re.search(r'\(property\s+"([^"]+)"', property_block)

    # Return property name if found
    if match:
        return match.group(1)

    # Return None if no property name was found
    return None


# Escape text for use inside KiCad quoted strings
def escape_kicad_string(value: str) -> str:
    # Escape backslashes first
    value = value.replace("\\", "\\\\")

    # Escape quotes
    value = value.replace('"', '\\"')

    # Return escaped text
    return value


# Find all top-level property blocks inside a symbol block
def find_top_level_property_blocks(symbol_block: str) -> list[dict]:
    # Top-level properties are inside the symbol at depth 1
    return find_list_blocks_at_depth(
        text=symbol_block,
        list_name="property",
        target_depth=1,
    )


# Find top-level property blocks by property name
def find_top_level_property_blocks_by_name(
    symbol_block: str,
    property_name: str,
) -> list[dict]:
    # Get all top-level property blocks
    property_blocks = find_top_level_property_blocks(symbol_block)

    # Store matching property blocks
    matching_blocks = []

    # Loop through property blocks
    for block in property_blocks:
        # Extract current property name
        current_property_name = extract_property_name(block["text"])

        # Store block if property name matches
        if current_property_name == property_name:
            matching_blocks.append(block)

    # Return matching blocks
    return matching_blocks


# Find best position for inserting a property block
def find_property_insert_position(symbol_block: str) -> int:
    # Get all existing top-level properties
    property_blocks = find_top_level_property_blocks(symbol_block)

    # If properties exist, insert after the last one
    if property_blocks:
        return property_blocks[-1]["end"] + 1

    # If no properties exist, insert after the first line
    first_newline = symbol_block.find("\n")

    # Insert after first line if possible
    if first_newline != -1:
        return first_newline + 1

    # Fallback to before final closing parenthesis
    return symbol_block.rfind(")")


# Build a clean KiCad property block
def build_property_block(
    property_name: str,
    property_value: str,
    hidden: bool = True,
) -> str:
    # Escape property name
    property_name = escape_kicad_string(property_name)

    # Escape property value
    property_value = escape_kicad_string(property_value)

    # Define visibility suffix
    visibility = " hide" if hidden else ""

    # Return complete property block
    return (
        '\n'
        f'    (property "{property_name}" "{property_value}"\n'
        '      (at 0 0 0)\n'
        f'      (effects (font (size 1.27 1.27)){visibility})\n'
        '    )'
    )


# Remove all old properties by name and insert one clean property
def replace_property(
    symbol_block: str,
    property_name: str,
    property_value: str,
    hidden: bool = True,
) -> str:
    # Find all old property blocks with this name
    old_property_blocks = find_top_level_property_blocks_by_name(
        symbol_block=symbol_block,
        property_name=property_name,
    )

    # Remove old properties
    cleaned_symbol_block = remove_blocks_from_text(
        text=symbol_block,
        blocks=old_property_blocks,
    )

    # Build new property block
    new_property_block = build_property_block(
        property_name=property_name,
        property_value=property_value,
        hidden=hidden,
    )

    # Find insertion point after existing properties
    insert_position = find_property_insert_position(cleaned_symbol_block)

    # Insert new property
    return (
        cleaned_symbol_block[:insert_position]
        + new_property_block
        + cleaned_symbol_block[insert_position:]
    )


# Remove old invalid fp_filters blocks if our previous version added them
def remove_old_fp_filters_blocks(symbol_block: str) -> str:
    # Find old fp_filters blocks
    old_filter_blocks = find_list_blocks_at_depth(
        text=symbol_block,
        list_name="fp_filters",
        target_depth=1,
    )

    # Remove them
    return remove_blocks_from_text(
        text=symbol_block,
        blocks=old_filter_blocks,
    )


# Get footprint names from imported .kicad_mod files
def get_footprint_names_from_files(footprint_files: list[str | Path]) -> list[str]:
    # Convert file paths to footprint names
    return [Path(footprint_file).stem for footprint_file in footprint_files]


# Build a full KiCad footprint reference
def build_footprint_reference(library_name: str, footprint_name: str) -> str:
    # Clean library nickname
    library_name = make_library_nickname(library_name)

    # Return full KiCad footprint reference
    return f"{library_name}:{footprint_name}"


# Normalize a preferred footprint name
def normalize_preferred_footprint_name(preferred_footprint_name: str) -> str:
    # If the user passed Library:Footprint, keep only Footprint
    if ":" in preferred_footprint_name:
        preferred_footprint_name = preferred_footprint_name.split(":")[-1]

    # Remove extension if provided
    preferred_footprint_name = Path(preferred_footprint_name).stem

    # Return normalized name
    return preferred_footprint_name


# Choose the default footprint from imported footprints
def choose_default_footprint_name(
    footprint_files: list[str | Path],
    preferred_footprint_name: str | None = None,
) -> str:
    # Get all footprint names
    footprint_names = get_footprint_names_from_files(footprint_files)

    # Stop if no footprints exist
    if not footprint_names:
        raise ValueError("No footprint files were provided.")

    # Use preferred footprint if provided and found
    if preferred_footprint_name:
        # Normalize preferred name
        preferred_name = normalize_preferred_footprint_name(preferred_footprint_name)

        # Exact match
        if preferred_name in footprint_names:
            return preferred_name

        # Case-insensitive match
        for footprint_name in footprint_names:
            if footprint_name.lower() == preferred_name.lower():
                return footprint_name

    # Prefer shortest name as default
    # This usually selects the base footprint instead of -L or -M variants
    return sorted(footprint_names, key=lambda name: (len(name), name))[0]


# Build exact footprint filters from all imported footprints
def build_exact_footprint_filters(
    library_name: str,
    footprint_files: list[str | Path],
    default_footprint_name: str | None = None,
    include_default_in_filters: bool = False,
) -> list[str]:
    # Get footprint names
    footprint_names = get_footprint_names_from_files(footprint_files)

    # Store filters
    filters = []

    # Loop through footprint names
    for footprint_name in footprint_names:
        # Skip the default footprint to avoid duplicate dropdown entry
        if not include_default_in_filters and footprint_name == default_footprint_name:
            continue

        # Add full footprint reference
        filters.append(
            build_footprint_reference(
                library_name=library_name,
                footprint_name=footprint_name,
            )
        )

    # Return filters
    return filters


# Build a wildcard footprint filter from all imported footprints
def build_wildcard_footprint_filter(
    library_name: str,
    footprint_files: list[str | Path],
) -> list[str]:
    # Get footprint names
    footprint_names = get_footprint_names_from_files(footprint_files)

    # Return empty list if no footprints exist
    if not footprint_names:
        return []

    # Start common prefix from first footprint
    common_prefix = footprint_names[0]

    # Shrink common prefix until every footprint starts with it
    for footprint_name in footprint_names[1:]:
        while common_prefix and not footprint_name.startswith(common_prefix):
            common_prefix = common_prefix[:-1]

    # Remove trailing separators
    common_prefix = common_prefix.rstrip("-_ ")

    # If no common prefix exists, fall back to exact filters
    if not common_prefix:
        return build_exact_footprint_filters(
            library_name=library_name,
            footprint_files=footprint_files,
        )

    # Build wildcard filter
    wildcard_filter = build_footprint_reference(
        library_name=library_name,
        footprint_name=f"{common_prefix}*",
    )

    # Return wildcard filter
    return [wildcard_filter]


# Build footprint filters according to selected mode
def build_footprint_filters(
    library_name: str,
    footprint_files: list[str | Path],
    default_footprint_name: str | None = None,
    filter_mode: str = "exact",
    include_default_in_filters: bool = False,
) -> list[str]:
    # Exact mode lists each compatible footprint explicitly
    if filter_mode == "exact":
        return build_exact_footprint_filters(
            library_name=library_name,
            footprint_files=footprint_files,
            default_footprint_name=default_footprint_name,
            include_default_in_filters=include_default_in_filters,
        )

    # Wildcard mode uses one common wildcard filter
    if filter_mode == "wildcard":
        return build_wildcard_footprint_filter(
            library_name=library_name,
            footprint_files=footprint_files,
        )

    # Stop if mode is invalid
    raise ValueError("filter_mode must be 'exact' or 'wildcard'.")


# Convert footprint filters to KiCad ki_fp_filters property value
def build_ki_fp_filters_value(footprint_filters: list[str]) -> str:
    # Remove empty filters
    footprint_filters = [
        filter_value.strip()
        for filter_value in footprint_filters
        if filter_value.strip()
    ]

    # Remove duplicates while preserving order
    footprint_filters = list(dict.fromkeys(footprint_filters))

    # KiCad stores ki_fp_filters as one space-separated string
    return " ".join(footprint_filters)


# Find top-level symbol blocks inside a KiCad symbol library
def find_symbol_blocks(symbol_library_content: str) -> list[dict]:
    # Top-level symbol blocks are inside kicad_symbol_lib at depth 1
    symbol_blocks = find_list_blocks_at_depth(
        text=symbol_library_content,
        list_name="symbol",
        target_depth=1,
    )

    # Add symbol names to blocks
    for block in symbol_blocks:
        block["name"] = extract_symbol_name(block["text"])

    # Return detected symbol blocks
    return symbol_blocks


# Select which symbol block should be updated
def select_symbol_block(
    symbol_blocks: list[dict],
    symbol_name: str | None = None,
) -> dict:
    # Stop if no symbols exist
    if not symbol_blocks:
        raise ValueError("No symbol blocks found in symbol library.")

    # If no symbol name was requested, update the first symbol
    if symbol_name is None:
        return symbol_blocks[0]

    # Exact match
    for symbol_block in symbol_blocks:
        if symbol_block["name"] == symbol_name:
            return symbol_block

    # Case-insensitive match
    for symbol_block in symbol_blocks:
        if symbol_block["name"].lower() == symbol_name.lower():
            return symbol_block

    # Stop if symbol was not found
    raise ValueError(f"Symbol not found: {symbol_name}")


# Link one KiCad symbol library to one default footprint and multiple footprint options
def link_symbol_library_to_footprints(
    symbol_library_path: str | Path,
    footprint_files: list[str | Path],
    library_name: str,
    default_footprint_name: str | None = None,
    symbol_name: str | None = None,
    filter_mode: str = "exact",
    include_default_in_filters: bool = False,
) -> dict:
    # Convert symbol library path to Path object
    symbol_library_path = Path(symbol_library_path)

    # Stop if symbol library does not exist
    if not symbol_library_path.exists():
        raise FileNotFoundError(f"Symbol library not found: {symbol_library_path.resolve()}")

    # Stop if no footprints were provided
    if not footprint_files:
        raise ValueError("At least one footprint file is required.")

    # Read symbol library file
    content = symbol_library_path.read_text(encoding="utf-8", errors="ignore")

    # Find top-level symbol blocks
    symbol_blocks = find_symbol_blocks(content)

    # Select symbol block to update
    selected_symbol_block = select_symbol_block(
        symbol_blocks=symbol_blocks,
        symbol_name=symbol_name,
    )

    # Choose default footprint name
    selected_default_footprint_name = choose_default_footprint_name(
        footprint_files=footprint_files,
        preferred_footprint_name=default_footprint_name,
    )

    # Build default footprint reference with library prefix
    default_footprint_reference = build_footprint_reference(
        library_name=library_name,
        footprint_name=selected_default_footprint_name,
    )

    # Build footprint filters
    footprint_filters = build_footprint_filters(
        library_name=library_name,
        footprint_files=footprint_files,
        default_footprint_name=selected_default_footprint_name,
        filter_mode=filter_mode,
        include_default_in_filters=include_default_in_filters,
    )

    # Convert filters to KiCad property value
    ki_fp_filters_value = build_ki_fp_filters_value(footprint_filters)

    # Get old symbol block text
    old_symbol_block_text = selected_symbol_block["text"]

    # Remove old invalid fp_filters blocks from previous linker version
    new_symbol_block_text = remove_old_fp_filters_blocks(old_symbol_block_text)

    # Replace old Footprint property with one clean fully qualified Footprint property
    new_symbol_block_text = replace_property(
        symbol_block=new_symbol_block_text,
        property_name="Footprint",
        property_value=default_footprint_reference,
        hidden=True,
    )

    # Replace old ki_fp_filters property with clean library-qualified filters
    new_symbol_block_text = replace_property(
        symbol_block=new_symbol_block_text,
        property_name="ki_fp_filters",
        property_value=ki_fp_filters_value,
        hidden=True,
    )

    # Build full updated library content
    updated_content = (
        content[:selected_symbol_block["start"]]
        + new_symbol_block_text
        + content[selected_symbol_block["end"] + 1:]
    )

    # Check if file changed
    changed = updated_content != content

    # Write updated symbol library
    symbol_library_path.write_text(updated_content, encoding="utf-8")

    # Return update summary
    return {
        "symbol_library": str(symbol_library_path),
        "updated": changed,
        "symbol_name": selected_symbol_block["name"],
        "default_footprint": default_footprint_reference,
        "footprint_filters": footprint_filters,
        "ki_fp_filters_value": ki_fp_filters_value,
        "filter_mode": filter_mode,
        "include_default_in_filters": include_default_in_filters,
        "available_footprints": [
            build_footprint_reference(library_name, footprint_name)
            for footprint_name in get_footprint_names_from_files(footprint_files)
        ],
    }