from pathlib import Path

import numpy as np
import soundfile as sf

from spectrosampler.audio_io import FFmpegError, describe_audio_load_error, extract_sample


def test_extract_sample_duration_bounds(tmp_path: Path):
    sr = 16000
    dur = 3.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    audio = 0.1 * np.sin(2 * np.pi * 440 * t)
    src = tmp_path / "in.wav"
    sf.write(src, audio, sr)
    out = tmp_path / "out.wav"
    extract_sample(src, out, start_sec=0.5, end_sec=2.0, format="wav")
    assert out.exists()
    data, osr = sf.read(out)
    assert osr == sr
    got = len(data) / sr
    assert abs(got - 1.5) <= 0.05


def test_describe_audio_load_error_handles_missing_file():
    advice = describe_audio_load_error(
        Path("missing.wav"), FileNotFoundError(2, "No such file or directory", "missing.wav")
    )
    assert "could not be found" in advice.reason.lower()
    assert "verify" in advice.suggestion.lower()


def test_describe_audio_load_error_handles_invalid_data():
    error = FFmpegError(
        ["ffprobe"],
        "ffprobe failed: Invalid data found when processing input",
        stderr="Invalid data found when processing input",
        context="Inspect audio metadata (ffprobe)",
    )
    advice = describe_audio_load_error(Path("broken.wav"), error)
    assert "unsupported" in advice.reason.lower() or "corrupted" in advice.reason.lower()
    assert "convert" in advice.suggestion.lower()
