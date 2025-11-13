"""Tests for settings persistence helpers and validation."""

import pytest

from spectrosampler.gui.settings import SettingsManager
from spectrosampler.pipeline_settings import ProcessingSettings


def test_detection_max_samples_persistent_and_clamped(tmp_path, monkeypatch):
    """Max samples should persist between manager instances and stay within 1-10,000."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    manager = SettingsManager()
    manager.set_detection_max_samples(10_000)
    assert manager.get_detection_max_samples() == 10_000

    # Values outside the allowed range should clamp.
    manager.set_detection_max_samples(0)
    assert manager.get_detection_max_samples() == 1

    manager.set_detection_max_samples(15_000)
    assert manager.get_detection_max_samples() == 10_000

    manager.set_detection_max_samples(5_432)

    # A fresh manager should read the persisted value.
    other_manager = SettingsManager()
    assert other_manager.get_detection_max_samples() == 5_432


def test_processing_settings_validation_defaults_are_valid():
    """Default settings should produce no validation issues."""
    settings = ProcessingSettings()
    assert settings.validate() == []


def test_processing_settings_validation_detects_duration_order():
    """Validation should fail when min duration exceeds max duration."""
    settings = ProcessingSettings(min_dur_ms=5000.0, max_dur_ms=1000.0)
    issues = settings.validate()
    assert issues
    assert any("Minimum duration" in issue.message for issue in issues)


def test_processing_settings_validation_detects_filter_bounds():
    """High-pass filter must be lower than low-pass filter."""
    settings = ProcessingSettings(hp=5000.0, lp=2000.0)
    issues = settings.validate()
    assert issues
    assert any("High-pass frequency must be lower" in issue.message for issue in issues)


def test_detection_settings_round_trip(tmp_path, monkeypatch):
    """Detection settings should persist across manager instances."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    manager = SettingsManager()
    original = ProcessingSettings(
        mode="voice",
        detection_pre_pad_ms=125.0,
        hp=150.0,
        lp=18000.0,
        max_samples=512,
        sample_spread=False,
        sample_spread_mode="closest",
        show_overlap_dialog=False,
        overlap_default_behavior="keep_all",
    )
    manager.set_detection_settings(original)

    other = SettingsManager()
    loaded = other.get_detection_settings()
    assert loaded is not None
    assert loaded.mode == "voice"
    assert loaded.detection_pre_pad_ms == pytest.approx(125.0)
    assert loaded.hp == pytest.approx(150.0)
    assert loaded.lp == pytest.approx(18000.0)
    assert loaded.max_samples == 512
    assert loaded.sample_spread is False
    assert loaded.sample_spread_mode == "closest"
    assert loaded.show_overlap_dialog is False
    assert loaded.overlap_default_behavior == "keep_all"


def test_project_round_trip_persists_overlap_preferences(tmp_path):
    """Project serialization should include overlap dialog preferences."""
    from spectrosampler.gui.project import ProjectData, UIState, load_project, save_project

    project_path = tmp_path / "project.ssproj"
    settings = ProcessingSettings(
        show_overlap_dialog=False,
        overlap_default_behavior="discard_overlaps",
        mode="voice",
    )
    project = ProjectData(
        audio_path=str(tmp_path / "dummy.wav"),
        detection_settings=settings.to_dict(),
        ui_state=UIState(),
    )
    project.ui_state.editor_splitter_sizes = [640, 120]
    project.ui_state.player_splitter_sizes = [0, 620]
    project.ui_state.main_splitter_sizes = [800, 0]
    project.ui_state.timeline_splitter_sizes = [320, 1024]
    project.ui_state.player_visible = False
    project.ui_state.info_table_visible = False
    save_project(project, project_path)
    loaded = load_project(project_path)
    assert loaded.detection_settings["show_overlap_dialog"] is False
    assert loaded.detection_settings["overlap_default_behavior"] == "discard_overlaps"
    assert loaded.ui_state.editor_splitter_sizes == [640, 120]
    assert loaded.ui_state.player_splitter_sizes == [0, 620]
    assert loaded.ui_state.main_splitter_sizes == [800, 0]
    assert loaded.ui_state.timeline_splitter_sizes == [320, 1024]
    assert loaded.ui_state.player_visible is False
    assert loaded.ui_state.info_table_visible is False


def test_export_settings_round_trip(tmp_path, monkeypatch):
    """Export settings should persist across manager instances."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    snapshot = {
        "export_pre_pad_ms": 75.0,
        "export_post_pad_ms": 150.0,
        "export_format": "flac",
        "export_sample_rate": 48000,
        "export_bit_depth": "24",
        "export_channels": "stereo",
    }

    manager = SettingsManager()
    manager.set_export_settings(snapshot)

    other = SettingsManager()
    loaded = other.get_export_settings()
    assert loaded["export_pre_pad_ms"] == pytest.approx(75.0)
    assert loaded["export_post_pad_ms"] == pytest.approx(150.0)
    assert loaded["export_format"] == "flac"
    assert loaded["export_sample_rate"] == 48000
    assert loaded["export_bit_depth"] == "24"
    assert loaded["export_channels"] == "stereo"


def test_player_auto_play_next_preference_round_trip(tmp_path, monkeypatch):
    """Auto-play-next preference should persist across manager instances."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    manager = SettingsManager()
    manager.set_player_auto_play_next(False)
    assert manager.get_player_auto_play_next() is False
    manager.set_player_auto_play_next(True)

    other = SettingsManager()
    assert other.get_player_auto_play_next() is True
