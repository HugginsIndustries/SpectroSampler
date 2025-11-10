from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from spectrosampler.audio_io import (
    AudioLoadError,
    FFmpegError,
    extract_sample,
    get_audio_info,
)


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


def test_get_audio_info_missing_file(tmp_path: Path):
    missing = tmp_path / "nope.wav"
    with pytest.raises(AudioLoadError) as excinfo:
        get_audio_info(missing)
    message = excinfo.value.to_user_message()
    assert "Cause: File not found" in message
    assert "Verify the file still exists" in message


def test_extract_sample_rejects_invalid_format(tmp_path: Path):
    sr = 8000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    audio = 0.1 * np.sin(2 * np.pi * 220 * t)
    src = tmp_path / "input.wav"
    sf.write(src, audio, sr)
    out = tmp_path / "output.ogg"
    with pytest.raises(ValueError):
        extract_sample(src, out, start_sec=0.0, end_sec=0.5, format="ogg")


def test_ffmpeg_error_to_user_message_includes_command():
    error = FFmpegError(
        "failed",
        command=["ffmpeg", "-i", "input.wav", "out.wav"],
        exit_code=1,
        stderr="Unknown encoder 'fake'\n",
    )
    message = error.to_user_message("Export samples")
    assert "Export samples failed." in message
    assert "Command: ffmpeg -i input.wav out.wav" in message
    assert "Try this:" in message
