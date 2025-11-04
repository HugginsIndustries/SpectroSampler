"""Tests for detector thresholding and z-score logic."""

import numpy as np
import pytest

from samplepacker.detectors.base import BaseDetector
from samplepacker.dsp import percentile_threshold, z_score_normalize


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
    from samplepacker.detectors import TransientFluxDetector, VoiceVADDetector

    vad = VoiceVADDetector()
    assert vad.name == "voicevad" or "vad" in vad.name.lower()

    flux = TransientFluxDetector()
    assert "flux" in flux.name.lower() or "transient" in flux.name.lower()
