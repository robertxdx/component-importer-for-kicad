# Import Path for filesystem paths
from pathlib import Path

# Import platform-specific app path helpers
from component_importer.app_paths import is_windows
from component_importer.app_paths import user_data_dir


# Cross-platform process lock used to keep only one GUI instance running
class SingleInstanceLock:
    # Create lock helper
    def __init__(self, lock_path: str | Path | None = None):
        if lock_path is None:
            lock_path = user_data_dir() / "app.lock"

        self.lock_path = Path(lock_path)
        self.lock_file = None

    # Acquire the lock without waiting
    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(self.lock_path, "a+b")

        try:
            lock_file.seek(0)

            if is_windows():
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(
                    lock_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
        except OSError:
            lock_file.close()
            return False

        self.lock_file = lock_file
        return True

    # Release the lock
    def release(self) -> None:
        if self.lock_file is None:
            return

        try:
            self.lock_file.seek(0)

            if is_windows():
                import msvcrt

                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self.lock_file.close()
            self.lock_file = None
