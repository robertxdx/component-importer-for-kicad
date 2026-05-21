# Import os for platform app data environment variables
import os

# Import sys to detect PyInstaller bundles
import sys

# Import Path for filesystem paths
from pathlib import Path


# User-visible application name
APP_NAME = "KiCad Component Importer"

# Folder name used in per-user config and installer paths
APP_DIR_NAME = "KiCadComponentImporter"


# Return True when running on Windows
def is_windows() -> bool:
    return sys.platform.startswith("win")


# Return True when running on Darwin-based systems
def is_darwin() -> bool:
    return sys.platform == "darwin"


# Return True when running on Linux
def is_linux() -> bool:
    return sys.platform.startswith("linux")


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


# Get the repository root when running from source
def source_root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


# Get a per-user writable app data folder
def user_data_dir() -> Path:
    if is_windows():
        # Prefer the normal Windows per-user local app data folder
        local_app_data = os.environ.get("LOCALAPPDATA")

        if local_app_data:
            return Path(local_app_data) / APP_DIR_NAME

        return Path.home() / "AppData" / "Local" / APP_DIR_NAME

    if is_darwin():
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    # Linux and other Unix-like systems follow XDG_CONFIG_HOME when available
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        return Path(xdg_config_home) / APP_DIR_NAME

    return Path.home() / ".config" / APP_DIR_NAME


# Parse the XDG user dirs file for a configured Downloads folder
def xdg_downloads_dir() -> Path | None:
    user_dirs_file = Path.home() / ".config" / "user-dirs.dirs"

    if not user_dirs_file.exists():
        return None

    for line in user_dirs_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()

        if not line.startswith("XDG_DOWNLOAD_DIR="):
            continue

        value = line.split("=", 1)[1].strip().strip('"')
        value = value.replace("$HOME", str(Path.home()))

        if value:
            return Path(value)

    return None


# Get the default downloads folder for the current platform
def default_downloads_dir() -> Path:
    if is_linux():
        downloads_dir = xdg_downloads_dir()

        if downloads_dir is not None:
            return downloads_dir

    return Path.home() / "Downloads"


# Get a runtime icon path that Qt can load on all supported platforms
def runtime_icon_path() -> Path:
    preferred_icons = [
        "gui_assets/app_icon.png",
        "gui_assets/app_icon.ico",
        "gui_assets/app_icon.svg",
    ]

    for relative_path in preferred_icons:
        icon_path = resource_path(relative_path)

        if icon_path.exists():
            return icon_path

    return resource_path(preferred_icons[0])


# Get the GUI config file path
def gui_config_file_path() -> Path:
    # Installed apps should never write beside the executable
    if is_frozen_app():
        return user_data_dir() / "gui_config.json"

    # Source runs keep the development config at the repository root
    return source_root_dir() / "gui_config.json"
