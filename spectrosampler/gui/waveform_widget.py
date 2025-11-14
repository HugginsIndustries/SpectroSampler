"""Interactive waveform widget that stays synchronized with the spectrogram view."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from spectrosampler.detectors.base import Segment
from spectrosampler.gui.waveform_manager import WaveformData


@dataclass(slots=True)
class _PlaybackState:
    """Internal playback indicator state."""

    segment_index: int | None
    time_sec: float | None
    paused: bool


class WaveformWidget(QWidget):
    """Widget that renders a downsampled waveform and optional segment overlays."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._waveform: WaveformData | None = None
        self._duration: float = 0.0
        self._view_start: float = 0.0
        self._view_end: float = 0.0
        self._segments: list[Segment] = []
        self._selected_indexes: set[int] = set()
        self._show_disabled: bool = True
        self._playback_state = _PlaybackState(None, None, False)

        self.setMinimumHeight(40)

        self._theme_colors: dict[str, QColor] = {
            "background": QColor(0x1E, 0x1E, 0x1E),
            "waveform_fill": QColor(0xEF, 0x7F, 0x22, 0x7F),
            "waveform_outline": QColor(0xEF, 0x7F, 0x22),
            "axis": QColor(0x33, 0x33, 0x33),
            "segment_enabled": QColor(0xEF, 0x7F, 0x22, 0x40),
            "segment_selected": QColor(0xEF, 0x7F, 0x22, 0x90),
            "segment_disabled": QColor(0x88, 0x88, 0x88, 0x40),
            "playback": QColor(0xFF, 0xCC, 0x00, 0xC0),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_duration(self, duration: float) -> None:
        """Set total audio duration."""
        self._duration = max(0.0, duration)
        if self._view_end <= self._view_start and self._duration > 0:
            self._view_start = 0.0
            self._view_end = min(60.0, self._duration)
        self.update()

    def set_view_range(self, start_time: float, end_time: float) -> None:
        """Update the visible time range."""
        clamped_start = max(0.0, min(start_time, self._duration))
        clamped_end = (
            max(clamped_start, min(end_time, self._duration))
            if self._duration
            else max(clamped_start, end_time)
        )
        if np.isclose(clamped_start, self._view_start) and np.isclose(clamped_end, self._view_end):
            return
        self._view_start = clamped_start
        self._view_end = clamped_end
        self.update()

    def set_waveform_data(self, data: WaveformData | None) -> None:
        """Assign precomputed waveform data."""
        self._waveform = data
        if data:
            self._duration = max(self._duration, data.duration)
        self.update()

    def clear_waveform(self) -> None:
        """Remove any associated waveform."""
        self._waveform = None
        self.update()

    def set_segments(self, segments: list[Segment]) -> None:
        """Set segments to render as overlays."""
        self._segments = list(segments)
        self.update()

    def set_selected_indexes(self, indexes: Iterable[int]) -> None:
        """Highlight the provided segment indexes."""
        normalized = {int(idx) for idx in indexes if isinstance(idx, int)}
        if normalized == self._selected_indexes:
            return
        self._selected_indexes = normalized
        self.update()

    def set_show_disabled(self, show: bool) -> None:
        """Toggle rendering of disabled segments."""
        if self._show_disabled == bool(show):
            return
        self._show_disabled = bool(show)
        self.update()

    def set_theme_colors(self, colors: dict[str, QColor]) -> None:
        """Apply theme colors from the main palette."""
        for key, value in colors.items():
            if key in self._theme_colors and isinstance(value, QColor):
                self._theme_colors[key] = value
        self.update()

    def set_playback_state(
        self,
        segment_index: int | None,
        playback_time: float | None,
        *,
        paused: bool = False,
    ) -> None:
        """Render a playback cursor representing the current audio position."""
        state = _PlaybackState(segment_index, playback_time, paused)
        if state == self._playback_state:
            return
        self._playback_state = state
        self.update()

    # ------------------------------------------------------------------
    # Painting helpers
    # ------------------------------------------------------------------

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, self._theme_colors["background"])

        if rect.width() <= 0 or rect.height() <= 0:
            return

        mid_y = rect.center().y()
        painter.setPen(QPen(self._theme_colors["axis"], 1))
        painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)

        if self._waveform and self._waveform.times.size > 0 and self._view_end > self._view_start:
            self._paint_waveform(painter, rect)

        if self._segments:
            self._paint_segments(painter, rect)

        if self._playback_state.time_sec is not None:
            self._paint_playback_cursor(painter, rect)

    def _paint_waveform(self, painter: QPainter, rect) -> None:
        view_duration = self._view_end - self._view_start
        if view_duration <= 0:
            return

        data = self._waveform
        if data is None or data.times.size == 0:
            return

        times = data.times
        pos_env = data.peak_positive
        neg_env = data.peak_negative

        # Determine which samples fall inside (or just outside) the view to avoid gaps.
        margin = view_duration * 0.05
        mask = (times >= self._view_start - margin) & (times <= self._view_end + margin)
        if not np.any(mask):
            return

        times_view = times[mask]
        pos_view = pos_env[mask]
        neg_view = neg_env[mask]

        if times_view.size < 2:
            return

        pixel_count = max(2, rect.width())
        sample_times = np.linspace(self._view_start, self._view_end, pixel_count, dtype=np.float32)
        pos_interp = np.interp(
            sample_times, times_view, pos_view, left=pos_view[0], right=pos_view[-1]
        )
        neg_interp = np.interp(
            sample_times, times_view, neg_view, left=neg_view[0], right=neg_view[-1]
        )

        xs = ((sample_times - self._view_start) / view_duration) * rect.width() + rect.left()
        scale = (rect.height() / 2.0) * 0.92 / max(1e-6, data.max_abs)
        upper = rect.center().y() - pos_interp * scale
        lower = rect.center().y() - neg_interp * scale

        path = QPainterPath()
        path.moveTo(xs[0], rect.center().y())
        for x, y in zip(xs, upper, strict=False):
            path.lineTo(float(x), float(y))
        for x, y in zip(reversed(xs), reversed(lower), strict=False):
            path.lineTo(float(x), float(y))
        path.closeSubpath()

        painter.setPen(QPen(self._theme_colors["waveform_outline"], 1.2))
        painter.setBrush(self._theme_colors["waveform_fill"])
        painter.drawPath(path)

    def _paint_segments(self, painter: QPainter, rect) -> None:
        if self._view_end <= self._view_start:
            return

        view_duration = self._view_end - self._view_start
        base_rect = rect.adjusted(0, 2, 0, -2)

        for idx, seg in enumerate(self._segments):
            if seg.end <= self._view_start or seg.start >= self._view_end:
                continue

            enabled = bool(getattr(seg, "attrs", {}).get("enabled", True))
            if not enabled and not self._show_disabled:
                continue

            x1 = (
                (max(seg.start, self._view_start) - self._view_start) / view_duration
            ) * rect.width()
            x2 = ((min(seg.end, self._view_end) - self._view_start) / view_duration) * rect.width()

            left = rect.left() + max(0.0, x1)
            right = rect.left() + min(rect.width(), x2)
            if right <= left:
                right = left + 1.0

            if idx in self._selected_indexes:
                color = self._theme_colors["segment_selected"]
            elif enabled:
                color = self._theme_colors["segment_enabled"]
            else:
                color = self._theme_colors["segment_disabled"]

            seg_rect = QRectF(left, base_rect.top(), max(1.0, right - left), base_rect.height())
            clipped = seg_rect.intersected(QRectF(base_rect))
            painter.fillRect(clipped, color)

    def _paint_playback_cursor(self, painter: QPainter, rect) -> None:
        time_sec = self._playback_state.time_sec
        if time_sec is None or self._view_end <= self._view_start:
            return
        if time_sec < self._view_start or time_sec > self._view_end:
            return
        x = (
            rect.left()
            + ((time_sec - self._view_start) / (self._view_end - self._view_start)) * rect.width()
        )
        pen = QPen(self._theme_colors["playback"], 1.5)
        pen.setStyle(Qt.PenStyle.DashLine if self._playback_state.paused else Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
