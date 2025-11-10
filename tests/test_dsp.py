import numpy as np
import pytest

from spectrosampler import dsp


def _component_magnitude(samples: np.ndarray, target_freq: float, sample_rate: int) -> float:
    """Return magnitude of the closest FFT bin to the requested frequency."""
    spectrum = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    index = int(np.argmin(np.abs(freqs - target_freq)))
    return float(np.abs(spectrum[index]))


@pytest.mark.parametrize(
    ("low_freq", "high_freq", "pass_freq", "reject_freq"),
    [
        (0.0, 400.0, 100.0, 1000.0),  # Lowpass configuration
        (600.0, 4000.0, 1200.0, 150.0),  # Highpass configuration
        (400.0, 600.0, 500.0, 120.0),  # Bandpass configuration
    ],
)
def test_bandpass_filter_selectively_attenuates_out_of_band_components(
    low_freq: float, high_freq: float, pass_freq: float, reject_freq: float
) -> None:
    sample_rate = 8000
    duration = 1.5  # seconds
    time = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)

    wanted = np.sin(2 * np.pi * pass_freq * time)
    unwanted = 0.5 * np.sin(2 * np.pi * reject_freq * time)
    mixture = wanted + unwanted

    filtered = dsp.bandpass_filter(mixture, sample_rate, low_freq, high_freq)

    pass_mag = _component_magnitude(filtered, pass_freq, sample_rate)
    reject_mag = _component_magnitude(filtered, reject_freq, sample_rate)

    # Ensure the filter keeps the in-band component dominant by a meaningful margin.
    assert pass_mag > reject_mag * 5


def test_bandpass_filter_preserves_shape_and_float_dtype() -> None:
    sample_rate = 48000
    audio = np.random.randn(sample_rate).astype(np.float32)

    filtered = dsp.bandpass_filter(audio, sample_rate, 80.0, 5000.0)

    assert filtered.shape == audio.shape
    assert filtered.dtype == audio.dtype


def test_bandpass_filter_rejects_invalid_cutoffs() -> None:
    with pytest.raises(ValueError):
        dsp.bandpass_filter(np.ones(1024), 8000, 2000.0, 1000.0)
