"""Spectrogram tiling system for efficient rendering of long files."""

import logging
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import soundfile as sf
from matplotlib.cm import get_cmap
from scipy import signal

logger = logging.getLogger(__name__)


class SpectrogramTile:
    """Represents a single spectrogram tile."""

    def __init__(
        self,
        start_time: float,
        end_time: float,
        spectrogram: np.ndarray,
        frequencies: np.ndarray,
        sample_rate: int,
        rgba: np.ndarray | None = None,
    ):
        """Initialize spectrogram tile.

        Args:
            start_time: Start time in seconds.
            end_time: End time in seconds.
            spectrogram: Spectrogram data (frequencies x time).
            frequencies: Frequency array in Hz.
            sample_rate: Audio sample rate.
        """
        self.start_time = start_time
        self.end_time = end_time
        self.spectrogram = spectrogram
        self.frequencies = frequencies
        self.sample_rate = sample_rate
        self.rgba = rgba  # Optional precolored image (freq x time x 4, uint8)

    @property
    def duration(self) -> float:
        """Get tile duration in seconds."""
        return self.end_time - self.start_time


class SpectrogramTiler:
    """Manages spectrogram tiling for long files."""

    def __init__(
        self,
        tile_duration_sec: float = 300.0,  # 5 minutes per tile
        nfft: int = 2048,
        hop_length: int | None = None,
        fmin: float | None = None,
        fmax: float | None = None,
    ):
        """Initialize spectrogram tiler.

        Args:
            tile_duration_sec: Duration of each tile in seconds.
            nfft: FFT size for spectrogram.
            hop_length: Hop length for STFT. If None, uses nfft // 4.
            fmin: Minimum frequency in Hz. If None, uses 0.
            fmax: Maximum frequency in Hz. If None, uses sample_rate / 2.
        """
        self.tile_duration_sec = tile_duration_sec
        self.nfft = nfft
        self.hop_length = hop_length or (nfft // 4)
        self.fmin = fmin
        self.fmax = fmax
        # Simple LRU cache with bounded size
        self._tile_cache: OrderedDict[str, SpectrogramTile] = OrderedDict()
        self._max_cache_items: int = 64
        # Background executor for async tile generation
        try:
            import os

            max_workers = max(2, min(8, (os.cpu_count() or 4) // 2))
        except Exception:
            max_workers = 4
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SpecTile")
        self._cmap = get_cmap("viridis")

    def _get_cache_key(self, audio_path: Path, start_time: float, end_time: float) -> str:
        """Generate cache key for tile.

        Args:
            audio_path: Path to audio file.
            start_time: Start time in seconds.
            end_time: End time in seconds.

        Returns:
            Cache key string.
        """
        return f"{audio_path}:{start_time:.3f}:{end_time:.3f}:{self.nfft}:{self.hop_length}:{self.fmin}:{self.fmax}"

    def generate_tile(
        self,
        audio_path: Path,
        start_time: float,
        end_time: float,
        sample_rate: int | None = None,
    ) -> SpectrogramTile:
        """Generate spectrogram tile for time range.

        Args:
            audio_path: Path to audio file.
            start_time: Start time in seconds.
            end_time: End time in seconds.
            sample_rate: Target sample rate. If None, uses file's sample rate.

        Returns:
            SpectrogramTile object.
        """
        cache_key = self._get_cache_key(audio_path, start_time, end_time)
        if cache_key in self._tile_cache:
            # Move to end to mark as recently used
            tile = self._tile_cache.pop(cache_key)
            self._tile_cache[cache_key] = tile
            logger.debug(f"Using cached tile: {cache_key}")
            return tile

        logger.debug(f"Generating tile: {audio_path} [{start_time:.2f}s - {end_time:.2f}s]")

        # Probe file sample rate without loading full data
        file_info = sf.info(audio_path)
        sr = int(file_info.samplerate)

        # Resample if needed
        if sample_rate and sample_rate != sr:
            # We'll resample after partial read if required
            target_sr = int(sample_rate)
        else:
            target_sr = sr

        # Extract time range
        start_sample = int(max(0.0, start_time) * sr)
        end_sample = int(max(start_time, end_time) * sr)
        # clamp to file frames
        total_frames = int(file_info.frames)
        start_sample = max(0, min(start_sample, total_frames))
        end_sample = max(start_sample, min(end_sample, total_frames))

        if start_sample >= end_sample:
            # Empty tile
            return SpectrogramTile(
                start_time=start_time,
                end_time=end_time,
                spectrogram=np.array([]).reshape(0, 0),
                frequencies=np.array([]),
                sample_rate=sr,
            )

        # Read only the needed frames
        audio_segment, _ = sf.read(audio_path, start=start_sample, stop=end_sample, always_2d=False)
        if getattr(audio_segment, "ndim", 1) > 1:
            audio_segment = np.mean(audio_segment, axis=1)
        # Optional resample of the visible window only
        if target_sr != sr and len(audio_segment) > 0:
            from scipy.signal import resample

            num_samples = int(len(audio_segment) * target_sr / sr)
            audio_segment = resample(audio_segment, num_samples)
            sr = target_sr

        # Compute spectrogram
        frequencies, times, spectrogram = signal.spectrogram(
            audio_segment,
            fs=sr,
            nperseg=self.nfft,
            noverlap=self.nfft - self.hop_length,
            nfft=self.nfft,
        )

        # Apply frequency filtering
        if self.fmin is not None or self.fmax is not None:
            fmin_idx = 0
            fmax_idx = len(frequencies)

            if len(frequencies) > 0:
                logger.debug(
                    f"Frequency filtering: original range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, requested=[{self.fmin}, {self.fmax}]"
                )
            else:
                logger.warning(
                    f"Frequency filtering: original frequencies array is empty, requested=[{self.fmin}, {self.fmax}]"
                )

            if self.fmin is not None:
                # Use searchsorted to find the first index where frequency >= fmin
                # This correctly handles edge cases where all frequencies are below fmin
                fmin_idx = np.searchsorted(frequencies, self.fmin)
                if fmin_idx >= len(frequencies):
                    # All frequencies are below fmin
                    logger.warning(
                        f"All frequencies ({frequencies[-1]:.1f} Hz) are below fmin ({self.fmin:.1f} Hz)"
                    )
                    fmin_idx = len(frequencies)  # This will result in empty slice, which is correct
                else:
                    logger.debug(
                        f"fmin_idx={fmin_idx}, frequency[{fmin_idx}]={frequencies[fmin_idx]:.1f} Hz"
                    )

            if self.fmax is not None:
                # Use searchsorted with side='right' to find the first index where frequency > fmax
                # This correctly handles edge cases where all frequencies are below fmax
                fmax_idx = np.searchsorted(frequencies, self.fmax, side="right")
                if fmax_idx == 0:
                    # All frequencies are above fmax
                    logger.warning(
                        f"All frequencies ({frequencies[0]:.1f} Hz) are above fmax ({self.fmax:.1f} Hz)"
                    )
                else:
                    logger.debug(
                        f"fmax_idx={fmax_idx}, frequency[{fmax_idx-1}]={frequencies[fmax_idx-1]:.1f} Hz"
                    )

            # Validate indices before slicing
            if fmin_idx >= fmax_idx:
                logger.warning(
                    f"Invalid frequency filter range: fmin_idx={fmin_idx}, fmax_idx={fmax_idx}. This will result in empty data."
                )
                # Return empty arrays when filter results in no valid range
                frequencies = np.array([])
                # Preserve time dimension if spectrogram has data, otherwise use empty shape
                if spectrogram.size > 0 and spectrogram.shape[1] > 0:
                    spectrogram = np.array([]).reshape(0, spectrogram.shape[1])
                else:
                    spectrogram = np.array([]).reshape(0, 0)
            else:
                frequencies = frequencies[fmin_idx:fmax_idx]
                spectrogram = spectrogram[fmin_idx:fmax_idx, :]
                logger.debug(
                    f"Frequency filtering applied: filtered range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, bins={len(frequencies)}"
                )

        # Convert to dB
        spectrogram_db = 10 * np.log10(spectrogram + 1e-10)

        # Precompute RGBA once for fast drawing (freq x time x 4)
        rgba = self._to_rgba(spectrogram_db)

        # Adjust times to absolute time
        times = times + start_time

        tile = SpectrogramTile(
            start_time=start_time,
            end_time=end_time,
            spectrogram=spectrogram_db,
            frequencies=frequencies,
            sample_rate=sr,
            rgba=rgba,
        )

        # Cache tile with LRU eviction
        self._tile_cache[cache_key] = tile
        if len(self._tile_cache) > self._max_cache_items:
            try:
                self._tile_cache.popitem(last=False)
            except Exception:
                pass
        return tile

    def generate_overview(
        self, audio_path: Path, duration: float, sample_rate: int | None = None
    ) -> SpectrogramTile:
        """Generate low-resolution overview spectrogram for entire file.

        Args:
            audio_path: Path to audio file.
            duration: Total duration in seconds.
            sample_rate: Target sample rate. If None, uses file's sample rate.

        Returns:
            SpectrogramTile object with overview.
        """
        # Use larger hop length for overview
        overview_nfft = self.nfft * 4
        overview_hop = overview_nfft // 2

        logger.debug(f"Generating overview: {audio_path}")

        # Load audio file
        audio_data, sr = sf.read(audio_path)
        if audio_data.ndim > 1:
            # Convert to mono
            audio_data = np.mean(audio_data, axis=1)

        # Resample if needed
        if sample_rate and sample_rate != sr:
            from scipy.signal import resample

            num_samples = int(len(audio_data) * sample_rate / sr)
            audio_data = resample(audio_data, num_samples)
            sr = sample_rate

        # Keep full bandwidth for overview to fill vertical axis; use coarse hops for speed
        sr_overview = sr

        # Compute spectrogram
        frequencies, times, spectrogram = signal.spectrogram(
            audio_data,
            fs=sr_overview,
            nperseg=overview_nfft,
            noverlap=overview_nfft - overview_hop,
            nfft=overview_nfft,
        )

        # Apply frequency filtering
        if self.fmin is not None or self.fmax is not None:
            fmin_idx = 0
            fmax_idx = len(frequencies)

            if len(frequencies) > 0:
                logger.debug(
                    f"Frequency filtering (overview): original range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, requested=[{self.fmin}, {self.fmax}]"
                )
            else:
                logger.warning(
                    f"Frequency filtering (overview): original frequencies array is empty, requested=[{self.fmin}, {self.fmax}]"
                )

            if self.fmin is not None:
                # Use searchsorted to find the first index where frequency >= fmin
                # This correctly handles edge cases where all frequencies are below fmin
                fmin_idx = np.searchsorted(frequencies, self.fmin)
                if fmin_idx >= len(frequencies):
                    # All frequencies are below fmin
                    logger.warning(
                        f"All frequencies ({frequencies[-1]:.1f} Hz) are below fmin ({self.fmin:.1f} Hz)"
                    )
                    fmin_idx = len(frequencies)  # This will result in empty slice, which is correct
                else:
                    logger.debug(
                        f"fmin_idx={fmin_idx}, frequency[{fmin_idx}]={frequencies[fmin_idx]:.1f} Hz"
                    )

            if self.fmax is not None:
                # Use searchsorted with side='right' to find the first index where frequency > fmax
                # This correctly handles edge cases where all frequencies are below fmax
                fmax_idx = np.searchsorted(frequencies, self.fmax, side="right")
                if fmax_idx == 0:
                    # All frequencies are above fmax
                    logger.warning(
                        f"All frequencies ({frequencies[0]:.1f} Hz) are above fmax ({self.fmax:.1f} Hz)"
                    )
                else:
                    logger.debug(
                        f"fmax_idx={fmax_idx}, frequency[{fmax_idx-1}]={frequencies[fmax_idx-1]:.1f} Hz"
                    )

            # Validate indices before slicing
            if fmin_idx >= fmax_idx:
                logger.warning(
                    f"Invalid frequency filter range: fmin_idx={fmin_idx}, fmax_idx={fmax_idx}. This will result in empty data."
                )
                # Return empty arrays when filter results in no valid range
                frequencies = np.array([])
                # Preserve time dimension if spectrogram has data, otherwise use empty shape
                if spectrogram.size > 0 and spectrogram.shape[1] > 0:
                    spectrogram = np.array([]).reshape(0, spectrogram.shape[1])
                else:
                    spectrogram = np.array([]).reshape(0, 0)
            else:
                frequencies = frequencies[fmin_idx:fmax_idx]
                spectrogram = spectrogram[fmin_idx:fmax_idx, :]
                logger.debug(
                    f"Frequency filtering applied (overview): filtered range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, bins={len(frequencies)}"
                )

        # Convert to dB and precompute RGBA
        spectrogram_db = 10 * np.log10(spectrogram + 1e-10)
        rgba = self._to_rgba(spectrogram_db)

        return SpectrogramTile(
            start_time=0.0,
            end_time=duration,
            spectrogram=spectrogram_db,
            frequencies=frequencies,
            sample_rate=sr_overview,
            rgba=rgba,
        )

    def clear_cache(self) -> None:
        """Clear tile cache."""
        self._tile_cache.clear()
        logger.debug("Cleared spectrogram tile cache")

    # --- Helpers ---
    def _to_rgba(self, spec_db: np.ndarray) -> np.ndarray:
        """Convert dB spectrogram to RGBA uint8 array (freq x time x 4).

        Uses robust normalization (5th-95th percentile) to improve contrast.
        """
        if spec_db.size == 0:
            return np.zeros((0, 0, 4), dtype=np.uint8)
        try:
            lo = float(np.nanpercentile(spec_db, 5))
            hi = float(np.nanpercentile(spec_db, 95))
            if hi <= lo:
                lo = float(np.nanmin(spec_db))
                hi = float(np.nanmax(spec_db) + 1e-6)
            norm = (spec_db - lo) / (hi - lo)
            norm = np.clip(norm, 0.0, 1.0)
            # cmap expects (H, W) with values [0,1] and returns RGBA in [0,1]
            rgba = self._cmap(norm, bytes=True)  # returns uint8 (H, W, 4)
            return cast(npt.NDArray[np.uint8], rgba.astype(np.uint8))
        except Exception:
            # Fallback to zeros on any failure
            return np.zeros((*spec_db.shape, 4), dtype=np.uint8)

    # --- Async API ---
    def request_tile(
        self,
        audio_path: Path,
        start_time: float,
        end_time: float,
        sample_rate: int | None = None,
        callback: Callable[[SpectrogramTile], None] | None = None,
    ) -> Future:
        """Submit tile generation to background executor and return a Future.

        If callback is provided, it will be called with the resulting tile in the worker's completion context.
        """

        def task() -> SpectrogramTile:
            return self.generate_tile(audio_path, start_time, end_time, sample_rate=sample_rate)

        fut = self._executor.submit(task)
        if callback is not None:

            def _done(f: Future) -> None:
                try:
                    tile = f.result()
                    callback(tile)
                except Exception:
                    pass

            fut.add_done_callback(_done)
        return fut

    def prefetch_neighbors(
        self,
        audio_path: Path,
        center_start: float,
        center_end: float,
        sample_rate: int | None = None,
    ) -> None:
        """Prefetch tiles adjacent to the current view to improve perceived responsiveness."""
        dur = max(0.0, center_end - center_start)
        if dur <= 0:
            return
        left_start = max(0.0, center_start - dur)
        left_end = center_start
        right_start = center_end
        right_end = center_end + dur

        # Fire-and-forget; callbacks not necessary
        self.request_tile(audio_path, left_start, left_end, sample_rate=sample_rate)
        self.request_tile(audio_path, right_start, right_end, sample_rate=sample_rate)
