"""Tests for MainWindow sample batch actions and action state updates."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from spectrosampler.audio_io import FFmpegError
from spectrosampler.detectors.base import Segment
from spectrosampler.gui.main_window import MainWindow


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window_with_segments(enabled_flags: list[bool]) -> MainWindow:
    app = _ensure_qapp()
    window = MainWindow()

    segments = []
    for idx, enabled in enumerate(enabled_flags):
        seg = Segment(
            start=float(idx),
            end=float(idx) + 0.5,
            detector="test",
            score=1.0,
        )
        seg.attrs["enabled"] = enabled
        segments.append(seg)

    wrapper = SimpleNamespace(current_segments=segments)
    window._pipeline_wrapper = wrapper
    window._update_sample_table(wrapper.current_segments)
    window._spectrogram_widget.set_segments(window._get_display_segments())
    window._update_navigator_markers()
    app.processEvents()
    return window


def test_enable_all_samples_sets_flags_and_updates_actions():
    app = _ensure_qapp()
    window = _make_window_with_segments([True, False])

    window._on_enable_all_samples()
    app.processEvents()

    assert all(
        seg.attrs.get("enabled", False)
        for seg in window._pipeline_wrapper.current_segments  # type: ignore[attr-defined]
    )
    assert window._enable_all_action.isEnabled() is False
    assert window._disable_all_action.isEnabled() is True

    window.deleteLater()
    app.processEvents()


def test_samples_enable_state_requested_toggle_swaps_each_segment():
    app = _ensure_qapp()
    window = _make_window_with_segments([True, False, True])

    window._on_samples_enable_state_requested([0, 1], "toggle")
    app.processEvents()

    states = [
        seg.attrs.get("enabled", True)
        for seg in window._pipeline_wrapper.current_segments  # type: ignore[attr-defined]
    ]
    assert states == [False, True, True]
    assert window._enable_all_action.isEnabled() is True
    assert window._disable_all_action.isEnabled() is True

    window.deleteLater()
    app.processEvents()


def test_disable_other_samples_preserves_selected_and_disables_rest():
    app = _ensure_qapp()
    window = _make_window_with_segments([True, True, True, False])

    window._on_disable_other_samples([1, 3])
    app.processEvents()

    states = [
        seg.attrs.get("enabled", True)
        for seg in window._pipeline_wrapper.current_segments  # type: ignore[attr-defined]
    ]
    assert states == [False, True, False, True]
    assert window._enable_all_action.isEnabled() is True
    assert window._disable_all_action.isEnabled() is True

    window.deleteLater()
    app.processEvents()


def test_delete_samples_removes_columns_and_segments():
    app = _ensure_qapp()
    window = _make_window_with_segments([True, True, True])

    window._on_delete_samples([0, 2])
    app.processEvents()

    segments = window._pipeline_wrapper.current_segments  # type: ignore[attr-defined]
    assert len(segments) == 1
    assert window._sample_table_model.columnCount() == 1
    assert segments[0].start == pytest.approx(1.0)

    window.deleteLater()
    app.processEvents()


def test_waveform_toggle_updates_visibility():
    app = _ensure_qapp()
    window = MainWindow()
    window.show()
    app.processEvents()

    if not window._show_waveform_action.isChecked():
        window._on_toggle_waveform()
        app.processEvents()

    sizes = window._player_spectro_splitter.sizes()
    assert len(sizes) == 3
    assert sizes[1] > 0

    window._on_toggle_waveform()
    app.processEvents()

    sizes_hidden = window._player_spectro_splitter.sizes()
    assert sizes_hidden[1] <= window._waveform_collapsed_size
    assert window._show_waveform_action.isChecked() is False

    window._on_toggle_waveform()
    app.processEvents()

    sizes_restored = window._player_spectro_splitter.sizes()
    assert window._show_waveform_action.isChecked()
    assert sizes_restored[1] >= window._waveform_min_visible

    window.deleteLater()
    app.processEvents()


def test_player_toggle_updates_splitter_sizes():
    app = _ensure_qapp()
    window = MainWindow()
    window.show()
    app.processEvents()

    sizes = window._player_spectro_splitter.sizes()
    assert len(sizes) == 3
    assert sizes[0] > 0

    window._on_toggle_player()
    app.processEvents()
    collapsed_sizes = window._player_spectro_splitter.sizes()
    assert collapsed_sizes[0] == 0
    assert collapsed_sizes[1] == sizes[1]
    assert collapsed_sizes[2] > 0

    window._on_toggle_player()
    app.processEvents()
    restored_sizes = window._player_spectro_splitter.sizes()
    assert restored_sizes[0] > 0
    assert restored_sizes[1] == sizes[1]
    assert restored_sizes[2] > 0

    window.deleteLater()
    app.processEvents()


def test_detection_error_routes_ffmpeg_dialog(monkeypatch):
    app = _ensure_qapp()
    window = MainWindow()

    captured = {}

    def fake_dialog(title: str, error: FFmpegError) -> None:
        captured["title"] = title
        captured["error"] = error

    monkeypatch.setattr(window, "_show_ffmpeg_failure_dialog", fake_dialog)

    err = FFmpegError(
        ["ffmpeg", "-i", "input.wav"],
        "ffmpeg failed",
        stderr="simulated failure",
        context="Detect samples",
    )

    window._on_detection_error(err)
    app.processEvents()

    assert captured["title"] == "Detection Error"
    assert captured["error"] is err
    assert window._status_label.text() == "Detection failed"

    window.deleteLater()
    app.processEvents()


def test_handle_end_of_media_without_autoplay_cleans_up(tmp_path):
    app = _ensure_qapp()
    window = _make_window_with_segments([True])

    window._loop_enabled = False
    window._auto_play_next_enabled = False
    window._current_playing_index = 0
    window._current_playing_start = 0.0
    window._current_playing_end = 0.5
    window._is_paused = False
    window._paused_position = 0

    temp_file = tmp_path / "playback.wav"
    temp_file.write_bytes(b"data")
    window._temp_playback_file = temp_file

    window._handle_end_of_media()
    app.processEvents()

    assert window._current_playing_index is None
    assert window._sample_player._is_playing is False
    assert window._sample_player._current_index is None
    assert not temp_file.exists()
    assert window._temp_playback_file is None

    window.deleteLater()
    app.processEvents()


def test_handle_end_of_media_with_autoplay_advances(monkeypatch, tmp_path):
    app = _ensure_qapp()
    window = _make_window_with_segments([True, False, True])

    window._auto_play_next_enabled = True
    window._loop_enabled = False
    window._current_playing_index = 0
    window._current_playing_start = 0.0
    window._current_playing_end = 0.5
    window._is_paused = False
    window._paused_position = 0
    window._current_audio_path = tmp_path / "dummy.wav"
    window._current_audio_path.write_bytes(b"data")

    played = []

    def fake_play_segment(self, start: float, end: float) -> None:
        played.append((start, end))
        self._current_playing_start = start
        self._current_playing_end = end

    monkeypatch.setattr(
        window,
        "_play_segment",
        fake_play_segment.__get__(window, window.__class__),
    )

    window._handle_end_of_media()
    app.processEvents()

    assert window._current_playing_index == 2
    assert window._active_sample_index == 2
    assert window._sample_player._current_index == 2
    assert window._sample_player._is_playing is True
    assert window._sample_table_view.currentIndex().column() == 2
    assert played
    assert played[0][0] == pytest.approx(2.0)
    assert played[0][1] == pytest.approx(2.5)

    window.deleteLater()
    app.processEvents()


def test_handle_end_of_media_autoplay_last_sample_finalizes(tmp_path):
    app = _ensure_qapp()
    window = _make_window_with_segments([True])

    window._auto_play_next_enabled = True
    window._loop_enabled = False
    window._current_playing_index = 0
    window._current_playing_start = 0.0
    window._current_playing_end = 0.5
    window._is_paused = False
    window._paused_position = 0
    window._current_audio_path = tmp_path / "dummy.wav"

    window._handle_end_of_media()
    app.processEvents()

    assert window._current_playing_index is None
    assert window._sample_player._is_playing is False
    assert window._sample_player._current_index is None

    window.deleteLater()
    app.processEvents()
