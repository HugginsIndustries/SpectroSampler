"""Tests for MainWindow sample batch actions and action state updates."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

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
