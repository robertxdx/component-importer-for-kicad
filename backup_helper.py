# Import datetime to create timestamped backup folders
from datetime import datetime

# Import Path for filesystem operations
from pathlib import Path

# Import shutil to copy files
import shutil


# Create a timestamp string for backup folder names
def get_backup_timestamp() -> str:
    # Return timestamp safe for Windows filenames
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


# Create the backup root folder
def create_backup_root(project_root: str | Path) -> Path:
    # Convert project root to Path object
    project_root = Path(project_root)

    # Store backups inside the project libraries folder
    backup_root = project_root / "libraries" / "backups"

    # Create backup folder if missing
    backup_root.mkdir(parents=True, exist_ok=True)

    # Return backup root path
    return backup_root


# Build a backup path that preserves the relative location of the original file
def build_backup_path(
    project_root: str | Path,
    target_file: str | Path,
    backup_timestamp: str,
) -> Path:
    # Convert inputs to Path objects
    project_root = Path(project_root)
    target_file = Path(target_file)

    # Create backup root
    backup_root = create_backup_root(project_root)

    # Try to preserve path relative to project root
    try:
        relative_target = target_file.relative_to(project_root)

    # If target is not inside project root, use only filename
    except ValueError:
        relative_target = Path(target_file.name)

    # Build backup path
    backup_path = backup_root / backup_timestamp / relative_target

    # Return backup path
    return backup_path


# Backup one file if it exists
def backup_file_if_exists(
    project_root: str | Path,
    target_file: str | Path,
    backup_timestamp: str,
) -> str | None:
    # Convert target file to Path object
    target_file = Path(target_file)

    # If the file does not exist, no backup is needed
    if not target_file.exists():
        return None

    # Build backup path
    backup_path = build_backup_path(
        project_root=project_root,
        target_file=target_file,
        backup_timestamp=backup_timestamp,
    )

    # Create backup parent folder
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy original file to backup location
    shutil.copy2(target_file, backup_path)

    # Return backup path as string
    return str(backup_path)


# Backup multiple files if they exist
def backup_files_if_exist(
    project_root: str | Path,
    target_files: list[str | Path],
    backup_timestamp: str,
) -> list[str]:
    # Store created backup paths
    backups = []

    # Loop through target files
    for target_file in target_files:
        # Backup current file
        backup_path = backup_file_if_exists(
            project_root=project_root,
            target_file=target_file,
            backup_timestamp=backup_timestamp,
        )

        # Store backup path if a backup was created
        if backup_path:
            backups.append(backup_path)

    # Return created backups
    return backups