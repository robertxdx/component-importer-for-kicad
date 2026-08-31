"""Content hashing for imported KiCad symbols and footprints.

The hashes produced here identify the *meaning* of an s-expression block, not
its exact text. They let a later import detect whether the user modified an
imported symbol or footprint in the library since the original import.

Canonicalization rules
-----------------------
Every hash is computed from a canonical serialization of the parsed
s-expression tree, so it is invariant to:

* Whitespace, indentation and newlines. The tree is re-serialized with single
  spaces and no indentation, so any layout change hashes identically.
* Rearrangement of sibling blocks. Inside every list the child elements are
  sorted alphabetically by their own canonical serialization, so reordering
  sibling ``(property ...)`` / ``(pin ...)`` blocks (or any other siblings)
  does not change the hash.
* Reordering of parameters within a block. Because sorting applies to every
  list, ``(effects (font (size 1 1)) hide)`` and ``(effects hide (font ...))``
  hash the same.
* Numeric formatting. Bare (unquoted) numeric atoms are normalized through a
  canonical numeric representation, so ``0``, ``0.0`` and ``0.00`` hash equal,
  and ``2.54`` equals ``2.540``.

Important details:

* The *head* atom of each list (position 0, e.g. ``symbol`` / ``pin`` / ``at``)
  is kept in place; only the remaining children are sorted among themselves.
  This keeps the node type meaningful while still normalizing sibling order.
* A consequence of sorting positional arguments is that positional numeric
  arguments become order-insensitive within their own list, e.g.
  ``(at 5 0 0)`` and ``(at 0 5 0)`` hash equally. This is an intentional
  trade-off of the "reorder parameters -> equal hash" requirement; changing
  any actual value still changes the hash.
* Only bare numeric atoms are normalized. Quoted strings are kept verbatim
  (their raw inner text, wrapped in quotes), so a pin name ``"2.540"`` stays
  distinct from ``"2.54"`` and non-numeric atoms keep their exact casing.
"""

# Import hashlib for the sha256 digest
import hashlib

# Import json to read metadata files during verification
import json

# Import re for numeric-atom detection
import re

# Import Path for filesystem operations
from pathlib import Path

# Reuse the escaped-quote detector and symbol block finder from the linker
from component_importer.symbol_footprint_linker import find_symbol_blocks, is_escaped


# Pattern that matches a bare numeric atom (int or float, optional exponent)
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


# One parsed atom that remembers whether it was originally quoted
class _Atom:
    # Store the atom value and whether it came from a quoted string
    def __init__(self, value: str, quoted: bool) -> None:
        self.value = value
        self.quoted = quoted


# Split s-expression text into tokens: open, close, and atoms
def _tokenize(text: str) -> list[tuple]:
    # Store detected tokens
    tokens: list[tuple] = []

    # Current scan index and text length
    index = 0
    length = len(text)

    # Scan the whole text
    while index < length:
        # Get current character
        char = text[index]

        # Skip whitespace between tokens
        if char.isspace():
            index += 1
            continue

        # Opening parenthesis
        if char == "(":
            tokens.append(("open", None, False))
            index += 1
            continue

        # Closing parenthesis
        if char == ")":
            tokens.append(("close", None, False))
            index += 1
            continue

        # Quoted string atom
        if char == '"':
            # Start reading after the opening quote
            end = index + 1

            # Read until an unescaped closing quote is found
            while end < length:
                if text[end] == '"' and not is_escaped(text, end):
                    break
                end += 1

            # Capture the raw inner text verbatim (escapes preserved)
            tokens.append(("atom", text[index + 1:end], True))

            # Continue after the closing quote
            index = end + 1
            continue

        # Bare atom: read until whitespace, a parenthesis, or a quote
        end = index
        while end < length and not text[end].isspace() and text[end] not in '()"':
            end += 1

        # Store the bare atom
        tokens.append(("atom", text[index:end], False))

        # Continue after the atom
        index = end

    # Return all tokens
    return tokens


# Parse tokens into a list of top-level forms (lists or atoms)
def _parse(text: str) -> list:
    # Tokenize the input
    tokens = _tokenize(text)

    # Track parse position as a mutable single-item list for the inner helper
    position = [0]

    # Parse one form starting at the current position
    def parse_form():
        # Get current token
        token = tokens[position[0]]

        # A list opens with "("
        if token[0] == "open":
            # Consume the opening parenthesis
            position[0] += 1

            # Collect children until the matching closing parenthesis
            children = []
            while position[0] < len(tokens) and tokens[position[0]][0] != "close":
                children.append(parse_form())

            # Stop if the closing parenthesis is missing
            if position[0] >= len(tokens):
                raise ValueError("Unbalanced parentheses in s-expression.")

            # Consume the closing parenthesis
            position[0] += 1

            # Return the list node
            return children

        # An atom token becomes an _Atom node
        if token[0] == "atom":
            position[0] += 1
            return _Atom(value=token[1], quoted=token[2])

        # A closing parenthesis without a matching open is invalid
        raise ValueError("Unexpected ')' in s-expression.")

    # Collect all top-level forms
    forms = []
    while position[0] < len(tokens):
        forms.append(parse_form())

    # Return the parsed forms
    return forms


# Return True when a bare atom string looks like a number
def _is_number(value: str) -> bool:
    # Empty atoms are never numbers
    if not value:
        return False

    # Match against the numeric pattern
    return bool(_NUMBER_RE.match(value))


# Produce a canonical representation of a numeric atom
def _canonical_number(value: str) -> str:
    # Parse the numeric atom as a float
    number = float(value)

    # Integer-valued numbers collapse to a plain integer (drops trailing zeros)
    if number.is_integer():
        return str(int(number))

    # Non-integer numbers use repr, which trims to the shortest round-trip form
    return repr(number)


# Serialize one parsed node into its canonical string form
def _canonical_node(node) -> str:
    # Lists sort their children (keeping the head in place)
    if isinstance(node, list):
        # An empty list serializes to "()"
        if not node:
            return "()"

        # Keep the head atom in position 0
        head = _canonical_node(node[0])

        # Sort the remaining children by their canonical serialization
        rest = sorted(_canonical_node(child) for child in node[1:])

        # Join with single spaces inside parentheses
        return "(" + " ".join([head] + rest) + ")"

    # Quoted strings keep their raw inner text wrapped in quotes
    if node.quoted:
        return '"' + node.value + '"'

    # Bare numeric atoms are normalized; other atoms are kept verbatim
    if _is_number(node.value):
        return _canonical_number(node.value)

    # Non-numeric bare atoms keep their exact text and casing
    return node.value


# Build the canonical serialization of an s-expression document
def canonicalize_sexpr(text: str) -> str:
    # Parse all top-level forms
    forms = _parse(text)

    # Canonicalize each top-level form, then sort them as siblings
    canonical_forms = sorted(_canonical_node(form) for form in forms)

    # Join with single spaces
    return " ".join(canonical_forms)


# Hash the canonical form of an s-expression document
def canonical_sexpr_hash(text: str) -> str:
    # Build the canonical serialization
    canonical = canonicalize_sexpr(text)

    # Return the sha256 hex digest
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Hash one named symbol block inside a KiCad symbol library file
def hash_symbol_in_library(library_path: str | Path, symbol_name: str) -> str | None:
    # Convert to a Path object
    library_path = Path(library_path)

    # Missing library means we cannot hash the symbol
    if not library_path.exists():
        return None

    # Read the library content
    content = library_path.read_text(encoding="utf-8", errors="ignore")

    # Find all top-level symbol blocks
    symbol_blocks = find_symbol_blocks(content)

    # Exact name match first
    for block in symbol_blocks:
        if block.get("name") == symbol_name:
            return canonical_sexpr_hash(block["text"])

    # Case-insensitive fallback
    for block in symbol_blocks:
        if block.get("name", "").lower() == (symbol_name or "").lower():
            return canonical_sexpr_hash(block["text"])

    # Symbol not found
    return None


# Hash one .kicad_mod footprint file
def hash_footprint_file(path: str | Path) -> str:
    # Convert to a Path object
    path = Path(path)

    # Read footprint content and hash its canonical form
    content = path.read_text(encoding="utf-8", errors="ignore")
    return canonical_sexpr_hash(content)


# Combine per-item statuses into one overall status
def _combine_statuses(statuses: list[str]) -> str:
    # A real mismatch dominates
    if "differs" in statuses:
        return "differs"

    # A missing file leaves the result unknown
    if "unknown" in statuses:
        return "unknown"

    # Everything matched
    if statuses:
        return "match"

    # Nothing to compare
    return "unknown"


# Verify stored content hashes against the current library and footprint files
def verify_component_hashes(
    metadata_path: str | Path,
    library_path: str | Path,
    footprint_dir: str | Path,
) -> dict:
    # Convert inputs to Path objects
    metadata_path = Path(metadata_path)
    library_path = Path(library_path)
    footprint_dir = Path(footprint_dir)

    # Default everything to unknown. Every failure below is deliberately
    # swallowed and left as "unknown" so a missing, empty, malformed, or
    # otherwise unreadable metadata file never crashes the overwrite flow.
    result = {"symbol": "unknown", "footprints": "unknown"}

    # Read metadata, returning all-unknown on any read/parse failure
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result

    # Metadata that is not a JSON object cannot carry usable hashes
    if not isinstance(metadata, dict):
        return result

    # Verify the symbol hash if metadata carries one; any surprise stays unknown
    try:
        stored_symbol_hash = metadata.get("symbol_hash")
        symbol_name = metadata.get("symbol_name")

        if stored_symbol_hash and isinstance(symbol_name, str) and symbol_name:
            current_symbol_hash = hash_symbol_in_library(library_path, symbol_name)

            # Missing symbol/library stays unknown
            if current_symbol_hash is None:
                result["symbol"] = "unknown"
            elif current_symbol_hash == stored_symbol_hash:
                result["symbol"] = "match"
            else:
                result["symbol"] = "differs"
    except Exception:
        result["symbol"] = "unknown"

    # Verify footprint hashes if metadata carries any; any surprise stays unknown
    try:
        footprint_hashes = metadata.get("footprint_hashes")

        if isinstance(footprint_hashes, dict) and footprint_hashes:
            # Collect a status for each stored footprint
            statuses = []
            for footprint_name, stored_hash in footprint_hashes.items():
                # Build the expected footprint path
                footprint_path = footprint_dir / f"{footprint_name}.kicad_mod"

                # Missing file is unknown
                if not footprint_path.exists():
                    statuses.append("unknown")
                    continue

                # Compare current hash against the stored hash
                current_hash = hash_footprint_file(footprint_path)
                statuses.append("match" if current_hash == stored_hash else "differs")

            # Reduce per-footprint statuses to one overall status
            result["footprints"] = _combine_statuses(statuses)
    except Exception:
        result["footprints"] = "unknown"

    # Return the verification result
    return result
