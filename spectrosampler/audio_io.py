"""Audio I/O and FFmpeg operations: denoising, cutting, analysis resampling."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from spectrosampler.utils import compute_file_hash, ensure_dir

logger = logging.getLogger(__name__)


def _quote_command(command: Sequence[str]) -> str:
    """Join a command sequence into a shell-escaped string."""

    return " ".join(shlex.quote(part) for part in command)


def _dedupe_suggestions(items: Iterable[str]) -> list[str]:
    """Return unique suggestions while preserving order."""

    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


class FFmpegError(Exception):
    """Exception raised when FFmpeg operations fail with actionable context."""

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str] | None = None,
        exit_code: int | None = None,
        stderr: str | None = None,
        stdout: str | None = None,
        suggestions: Iterable[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.command: list[str] | None = list(command) if command is not None else None
        self.exit_code = exit_code
        self.stderr = (stderr or "").strip()
        self.stdout = (stdout or "").strip()
        self._suggestions = _dedupe_suggestions(
            suggestions
            or (
                [
                    "Verify FFmpeg is installed and accessible on PATH.",
                    "Check that the source file exists and is readable.",
                    "Ensure the output directory is writable.",
                ]
            )
        )

    @property
    def suggestions(self) -> list[str]:
        """Actionable hints for the caller."""

        return list(self._suggestions)

    def command_string(self) -> str:
        """Return the command as a shell-escaped string."""

        if not self.command:
            return ""
        return _quote_command(self.command)

    def brief_stderr(self, max_lines: int = 6) -> str:
        """Return a truncated view of stderr for display purposes."""

        if not self.stderr:
            return ""
        lines = [line.rstrip() for line in self.stderr.splitlines() if line.strip()]
        if len(lines) > max_lines:
            return "\n".join(lines[: max_lines - 1] + ["… (truncated)"])
        return "\n".join(lines)

    def to_user_message(self, operation: str | None = None) -> str:
        """Build a rich, user-facing message with context and guidance."""

        label = operation or "FFmpeg operation"
        lines = [f"{label} failed."]
        if self.exit_code is not None:
            lines.append(f"Exit code: {self.exit_code}")
        if self.command:
            lines.append(f"Command: {self.command_string()}")
        stderr_preview = self.brief_stderr()
        if stderr_preview:
            lines.append("Details:")
            lines.append(stderr_preview)
        if self._suggestions:
            lines.append("")
            lines.append("Try this:")
            for suggestion in self._suggestions:
                lines.append(f"• {suggestion}")
        return "\n".join(lines)


class AudioLoadError(Exception):
    """Represents a user-facing audio load failure with remediation hints."""

    __slots__ = ("path", "cause", "suggestions", "details", "original")

    def __init__(
        self,
        path: Path,
        cause: str,
        suggestions: Iterable[str],
        details: str | None = None,
        original: Exception | None = None,
    ) -> None:
        super().__init__(cause)
        self.path = path
        self.cause = cause
        self.suggestions = tuple(_dedupe_suggestions(suggestions))
        self.details = details
        self.original = original
        if original is not None:
            self.__cause__ = original

    def to_user_message(self) -> str:
        """Return a detailed message suitable for dialog display."""

        lines = [f"Could not open '{self.path.name}'."]
        if self.cause:
            lines.append(f"Cause: {self.cause}")
        if self.details:
            lines.append(self.details.strip())
        if self.suggestions:
            lines.append("")
            lines.append("Try this:")
            for suggestion in self.suggestions:
                lines.append(f"• {suggestion}")
        return "\n".join(lines)


def _run_media_command(
    command: Sequence[str],
    *,
    operation: str,
    expect_success: bool = True,
    suggestions: Iterable[str] | None = None,
) -> subprocess.CompletedProcess:
    """Execute an ffmpeg/ffprobe command with consistent error handling."""

    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise FFmpegError(
            f"{operation} failed because FFmpeg is not available.",
            command=command,
            exit_code=None,
            stderr="Executable not found on PATH.",
            suggestions=[
                "Install FFmpeg (https://ffmpeg.org/download.html) and restart the application.",
                "Ensure the ffmpeg and ffprobe binaries are available on PATH.",
            ],
        ) from exc

    if expect_success and proc.returncode != 0:
        logger.error(
            "%s failed (exit code %s) for command: %s",
            operation,
            proc.returncode,
            _quote_command(command),
        )
        combined_suggestions = (
            list(suggestions)
            + [
                "Verify FFmpeg is installed and accessible on PATH.",
                "Check that the source file exists and is readable.",
                "Ensure the output directory is writable.",
            ]
            if suggestions is not None
            else None
        )
        raise FFmpegError(
            f"{operation} failed with exit code {proc.returncode}.",
            command=command,
            exit_code=proc.returncode,
            stderr=proc.stderr,
            stdout=proc.stdout,
            suggestions=combined_suggestions,
        )
    return proc


def _build_load_error(
    file_path: Path,
    exc: Exception,
    *,
    default_details: str | None = None,
) -> AudioLoadError:
    """Translate low-level errors into actionable audio load failures."""

    base_suggestions: list[str] = [
        "Verify the file still exists at the selected location.",
        "Check your read permissions for the file and containing directory.",
    ]
    cause = "Failed to open audio file"
    details = default_details

    if isinstance(exc, FileNotFoundError):
        cause = "File not found"
    elif isinstance(exc, PermissionError):
        cause = "Permission denied"
        base_suggestions.append("Close any other application that may be locking the file.")
    elif isinstance(exc, IsADirectoryError):
        cause = "Selected item is a directory"
        details = "Please choose an audio file instead of a directory."
    elif isinstance(exc, FFmpegError):
        stderr_lower = exc.stderr.lower()
        if "invalid data" in stderr_lower or "corrupt" in stderr_lower:
            cause = "Unsupported or corrupt audio format"
            details = (
                default_details
                or "FFmpeg could not decode the stream. Try re-exporting the audio or using a different format."
            )
            base_suggestions.extend(
                [
                    "Try converting the file to WAV or FLAC with FFmpeg or your DAW.",
                    "If the file was recorded on portable media, copy it locally first.",
                ]
            )
        elif "no such file or directory" in stderr_lower:
            cause = "File not found"
        elif "permission denied" in stderr_lower:
            cause = "Permission denied"
        elif exc.stderr:
            details = exc.brief_stderr(max_lines=4) or default_details
            base_suggestions.append("Review the FFmpeg details above for additional clues.")
    elif isinstance(exc, json.JSONDecodeError):
        cause = "Invalid metadata"
        details = "ffprobe returned malformed metadata. The file may be truncated or unsupported."
        base_suggestions.append("Verify the recording completes successfully and re-import.")
    elif isinstance(exc, ValueError):
        cause = str(exc) or "Invalid audio file"

    return AudioLoadError(
        path=file_path,
        cause=cause,
        details=details,
        suggestions=tuple(_dedupe_suggestions(base_suggestions)),
        original=exc,
    )


def _ensure_input_file(path: Path, *, purpose: str) -> None:
    """Ensure the provided path points to a readable file before invoking FFmpeg."""

    if not path.exists():
        raise FileNotFoundError(f"{purpose}: input file not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"{purpose}: expected a file but received directory: {path}")


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available in PATH.

    Returns:
        True if ffmpeg is found, False otherwise.
    """
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_audio_info(file_path: Path) -> dict:
    """Get audio file metadata using ffprobe.

    Args:
        file_path: Path to audio file.

    Returns:
        Dictionary with: duration (seconds), sample_rate (Hz), channels (int),
                          bit_depth (int), format (str).

    Raises:
        AudioLoadError: If the file cannot be opened or parsed.
    """
    path = Path(file_path)
    if not path.exists():
        raise AudioLoadError(
            path=path,
            cause="File not found",
            suggestions=(
                "Verify the file still exists at the selected location.",
                "If it lives on removable storage, make sure the drive is mounted.",
            ),
        )
    if path.is_dir():
        raise AudioLoadError(
            path=path,
            cause="Selected item is a directory",
            details="Please choose an audio file instead of a directory.",
            suggestions=("Pick a supported audio file (e.g., WAV, FLAC, MP3).",),
        )
    try:
        stat = path.stat()
    except PermissionError as exc:
        raise AudioLoadError(
            path=path,
            cause="Permission denied",
            suggestions=(
                "Check your read permissions for the file.",
                "Close any other applications that may be locking the file.",
            ),
            original=exc,
        ) from exc
    if stat.st_size == 0:
        raise AudioLoadError(
            path=path,
            cause="File is empty",
            details="The selected audio file contains no data.",
            suggestions=("Re-export or re-record the audio file before importing it.",),
        )

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = _run_media_command(cmd, operation="Read audio metadata")
    except FFmpegError as exc:
        raise _build_load_error(path, exc) from exc

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise _build_load_error(path, exc) from exc

    streams = data.get("streams", [])
    astream: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", astream.get("duration", 0.0)) or 0.0)
    sr = int(astream.get("sample_rate", 0) or fmt.get("sample_rate", 0) or 0)
    channels = int(astream.get("channels", 0) or 0)
    # Prefer explicit bit fields
    bit_depth = 0
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        val = astream.get(key)
        if val:
            try:
                bit_depth = int(val)
                break
            except (TypeError, ValueError) as exc:
                logging.debug(
                    "Failed to parse bit depth '%s' using key %s: %s", val, key, exc, exc_info=exc
                )
    # Fallback to sample_fmt inference
    if not bit_depth:
        sample_fmt = astream.get("sample_fmt", "")
        if "s16" in sample_fmt:
            bit_depth = 16
        elif "s24" in sample_fmt:
            bit_depth = 24
        elif "s32" in sample_fmt or "fltp" in sample_fmt or "flt" in sample_fmt:
            bit_depth = 32
    return {
        "duration": duration,
        "sample_rate": sr,
        "channels": channels,
        "bit_depth": bit_depth,
        "format": fmt.get("format_name", ""),
    }


def denoise_audio(
    input_path: Path,
    output_path: Path,
    method: str = "afftdn",
    highpass_hz: float | None = None,
    lowpass_hz: float | None = None,
    nr_strength: float = 12.0,
    arnndn_model: Path | None = None,
) -> None:
    """Denoise audio using FFmpeg filters.

    Args:
        input_path: Input audio file.
        output_path: Output denoised audio file.
        method: Denoising method: 'arnndn', 'afftdn', or 'off'.
        highpass_hz: Optional high-pass filter frequency (Hz).
        lowpass_hz: Optional low-pass filter frequency (Hz).
        nr_strength: Noise reduction strength for afftdn.
        arnndn_model: Optional path to arnndn model file (.mdl).

    Raises:
        ValueError: If the requested settings are invalid.
        FFmpegError: If FFmpeg operation fails.
    """
    valid_methods = {"arnndn", "afftdn", "off"}
    if method not in valid_methods:
        raise ValueError(f"method must be one of {sorted(valid_methods)}")
    if highpass_hz is not None and highpass_hz < 0:
        raise ValueError("highpass_hz must be non-negative")
    if lowpass_hz is not None and lowpass_hz < 0:
        raise ValueError("lowpass_hz must be non-negative")
    if nr_strength <= 0:
        raise ValueError("nr_strength must be positive")

    input_path = Path(input_path)
    output_path = Path(output_path)
    _ensure_input_file(input_path, purpose="Denoise audio")
    ensure_dir(output_path.parent)
    logging.info(f"Denoising {input_path} -> {output_path} (method={method})")
    filters: list[str] = []
    if highpass_hz and highpass_hz > 0:
        filters.append(f"highpass=f={highpass_hz}")
    if lowpass_hz and lowpass_hz > 0:
        filters.append(f"lowpass=f={lowpass_hz}")
    if method == "arnndn" and arnndn_model and arnndn_model.exists():
        filters.append(f"arnndn=m={arnndn_model.as_posix()}")
    elif method != "off":
        filters.append(f"afftdn=nr={nr_strength}:nt=w")
    af = ",".join(filters) if filters else "anull"
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-af", af, str(output_path)]
    _run_media_command(
        cmd,
        operation="Denoise audio",
        suggestions=[
            "Check that the selected denoise method is supported by your FFmpeg build.",
            "Confirm the input file is readable and the output directory is writable.",
        ],
    )


def resample_for_analysis(
    input_path: Path, output_path: Path, target_sr: int = 16000, channels: int = 1
) -> None:
    """Resample audio to analysis sample rate (16k mono by default).

    Args:
        input_path: Input audio file.
        output_path: Output resampled audio file.
        target_sr: Target sample rate (Hz).
        channels: Target number of channels (1=mono).

    Raises:
        ValueError: If the requested settings are invalid.
        FFmpegError: If FFmpeg operation fails.
    """
    if target_sr <= 0:
        raise ValueError("target_sr must be a positive integer")
    if channels not in (1, 2):
        raise ValueError("channels must be either 1 (mono) or 2 (stereo)")

    input_path = Path(input_path)
    output_path = Path(output_path)
    _ensure_input_file(input_path, purpose="Resample audio")
    ensure_dir(output_path.parent)
    logging.debug(f"Resampling {input_path} -> {output_path} ({target_sr} Hz, {channels}ch)")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        str(channels),
        "-ar",
        str(target_sr),
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    _run_media_command(
        cmd,
        operation="Resample audio",
        suggestions=[
            "Check that the input file is readable and not truncated.",
            "Ensure the requested sample rate is supported by FFmpeg.",
        ],
    )


def extract_sample(
    input_path: Path,
    output_path: Path,
    start_sec: float,
    end_sec: float,
    fade_in_ms: float = 0.0,
    fade_out_ms: float = 0.0,
    format: str = "wav",
    sample_rate: int | None = None,
    bit_depth: str | None = None,
    channels: str | None = None,
    normalize: bool = False,
    lufs_target: float | None = None,
) -> None:
    """Extract a sample segment from audio using FFmpeg.

    Attempts to use -c copy for speed; falls back to re-encoding if needed.

    Args:
        input_path: Input audio file.
        output_path: Output sample file.
        start_sec: Start time in seconds.
        end_sec: End time in seconds.
        fade_in_ms: Fade-in duration in milliseconds (0 = no fade).
        fade_out_ms: Fade-out duration in milliseconds (0 = no fade).
        format: Output format ('wav' or 'flac').
        sample_rate: Target sample rate (None = preserve original).
        bit_depth: Target bit depth ('16', '24', or '32f').
        channels: Target channels ('mono' or 'stereo').
        normalize: Whether to normalize output.
        lufs_target: Optional LUFS target for loudness normalization.

    Raises:
        ValueError: If the requested settings are invalid.
        FFmpegError: If FFmpeg operation fails.
    """
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")
    if fade_in_ms < 0 or fade_out_ms < 0:
        raise ValueError("fade durations must be non-negative")
    if format and format.lower() not in {"wav", "flac"}:
        raise ValueError("format must be 'wav' or 'flac'")
    if channels and channels not in {"mono", "stereo"}:
        raise ValueError("channels must be 'mono', 'stereo', or None")
    if sample_rate is not None and sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    if bit_depth and bit_depth not in {"16", "24", "32f"}:
        raise ValueError("bit_depth must be one of {'16', '24', '32f'}")

    input_path = Path(input_path)
    output_path = Path(output_path)
    _ensure_input_file(input_path, purpose="Export audio sample")
    ensure_dir(output_path.parent)

    duration = end_sec - start_sec
    logging.debug(f"Extracting sample: {start_sec:.3f}s-{end_sec:.3f}s -> {output_path}")

    # Try stream copy first (skip for WAV to ensure precise duration)
    fast_copy_succeeded = False
    if (format or "").lower() != "wav" and not str(output_path).lower().endswith(".wav"):
        cmd_copy = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.6f}",
            "-i",
            str(input_path),
            "-t",
            f"{duration:.6f}",
            "-c",
            "copy",
            str(output_path),
        ]
        proc = _run_media_command(
            cmd_copy,
            operation="Fast sample export",
            expect_success=False,
        )
        fast_copy_succeeded = proc.returncode == 0
    if fast_copy_succeeded:
        return

    # Fallback: re-encode
    af_filters: list[str] = []
    if fade_in_ms and fade_in_ms > 0:
        af_filters.append(f"afade=t=in:st=0:d={fade_in_ms/1000.0:.3f}")
    if fade_out_ms and fade_out_ms > 0:
        start_out = max(0.0, duration - fade_out_ms / 1000.0)
        af_filters.append(f"afade=t=out:st={start_out:.3f}:d={fade_out_ms/1000.0:.3f}")
    if lufs_target is not None:
        af_filters.append(f"loudnorm=I={lufs_target}")
    elif normalize:
        af_filters.append("dynaudnorm")

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_sec:.6f}",
        "-i",
        str(input_path),
        "-t",
        f"{duration:.6f}",
    ]
    if af_filters:
        cmd += ["-af", ",".join(af_filters)]
    if channels:
        cmd += ["-ac", "1" if channels == "mono" else "2"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    if bit_depth:
        sample_fmt = {"16": "s16", "24": "s32", "32f": "fltp"}[bit_depth]
        cmd += ["-sample_fmt", sample_fmt]
    if format:
        cmd += ["-f", format]
    cmd += [str(output_path)]

    _run_media_command(
        cmd,
        operation="Export audio sample",
        suggestions=[
            "Ensure the output directory is writable.",
            "Try exporting to WAV if your FFmpeg build cannot write the requested format.",
            "Confirm the source audio is readable and not truncated.",
        ],
    )


def generate_spectrogram_png(
    input_path: Path,
    output_path: Path,
    size: str = "4096x1024",
    gain_db: float = 20.0,
    scale: str = "log",
) -> None:
    """Generate spectrogram PNG using FFmpeg showspectrumpic.

    Args:
        input_path: Input audio file.
        output_path: Output PNG path.
        size: Image size (e.g., "4096x1024").
        gain_db: Gain in dB for visualization.
        scale: Frequency scale ('log' or 'lin').

    Raises:
        FFmpegError: If FFmpeg operation fails.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    _ensure_input_file(input_path, purpose="Create spectrogram image")
    ensure_dir(output_path.parent)
    logging.debug(f"Generating spectrogram PNG: {input_path} -> {output_path}")
    vf = f"showspectrumpic=s={size}:legend=disabled:color=intensity:scale={scale}:gain={gain_db}"
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-lavfi", vf, str(output_path)]
    _run_media_command(
        cmd,
        operation="Create spectrogram image",
        suggestions=[
            "Verify the input file is readable and supported by FFmpeg.",
            "Check that the output directory is writable.",
        ],
    )


def generate_spectrogram_video(
    input_path: Path,
    output_path: Path,
    fstart: float = 200.0,
    fstop: float = 3400.0,
    size: str = "1920x1080",
    gain_db: float = 20.0,
) -> None:
    """Generate spectrogram video (MP4) for voice band.

    Args:
        input_path: Input audio file.
        output_path: Output MP4 path.
        fstart: Start frequency (Hz).
        fstop: Stop frequency (Hz).
        size: Video size.
        gain_db: Gain in dB.

    Raises:
        FFmpegError: If FFmpeg operation fails.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    _ensure_input_file(input_path, purpose="Create spectrogram video")
    ensure_dir(output_path.parent)
    logging.debug(f"Generating spectrogram video: {input_path} -> {output_path}")
    vf = f"showspectrum=fstart={fstart}:fstop={fstop}:size={size}:color=intensity:scale=log:legend=disabled:gain={gain_db}"
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-lavfi", vf, str(output_path)]
    _run_media_command(
        cmd,
        operation="Create spectrogram video",
        suggestions=[
            "Verify the input file is readable and supported by FFmpeg.",
            "Check that the output directory is writable.",
            "Try reducing resolution if FFmpeg cannot allocate enough memory.",
        ],
    )


class AudioCache:
    """Cache for denoised and analysis-ready audio files."""

    def __init__(self, cache_dir: Path):
        """Initialize cache.

        Args:
            cache_dir: Base directory for cache storage.
        """
        self.cache_dir = cache_dir
        ensure_dir(cache_dir)

    def get_cache_key(
        self,
        source_file: Path,
        denoise_params: dict,
        analysis_params: dict,
    ) -> str:
        """Generate cache key from source file hash and parameters.

        Args:
            source_file: Source audio file path.
            denoise_params: Denoising parameters dict.
            analysis_params: Analysis resampling parameters dict.

        Returns:
            Hex string cache key.
        """
        source_hash = compute_file_hash(source_file)
        params_str = json.dumps(
            {"denoise": denoise_params, "analysis": analysis_params}, sort_keys=True
        )
        return f"{source_hash}_{abs(hash(params_str))}"

    def get_cached_path(self, cache_key: str, suffix: str) -> Path:
        """Get path for cached file.

        Args:
            cache_key: Cache key.
            suffix: File suffix (e.g., "_denoised.wav").

        Returns:
            Path to cached file.
        """
        return self.cache_dir / f"{cache_key}{suffix}"

    def is_cached(self, cache_key: str, suffix: str) -> bool:
        """Check if file is cached.

        Args:
            cache_key: Cache key.
            suffix: File suffix.

        Returns:
            True if cached file exists.
        """
        return self.get_cached_path(cache_key, suffix).exists()
