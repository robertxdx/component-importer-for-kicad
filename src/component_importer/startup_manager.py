# Import os for XDG startup paths
import os

# Import subprocess for platform command-line quoting
import subprocess

# Import sys to build the current app launch command
import sys

# Import Path for Linux autostart files
from pathlib import Path

# Import app path helpers
from component_importer.app_paths import APP_NAME
from component_importer.app_paths import is_frozen_app
from component_importer.app_paths import is_linux
from component_importer.app_paths import is_windows
from component_importer.app_paths import runtime_icon_path


# Command-line flag used by OS startup entries
START_MINIMIZED_TO_TRAY_ARG = "--start-minimized-to-tray"


# Registry value name used for Windows startup
RUN_VALUE_NAME = APP_NAME

# Registry path for per-user Windows startup apps
RUN_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Linux autostart desktop entry file name
LINUX_AUTOSTART_FILE_NAME = "kicad-component-importer.desktop"


# Return True when startup integration is available
def startup_supported() -> bool:
    return is_windows() or is_linux()


# Return True when this process was launched in tray-start mode
def start_minimized_to_tray_requested(args: list[str] | None = None) -> bool:
    if args is None:
        args = sys.argv

    return START_MINIMIZED_TO_TRAY_ARG in args


# Build the argv OS startup should run on login
def build_startup_argv() -> list[str]:
    # PyInstaller apps should restart the executable directly
    if getattr(sys, "frozen", False):
        return [sys.executable, START_MINIMIZED_TO_TRAY_ARG]

    # Source/development runs use the current Python environment
    return [
        sys.executable,
        "-m",
        "component_importer.gui_main",
        START_MINIMIZED_TO_TRAY_ARG,
    ]


# Build the command Windows should run on login
def build_windows_startup_command() -> str:
    return subprocess.list2cmdline(build_startup_argv())


# Quote one argument for a Linux desktop-entry Exec line
def quote_desktop_exec_argument(value: str) -> str:
    escaped_value = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("%", "%%")
    )

    return f'"{escaped_value}"'


# Build the Exec line Linux should run on login
def build_linux_startup_exec() -> str:
    return " ".join(
        quote_desktop_exec_argument(argument)
        for argument in build_startup_argv()
    )


# Return the per-user XDG autostart folder
def linux_autostart_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")

    if xdg_config_home:
        return Path(xdg_config_home) / "autostart"

    return Path.home() / ".config" / "autostart"


# Return the per-user XDG autostart file path
def linux_autostart_file_path() -> Path:
    return linux_autostart_dir() / LINUX_AUTOSTART_FILE_NAME


# Return a stable icon path for Linux autostart desktop entries
def linux_startup_icon_path() -> Path | None:
    if is_frozen_app():
        sidecar_icon_path = Path(sys.executable).resolve().parent / "app_icon.png"

        if sidecar_icon_path.exists():
            return sidecar_icon_path

    icon_path = runtime_icon_path()

    if icon_path.exists():
        return icon_path

    return None


# Build the Linux autostart desktop entry
def build_linux_autostart_entry() -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_NAME}",
        f"Exec={build_linux_startup_exec()}",
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        "NoDisplay=false",
        f"Comment=Start {APP_NAME} on login",
    ]

    icon_path = linux_startup_icon_path()

    if icon_path is not None:
        lines.insert(4, f"Icon={icon_path}")

    return "\n".join(lines) + "\n"


# Read the currently registered Windows startup command
def get_windows_startup_command() -> str | None:
    if not is_windows():
        return None

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_REGISTRY_PATH,
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None


# Return True when this app is registered to start on login
def startup_enabled() -> bool:
    if is_linux():
        startup_file_path = linux_autostart_file_path()

        if not startup_file_path.exists():
            return False

        expected_exec_line = f"Exec={build_linux_startup_exec()}"
        try:
            entry_text = startup_file_path.read_text(encoding="utf-8")
        except OSError:
            return False

        return expected_exec_line in entry_text.splitlines()

    if not is_windows():
        return False

    expected_command = build_windows_startup_command()
    current_command = get_windows_startup_command()

    return current_command == expected_command


# Enable or disable startup for the current user
def set_startup_enabled(enabled: bool) -> None:
    if is_linux():
        startup_file_path = linux_autostart_file_path()

        if enabled:
            startup_file_path.parent.mkdir(parents=True, exist_ok=True)
            startup_file_path.write_text(
                build_linux_autostart_entry(),
                encoding="utf-8",
            )
            startup_file_path.chmod(0o755)
            return

        try:
            startup_file_path.unlink()
        except FileNotFoundError:
            return

        return

    if not is_windows():
        return

    import winreg

    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        RUN_REGISTRY_PATH,
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                RUN_VALUE_NAME,
                0,
                winreg.REG_SZ,
                build_windows_startup_command(),
            )
            return

        try:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        except FileNotFoundError:
            return


# Backward-compatible names for older imports and config field naming
def start_with_windows_supported() -> bool:
    return startup_supported()


def start_with_windows_enabled() -> bool:
    return startup_enabled()


def set_start_with_windows(enabled: bool) -> None:
    set_startup_enabled(enabled)
