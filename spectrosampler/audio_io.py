"""Audio I/O and FFmpeg operations: denoising, cutting, analysis resampling."""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spectrosampler.utils import compute_file_hash, ensure_dir


class FFmpegError(Exception):
    """Exception raised when FFmpeg operations fail."""

    pass


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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {proc.stderr}")
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr)


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
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr)


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
        FFmpegError: If FFmpeg operation fails.
    """
    ensure_dir(output_path.parent)
    logging.debug(f"Extracting sample: {start_sec:.3f}s-{end_sec:.3f}s -> {output_path}")
    duration = max(0.0, end_sec - start_sec)

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

        proc = subprocess.run(volumedetect_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise FFmpegError(proc.stderr)

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
        cmd += [str(output_path)]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise FFmpegError(proc.stderr)
        return

    # Try stream copy first (skip for WAV to ensure precise duration, and skip if normalization needed)
    if (
        (format or "").lower() != "wav"
        and not str(output_path).lower().endswith(".wav")
        and not normalize
    ):
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
        proc = subprocess.run(cmd_copy, capture_output=True, text=True)
        if proc.returncode == 0:
            return
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
    cmd += [str(output_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr)


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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr)


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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr)


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
