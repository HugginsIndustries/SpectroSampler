"""Tests for detector thresholding and z-score logic."""

import numpy as np
import pytest

from spectrosampler.detectors.base import BaseDetector
from spectrosampler.dsp import percentile_threshold, z_score_normalize


def test_z_score_normalize():
    """Test z-score normalization."""
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z_scored = z_score_normalize(data)

    assert np.isclose(np.mean(z_scored), 0.0, atol=1e-10)
    assert np.isclose(np.std(z_scored), 1.0, atol=1e-10)

    # Constant array should return zeros
    constant = np.array([5.0, 5.0, 5.0])
    z_const = z_score_normalize(constant)
    assert np.allclose(z_const, 0.0)


def test_percentile_threshold():
    """Test percentile threshold calculation."""
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])

    # 50th percentile (median) should be 5.5
    threshold_50 = percentile_threshold(data, 50.0)
    assert np.isclose(threshold_50, 5.5)

    # 85th percentile
    threshold_85 = percentile_threshold(data, 85.0)
    assert threshold_85 >= 8.0

    # 0th percentile should be minimum
    threshold_0 = percentile_threshold(data, 0.0)
    assert np.isclose(threshold_0, 1.0)

    # 100th percentile should be maximum
    threshold_100 = percentile_threshold(data, 100.0)
    assert np.isclose(threshold_100, 10.0)


def test_base_detector_init():
    """Test base detector initialization."""
    detector = BaseDetector(sample_rate=16000)

    assert detector.sample_rate == 16000
    assert detector.name == "base"

    # Test that detect() raises NotImplementedError
    with pytest.raises(NotImplementedError):
        detector.detect(np.array([1.0, 2.0, 3.0]))


def test_detector_name_extraction():
    """Test that detector names are extracted correctly."""
    from spectrosampler.detectors import TransientFluxDetector, VoiceVADDetector

    vad = VoiceVADDetector()
    assert vad.name == "voicevad" or "vad" in vad.name.lower()

    flux = TransientFluxDetector()
    assert "flux" in flux.name.lower() or "transient" in flux.name.lower()


def test_voice_vad_prefilter_invokes_bandpass(monkeypatch: pytest.MonkeyPatch) -> None:
    import spectrosampler.detectors.vad as vad_module

    call_args: list[tuple[float, float]] = []

    def fake_bandpass(
        audio: np.ndarray,
        sample_rate: int,
        low_freq: float,
        high_freq: float,
        *,
        order: int = 4,
    ) -> np.ndarray:
        call_args.append((low_freq, high_freq))
        return np.ones_like(audio)

    monkeypatch.setattr(vad_module, "bandpass_filter", fake_bandpass)

    detector = vad_module.VoiceVADDetector(low_freq=120.0, high_freq=3200.0)
    audio = np.random.randn(4096).astype(np.float32)
    result = detector._prefilter_audio(audio)

    assert call_args == [(120.0, 3200.0)]
    assert result.shape == audio.shape
    assert result.dtype == audio.dtype


def test_voice_vad_prefilter_skips_when_full_band(monkeypatch: pytest.MonkeyPatch) -> None:
    import spectrosampler.detectors.vad as vad_module

    call_args: list[tuple[float, float]] = []

    def fake_bandpass(
        audio: np.ndarray,
        sample_rate: int,
        low_freq: float,
        high_freq: float,
        *,
        order: int = 4,
    ) -> np.ndarray:
        call_args.append((low_freq, high_freq))
        return audio

    monkeypatch.setattr(vad_module, "bandpass_filter", fake_bandpass)

    detector = vad_module.VoiceVADDetector(low_freq=None, high_freq=None)
    audio = np.random.randn(4096).astype(np.float32)
    result = detector._prefilter_audio(audio)

    assert call_args == []
    assert np.shares_memory(result, audio)


def test_voice_vad_detect_filters_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    import spectrosampler.detectors.vad as vad_module

    call_args: list[tuple[int, float, float]] = []

    def fake_bandpass(
        audio: np.ndarray,
        sample_rate: int,
        low_freq: float,
        high_freq: float,
        *,
        order: int = 4,
    ) -> np.ndarray:
        call_args.append((sample_rate, low_freq, high_freq))
        return audio

    class DummyVadModule:
        class Vad:
            def __init__(self, aggressiveness: int) -> None:  # noqa: D401 - minimal stub
                self.aggressiveness = aggressiveness

            def is_speech(self, frame: bytes, sample_rate: int) -> bool:
                return False

    monkeypatch.setattr(vad_module, "bandpass_filter", fake_bandpass)
    monkeypatch.setattr(vad_module, "webrtcvad", DummyVadModule)

    detector = vad_module.VoiceVADDetector(
        sample_rate=16000, aggressiveness=2, low_freq=100.0, high_freq=2500.0
    )
    audio = np.random.randn(detector.frame_size * 10).astype(np.float32)
    segments = detector.detect(audio)

    assert segments == []
    assert call_args == [(16000, 100.0, 2500.0)]
