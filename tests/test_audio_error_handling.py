"""Regression tests around FFmpeg failure reporting and user-facing advice."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import spectrosampler.audio_io as audio_io
import spectrosampler.export as export_mod
from spectrosampler.detectors.base import Segment


def test_export_sample_surfaces_ffmpeg_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure FFmpeg subprocess failures bubble up as FFmpegError."""

    src = tmp_path / "source.wav"
    src.write_text("placeholder audio file", encoding="utf-8")
    out = tmp_path / "failed.wav"

    calls: list[list[str]] = []

    def fake_run(*args, **kwargs):
        calls.append(list(args[0]))
        return SimpleNamespace(returncode=1, stderr="simulated ffmpeg failure", stdout="")

    monkeypatch.setattr(audio_io.subprocess, "run", fake_run)

    segment = Segment(start=0.0, end=1.0, detector="test", score=0.1)

    with pytest.raises(audio_io.FFmpegError):
        export_mod.export_sample(src, out, segment, format="wav")

    assert calls, "Expected export_sample to invoke ffmpeg subprocess"


def test_describe_audio_load_error_prompts_ffmpeg_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Advise the user to install FFmpeg when tooling is unavailable."""

    monkeypatch.setattr(audio_io, "check_ffmpeg", lambda: False)

    advice = audio_io.describe_audio_load_error(
        Path("clip.wav"), audio_io.FFmpegError(["ffmpeg"], "failure")
    )

    assert "ffmpeg" in advice.reason.lower()
    assert "install" in advice.suggestion.lower()


def test_describe_ffmpeg_failure_provides_actionable_hints() -> None:
    """FFmpeg failure summaries should include contextual remediation hints."""

    error = audio_io.FFmpegError(
        ["ffmpeg", "-i", "missing.wav"],
        "ffmpeg command failed",
        stderr="missing.wav: No such file or directory",
        exit_code=1,
        context="Export sample",
    )

    summary, hints = audio_io.describe_ffmpeg_failure(error)

    assert "export sample" in summary.lower()
    assert any("verify the source audio" in hint.lower() for hint in hints)
