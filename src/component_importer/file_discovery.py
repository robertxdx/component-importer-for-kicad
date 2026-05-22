# Import Path for filesystem paths
from pathlib import Path


# Return ZIP files in a folder with case-insensitive extension matching
def iter_zip_files(folder: str | Path) -> list[Path]:
    folder = Path(folder)

    if not folder.exists():
        return []

    try:
        candidates = folder.iterdir()
    except OSError:
        return []

    zip_files = []

    for path in candidates:
        try:
            is_zip_file = path.is_file() and path.suffix.lower() == ".zip"
        except OSError:
            continue

        if is_zip_file:
            zip_files.append(path)

    return zip_files
