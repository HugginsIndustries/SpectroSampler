from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import spectrosampler.pipeline as pipeline_module
from spectrosampler.pipeline_settings import ProcessingSettings


class _NoopDetector:
    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - simple stub
        pass

    def detect(self, audio) -> list:
        return []


def _stub_pipeline_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    expected_duration: float,
    analysis_duration: float,
    sample_rate: int = 16000,
) -> None:
    """Replace expensive pipeline operations with lightweight stubs for testing."""

    monkeypatch.setattr(
        pipeline_module,
        "get_audio_info",
        lambda _path: {"duration": expected_duration, "sample_rate": sample_rate},
    )
    monkeypatch.setattr(pipeline_module, "denoise_audio", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline_module, "resample_for_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline_module, "merge_segments", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        pipeline_module,
        "deduplicate_segments_after_padding",
        lambda *args, **kwargs: [],
    )
    for name in (
        "export_timestamps_csv",
        "export_markers_audacity",
        "export_markers_reaper",
        "export_sample",
        "generate_spectrogram_png",
        "create_annotated_spectrogram",
        "save_summary_json",
        "create_html_report",
    ):
        monkeypatch.setattr(pipeline_module, name, lambda *args, **kwargs: None)

    # Ensure detectors do not produce segments
    monkeypatch.setattr(pipeline_module, "VoiceVADDetector", _NoopDetector)
    monkeypatch.setattr(pipeline_module, "TransientFluxDetector", _NoopDetector)
    monkeypatch.setattr(pipeline_module, "NonSilenceEnergyDetector", _NoopDetector)
    monkeypatch.setattr(pipeline_module, "SpectralInterestingnessDetector", _NoopDetector)

    def _fake_read(_path: Path):
        total_samples = int(sample_rate * analysis_duration)
        return np.zeros(total_samples), sample_rate

    monkeypatch.setattr(sf, "read", _fake_read)


def _make_settings(strategy: str) -> ProcessingSettings:
    settings = ProcessingSettings(
        mode="auto",
        denoise="off",
        cache=False,
        create_subfolders=False,
        spectrogram=False,
        report=None,
        analysis_resample_strategy=strategy,
    )
    return settings


def test_process_file_emits_duration_warning_with_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Duration mismatches should populate warnings with a retry suggestion."""

    _stub_pipeline_dependencies(
        monkeypatch,
        expected_duration=10.0,
        analysis_duration=8.0,
    )

    input_path = tmp_path / "input.wav"
    input_path.write_text("dummy audio placeholder", encoding="utf-8")
    output_dir = tmp_path / "output"

    settings = _make_settings("default")

    result = pipeline_module.process_file(input_path, output_dir, settings, cache=None)

    warnings = result.get("warnings", [])
    assert warnings, "Expected process_file to report a warning for duration mismatch."
    warning = warnings[0]
    assert warning["code"] == "analysis_duration_mismatch"
    assert warning["resample_strategy"] == "default"
    assert warning["retry_strategy"] == "soxr"
    assert pytest.approx(warning["difference"], abs=1e-6) == pytest.approx(-2.0, abs=1e-6)


def test_process_file_warning_without_retry_for_soxr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When already using SOXR strategy, the warning should not request another retry."""

    _stub_pipeline_dependencies(
        monkeypatch,
        expected_duration=12.0,
        analysis_duration=13.5,
    )

    input_path = tmp_path / "input.wav"
    input_path.write_text("dummy audio placeholder", encoding="utf-8")
    output_dir = tmp_path / "output"

    settings = _make_settings("soxr")

    result = pipeline_module.process_file(input_path, output_dir, settings, cache=None)

    warnings = result.get("warnings", [])
    assert warnings, "Expected warnings when mismatch persists even with SOXR."
    warning = warnings[0]
    assert warning["resample_strategy"] == "soxr"
    assert warning["retry_strategy"] is None
