"""Tests for the waveform widget view syncing and state handling."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from spectrosampler.gui.waveform_manager import WaveformData
from spectrosampler.gui.waveform_widget import WaveformWidget


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_waveform_data() -> WaveformData:
    times = np.linspace(0.0, 1.0, 5, dtype=np.float32)
    positive = np.linspace(0.1, 0.5, 5, dtype=np.float32)
    negative = -positive
    return WaveformData(
        times=times,
        peak_positive=positive,
        peak_negative=negative,
        duration=1.0,
        sample_rate=48000,
        max_abs=float(np.max(positive)),
    )


def test_waveform_widget_view_range_clamps_and_updates():
    app = _ensure_qapp()
    widget = WaveformWidget()
    widget.set_duration(1.0)
    widget.set_waveform_data(_make_waveform_data())

    widget.set_view_range(-5.0, 10.0)
    assert widget._view_start == pytest.approx(0.0)
    assert widget._view_end == pytest.approx(1.0)

    widget.set_view_range(0.2, 0.4)
    assert widget._view_start == pytest.approx(0.2)
    assert widget._view_end == pytest.approx(0.4)

    widget.deleteLater()
    app.processEvents()


def test_waveform_widget_selection_tracks_indexes():
    app = _ensure_qapp()
    widget = WaveformWidget()
    widget.set_segments([])
    widget.set_selected_indexes([1, 3, 5])
    assert widget._selected_indexes == {1, 3, 5}

    widget.set_selected_indexes([])
    assert widget._selected_indexes == set()

    widget.deleteLater()
    app.processEvents()
