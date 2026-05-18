# Import os for Windows app data environment variables
import os

# Import sys to detect PyInstaller bundles
import sys

# Import Path for filesystem paths
from pathlib import Path


# User-visible application name
APP_NAME = "KiCad Component Importer"

# Folder name used in AppData and installer paths
APP_DIR_NAME = "KiCadComponentImporter"


# Return True when running from a PyInstaller-built executable
def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


# Resolve bundled assets in source runs and PyInstaller builds
def resource_path(relative_path: str) -> Path:
    # PyInstaller exposes bundled data through sys._MEIPASS
    bundle_root = getattr(sys, "_MEIPASS", None)

    if bundle_root:
        return Path(bundle_root) / relative_path

    # Source run: resources live beside this file
    return Path(__file__).resolve().parent / relative_path


# Get a per-user writable app data folder
def user_data_dir() -> Path:
    # Prefer the normal Windows per-user local app data folder
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME

    # Fallback for unusual environments
    return Path.home() / f".{APP_DIR_NAME}"


# Get the GUI config file path
def gui_config_file_path() -> Path:
    # Installed apps should never write beside the executable
    if is_frozen_app():
        return user_data_dir() / "gui_config.json"

    # Source runs keep the development config beside the scripts
    return Path(__file__).with_name("gui_config.json")
