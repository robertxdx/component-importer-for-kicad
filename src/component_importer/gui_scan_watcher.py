# Import QObject, filesystem watcher, timer, and signals
from PyQt6.QtCore import QFileSystemWatcher
from PyQt6.QtCore import QObject
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import pyqtSignal

# Import Path for folder scanning
from pathlib import Path

# Import time for stability delay checks
import time

# Import case-insensitive ZIP discovery helper
from component_importer.file_discovery import iter_zip_files


# Event-driven ZIP folder watcher
class ZipFolderWatcher(QObject):
    # Emitted when a stable new ZIP file is detected
    zipDetected = pyqtSignal(str)

    # Emitted for log messages
    message = pyqtSignal(str)

    # Create watcher
    def __init__(self, parent=None):
        # Initialize QObject
        super().__init__(parent)

        # Watch folder changes reported by the OS
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.directoryChanged.connect(self.on_directory_changed)

        # Timer checks whether newly found ZIP files are stable
        self.stability_timer = QTimer(self)
        self.stability_timer.timeout.connect(self.check_candidates)

        # One-shot follow-up handles browser temp-file rename timing
        self.directory_rescan_timer = QTimer(self)
        self.directory_rescan_timer.setSingleShot(True)
        self.directory_rescan_timer.timeout.connect(self.scan_for_new_zip_candidates)

        # Store watched folder
        self.folder = None

        # Store known ZIP paths
        self.known_files = set()

        # Store candidate data
        self.candidates = {}

        # Store delay in seconds
        self.stable_delay_seconds = 4

    # Start watching a folder
    def start(
        self,
        folder: str,
        stable_delay_seconds: int = 4,
    ) -> None:
        # Stop before reconfiguring
        self.stop()

        # Convert folder to Path
        self.folder = Path(folder)

        # Store delay
        self.stable_delay_seconds = stable_delay_seconds

        # Clear candidates
        self.candidates = {}

        # If folder is invalid, log and return
        if not self.folder.exists():
            self.message.emit(f"Watch folder does not exist: {self.folder}")
            return

        # Mark existing ZIP files as known so they are not auto-imported immediately
        self.known_files = {
            str(path.resolve())
            for path in iter_zip_files(self.folder)
        }

        # Watch this folder for OS-reported changes
        self.file_watcher.addPath(str(self.folder))

        # Log status
        self.message.emit(f"Watching folder for new ZIP files: {self.folder}")

    # Stop watching
    def stop(self) -> None:
        # Only log a stop when the watcher was actually active
        was_running = bool(self.file_watcher.directories())

        # Stop timers
        self.stability_timer.stop()
        self.directory_rescan_timer.stop()

        # Remove watched folders
        watched_directories = self.file_watcher.directories()

        if watched_directories:
            self.file_watcher.removePaths(watched_directories)

        # Clear pending candidates
        self.candidates = {}

        # Log message
        if was_running:
            self.message.emit("Stopped ZIP folder watcher.")

    # React to an OS-reported folder change
    def on_directory_changed(self, folder: str) -> None:
        # Some platforms drop the watch after changes; keep it attached
        if folder and folder not in self.file_watcher.directories():
            self.file_watcher.addPath(folder)

        # Scan immediately for new ZIP candidates
        self.scan_for_new_zip_candidates()

        # Browsers can signal the folder while the ZIP is still a temp file.
        # Scan once more after that change burst so a final rename is visible.
        self.directory_rescan_timer.start(1000)

    # Scan for new ZIP candidates
    def scan_for_new_zip_candidates(self) -> None:
        # Return if folder is missing
        if self.folder is None or not self.folder.exists():
            return

        # Current time
        now = time.time()

        # Loop through ZIP files
        for zip_path in iter_zip_files(self.folder):
            # Get resolved path key
            path_key = str(zip_path.resolve())

            # Skip already known files
            if path_key in self.known_files:
                continue

            # Try to stat file
            try:
                stat = zip_path.stat()
            except OSError:
                continue

            # Get file size
            size = stat.st_size

            # Get candidate info
            candidate = self.candidates.get(path_key)

            # First time seeing candidate
            if candidate is None:
                self.candidates[path_key] = {
                    "size": size,
                    "first_seen": now,
                    "last_seen": now,
                    "path": zip_path,
                }
                continue

            # If size changed, reset stability timer
            if candidate["size"] != size:
                candidate["size"] = size
                candidate["first_seen"] = now
                candidate["last_seen"] = now

        # Start stability checks if there are candidates
        if self.candidates and not self.stability_timer.isActive():
            self.stability_timer.start(500)

    # Check whether candidate ZIP files have stopped changing
    def check_candidates(self) -> None:
        # Stop timer if nothing is pending
        if not self.candidates:
            self.stability_timer.stop()
            return

        # Return if folder is missing
        if self.folder is None or not self.folder.exists():
            self.stability_timer.stop()
            return

        # Current time
        now = time.time()

        # Check each candidate
        for path_key, candidate in list(self.candidates.items()):
            zip_path = Path(candidate["path"])

            # If file disappeared, remove it
            if not zip_path.exists():
                self.candidates.pop(path_key, None)
                continue

            # Try to stat file
            try:
                stat = zip_path.stat()
            except OSError:
                continue

            # Reset stability timer if size changed
            if stat.st_size != candidate["size"]:
                candidate["size"] = stat.st_size
                candidate["first_seen"] = now
                candidate["last_seen"] = now
                continue

            # Update last seen
            candidate["last_seen"] = now

            # Wait until file has remained unchanged long enough
            if now - candidate["first_seen"] < self.stable_delay_seconds:
                continue

            # Mark as known
            self.known_files.add(path_key)

            # Remove candidate
            self.candidates.pop(path_key, None)

            # Emit detected signal
            self.zipDetected.emit(str(zip_path))

        # Stop timer when all candidates are done
        if not self.candidates:
            self.stability_timer.stop()
