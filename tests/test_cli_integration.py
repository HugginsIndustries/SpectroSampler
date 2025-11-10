"""Integration tests for CLI (generate synthetic audio, run CLI, verify outputs)."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from spectrosampler.export import build_sample_filename
from spectrosampler.utils import sanitize_filename


@pytest.fixture
def test_audio_file(tmp_path: Path) -> Path:
    """Generate synthetic test audio file (10-15 seconds).

    Creates: pink-noise "rain" bed + a few "speech-like" AM tones (200-3kHz) + sharp transients.
    """
    sample_rate = 16000
    duration = 12.0  # seconds
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Pink noise bed (rain)
    pink_noise = np.random.randn(len(t))
    # Simple pink noise approximation: use cumulative sum as approximation
    pink_noise = np.cumsum(pink_noise) * 0.01
    pink_noise = pink_noise / np.std(pink_noise) * 0.3  # Normalize

    # Speech-like AM tones (200-3kHz range)
    # Tone at 1000 Hz, amplitude modulated
    am_freq = 5.0  # 5 Hz modulation
    tone_freq = 1000.0
    tone = np.sin(2 * np.pi * tone_freq * t)
    modulation = (np.sin(2 * np.pi * am_freq * t) + 1) / 2
    speech_segment = tone * modulation * 0.5

    # Activate speech in segments: 1-2s, 5-6s, 9-10s
    mask = np.zeros_like(t)
    mask[(t >= 1.0) & (t < 2.0)] = 1.0
    mask[(t >= 5.0) & (t < 6.0)] = 1.0
    mask[(t >= 9.0) & (t < 10.0)] = 1.0
    speech_segment = speech_segment * mask

    # Sharp transients (clicks) at 3s, 7s
    transients = np.zeros_like(t)
    transient_times = [3.0, 7.0]
    for tt in transient_times:
        idx = int(tt * sample_rate)
        # Sharp click: short burst of high frequency
        click_len = int(0.01 * sample_rate)  # 10ms
        click = np.sin(2 * np.pi * 5000 * np.linspace(0, 0.01, click_len)) * np.exp(
            -np.linspace(0, 10, click_len)
        )
        if idx + click_len < len(transients):
            transients[idx : idx + click_len] = click * 0.8

    # Combine all
    audio = pink_noise + speech_segment + transients

    # Normalize to prevent clipping
    audio = audio / np.max(np.abs(audio)) * 0.8

    output_file = tmp_path / "test_audio.wav"
    sf.write(output_file, audio, sample_rate)

    return output_file


@pytest.fixture
def test_output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


def test_build_sample_filename():
    """Test sample filename generation."""
    from spectrosampler.detectors.base import Segment

    seg = Segment(start=278.7, end=313.6, detector="transient_flux", score=0.85)
    filename = build_sample_filename("test_recording", seg, index=0, total=10)

    assert "test_recording" in filename
    assert "sample_000" in filename or "sample_0" in filename
    assert "278.7s-313.6s" in filename or "278.7" in filename
    assert "transient" in filename.lower() or "flux" in filename.lower()


def test_filename_detector_collapse():
    from spectrosampler.detectors.base import Segment

    seg = Segment(
        start=1.0, end=2.0, detector="transient_flux+transient_flux+transient_flux", score=0.9
    )
    name = build_sample_filename("x", seg, 0, 1)
    assert "detector-transient_flux" in name


def test_filename_primary_detector():
    from spectrosampler.detectors.base import Segment

    seg = Segment(
        start=1.0,
        end=2.0,
        detector="nonsilence_energy+transient_flux",
        score=0.9,
        attrs={"primary_detector": "transient_flux"},
    )
    name = build_sample_filename("x", seg, 0, 1)
    assert "detector-transient_flux" in name


def test_sanitize_filename():
    """Test filename sanitization."""
    # Test invalid characters
    name = "test<>file|name?.wav"
    sanitized = sanitize_filename(name)
    assert "<" not in sanitized
    assert ">" not in sanitized
    assert "|" not in sanitized
    assert "?" not in sanitized

    # Test length truncation
    long_name = "a" * 300
    sanitized = sanitize_filename(long_name)
    assert len(sanitized) <= 200

    # Test extension preservation
    name_with_ext = "test" * 50 + ".wav"
    sanitized = sanitize_filename(name_with_ext, max_length=50)
    assert sanitized.endswith(".wav")

    # Test control characters replaced
    control_name = "bad\x00name.wav"
    sanitized_control = sanitize_filename(control_name)
    assert "\x00" not in sanitized_control
    assert sanitized_control.startswith("bad")

    # Test Windows reserved device names avoided
    reserved_name = sanitize_filename("CON.txt")
    assert reserved_name.endswith(".txt")
    assert reserved_name.split(".", 1)[0].upper() != "CON"

    # Test Unicode normalization combines decomposed characters
    unicode_name = "Cafe\u0301"
    sanitized_unicode = sanitize_filename(unicode_name)
    assert sanitized_unicode == "Café"


def test_cli_integration(test_audio_file: Path, test_output_dir: Path):
    """Integration test placeholder to ensure test audio generation and output structure exists."""
    assert test_audio_file.exists()
    assert test_audio_file.stat().st_size > 0

    # Placeholder: verify structure can be created
    samples_dir = test_output_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    assert samples_dir.exists()


def test_timestamps_csv_format(test_output_dir: Path):
    """Test that timestamps CSV has correct format."""
    from spectrosampler.detectors.base import Segment
    from spectrosampler.export import export_timestamps_csv

    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=0.8),
        Segment(start=5.0, end=6.5, detector="test", score=0.9),
    ]

    csv_path = test_output_dir / "timestamps.csv"
    export_timestamps_csv(segments, csv_path)

    assert csv_path.exists()

    # Verify CSV format
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 2
        assert "id" in rows[0]
        assert "start_sec" in rows[0]
        assert "end_sec" in rows[0]
        assert "duration_sec" in rows[0]
        assert "detector" in rows[0]
        assert "score" in rows[0]


def test_marked_spectrogram_overlay_smoke(tmp_path: Path, test_audio_file: Path):
    import matplotlib.image as mpimg

    from spectrosampler.audio_io import generate_spectrogram_png
    from spectrosampler.detectors.base import Segment
    from spectrosampler.report import create_annotated_spectrogram

    # make clean png
    clean = tmp_path / "clean.png"
    generate_spectrogram_png(test_audio_file, clean, size="1024x256")
    # overlay with one segment
    marked = tmp_path / "marked.png"
    segs = [Segment(start=1.0, end=2.0, detector="transient_flux", score=1.0)]
    create_annotated_spectrogram(test_audio_file, marked, segs, background_png=clean, duration=12.0)
    assert clean.exists() and marked.exists()
    a = mpimg.imread(str(clean))
    b = mpimg.imread(str(marked))
    assert abs(float(b.var()) - float(a.var())) > 0.0


def test_summary_json_format(test_output_dir: Path):
    """Test that summary JSON has correct structure."""
    from spectrosampler.detectors.base import Segment
    from spectrosampler.report import save_summary_json

    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=0.8),
        Segment(start=5.0, end=6.5, detector="test", score=0.9),
    ]

    json_path = test_output_dir / "summary.json"
    save_summary_json(
        json_path,
        audio_info={"duration": 10.0, "sample_rate": 16000, "channels": 1},
        settings={"mode": "auto"},
        segments=segments,
        detector_stats={"test": {"count": 2}},
        versions={"spectrosampler": "0.1.0"},
    )

    assert json_path.exists()

    # Verify JSON structure
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
        assert "segments" in data
        assert "segments_summary" in data
        assert "versions" in data
        assert len(data["segments"]) == 2
