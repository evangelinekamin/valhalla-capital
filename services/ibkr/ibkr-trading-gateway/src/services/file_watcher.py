"""File watcher service using watchdog for trade request monitoring."""
from pathlib import Path
from typing import Callable

import structlog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

log = structlog.get_logger()


class RequestFileHandler(FileSystemEventHandler):
    """Handles file system events for trade requests."""

    def __init__(self, callback: Callable[[Path], None]):
        """
        Initialize file handler.

        Args:
            callback: Function to call when new request file detected
        """
        super().__init__()
        self.callback = callback
        self.logger = log.bind(component="request_file_handler")

    def on_created(self, event: FileCreatedEvent):
        """
        Called when a file is created in the watched directory.

        Args:
            event: File creation event
        """
        if event.is_directory:
            return

        filepath = Path(event.src_path)

        # Only process .json files (not temp files or hidden files)
        if filepath.suffix == ".json" and not filepath.name.startswith("."):
            self.logger.info("request_file_detected", filepath=str(filepath))
            try:
                self.callback(filepath)
            except Exception as e:
                self.logger.error(
                    "callback_failed", filepath=str(filepath), error=str(e)
                )


class FileWatcher:
    """
    Watches directory for new trade request files.

    Uses watchdog library to monitor file system events and
    trigger processing of new requests.
    """

    def __init__(self, watch_path: Path, callback: Callable[[Path], None]):
        """
        Initialize file watcher.

        Args:
            watch_path: Directory to watch
            callback: Function to call for each new file
        """
        self.watch_path = Path(watch_path)
        self.callback = callback
        self.observer = Observer()
        self._running = False
        self.logger = log.bind(component="file_watcher")

        # Ensure watch path exists
        self.watch_path.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            self.logger.warning("watcher_already_running")
            return

        handler = RequestFileHandler(self.callback)
        self.observer.schedule(handler, str(self.watch_path), recursive=False)
        self.observer.start()
        self._running = True

        self.logger.info("file_watcher_started", path=str(self.watch_path))

    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running:
            return

        self.observer.stop()
        self.observer.join(timeout=5.0)
        self._running = False

        self.logger.info("file_watcher_stopped")

    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    def process_existing(self) -> int:
        """
        Process any existing files in directory on startup.

        Returns:
            Number of files processed
        """
        json_files = sorted(self.watch_path.glob("*.json"))

        # Filter out hidden files
        json_files = [f for f in json_files if not f.name.startswith(".")]

        self.logger.info(
            "processing_existing_requests", count=len(json_files)
        )

        for filepath in json_files:
            try:
                self.logger.info("processing_existing_file", filepath=str(filepath))
                self.callback(filepath)
            except Exception as e:
                self.logger.error(
                    "existing_file_processing_failed",
                    filepath=str(filepath),
                    error=str(e),
                )

        return len(json_files)
