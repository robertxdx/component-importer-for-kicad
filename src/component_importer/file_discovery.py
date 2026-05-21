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

    return [
        path
        for path in candidates
        if path.is_file() and path.suffix.lower() == ".zip"
    ]
