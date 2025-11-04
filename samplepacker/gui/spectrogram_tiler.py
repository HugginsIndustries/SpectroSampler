"""Spectrogram tiling system for efficient rendering of long files."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal
import soundfile as sf

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
        self._tile_cache: dict[str, SpectrogramTile] = {}

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
            logger.debug(f"Using cached tile: {cache_key}")
            return self._tile_cache[cache_key]

        logger.debug(f"Generating tile: {audio_path} [{start_time:.2f}s - {end_time:.2f}s]")

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

        # Extract time range
        start_sample = int(start_time * sr)
        end_sample = int(end_time * sr)
        start_sample = max(0, min(start_sample, len(audio_data)))
        end_sample = max(start_sample, min(end_sample, len(audio_data)))

        if start_sample >= end_sample:
            # Empty tile
            return SpectrogramTile(
                start_time=start_time,
                end_time=end_time,
                spectrogram=np.array([]).reshape(0, 0),
                frequencies=np.array([]),
                sample_rate=sr,
            )

        audio_segment = audio_data[start_sample:end_sample]

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
                logger.debug(f"Frequency filtering: original range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, requested=[{self.fmin}, {self.fmax}]")
            else:
                logger.warning(f"Frequency filtering: original frequencies array is empty, requested=[{self.fmin}, {self.fmax}]")
            
            if self.fmin is not None:
                # Use searchsorted to find the first index where frequency >= fmin
                # This correctly handles edge cases where all frequencies are below fmin
                fmin_idx = np.searchsorted(frequencies, self.fmin)
                if fmin_idx >= len(frequencies):
                    # All frequencies are below fmin
                    logger.warning(f"All frequencies ({frequencies[-1]:.1f} Hz) are below fmin ({self.fmin:.1f} Hz)")
                    fmin_idx = len(frequencies)  # This will result in empty slice, which is correct
                else:
                    logger.debug(f"fmin_idx={fmin_idx}, frequency[{fmin_idx}]={frequencies[fmin_idx]:.1f} Hz")
                    
            if self.fmax is not None:
                # Use searchsorted with side='right' to find the first index where frequency > fmax
                # This correctly handles edge cases where all frequencies are below fmax
                fmax_idx = np.searchsorted(frequencies, self.fmax, side='right')
                if fmax_idx == 0:
                    # All frequencies are above fmax
                    logger.warning(f"All frequencies ({frequencies[0]:.1f} Hz) are above fmax ({self.fmax:.1f} Hz)")
                else:
                    logger.debug(f"fmax_idx={fmax_idx}, frequency[{fmax_idx-1}]={frequencies[fmax_idx-1]:.1f} Hz")
            
            # Validate indices before slicing
            if fmin_idx >= fmax_idx:
                logger.warning(f"Invalid frequency filter range: fmin_idx={fmin_idx}, fmax_idx={fmax_idx}. This will result in empty data.")
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
                logger.debug(f"Frequency filtering applied: filtered range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, bins={len(frequencies)}")

        # Convert to dB
        spectrogram_db = 10 * np.log10(spectrogram + 1e-10)

        # Adjust times to absolute time
        times = times + start_time

        tile = SpectrogramTile(
            start_time=start_time,
            end_time=end_time,
            spectrogram=spectrogram_db,
            frequencies=frequencies,
            sample_rate=sr,
        )

        # Cache tile (limit cache size)
        if len(self._tile_cache) > 50:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self._tile_cache))
            del self._tile_cache[oldest_key]

        self._tile_cache[cache_key] = tile
        return tile

    def generate_overview(self, audio_path: Path, duration: float, sample_rate: int | None = None) -> SpectrogramTile:
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

        # Downsample for overview (every Nth sample)
        downsample_factor = max(1, int(sr / 1000))  # ~1kHz sample rate for overview
        audio_data = audio_data[::downsample_factor]
        sr_overview = sr // downsample_factor

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
                logger.debug(f"Frequency filtering (overview): original range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, requested=[{self.fmin}, {self.fmax}]")
            else:
                logger.warning(f"Frequency filtering (overview): original frequencies array is empty, requested=[{self.fmin}, {self.fmax}]")
            
            if self.fmin is not None:
                # Use searchsorted to find the first index where frequency >= fmin
                # This correctly handles edge cases where all frequencies are below fmin
                fmin_idx = np.searchsorted(frequencies, self.fmin)
                if fmin_idx >= len(frequencies):
                    # All frequencies are below fmin
                    logger.warning(f"All frequencies ({frequencies[-1]:.1f} Hz) are below fmin ({self.fmin:.1f} Hz)")
                    fmin_idx = len(frequencies)  # This will result in empty slice, which is correct
                else:
                    logger.debug(f"fmin_idx={fmin_idx}, frequency[{fmin_idx}]={frequencies[fmin_idx]:.1f} Hz")
                    
            if self.fmax is not None:
                # Use searchsorted with side='right' to find the first index where frequency > fmax
                # This correctly handles edge cases where all frequencies are below fmax
                fmax_idx = np.searchsorted(frequencies, self.fmax, side='right')
                if fmax_idx == 0:
                    # All frequencies are above fmax
                    logger.warning(f"All frequencies ({frequencies[0]:.1f} Hz) are above fmax ({self.fmax:.1f} Hz)")
                else:
                    logger.debug(f"fmax_idx={fmax_idx}, frequency[{fmax_idx-1}]={frequencies[fmax_idx-1]:.1f} Hz")
            
            # Validate indices before slicing
            if fmin_idx >= fmax_idx:
                logger.warning(f"Invalid frequency filter range: fmin_idx={fmin_idx}, fmax_idx={fmax_idx}. This will result in empty data.")
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
                logger.debug(f"Frequency filtering applied (overview): filtered range=[{frequencies[0]:.1f}, {frequencies[-1]:.1f}] Hz, bins={len(frequencies)}")

        # Convert to dB
        spectrogram_db = 10 * np.log10(spectrogram + 1e-10)

        return SpectrogramTile(
            start_time=0.0,
            end_time=duration,
            spectrogram=spectrogram_db,
            frequencies=frequencies,
            sample_rate=sr_overview,
        )

    def clear_cache(self) -> None:
        """Clear tile cache."""
        self._tile_cache.clear()
        logger.debug("Cleared spectrogram tile cache")

