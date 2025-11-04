import numpy as np
import soundfile as sf
from pathlib import Path

from samplepacker.audio_io import extract_sample


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


