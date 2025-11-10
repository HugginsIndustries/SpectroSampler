"""Utility functions for logging, hashing, timing, and path operations."""

import hashlib
import logging
import time
import unicodedata
from pathlib import Path
from typing import Final


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
    matplotlib_level = logging.INFO if verbose else logging.WARNING
    logging.getLogger("matplotlib").setLevel(matplotlib_level)
    logging.getLogger("matplotlib.font_manager").setLevel(matplotlib_level)


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


_INVALID_FILENAME_CHARS: Final[set[str]] = set('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES: Final[set[str]] = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}
_RESERVED_STEMS: Final[set[str]] = {"", ".", ".."}


def _is_control_char(char: str) -> bool:
    """Return True when the code point is a control/non-printable character."""
    return unicodedata.category(char).startswith("C")


def _sanitize_chars(raw: str) -> str:
    """Normalize Unicode and replace filesystem-problematic characters with underscores."""
    normalized = unicodedata.normalize("NFKC", raw or "")
    safe_chars: list[str] = []
    for char in normalized:
        if char in _INVALID_FILENAME_CHARS or char == "\x00" or _is_control_char(char):
            safe_chars.append("_")
        else:
            safe_chars.append(char)
    candidate = "".join(safe_chars).strip()
    while ".." in candidate:
        candidate = candidate.replace("..", ".")
    return candidate


def _split_extension(name: str) -> tuple[str, str]:
    """Return (stem, extension) without leading dots on the extension."""
    if "." not in name:
        return name, ""
    stem, ext = name.rsplit(".", 1)
    return stem, ext


def _is_reserved_stem(stem: str) -> bool:
    """Detect Windows device names and trivial dot names after trimming."""
    trimmed = stem.rstrip(" .")
    if trimmed in _RESERVED_STEMS:
        return True
    return trimmed.upper() in _WINDOWS_RESERVED_NAMES


def _ensure_safe_stem(stem: str, limit: int) -> str:
    """Fit the stem within limit characters while avoiding reserved names."""
    limit = max(limit, 1)
    base = (stem or "").strip().rstrip(" .")
    if not base:
        base = "untitled"
    base = base[:limit].rstrip(" .") or "untitled"[:limit] or "u"

    if not _is_reserved_stem(base):
        return base

    if limit == 1:
        return "X"

    trimmed = base[: limit - 1].rstrip(" .")
    if not trimmed:
        trimmed = "untitled"[: limit - 1] or "u"
    candidate = f"{trimmed}_"
    if len(candidate) > limit:
        candidate = candidate[:limit]

    if _is_reserved_stem(candidate):
        fallback = ("x" * (limit - 1) + "_") if limit > 1 else "X"
        candidate = fallback[:limit]

    if _is_reserved_stem(candidate):
        candidate = "x" * limit

    return candidate


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a filename string for cross-platform filesystem compatibility."""
    if max_length < 1:
        raise ValueError("max_length must be >= 1")

    # Normalize text and swap out characters that are illegal on common filesystems.
    sanitized = _sanitize_chars(name)
    # Work with stem/extension separately so we can honor the max length while keeping the suffix.
    stem, ext = _split_extension(sanitized)
    stem = stem.rstrip(" .")
    ext = ext.strip().rstrip(" .")

    if not stem and ext:
        stem, ext = ext, ""

    if "." not in sanitized:
        stem, ext = sanitized, ""

    dot_len = 1 if ext else 0
    allowed_stem_len = max_length - len(ext) - dot_len
    if allowed_stem_len < 1:
        ext = ""
        allowed_stem_len = max_length

    safe_stem = _ensure_safe_stem(stem, allowed_stem_len)
    if len(safe_stem) > allowed_stem_len:
        safe_stem = safe_stem[:allowed_stem_len].rstrip(" .") or _ensure_safe_stem(
            "", allowed_stem_len
        )

    sanitized_name = f"{safe_stem}.{ext}" if ext else safe_stem

    if len(sanitized_name) > max_length:
        sanitized_name = sanitized_name[:max_length].rstrip(" .")
        if not sanitized_name:
            sanitized_name = _ensure_safe_stem("untitled", max_length)
        else:
            stem, ext = _split_extension(sanitized_name)
            dot_len = 1 if ext else 0
            allowed_stem_len = max_length - len(ext) - dot_len
            safe_stem = _ensure_safe_stem(stem, allowed_stem_len)
            sanitized_name = f"{safe_stem}.{ext}" if ext else safe_stem

    if _is_reserved_stem(sanitized_name.split(".", 1)[0]):
        stem, ext = _split_extension(sanitized_name)
        dot_len = 1 if ext else 0
        allowed_stem_len = max_length - len(ext) - dot_len
        safe_stem = _ensure_safe_stem(stem, allowed_stem_len)
        sanitized_name = f"{safe_stem}.{ext}" if ext else safe_stem

    return sanitized_name


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
    if seconds < 60:
        return f"{seconds:.{precision}f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.{precision}f}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m {secs:.{precision}f}s"
