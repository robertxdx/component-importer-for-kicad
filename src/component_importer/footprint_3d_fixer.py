# Import Path for filesystem operations
from pathlib import Path

# Import re for regular expression search, cleaning names, and replacing model paths
import re


# Regex pattern used to find KiCad footprint model paths
# It matches lines like:
# (model "some/path/model.step"
# or:
# (model some/path/model.step
MODEL_BLOCK_PATTERN = re.compile(
    r'\(model\s+"?([^"\s\)]+)"?',
    re.IGNORECASE
)


# Normalize names so we can compare footprint names and 3D model names more reliably
def normalize_name(name: str) -> str:
    # Convert to lowercase
    name = name.lower()

    # Replace all non-letter and non-number characters with spaces
    name = re.sub(r"[^a-z0-9]+", " ", name)

    # Remove extra spaces
    name = " ".join(name.split())

    # Return cleaned name
    return name


# Split a normalized name into searchable tokens
def get_name_tokens(name: str) -> set[str]:
    # Normalize the name first
    normalized = normalize_name(name)

    # Split into words and remove very short tokens
    return {token for token in normalized.split() if len(token) >= 2}


# Give a small bonus depending on 3D model format
def get_model_format_bonus(model_path: str | Path) -> int:
    # Convert model path to Path object
    model_path = Path(model_path)

    # KiCad works best with STEP and STP models for mechanical checking
    if model_path.suffix.lower() in [".step", ".stp"]:
        return 10

    # WRL is valid for visual 3D preview
    if model_path.suffix.lower() == ".wrl":
        return 6

    # STL can be useful for visual 3D preview, but it is less ideal than STEP
    if model_path.suffix.lower() == ".stl":
        return 4

    # Unknown format gets no bonus
    return 0


# Score how well a 3D model filename matches a footprint filename
# The returned score is always between 0 and 100
def score_model_match(footprint_path: str | Path, model_path: str | Path) -> int:
    # Convert inputs to Path objects
    footprint_path = Path(footprint_path)
    model_path = Path(model_path)

    # Normalize footprint and model names without file extensions
    footprint_name = normalize_name(footprint_path.stem)
    model_name = normalize_name(model_path.stem)

    # If either name is empty, return zero confidence
    if not footprint_name or not model_name:
        return 0

    # Get format bonus
    format_bonus = get_model_format_bonus(model_path)

    # Exact normalized name match is the strongest case
    if footprint_name == model_name:
        return min(100, 90 + format_bonus)

    # Start with zero score for non-exact matches
    score = 0

    # Add points if one name contains the other
    if footprint_name in model_name or model_name in footprint_name:
        score += 45

    # Get token sets from both names
    footprint_tokens = get_name_tokens(footprint_path.stem)
    model_tokens = get_name_tokens(model_path.stem)

    # Add token overlap score
    if footprint_tokens and model_tokens:
        # Find common tokens between footprint and model names
        common_tokens = footprint_tokens.intersection(model_tokens)

        # Calculate overlap ratio relative to the larger token set
        overlap_ratio = len(common_tokens) / max(len(footprint_tokens), len(model_tokens))

        # Token overlap can add up to 35 points
        score += round(overlap_ratio * 35)

    # Add model format bonus
    score += format_bonus

    # Clamp score to 0...100
    return max(0, min(100, score))


# Find the best 3D model for one footprint
def find_best_matching_model(
    footprint_path: str | Path,
    model_files: list[str | Path],
) -> Path | None:
    # Return None if no model files exist
    if not model_files:
        return None

    # Convert all model files to Path objects
    model_paths = [Path(model_file) for model_file in model_files]

    # Sort models by match score, highest first
    ranked_models = sorted(
        model_paths,
        key=lambda model_path: score_model_match(footprint_path, model_path),
        reverse=True,
    )

    # Get best model
    best_model = ranked_models[0]

    # Return best matching model
    return best_model


# Find all 3D model paths currently referenced inside a KiCad footprint file
def find_3d_models_in_footprint(footprint_path: str | Path) -> list[str]:
    # Convert input to a Path object
    footprint_path = Path(footprint_path)

    # Stop early if the footprint file does not exist
    if not footprint_path.exists():
        raise FileNotFoundError(f"Footprint file not found: {footprint_path.resolve()}")

    # Read footprint text
    content = footprint_path.read_text(encoding="utf-8", errors="ignore")

    # Return all detected model paths
    return MODEL_BLOCK_PATTERN.findall(content)


# Replace or add the 3D model path in one KiCad footprint
def replace_3d_model_paths(
    footprint_path: str | Path,
    model_filename: str,
    project_relative_model_dir: str = "libraries/3dmodels",
) -> bool:
    # Convert input to a Path object
    footprint_path = Path(footprint_path)

    # Stop early if the footprint file does not exist
    if not footprint_path.exists():
        raise FileNotFoundError(f"Footprint file not found: {footprint_path.resolve()}")

    # Read footprint text
    content = footprint_path.read_text(encoding="utf-8", errors="ignore")

    # Build the new KiCad project-relative 3D model path
    new_model_path = f"${{KIPRJMOD}}/{project_relative_model_dir}/{model_filename}"

    # If the footprint has no 3D model block, add one before the final closing parenthesis
    if "(model " not in content:
        # Create a default KiCad 3D model block
        model_block = f'''
  (model "{new_model_path}"
    (offset (xyz 0 0 0))
    (scale (xyz 1 1 1))
    (rotate (xyz 0 0 0))
  )
'''

        # Find the last closing parenthesis in the footprint file
        insert_position = content.rfind(")")

        # If no closing parenthesis exists, the footprint file is invalid
        if insert_position == -1:
            raise ValueError(f"Invalid KiCad footprint file: {footprint_path}")

        # Insert the model block before the final closing parenthesis
        updated_content = content[:insert_position] + model_block + content[insert_position:]

    # If a 3D model block already exists, replace only the model path
    else:
        updated_content = re.sub(
            r'\(model\s+"?([^"\s\)]+)"?',
            f'(model "{new_model_path}"',
            content,
            flags=re.IGNORECASE,
        )

    # Write the updated footprint back to disk
    footprint_path.write_text(updated_content, encoding="utf-8")

    # Return True if the file changed
    return updated_content != content


# Fix 3D model paths for all imported footprints
def fix_3d_paths_for_imported_footprints(
    footprint_files: list[str | Path],
    model_files: list[str | Path],
) -> dict:
    # Prepare result dictionary
    result = {
        "updated_footprints": [],
        "skipped_footprints": [],
        "available_models": [str(Path(model).name) for model in model_files],
        "model_matches": [],
    }

    # If no 3D models were imported, we cannot fix any footprint paths
    if not model_files:
        result["skipped_footprints"] = [str(path) for path in footprint_files]
        return result

    # Loop through every imported footprint file
    for footprint_file in footprint_files:
        # Convert footprint path to Path object
        footprint_file = Path(footprint_file)

        # Find best matching model for this footprint
        best_model = find_best_matching_model(
            footprint_path=footprint_file,
            model_files=model_files,
        )

        # If no model could be selected, skip this footprint
        if best_model is None:
            result["skipped_footprints"].append(str(footprint_file))
            continue

        # Calculate matching score from 0 to 100
        match_score = score_model_match(footprint_file, best_model)

        # Replace or add the 3D model path
        changed = replace_3d_model_paths(
            footprint_path=footprint_file,
            model_filename=best_model.name,
        )

        # Store matching details for debugging and summary display
        result["model_matches"].append(
            {
                "footprint": str(footprint_file),
                "model": str(best_model),
                "score": match_score,
            }
        )

        # Store result depending on whether the file changed
        if changed:
            result["updated_footprints"].append(str(footprint_file))
        else:
            result["skipped_footprints"].append(str(footprint_file))

    # Return summary
    return result