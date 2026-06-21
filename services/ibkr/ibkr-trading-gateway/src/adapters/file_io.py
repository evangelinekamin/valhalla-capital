"""File I/O adapter for shared volume communication with atomic operations."""
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from src.models.trade_request import TradeRequest
from src.models.trade_result import TradeResult
from src.models.portfolio_state import PortfolioState

log = structlog.get_logger()


class FileIOAdapter:
    """
    Handles file-based communication with Overseer.

    Implements atomic file operations to prevent partial reads/writes.
    """

    def __init__(
        self, requests_path: Path, results_path: Path, portfolio_path: Path
    ):
        """
        Initialize file I/O adapter.

        Args:
            requests_path: Directory for incoming trade requests
            results_path: Directory for outgoing trade results
            portfolio_path: Directory for portfolio state
        """
        self.requests_path = Path(requests_path)
        self.results_path = Path(results_path)
        self.portfolio_path = Path(portfolio_path)
        self.logger = log.bind(component="file_io")

        # Ensure directories exist
        for path in [self.requests_path, self.results_path, self.portfolio_path]:
            path.mkdir(parents=True, exist_ok=True)
            self.logger.debug("directory_ensured", path=str(path))

    def read_request(self, filepath: Path) -> Optional[TradeRequest]:
        """
        Read and validate a trade request file.

        Args:
            filepath: Path to request JSON file

        Returns:
            TradeRequest object or None if invalid
        """
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            request = TradeRequest.model_validate(data)
            self.logger.info(
                "request_read",
                request_id=str(request.request_id),
                ticker=request.ticker,
                action=request.action,
            )
            return request

        except json.JSONDecodeError as e:
            self.logger.error(
                "request_json_invalid", filepath=str(filepath), error=str(e)
            )
            return None

        except Exception as e:
            self.logger.error(
                "request_read_failed", filepath=str(filepath), error=str(e)
            )
            return None

    def write_result(self, result: TradeResult) -> Path:
        """
        Write trade result atomically.

        Uses temp file + rename for atomic operation.

        Args:
            result: TradeResult object

        Returns:
            Path to written result file
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{result.request_id}.json"
        filepath = self.results_path / filename

        # Atomic write: write to temp file, then rename
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.results_path, suffix=".tmp", text=True
        )

        try:
            # mkstemp returns an open fd; wrap it instead of opening a 2nd handle
            with os.fdopen(temp_fd, "w") as f:
                f.write(result.model_dump_json(indent=2))

            # Atomic rename
            shutil.move(temp_path, filepath)

            self.logger.info(
                "result_written",
                filepath=str(filepath),
                request_id=str(result.request_id),
                approved=result.approved,
            )

            return filepath

        except Exception as e:
            # Clean up temp file on error
            Path(temp_path).unlink(missing_ok=True)
            self.logger.error(
                "result_write_failed",
                request_id=str(result.request_id),
                error=str(e),
            )
            raise

    def write_portfolio_state(self, state: PortfolioState) -> Path:
        """
        Write current portfolio state atomically.

        Always writes to "current.json" for easy access.

        Args:
            state: PortfolioState object

        Returns:
            Path to written state file
        """
        filepath = self.portfolio_path / "current.json"

        # Atomic write
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.portfolio_path, suffix=".tmp", text=True
        )

        try:
            # mkstemp returns an open fd; wrap it instead of opening a 2nd handle
            with os.fdopen(temp_fd, "w") as f:
                f.write(state.model_dump_json(indent=2))

            shutil.move(temp_path, filepath)

            self.logger.info(
                "portfolio_state_written",
                total_value=state.total_value,
                positions=len(state.positions),
            )

            return filepath

        except Exception as e:
            Path(temp_path).unlink(missing_ok=True)
            self.logger.error("portfolio_state_write_failed", error=str(e))
            raise

    def archive_request(self, filepath: Path) -> Path:
        """
        Move processed request to archive subdirectory.

        Args:
            filepath: Path to request file

        Returns:
            Path to archived file
        """
        archive_dir = self.requests_path / "processed"
        archive_dir.mkdir(exist_ok=True)

        dest = archive_dir / filepath.name

        try:
            shutil.move(str(filepath), str(dest))
            self.logger.info("request_archived", filepath=str(dest))
            return dest

        except Exception as e:
            self.logger.error(
                "request_archive_failed", filepath=str(filepath), error=str(e)
            )
            raise

    def get_pending_requests(self) -> list[Path]:
        """
        Get list of pending request files.

        Returns:
            List of request file paths, sorted by filename
        """
        request_files = sorted(self.requests_path.glob("*.json"))

        # Filter out hidden files and processed directory
        request_files = [
            f for f in request_files if not f.name.startswith(".") and f.is_file()
        ]

        self.logger.debug("pending_requests_found", count=len(request_files))
        return request_files
