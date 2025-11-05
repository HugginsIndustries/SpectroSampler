"""DSP utilities: envelopes, z-scores, windows, spectral features."""

from typing import cast

import numpy as np
import numpy.typing as npt


def rms_envelope(audio: np.ndarray, window_size: int, hop_size: int) -> np.ndarray:
    """Compute RMS envelope of audio signal.

    Args:
        audio: Input audio signal (1D array).
        window_size: Size of analysis window in samples.
        hop_size: Hop size between windows in samples.

    Returns:
        RMS envelope values, one per window.
    """
    if window_size <= 0 or hop_size <= 0 or len(audio) < window_size:
        return np.array([])
    n_frames = 1 + (len(audio) - window_size) // hop_size
    env = np.empty(n_frames, dtype=float)
    for i in range(n_frames):
        start = i * hop_size
        end = start + window_size
        window = audio[start:end]
        env[i] = np.sqrt(np.mean(window * window) + 1e-12)
    return env


def z_score_normalize(data: np.ndarray) -> np.ndarray:
    """Compute z-scores: (x - mean) / std.

    Args:
        data: Input array.

    Returns:
        Z-scored array (mean=0, std=1).
    """
    mean = np.mean(data)
    std = np.std(data)
    if std == 0:
        return cast(npt.NDArray[np.float64], np.zeros_like(data))
    return cast(npt.NDArray[np.float64], (data - mean) / std)


def percentile_threshold(data: np.ndarray, percentile: float) -> float:
    """Compute threshold at a given percentile.

    Args:
        data: Input array.
        percentile: Percentile (0-100).

    Returns:
        Value at the specified percentile.
    """
    return float(np.percentile(data, percentile))


def apply_hysteresis(
    values: np.ndarray, rise_threshold: float, fall_threshold: float
) -> np.ndarray:
    """Apply hysteresis to a binary signal.

    Args:
        binary: Binary signal (0/1 or bool).
        rise_threshold: Threshold to switch from 0 to 1.
        fall_threshold: Threshold to switch from 1 to 0 (typically lower).

    Returns:
        Hysteresis-filtered binary signal.
    """
    output = np.zeros_like(values, dtype=bool)
    state = False
    for i, val in enumerate(values):
        if not state:
            if val >= rise_threshold:
                state = True
        else:
            if val < fall_threshold:
                state = False
        output[i] = state
    return output


def spectral_flux(spectrogram: np.ndarray, hop_size: int = 1) -> np.ndarray:
    """Compute spectral flux between consecutive frames.

    Args:
        spectrogram: Magnitude spectrogram (freq_bins, time_frames).
        hop_size: Step size between frames for comparison.

    Returns:
        Spectral flux per frame.
    """
    if spectrogram.shape[1] < 2:
        return np.zeros(spectrogram.shape[1])
    spec = spectrogram / (np.sum(spectrogram, axis=0, keepdims=True) + 1e-9)
    diff = np.diff(spec, n=1, axis=1)
    diff = np.maximum(diff, 0)
    flux = np.sum(diff, axis=0)
    return np.concatenate([[0.0], flux])


def spectral_centroid(frequencies: np.ndarray, magnitude_spectrum: np.ndarray) -> float:
    """Compute spectral centroid.

    Args:
        frequencies: Frequency bin centers (Hz).
        magnitude_spectrum: Magnitude spectrum for one frame.

    Returns:
        Centroid frequency in Hz.
    """
    if np.sum(magnitude_spectrum) == 0:
        return 0.0
    return float(np.sum(frequencies * magnitude_spectrum) / np.sum(magnitude_spectrum))


def spectral_rolloff(
    frequencies: np.ndarray, magnitude_spectrum: np.ndarray, rolloff_percent: float = 0.85
) -> float:
    """Compute spectral rolloff frequency.

    Args:
        frequencies: Frequency bin centers (Hz).
        magnitude_spectrum: Magnitude spectrum for one frame.
        rolloff_percent: Percentile (0-1) for rolloff calculation.

    Returns:
        Rolloff frequency in Hz.
    """
    cumsum = np.cumsum(magnitude_spectrum)
    total = cumsum[-1]
    if total == 0:
        return 0.0
    threshold = total * rolloff_percent
    idx = np.searchsorted(cumsum, threshold)
    if idx >= len(frequencies):
        return float(frequencies[-1])
    return float(frequencies[idx])


def spectral_flatness(magnitude_spectrum: np.ndarray, eps: float = 1e-10) -> float:
    """Compute spectral flatness (ratio of geometric to arithmetic mean).

    Args:
        magnitude_spectrum: Magnitude spectrum for one frame.
        eps: Small value to avoid log(0).

    Returns:
        Flatness value (0-1, higher = more flat/noisy).
    """
    # TODO: Compute geometric mean / arithmetic mean
    magnitude_spectrum = magnitude_spectrum + eps
    geometric_mean = np.exp(np.mean(np.log(magnitude_spectrum)))
    arithmetic_mean = np.mean(magnitude_spectrum)
    if arithmetic_mean == 0:
        return 0.0
    return float(geometric_mean / arithmetic_mean)


def hanning_window(size: int) -> np.ndarray:
    """Generate a Hanning window.

    Args:
        size: Window size in samples.

    Returns:
        Hanning window array.
    """
    return np.hanning(size)


def bandpass_filter(
    audio: np.ndarray, sample_rate: int, low_freq: float, high_freq: float
) -> np.ndarray:
    """Apply a simple bandpass filter (placeholder for FFmpeg implementation).

    Note: This is a placeholder. Actual filtering should be done via FFmpeg.

    Args:
        audio: Input audio signal.
        sample_rate: Sample rate in Hz.
        low_freq: Low cutoff frequency in Hz.
        high_freq: High cutoff frequency in Hz.

    Returns:
        Filtered audio (placeholder returns input).
    """
    # TODO: Implement or delegate to FFmpeg highpass/lowpass
    # For now, this is a placeholder as filtering is done via FFmpeg
    return audio
