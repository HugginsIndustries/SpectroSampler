"""Utility functions for logging, hashing, timing, and path operations."""

import hashlib
import logging
import time
from pathlib import Path


class Timer:
    """Simple context manager for timing operations."""

    def __init__(self, label: str = "Operation"):
        """Initialize timer with a label.

        Args:
            label: Description of what is being timed.
        """
        self.label = label
        self.start_time: float | None = None
        self.elapsed: float | None = None

    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and log elapsed time."""
        if self.start_time is not None:
            self.elapsed = time.time() - self.start_time
            logging.debug(f"{self.label} took {self.elapsed:.3f}s")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.

    Args:
        verbose: If True, set log level to DEBUG, otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def compute_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 hash of a file for caching purposes.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Size of chunks to read at a time.

    Returns:
        Hex digest of the file's SHA256 hash.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a filename by removing invalid characters.

    Args:
        name: Original filename or string.
        max_length: Maximum length of the sanitized name.

    Returns:
        Sanitized filename safe for filesystem use.
    """
    # TODO: Replace invalid characters (Windows + Linux), remove control chars,
    #       handle non-ASCII gracefully, truncate if needed
    invalid_chars = '<>:"/\\|?*'
    sanitized = name
    for char in invalid_chars:
        sanitized = sanitized.replace(char, "_")
    # Remove control characters
    sanitized = "".join(c for c in sanitized if ord(c) >= 32 or c in ("\n", "\t"))
    if len(sanitized) > max_length:
        # Try to preserve extension if present
        if "." in sanitized:
            name_part, ext = sanitized.rsplit(".", 1)
            truncate_at = max_length - len(ext) - 1
            if truncate_at > 0:
                sanitized = name_part[:truncate_at] + "." + ext
            else:
                sanitized = sanitized[:max_length]
        else:
            sanitized = sanitized[:max_length]
    return sanitized.strip()


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure.

    Returns:
        The path object (created if it didn't exist).
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_duration(seconds: float, precision: int = 1) -> str:
    """Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds.
        precision: Decimal places for seconds.

    Returns:
        Formatted string like "1h 23m 45.6s" or "45.6s".
    """
    # TODO: Implement hours/minutes formatting for long durations
    if seconds < 60:
        return f"{seconds:.{precision}f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.{precision}f}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m {secs:.{precision}f}s"
