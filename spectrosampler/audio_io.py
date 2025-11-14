"""Audio I/O and FFmpeg operations: denoising, cutting, analysis resampling."""

import json
import logging
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spectrosampler.utils import compute_file_hash, ensure_dir


class FFmpegError(Exception):
    """Exception raised when FFmpeg/ffprobe operations fail.

    Attributes:
        command: Full command that was attempted.
        stderr: Raw stderr output (if any).
        stdout: Raw stdout output (if any).
        exit_code: Exit code returned by FFmpeg, if the process started.
        context: Optional high-level context string describing the attempted action.
        hints: Suggested remediation steps gathered during failure analysis.
    """

    def __init__(
        self,
        command: Sequence[str],
        message: str,
        *,
        stderr: str = "",
        stdout: str = "",
        exit_code: int | None = None,
        context: str | None = None,
        hints: Sequence[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.command = list(command)
        self.stderr = stderr
        self.stdout = stdout
        self.exit_code = exit_code
        self.context = context
        self.hints = list(hints or [])

    @property
    def command_summary(self) -> str:
        """Return the command rendered as a single quoted string."""

        return " ".join(shlex.quote(part) for part in self.command)


@dataclass(frozen=True, slots=True)
class AudioLoadAdvice:
    """Represents a user-facing explanation for audio load failures."""

    reason: str
    suggestion: str


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
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    proc = _run_media_tool(
        cmd,
        expected_inputs=[file_path],
        context="Inspect audio metadata (ffprobe)",
        tool_name="ffprobe",
    )
    data = json.loads(proc.stdout or "{}")
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


def describe_audio_load_error(file_path: Path | None, error: BaseException) -> AudioLoadAdvice:
    """Convert low-level audio loading exceptions into user-facing guidance."""

    display_name = file_path.name if isinstance(file_path, Path) else "audio file"
    message = str(error) if error else ""
    lower_msg = message.lower()

    if isinstance(error, FileNotFoundError):
        filename = getattr(error, "filename", "") or ""
        if filename and Path(filename).name in {"ffprobe", "ffmpeg"}:
            return AudioLoadAdvice(
                reason="FFmpeg (ffprobe) is not installed or not on your PATH.",
                suggestion="Install FFmpeg and ensure the ffprobe executable is accessible, then restart SpectroSampler.",
            )
        return AudioLoadAdvice(
            reason=f"The file '{display_name}' could not be found.",
            suggestion="Verify the file still exists at that location or choose a different file.",
        )

    if isinstance(error, PermissionError):
        return AudioLoadAdvice(
            reason="SpectroSampler does not have permission to read the selected file.",
            suggestion="Adjust the file permissions or copy it to a readable location and retry.",
        )

    if isinstance(error, FFmpegError):
        if "invalid data" in lower_msg or "unable to find stream info" in lower_msg:
            return AudioLoadAdvice(
                reason=f"The file '{display_name}' appears to be corrupted or uses an unsupported codec.",
                suggestion="Try playing it in another application or convert the file to WAV/FLAC before importing.",
            )
        if "no such file or directory" in lower_msg and (
            "ffmpeg" in lower_msg or "ffprobe" in lower_msg
        ):
            return AudioLoadAdvice(
                reason="FFmpeg (ffprobe) is not installed or not accessible.",
                suggestion="Install FFmpeg and ensure ffprobe is on your PATH, then restart SpectroSampler.",
            )
        if "permission" in lower_msg:
            return AudioLoadAdvice(
                reason="FFmpeg reported a permission error while reading the file.",
                suggestion="Check your file permissions and try again.",
            )
        if not check_ffmpeg():
            return AudioLoadAdvice(
                reason="FFmpeg tools are not installed or could not be executed.",
                suggestion="Install FFmpeg and ensure it is available on your PATH, then restart SpectroSampler.",
            )
        return AudioLoadAdvice(
            reason="FFmpeg was unable to analyze the audio file.",
            suggestion="Review the application log for details or convert the file to WAV/FLAC and try again.",
        )

    if isinstance(error, ValueError):
        return AudioLoadAdvice(
            reason=f"The file '{display_name}' is not a valid audio file.",
            suggestion="Confirm the file contains audio data and convert it to WAV if necessary.",
        )

    if isinstance(error, OSError):
        return AudioLoadAdvice(
            reason=f"An OS error prevented opening '{display_name}'. {message}",
            suggestion="Ensure no other program is locking the file and that you have read access.",
        )

    return AudioLoadAdvice(
        reason="An unexpected error occurred while opening the audio file.",
        suggestion="Check the application log for more details or try converting the file to WAV/FLAC.",
    )


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
        FFmpegError: If FFmpeg operation fails.
    """
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
    _run_media_tool(
        cmd,
        expected_inputs=[input_path],
        context="Denoise audio",
    )


def resample_for_analysis(
    input_path: Path,
    output_path: Path,
    target_sr: int = 16000,
    channels: int = 1,
    *,
    resample_strategy: str = "default",
) -> None:
    """Resample audio to analysis sample rate (16k mono by default).

    Args:
        input_path: Input audio file.
        output_path: Output resampled audio file.
        target_sr: Target sample rate (Hz).
        channels: Target number of channels (1=mono).

    Raises:
        FFmpegError: If FFmpeg operation fails.
    """
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
    ]
    filters: list[str] = []
    if resample_strategy == "soxr":
        filters.append("aresample=resampler=soxr:precision=28")
    cmd += ["-sample_fmt", "s16"]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd.append(str(output_path))
    _run_media_tool(
        cmd,
        expected_inputs=[input_path],
        context="Prepare analysis resample",
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
    metadata: dict[str, Any] | None = None,
    bandpass_low_hz: float | None = None,
    bandpass_high_hz: float | None = None,
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
        FFmpegError: If FFmpeg operation fails.
    """
    ensure_dir(output_path.parent)
    logging.debug(f"Extracting sample: {start_sec:.3f}s-{end_sec:.3f}s -> {output_path}")
    duration = max(0.0, end_sec - start_sec)

    metadata_entries: dict[str, str] = {}
    if metadata:
        for key, value in metadata.items():
            if value in (None, ""):
                continue
            metadata_entries[str(key)] = str(value)

    bp_low = float(bandpass_low_hz) if bandpass_low_hz is not None else None
    bp_high = float(bandpass_high_hz) if bandpass_high_hz is not None else None
    if bp_low is not None and bp_low < 0.0:
        raise ValueError("bandpass_low_hz must be non-negative.")
    if bp_high is not None and bp_high <= 0.0:
        raise ValueError("bandpass_high_hz must be positive when provided.")
    if bp_low is not None and bp_high is not None and bp_low >= bp_high:
        raise ValueError("bandpass_low_hz must be lower than bandpass_high_hz.")

    def _bandpass_filter_list() -> list[str]:
        filters: list[str] = []
        if bp_low is not None and bp_high is not None:
            # Use highpass and lowpass filters chained together for reliable bandpass
            filters.append(f"highpass=f={bp_low}")
            filters.append(f"lowpass=f={bp_high}")
        elif bp_low is not None:
            filters.append(f"highpass=f={bp_low}")
        elif bp_high is not None:
            filters.append(f"lowpass=f={bp_high}")
        return filters

    bandpass_filters = _bandpass_filter_list()

    def _apply_metadata(cmd: list[str]) -> None:
        for key, value in metadata_entries.items():
            cmd += ["-metadata", f"{key}={value}"]

    fmt_lower = (format or "").lower()
    input_ext = input_path.suffix.lower().lstrip(".")
    same_format = bool(fmt_lower) and fmt_lower == input_ext

    # If normalization is requested, we need to re-encode (can't use stream copy)
    # For peak normalization, we need two passes: detect peak, then normalize
    if normalize and lufs_target is None:
        # Two-pass peak normalization to -0.1 dBFS
        # First pass: detect peak level using volumedetect
        temp_extract_filters: list[str] = []
        if fade_in_ms and fade_in_ms > 0:
            temp_extract_filters.append(f"afade=t=in:st=0:d={fade_in_ms/1000.0:.3f}")
        if fade_out_ms and fade_out_ms > 0:
            start_out = max(0.0, duration - fade_out_ms / 1000.0)
            temp_extract_filters.append(
                f"afade=t=out:st={start_out:.3f}:d={fade_out_ms/1000.0:.3f}"
            )
        temp_extract_filters.extend(bandpass_filters)

        # Run volumedetect to find peak level
        volumedetect_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.6f}",
            "-i",
            str(input_path),
            "-t",
            f"{duration:.6f}",
        ]
        # Combine fade filters with volumedetect in a single -af option
        volumedetect_filters = temp_extract_filters.copy()
        volumedetect_filters.append("volumedetect")
        volumedetect_cmd += ["-af", ",".join(volumedetect_filters), "-f", "null", "-"]

        proc = _run_media_tool(
            volumedetect_cmd,
            expected_inputs=[input_path],
            context="Sample normalization (peak detect)",
        )

        # Parse peak level from volumedetect output
        # Format: "max_volume: -X.XX dB"
        peak_db = None
        for line in proc.stderr.split("\n"):
            if "max_volume:" in line:
                try:
                    peak_db = float(line.split("max_volume:")[1].split("dB")[0].strip())
                    break
                except (ValueError, IndexError):
                    pass

        if peak_db is None:
            # Fallback: assume peak is at 0 dBFS if detection fails
            peak_db = 0.0

        # Calculate gain needed to normalize to -0.1 dBFS
        target_db = -0.1
        gain_db = target_db - peak_db

        # Second pass: apply volume adjustment
        af_filters: list[str] = []
        if fade_in_ms and fade_in_ms > 0:
            af_filters.append(f"afade=t=in:st=0:d={fade_in_ms/1000.0:.3f}")
        if fade_out_ms and fade_out_ms > 0:
            start_out = max(0.0, duration - fade_out_ms / 1000.0)
            af_filters.append(f"afade=t=out:st={start_out:.3f}:d={fade_out_ms/1000.0:.3f}")

        # Apply volume adjustment (only if gain is needed)
        if abs(gain_db) > 0.01:  # Only apply if gain change is significant
            af_filters.append(f"volume={gain_db}dB")
        af_filters.extend(bandpass_filters)

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
            sample_fmt = {"16": "s16", "24": "s32", "32f": "fltp"}.get(bit_depth, None)
            if sample_fmt:
                cmd += ["-sample_fmt", sample_fmt]
        if format:
            cmd += ["-f", format]
        if fmt_lower == "mp3":
            cmd += ["-codec:a", "libmp3lame"]
        _apply_metadata(cmd)
        cmd += [str(output_path)]

        _run_media_tool(
            cmd,
            expected_inputs=[input_path],
            context="Sample export (normalized)",
        )
        return

    # Try stream copy first (skip for WAV to ensure precise duration, and skip if normalization needed)
    # Note: Stream copy cannot reliably write metadata for many audio formats, so skip it when metadata is present
    can_stream_copy = (
        same_format
        and not normalize
        and lufs_target is None
        and not bandpass_filters
        and not fade_in_ms
        and not fade_out_ms
        and sample_rate is None
        and bit_depth is None
        and channels is None
        and not metadata_entries  # Skip stream copy when metadata is present
    )
    if can_stream_copy:
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
        ]
        # Do not apply metadata in stream copy mode - it's unreliable and requires re-encoding
        cmd_copy.append(str(output_path))
        try:
            _run_media_tool(
                cmd_copy,
                expected_inputs=[input_path],
                context="Sample export (stream copy)",
            )
            return
        except FFmpegError:
            # Stream copy failed; fall back to re-encode path below.
            logging.debug(
                "FFmpeg stream copy failed; falling back to re-encode for %s", output_path
            )
    # Fallback: re-encode (for non-normalized exports or when stream copy fails)
    fallback_filters: list[str] = []
    if fade_in_ms and fade_in_ms > 0:
        fallback_filters.append(f"afade=t=in:st=0:d={fade_in_ms/1000.0:.3f}")
    if fade_out_ms and fade_out_ms > 0:
        start_out = max(0.0, duration - fade_out_ms / 1000.0)
        fallback_filters.append(f"afade=t=out:st={start_out:.3f}:d={fade_out_ms/1000.0:.3f}")
    if lufs_target is not None:
        fallback_filters.append(f"loudnorm=I={lufs_target}")
    elif normalize:
        # This shouldn't be reached due to early return above, but keep as fallback
        # Peak normalization to -0.1 dBFS using loudnorm with True Peak target
        fallback_filters.append("loudnorm=I=-23:TP=-0.1")
    fallback_filters.extend(bandpass_filters)
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
    if fallback_filters:
        cmd += ["-af", ",".join(fallback_filters)]
    if channels:
        cmd += ["-ac", "1" if channels == "mono" else "2"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    if bit_depth:
        sample_fmt = {"16": "s16", "24": "s32", "32f": "fltp"}.get(bit_depth, None)
        if sample_fmt:
            cmd += ["-sample_fmt", sample_fmt]
    if format:
        cmd += ["-f", format]
    if fmt_lower == "mp3":
        cmd += ["-codec:a", "libmp3lame"]
    _apply_metadata(cmd)
    cmd += [str(output_path)]
    _run_media_tool(
        cmd,
        expected_inputs=[input_path],
        context="Sample export",
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
    ensure_dir(output_path.parent)
    logging.debug(f"Generating spectrogram PNG: {input_path} -> {output_path}")
    vf = f"showspectrumpic=s={size}:legend=disabled:color=intensity:scale={scale}:gain={gain_db}"
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-lavfi", vf, str(output_path)]
    _run_media_tool(
        cmd,
        expected_inputs=[input_path],
        context="Generate spectrogram PNG",
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
    ensure_dir(output_path.parent)
    logging.debug(f"Generating spectrogram video: {input_path} -> {output_path}")
    vf = f"showspectrum=fstart={fstart}:fstop={fstop}:size={size}:color=intensity:scale=log:legend=disabled:gain={gain_db}"
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-lavfi", vf, str(output_path)]
    _run_media_tool(
        cmd,
        expected_inputs=[input_path],
        context="Generate spectrogram video",
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


def _run_media_tool(
    command: Sequence[str],
    *,
    expected_inputs: Sequence[Path] | None = None,
    context: str | None = None,
    tool_name: str = "ffmpeg",
) -> subprocess.CompletedProcess:
    """Execute an FFmpeg/ffprobe command with preflight validation and rich errors.

    Args:
        command: Command arguments to execute.
        expected_inputs: Optional iterable of paths that must exist before execution.
        context: Human-readable description of the attempted action.
        tool_name: Display name for the media tool ('ffmpeg' or 'ffprobe').

    Returns:
        CompletedProcess instance from subprocess.run.

    Raises:
        FFmpegError: If preflight validation fails or the subprocess exits non-zero.
    """

    inputs = list(expected_inputs or [])
    missing = [str(path) for path in inputs if not Path(path).exists()]
    if missing:
        hints = [
            "Confirm the source file still exists and is readable.",
            "Reconnect external drives if the audio file is stored externally.",
        ]
        message = (
            f"{tool_name} could not start because required input file(s) were missing: "
            + ", ".join(missing)
        )
        raise FFmpegError(
            command,
            message,
            context=context,
            hints=hints,
        )

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        hints = [
            "Install FFmpeg and ensure the executables are on your system PATH.",
            "Restart SpectroSampler after installing FFmpeg so the new PATH is picked up.",
        ]
        message = f"{tool_name} executable was not found. Install FFmpeg and ensure '{command[0]}' is on PATH."
        raise FFmpegError(
            command,
            message,
            context=context,
            hints=hints,
        ) from exc

    if proc.returncode != 0:
        hints = [
            "Open Help → Diagnostics to verify FFmpeg is detected.",
            "Check that the export/output folder is writable.",
            "Review the detailed FFmpeg output for specific codec or format errors.",
        ]
        message = f"{tool_name} command failed with exit code {proc.returncode}."
        raise FFmpegError(
            command,
            message,
            stderr=proc.stderr or "",
            stdout=proc.stdout or "",
            exit_code=proc.returncode,
            context=context,
            hints=hints,
        )

    return proc


def describe_ffmpeg_failure(error: FFmpegError) -> tuple[str, list[str]]:
    """Return a user-facing summary and remediation suggestions for FFmpeg failures."""

    base_summary = error.args[0] if error.args else "FFmpeg reported an error."
    if error.exit_code is not None:
        base_summary = f"{base_summary} (exit code {error.exit_code})"
    if error.context:
        base_summary = f"{error.context} failed.\n{base_summary}"

    stderr_lower = (error.stderr or "").lower()
    suggestions = list(error.hints)

    def _ensure_hint(hint: str) -> None:
        if hint not in suggestions:
            suggestions.append(hint)

    if "no such file or directory" in stderr_lower or "could not open" in stderr_lower:
        _ensure_hint("Verify the source audio still exists and that the path has not changed.")
    if "permission denied" in stderr_lower or "access is denied" in stderr_lower:
        _ensure_hint("Confirm you have write permission to the export folder and try again.")
    if "invalid argument" in stderr_lower:
        _ensure_hint("Adjust the selected sample rate, bit depth, or format to supported values.")
    if "decoder" in stderr_lower or "unable to find stream info" in stderr_lower:
        _ensure_hint(
            "Try converting the source file to WAV/FLAC using a separate tool, then re-import."
        )

    # Always provide at least one actionable next step.
    if not suggestions:
        suggestions.append("Review the detailed FFmpeg output and adjust settings before retrying.")

    return base_summary, suggestions
