"""DAW-style spectrogram widget with zoom, pan, and sample markers."""

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import NullLocator
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import QMenu, QVBoxLayout, QWidget

from spectrosampler.detectors.base import Segment
from spectrosampler.gui.grid_manager import GridManager
from spectrosampler.gui.spectrogram_tiler import SpectrogramTiler

logger = logging.getLogger(__name__)


class SpectrogramWidget(QWidget):
    """Interactive spectrogram widget with zoom, pan, and sample markers."""

    sample_selected = Signal(int)  # Emitted when sample is selected (index)
    sample_moved = Signal(int, float, float)  # Emitted when sample is moved (index, start, end)
    sample_resized = Signal(int, float, float)  # Emitted when sample is resized (index, start, end)
    sample_created = Signal(float, float)  # Emitted when sample is created (start, end)
    sample_deleted = Signal(int)  # Emitted when sample is deleted (index)
    sample_play_requested = Signal(int)  # Emitted when sample play is requested (index)
    time_clicked = Signal(float)  # Emitted when spectrogram is clicked (time)
    sample_drag_started = Signal(int)  # Emitted when sample drag starts (index)
    sample_resize_started = Signal(int)  # Emitted when sample resize starts (index)
    sample_create_started = Signal()  # Emitted when sample creation starts
    # New actions
    sample_disable_requested = Signal(int, bool)  # (index, disabled)
    sample_disable_others_requested = Signal(int)  # (index)
    sample_name_edit_requested = Signal(int)  # (index)
    sample_center_requested = Signal(int)  # (index)
    sample_center_fill_requested = Signal(int)  # (index)
    samples_enable_state_requested = Signal(list, str)  # (indexes, mode: enable/disable/toggle)
    samples_disable_others_requested = Signal(list)  # (indexes)
    samples_name_edit_requested = Signal(list)  # (indexes)
    samples_delete_requested = Signal(list)  # (indexes)
    # Emitted whenever the visible time range changes (start_time, end_time)
    view_changed = Signal(float, float)
    selection_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        """Initialize spectrogram widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Theme colors
        self._theme_colors = {
            "background": QColor(0x1E, 0x1E, 0x1E),
            "background_secondary": QColor(0x25, 0x25, 0x26),
            "text": QColor(0xCC, 0xCC, 0xCC),
            "text_secondary": QColor(0x99, 0x99, 0x99),
            "border": QColor(0x3C, 0x3C, 0x3C),
            "grid": QColor(0x3C, 0x3C, 0x3C, 0x80),
            "grid_major": QColor(0x45, 0x45, 0x45, 0xA0),
            "marker_voice": QColor(0x00, 0xFF, 0xAA, 0x80),
            "marker_transient": QColor(0xFF, 0xCC, 0x00, 0x80),
            "marker_nonsilence": QColor(0xFF, 0x66, 0xAA, 0x80),
            "marker_spectral": QColor(0x66, 0xAA, 0xFF, 0x80),
            "selection": QColor(0xEF, 0x7F, 0x22, 0xA0),
            "selection_border": QColor(0xEF, 0x7F, 0x22),
        }

        # Spectrogram data/state placeholders (initialized early to allow theme calls)
        self._tiler = SpectrogramTiler()
        self._current_tile: Any = None
        self._overview_tile: Any = None
        self._im: Any | None = None  # persistent AxesImage for spectrogram
        self._grid_artists: list[Any] = []
        self._segment_artists: list[Any] = []
        self._audio_path: Path | None = None
        self._duration = 0.0
        self._start_time = 0.0
        self._end_time = 0.0
        self._pixels_per_second = 100.0
        self._zoom_level = 1.0

        # Segments
        self._segments: list[Segment] = []
        self._selected_index: int | None = None
        self._selected_indexes: set[int] = set()
        self._selection_anchor: int | None = None

        # Grid
        self._grid_manager = GridManager()
        self._show_disabled: bool = True

        # Interaction state
        self._dragging = False
        self._drag_start_pos: QPoint | None = None
        self._drag_start_time = 0.0
        self._creating_sample = False
        self._create_start_time = 0.0
        self._resizing_left = False
        self._resizing_right = False
        self._resize_initial_start = 0.0  # Initial segment start when resizing left
        self._resize_initial_end = 0.0  # Initial segment end when resizing right
        self._hover_handle: str | None = None  # 'left', 'right', or None
        self._last_click_time = 0.0
        self._last_click_time_pos: QPoint | None = None
        self._last_clicked_index: int | None = None

        # Pending changes for deferred updates
        self._pending_drag_start: float | None = None
        self._pending_drag_end: float | None = None
        self._pending_resize_start: float | None = None
        self._pending_resize_end: float | None = None
        self._pending_create_start: float | None = None
        self._pending_create_end: float | None = None
        self._original_segment_start: float | None = None  # For ESC cancellation
        self._original_segment_end: float | None = None  # For ESC cancellation

        # Playback indicator state
        self._playback_time: float | None = None
        self._playback_segment_index: int | None = None
        self._playback_paused: bool = False

        # Drag start timer for double-click prevention
        self._drag_start_timer: QTimer | None = None
        self._min_hold_duration_ms = 150  # Minimum hold duration before drag starts
        self._pending_drag_operation: str | None = (
            None  # 'drag', 'resize_left', 'resize_right', or None
        )
        self._pending_drag_index: int | None = None  # Segment index for pending drag
        self._pending_drag_click_time: float | None = None  # Time position where click occurred

        # Create matplotlib figure
        fig_bg = self._theme_colors["background"]
        axes_bg = self._theme_colors.get("background_secondary", fig_bg)
        self._figure = Figure(figsize=(10, 6), facecolor=self._to_rgba(fig_bg))
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._ax = self._figure.add_subplot(111, facecolor=self._to_rgba(axes_bg))
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self.setLayout(layout)

        # Connect mouse events
        self._canvas.mpl_connect("button_press_event", self._on_mouse_press)
        self._canvas.mpl_connect("button_release_event", self._on_mouse_release)
        self._canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        self._canvas.mpl_connect("scroll_event", self._on_wheel)

        # Set cursor tracking
        self._canvas.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        # Install event filter on canvas for double-click detection
        self._canvas.installEventFilter(self)

    def _adjust_figure_geometry(self) -> None:
        """Position axes to fill canvas (labels drawn manually)."""
        self._figure.subplots_adjust(0.0, 0.0, 1.0, 1.0)
        self._ax.set_position([0.0, 0.0, 1.0, 1.0])

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adjust_figure_geometry()
        self._canvas.draw_idle()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._adjust_figure_geometry()
        self._canvas.draw_idle()

    @staticmethod
    def _to_rgba(color: QColor) -> tuple[float, float, float, float]:
        """Convert QColor to an RGBA tuple for matplotlib."""
        if not isinstance(color, QColor):
            return 0.0, 0.0, 0.0, 1.0
        rgb = cast("tuple[float, float, float, float]", color.getRgbF())
        return rgb

    @staticmethod
    def _color_to_hex(color: QColor | str, default: str = "#FFFFFF") -> str:
        """Convert a QColor or color string to a hex string."""
        if isinstance(color, QColor):
            return color.name()
        if isinstance(color, str) and color:
            return color
        return default

    @staticmethod
    def _float_close(value_a: float | None, value_b: float | None, *, eps: float = 1e-4) -> bool:
        """Return True when both floats are either None or within eps."""
        if value_a is None and value_b is None:
            return True
        if value_a is None or value_b is None:
            return False
        return abs(value_a - value_b) <= eps

    def _apply_theme_to_axes(self) -> None:
        """Apply current theme colors to matplotlib axes."""
        bg = self._theme_colors.get("background", QColor(0x1E, 0x1E, 0x1E))
        axes_bg = self._theme_colors.get("background_secondary", bg)
        self._figure.set_facecolor(self._to_rgba(bg))
        self._ax.set_facecolor(self._to_rgba(axes_bg))
        self._ax.set_xlabel("")
        self._ax.set_ylabel("")
        self._ax.tick_params(
            bottom=False,
            top=False,
            left=False,
            right=False,
            labelbottom=False,
            labelleft=False,
        )
        self._ax.xaxis.set_major_locator(NullLocator())
        self._ax.xaxis.set_minor_locator(NullLocator())
        self._ax.yaxis.set_major_locator(NullLocator())
        self._ax.yaxis.set_minor_locator(NullLocator())
        for spine in self._ax.spines.values():
            spine.set_visible(False)
        self._adjust_figure_geometry()

    def _emit_view_changed(self) -> None:
        """Emit view_changed signal with defensive logging."""
        try:
            self.view_changed.emit(self._start_time, self._end_time)
        except (RuntimeError, TypeError) as exc:
            logger.warning("Failed to emit view_changed signal: %s", exc, exc_info=exc)

    def set_duration(self, duration: float) -> None:
        """Set total audio duration.

        Args:
            duration: Duration in seconds.
        """
        self._duration = max(0.0, duration)
        self.update()

    def set_time_range(self, start_time: float, end_time: float) -> None:
        """Set visible time range.

        Args:
            start_time: Start time in seconds.
            end_time: End_time in seconds.
        """
        self._start_time = max(0.0, min(start_time, self._duration))
        self._end_time = max(self._start_time, min(end_time, self._duration))
        self._update_display()
        # Notify listeners to allow external widgets (navigator) to sync
        self._emit_view_changed()

    def set_zoom_level(self, zoom: float) -> None:
        """Set zoom level.

        Args:
            zoom: Zoom level (0.5x to 32x).
        """
        self._zoom_level = max(0.5, min(32.0, zoom))
        self._pixels_per_second = 100.0 * self._zoom_level
        self._update_display()

    def set_segments(self, segments: list[Segment], update_tiles: bool = False) -> None:
        """Set detected segments.

        Args:
            segments: List of segments.
            update_tiles: If True, request tiles (for time range changes).
                          If False, only update overlays (for segment-only changes).
        """
        self._segments = segments
        self._selected_index = None
        self._selected_indexes.clear()
        self._selection_anchor = None
        if self._playback_segment_index is not None:
            if not (0 <= self._playback_segment_index < len(self._segments)):
                self._playback_segment_index = None
                self._playback_time = None
                self._playback_paused = False
        if update_tiles:
            self._update_display()
        else:
            self._update_overlays_only()

    def set_playback_state(
        self,
        segment_index: int | None,
        playback_time: float | None,
        *,
        paused: bool = False,
    ) -> None:
        """Update playback indicator state and redraw overlays if needed.

        Args:
            segment_index: Index of the segment currently playing or None to clear.
            playback_time: Absolute playback time in seconds or None to clear.
            paused: True if playback is currently paused.
        """
        if segment_index is None or playback_time is None:
            new_index = None
            new_time = None
            new_paused = False
        else:
            new_index = segment_index
            new_time = min(self._duration, max(0.0, playback_time))
            new_paused = paused

        if (
            self._playback_segment_index == new_index
            and self._float_close(self._playback_time, new_time)
            and self._playback_paused == new_paused
        ):
            return

        self._playback_segment_index = new_index
        self._playback_time = new_time
        self._playback_paused = new_paused
        self._update_overlays_only()

    def set_selected_index(self, index: int | None) -> None:
        """Set selected segment index.

        Args:
            index: Segment index or None.
        """
        if index is None:
            self.set_selected_indexes([])
        else:
            self.set_selected_indexes([index], anchor=index)

    def set_selected_indexes(self, indexes: Iterable[int], *, anchor: int | None = None) -> None:
        """Set the current selection to the provided segment indexes."""

        normalized = {int(idx) for idx in indexes if isinstance(idx, int)}
        self._apply_selection(normalized, anchor, anchor)

    def _apply_selection(
        self,
        indexes: set[int],
        anchor: int | None,
        active: int | None,
    ) -> None:
        """Apply selection state and emit signals if anything changed."""

        if indexes:
            max_index = len(self._segments) - 1
            indexes = {idx for idx in indexes if 0 <= idx <= max_index}
            if not indexes:
                anchor = None
                active = None
            else:
                if anchor is None or anchor not in indexes:
                    anchor = sorted(indexes)[-1]
                if active is None or active not in indexes:
                    active = anchor
        else:
            anchor = None
            active = None

        changed = indexes != self._selected_indexes or anchor != self._selection_anchor
        active_changed = active != self._selected_index

        self._selected_indexes = indexes
        self._selection_anchor = anchor
        self._selected_index = active

        if changed or active_changed:
            self._update_overlays_only()

        if changed:
            self.selection_changed.emit(sorted(indexes))

        if active_changed and active is not None:
            self.sample_selected.emit(active)

    def handle_selection_click(self, clicked_index: int, *, ctrl: bool, shift: bool) -> None:
        """Update selection state in response to a user click."""

        new_selection = set(self._selected_indexes)
        active = clicked_index
        anchor_for_apply: int | None = None

        if shift:
            base_anchor = self._selected_index
            if base_anchor is None:
                base_anchor = self._selection_anchor
            if base_anchor is None:
                base_anchor = clicked_index
            start = min(base_anchor, clicked_index)
            end = max(base_anchor, clicked_index)
            range_selection = set(range(start, end + 1))
            new_selection.update(range_selection)
            anchor_for_apply = clicked_index
        elif ctrl:
            if clicked_index in new_selection:
                new_selection.remove(clicked_index)
                if new_selection:
                    active = sorted(new_selection)[-1]
                    anchor_for_apply = active
                else:
                    active = None
                    anchor_for_apply = None
            else:
                new_selection.add(clicked_index)
                anchor_for_apply = clicked_index
        else:
            new_selection = {clicked_index}
            anchor_for_apply = clicked_index

        if not new_selection:
            self._apply_selection(set(), None, None)
        else:
            if anchor_for_apply is None or anchor_for_apply not in new_selection:
                anchor_for_apply = sorted(new_selection)[-1]
            if active is None or active not in new_selection:
                active = anchor_for_apply
            self._apply_selection(new_selection, anchor_for_apply, active)

    def fit_selection(self, indexes: Iterable[int] | None = None) -> bool:
        """Zoom the view to tightly frame the selected segments.

        Args:
            indexes: Optional iterable of segment indexes. When omitted, uses the
                internally tracked selection.

        Returns:
            True if a view change was applied, False when no selection is available.
        """

        if self._duration <= 0:
            return False

        if indexes is None:
            if self._selected_indexes:
                indexes = self._selected_indexes
            elif self._selected_index is not None:
                indexes = [self._selected_index]
            else:
                return False

        spans: list[tuple[float, float]] = []
        for idx in indexes:
            if isinstance(idx, int) and 0 <= idx < len(self._segments):
                seg = self._segments[idx]
                start = min(seg.start, seg.end)
                end = max(seg.start, seg.end)
                if end > start:
                    spans.append((start, end))

        if not spans:
            return False

        start_time = max(0.0, min(start for start, _ in spans))
        end_time = min(self._duration, max(end for _, end in spans))

        if end_time <= start_time:
            end_time = min(self._duration, start_time + 0.1)

        visible_span = max(0.01, end_time - start_time)
        margin = max(0.05, min(1.0, visible_span * 0.05))

        new_start = max(0.0, start_time - margin)
        new_end = min(self._duration, end_time + margin)

        if new_end - new_start < 0.01:
            new_end = min(self._duration, new_start + 0.01)

        self.set_time_range(new_start, new_end)
        return True

    def set_grid_manager(self, grid_manager: GridManager) -> None:
        """Set grid manager.

        Args:
            grid_manager: GridManager instance.
        """
        self._grid_manager = grid_manager
        self._update_overlays_only()

    def set_show_disabled(self, show: bool) -> None:
        """Control whether disabled samples are drawn with indication.

        Args:
            show: True to show disabled samples (with visual indication).
        """
        self._show_disabled = bool(show)
        self._update_overlays_only()

    def set_audio_path(self, audio_path: Path | None) -> None:
        """Set audio file path for spectrogram generation.

        Args:
            audio_path: Path to audio file or None.
        """
        self._audio_path = audio_path
        self._tiler.clear_cache()
        self._update_display()

    def set_overview_tile(self, tile: Any) -> None:
        """Provide a low-resolution overview tile covering the entire file.

        This is used as a visual fallback while high-res tiles are loading.
        """
        self._overview_tile = tile
        # If no current detail tile yet, draw the overview immediately
        self._update_display()

    def preload_current_view(self) -> None:
        """Synchronously generate and display the current view's spectrogram tile.

        Use only at initialization to ensure the first frame is visible immediately.
        """
        try:
            if self._audio_path and self._audio_path.exists() and self._end_time > self._start_time:
                tile = self._tiler.generate_tile(
                    self._audio_path, self._start_time, self._end_time, sample_rate=None
                )
                self._current_tile = tile
                # Force an immediate draw with the new tile
                self._im = None  # ensure creation if not present
                self._draw_overlays()
                self._update_display()
        except (RuntimeError, ValueError, OSError) as exc:
            logger.error("Failed to preload spectrogram view: %s", exc, exc_info=exc)

    def set_frequency_range(self, fmin: float | None = None, fmax: float | None = None) -> None:
        """Set frequency range for spectrogram.

        Args:
            fmin: Minimum frequency in Hz.
            fmax: Maximum frequency in Hz.
        """
        self._tiler.fmin = fmin
        self._tiler.fmax = fmax
        self._tiler.clear_cache()
        self._update_display()

    def set_theme_colors(self, colors: dict[str, QColor]) -> None:
        """Set theme colors.

        Args:
            colors: Dictionary with color definitions.
        """
        self._theme_colors.update(colors)
        self._apply_theme_to_axes()
        self._update_display()

    def _update_display(self) -> None:
        """Update spectrogram display with persistent image and async tiles."""
        if self._duration <= 0:
            return
        # Show tile only if it matches current view (or use overview fallback)
        current_tile_matches = (
            self._current_tile is not None
            and abs(self._current_tile.start_time - self._start_time) < 0.1
            and abs(self._current_tile.end_time - self._end_time) < 0.1
        )
        if current_tile_matches and self._current_tile.spectrogram.size > 0:
            try:
                self._apply_tile_to_image(self._current_tile)
            except (RuntimeError, ValueError) as exc:
                logger.error("Failed to apply current spectrogram tile: %s", exc, exc_info=exc)
        elif self._overview_tile is not None and self._overview_tile.spectrogram.size > 0:
            try:
                # Extract/crop overview to current view window
                self._apply_overview_to_image()
            except (RuntimeError, ValueError) as exc:
                logger.error("Failed to apply overview spectrogram tile: %s", exc, exc_info=exc)

        # Async request for current view
        if self._audio_path and self._audio_path.exists():

            def _on_ready(tile):
                # Ensure UI updates occur on the GUI thread
                def _apply() -> None:
                    self._current_tile = tile
                    try:
                        self._apply_tile_to_image(tile)
                    except (RuntimeError, ValueError) as exc:
                        logger.error(
                            "Failed to update spectrogram with async tile: %s", exc, exc_info=exc
                        )
                        return
                    self._draw_overlays()
                    # Use draw_idle to coalesce repaints
                    self._canvas.draw_idle()

                try:
                    QTimer.singleShot(0, _apply)
                except RuntimeError as exc:
                    # Fallback in case QTimer fails in this context
                    logger.debug(
                        "QTimer.singleShot failed, applying tile directly: %s", exc, exc_info=exc
                    )
                    _apply()

            try:
                self._tiler.request_tile(
                    self._audio_path,
                    self._start_time,
                    self._end_time,
                    sample_rate=None,
                    callback=_on_ready,
                )
                self._tiler.prefetch_neighbors(self._audio_path, self._start_time, self._end_time)
            except (RuntimeError, ValueError, OSError) as exc:
                logger.error("Failed to request spectrogram tile: %s", exc, exc_info=exc)
        else:
            if not self._audio_path:
                logger.debug("No audio path set, skipping spectrogram generation")
            elif not self._audio_path.exists():
                logger.warning(f"Audio path does not exist: {self._audio_path}")

        # Draw overlays (includes segments, grid, preview)
        self._draw_overlays()

        self._canvas.draw()

    def _update_overlays_only(self) -> None:
        """Update only overlays (segments, grid) without requesting tiles.

        Use this during drag/resize operations when the time range hasn't changed
        to avoid unnecessary tile cache lookups.
        """
        if self._duration <= 0:
            return
        # Draw overlays (includes segments, grid, preview)
        self._draw_overlays()
        self._canvas.draw_idle()

    def _draw_overlays(self) -> None:
        """Redraw grid, segments, and previews without clearing the spectrogram image."""
        # Clear previous overlay artists
        for a in self._grid_artists:
            try:
                a.remove()
            except (ValueError, RuntimeError) as exc:
                logger.debug("Failed to remove grid artist: %s", exc, exc_info=exc)
        self._grid_artists.clear()
        for a in self._segment_artists:
            try:
                a.remove()
            except (ValueError, RuntimeError) as exc:
                logger.debug("Failed to remove segment artist: %s", exc, exc_info=exc)
        self._segment_artists.clear()

        major_positions: list[float] = []

        # Apply current limits upfront so downstream calculations use fresh values
        self._ax.set_xlim(self._start_time, self._end_time)
        if self._tiler.fmin is not None and self._tiler.fmax is not None:
            self._ax.set_ylim(self._tiler.fmin, self._tiler.fmax)
        else:
            self._ax.set_ylim(0, 20000)

        # Grid (on top of spectrogram) with line count limiting
        if self._grid_manager.settings.visible:
            grid_positions = self._grid_manager.get_grid_positions(self._start_time, self._end_time)
            major_positions = self._grid_manager.get_major_grid_positions(
                self._start_time, self._end_time
            )
            minor_color = self._to_rgba(
                self._theme_colors.get("grid", QColor(0x3C, 0x3C, 0x3C, 0x80))
            )
            major_color = self._to_rgba(
                self._theme_colors.get("grid_major", QColor(0x45, 0x45, 0x45, 0xA0))
            )
            max_lines = 80
            if len(grid_positions) > max_lines:
                step = max(1, int(len(grid_positions) / max_lines))
                grid_positions = grid_positions[::step]
            if len(major_positions) > max_lines // 2:
                step = max(1, int(len(major_positions) / (max_lines // 2)))
                major_positions = major_positions[::step]
            for pos in grid_positions:
                if pos not in major_positions:
                    ln = self._ax.axvline(
                        pos,
                        color=minor_color,
                        linestyle="--",
                        linewidth=0.5,
                        zorder=1,
                    )
                    self._grid_artists.append(ln)
            for pos in major_positions:
                ln = self._ax.axvline(
                    pos,
                    color=major_color,
                    linestyle="-",
                    linewidth=1,
                    zorder=1,
                )
                self._grid_artists.append(ln)

        # Horizontal frequency guides (skip min/max) and labels
        y_min, y_max = self._ax.get_ylim()
        freq_line_color = self._theme_colors.get("grid", QColor(0x3C, 0x3C, 0x3C, 0x60)).name()
        text_color = self._theme_colors.get(
            "text_secondary", self._theme_colors.get("text", QColor("white"))
        ).name()
        freq_steps = np.linspace(y_min, y_max, 10)[1:-1]  # omit extremes
        for freq in freq_steps:
            ln = self._ax.axhline(
                freq,
                color=freq_line_color,
                linestyle="--",
                linewidth=0.6,
                zorder=1,
            )
            self._grid_artists.append(ln)
            frac = (freq - y_min) / max(1e-6, y_max - y_min)
            label = self._ax.text(
                0.01,
                frac,
                f"{freq:,.0f} Hz",
                color=text_color,
                ha="left",
                va="center",
                fontsize=9,
                transform=self._ax.transAxes,
                zorder=5,
            )
            self._grid_artists.append(label)

        # Time labels along bottom (skip endpoints)
        x_min, x_max = self._ax.get_xlim()
        if major_positions:
            candidate_times = [pos for pos in major_positions if x_min < pos < x_max]
        else:
            candidate_times = np.linspace(x_min, x_max, 8)[1:-1]

        filtered_times: list[tuple[float, float]] = []
        min_spacing = 0.08  # in axes fraction
        last_frac = None
        denom = max(1e-6, x_max - x_min)
        for t in candidate_times:
            frac = (t - x_min) / denom
            if last_frac is not None and frac - last_frac < min_spacing:
                continue
            filtered_times.append((t, frac))
            last_frac = frac

        for t, frac in filtered_times:
            label = self._ax.text(
                frac,
                0.015,
                f"{t:,.0f} s",
                color=text_color,
                ha="center",
                va="bottom",
                fontsize=9,
                transform=self._ax.transAxes,
                zorder=5,
            )
            self._grid_artists.append(label)

        # Segments
        for i, seg in enumerate(self._segments):
            if seg.end < self._start_time or seg.start > self._end_time:
                continue
            color = self._get_segment_color(seg.detector)
            is_selected = i in self._selected_indexes
            alpha = 0.35 if i == self._selected_index else (0.28 if is_selected else 0.2)
            default_edge = self._theme_colors.get(
                "border", self._theme_colors.get("text", QColor("white"))
            )
            edge_color = (
                self._theme_colors["selection_border"].name()
                if is_selected
                else (default_edge.name() if isinstance(default_edge, QColor) else "white")
            )
            line_style = "-"
            if self._playback_segment_index == i:
                edge_color = self._color_to_hex(
                    self._theme_colors.get("selection_border", "#EF7F22"),
                    default="#EF7F22",
                )
                alpha = max(alpha, 0.4)
                if self._playback_paused:
                    line_style = "--"
            seg_start = max(seg.start, self._start_time)
            seg_end = min(seg.end, self._end_time)
            seg_width = seg_end - seg_start
            is_enabled = True
            try:
                is_enabled = seg.attrs.get("enabled", True)
            except (AttributeError, TypeError) as exc:
                logger.debug("Segment attrs missing 'enabled': %s", exc, exc_info=exc)
                is_enabled = True
            if not is_enabled and not self._show_disabled:
                continue
            draw_alpha = alpha if is_enabled else 0.1
            span = self._ax.axvspan(
                seg_start,
                seg_end,
                alpha=draw_alpha,
                facecolor=color,
                edgecolor=edge_color,
                linewidth=2,
                linestyle=line_style,
                zorder=2,
            )
            self._segment_artists.append(span)
            ylim = self._ax.get_ylim()
            if not is_enabled and self._show_disabled:
                x0, x1 = seg_start, seg_end
                y0, y1 = ylim[0], ylim[1]
                (ln1,) = self._ax.plot([x0, x1], [y0, y1], color="#FF6666", linewidth=1.5, zorder=3)
                (ln2,) = self._ax.plot([x0, x1], [y1, y0], color="#FF6666", linewidth=1.5, zorder=3)
                self._segment_artists.extend([ln1, ln2])
            label_x = seg_start + seg_width / 2
            label_color = self._theme_colors.get(
                "text_secondary", self._theme_colors.get("text", QColor("white"))
            )
            if isinstance(label_color, QColor):
                label_color_name = label_color.name()
            else:
                label_color_name = str(label_color)
            txt = self._ax.text(
                label_x,
                ylim[1] * 0.95,
                str(i),
                color=label_color_name,
                ha="center",
                va="top",
                fontsize=8,
            )
            self._segment_artists.append(txt)
            display_name = ""
            try:
                display_name = str(seg.attrs.get("name", "")).strip()
            except (AttributeError, TypeError) as exc:
                logger.debug("Segment attrs missing 'name': %s", exc, exc_info=exc)
                display_name = ""
            if display_name:
                safe_name = display_name.replace("\n", " ").replace("\r", " ")
                max_len = 28
                if len(safe_name) > max_len:
                    safe_name = safe_name[: max_len - 3].rstrip() + "..."
                name_txt = self._ax.text(
                    label_x,
                    ylim[1] * 0.90,
                    safe_name,
                    color=label_color_name,
                    ha="center",
                    va="top",
                    fontsize=8,
                )
                self._segment_artists.append(name_txt)

        playback_time = self._playback_time
        playback_index = self._playback_segment_index
        if playback_time is not None and playback_index is not None:
            if self._start_time <= playback_time <= self._end_time:
                y_min, y_max = self._ax.get_ylim()
                playback_color_hex = self._color_to_hex(
                    self._theme_colors.get("selection_border", "#FFCC33"), default="#FFCC33"
                )
                line_style = "-" if not self._playback_paused else "--"
                line_alpha = 0.9 if not self._playback_paused else 0.6
                ln = self._ax.axvline(
                    playback_time,
                    ymin=0.0,
                    ymax=1.0,
                    color=playback_color_hex,
                    linewidth=2.5,
                    linestyle=line_style,
                    alpha=line_alpha,
                    zorder=4,
                )
                self._segment_artists.append(ln)
                marker_alpha = 1.0 if not self._playback_paused else 0.7
                (marker_top,) = self._ax.plot(
                    [playback_time],
                    [y_max],
                    marker="o",
                    markersize=6,
                    color=playback_color_hex,
                    alpha=marker_alpha,
                    markeredgecolor="#202020",
                    markeredgewidth=0.8,
                    zorder=5,
                )
                (marker_bottom,) = self._ax.plot(
                    [playback_time],
                    [y_min],
                    marker="o",
                    markersize=5,
                    color=playback_color_hex,
                    alpha=marker_alpha,
                    markeredgecolor="#202020",
                    markeredgewidth=0.8,
                    zorder=5,
                )
                self._segment_artists.extend([marker_top, marker_bottom])

        # Preview rectangle for sample creation
        if (
            self._creating_sample
            and self._pending_create_start is not None
            and self._pending_create_end is not None
        ):
            preview_start = max(self._pending_create_start, self._start_time)
            preview_end = min(self._pending_create_end, self._end_time)
            if preview_end > preview_start:
                from matplotlib.patches import Rectangle

                ylim = self._ax.get_ylim()
                rect = Rectangle(
                    (preview_start, ylim[0]),
                    preview_end - preview_start,
                    ylim[1] - ylim[0],
                    alpha=0.3,
                    facecolor="white",
                    edgecolor="white",
                    linewidth=2,
                    linestyle="--",
                    zorder=2,
                )
                self._ax.add_patch(rect)
                self._segment_artists.append(rect)

    def _apply_tile_to_image(self, tile) -> None:
        """Apply a spectrogram tile to the persistent image, creating it if needed."""
        try:
            freq = tile.frequencies
            if len(freq) == 0:
                return
            freq_min = freq[0]
            freq_max = freq[-1]
            extent = (
                float(tile.start_time),
                float(tile.end_time),
                float(freq_min),
                float(freq_max),
            )
            # Prefer precolored RGBA if present
            if getattr(tile, "rgba", None) is not None and tile.rgba.size > 0:
                rgba = tile.rgba  # shape: (freq, time, 4)
                if self._im is None:
                    self._im = self._ax.imshow(
                        rgba,
                        aspect="auto",
                        origin="lower",
                        extent=extent,
                        interpolation="bilinear",
                        zorder=0,
                    )
                else:
                    self._im.set_data(rgba)
                    self._im.set_extent(extent)
            else:
                # Fallback to per-frame normalization (slower)
                spec = tile.spectrogram
                if spec.shape[0] == 0 or spec.shape[1] == 0:
                    return
                spec_min = np.nanmin(spec)
                spec_max = np.nanmax(spec)
                spec_normalized = (
                    np.zeros_like(spec)
                    if spec_max <= spec_min
                    else (spec - spec_min) / (spec_max - spec_min)
                )
                if self._im is None:
                    self._im = self._ax.imshow(
                        spec_normalized,
                        aspect="auto",
                        origin="lower",
                        extent=extent,
                        cmap="viridis",
                        interpolation="bilinear",
                        vmin=0.0,
                        vmax=1.0,
                        zorder=0,
                    )
                else:
                    self._im.set_data(spec_normalized)
                    self._im.set_extent(extent)
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.error("Failed to draw spectrogram tile: %s", exc, exc_info=exc)

    def _apply_overview_to_image(self) -> None:
        """Extract the current view window from the overview tile and display it."""
        if self._overview_tile is None or self._overview_tile.spectrogram.size == 0:
            return
        try:
            tile = self._overview_tile
            freq = tile.frequencies
            if len(freq) == 0:
                return
            freq_min = freq[0]
            freq_max = freq[-1]
            # Calculate time indices for current view
            if tile.end_time <= tile.start_time or self._duration <= 0:
                return
            time_ratio_start = (self._start_time - tile.start_time) / (
                tile.end_time - tile.start_time
            )
            time_ratio_end = (self._end_time - tile.start_time) / (tile.end_time - tile.start_time)
            time_ratio_start = max(0.0, min(1.0, time_ratio_start))
            time_ratio_end = max(0.0, min(1.0, time_ratio_end))
            # Extract time slice from overview (rgba is freq x time x 4)
            if getattr(tile, "rgba", None) is not None and tile.rgba.size > 0:
                rgba = tile.rgba
                time_bins = rgba.shape[1]
                t0 = int(time_ratio_start * time_bins)
                t1 = int(time_ratio_end * time_bins)
                t1 = max(t0 + 1, min(t1, time_bins))
                rgba_crop = rgba[:, t0:t1, :]  # (freq, cropped_time, 4)
                extent = (
                    float(self._start_time),
                    float(self._end_time),
                    float(freq_min),
                    float(freq_max),
                )
                if self._im is None:
                    self._im = self._ax.imshow(
                        rgba_crop,
                        aspect="auto",
                        origin="lower",
                        extent=extent,
                        interpolation="bilinear",
                        zorder=0,
                    )
                else:
                    self._im.set_data(rgba_crop)
                    self._im.set_extent(extent)
            else:
                # Fallback: use raw spectrogram
                spec = tile.spectrogram
                if spec.shape[0] == 0 or spec.shape[1] == 0:
                    return
                time_bins = spec.shape[1]
                t0 = int(time_ratio_start * time_bins)
                t1 = int(time_ratio_end * time_bins)
                t1 = max(t0 + 1, min(t1, time_bins))
                spec_crop = spec[:, t0:t1]
                spec_min = np.nanmin(spec_crop)
                spec_max = np.nanmax(spec_crop)
                spec_normalized = (
                    np.zeros_like(spec_crop)
                    if spec_max <= spec_min
                    else (spec_crop - spec_min) / (spec_max - spec_min)
                )
                extent = (
                    float(self._start_time),
                    float(self._end_time),
                    float(freq_min),
                    float(freq_max),
                )
                if self._im is None:
                    self._im = self._ax.imshow(
                        spec_normalized,
                        aspect="auto",
                        origin="lower",
                        extent=extent,
                        cmap="viridis",
                        interpolation="bilinear",
                        vmin=0.0,
                        vmax=1.0,
                        zorder=0,
                    )
                else:
                    self._im.set_data(spec_normalized)
                    self._im.set_extent(extent)
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.error("Failed to draw overview spectrogram: %s", exc, exc_info=exc)

    def _get_segment_color(self, detector: str) -> str:
        """Get color for detector type.

        Args:
            detector: Detector name.

        Returns:
            Color name or hex code.
        """
        color_map = {
            "voice_vad": self._theme_colors["marker_voice"].name(),
            "transient_flux": self._theme_colors["marker_transient"].name(),
            "nonsilence_energy": self._theme_colors["marker_nonsilence"].name(),
            "spectral_interestingness": self._theme_colors["marker_spectral"].name(),
        }
        return color_map.get(detector, "#FFFFFF")

    def _get_handle_width(self) -> float:
        """Get handle width in seconds based on zoom level.

        Returns:
            Handle width in seconds.
        """
        # Make handle width relative to visible time range
        time_range = self._end_time - self._start_time
        # Tighter handles: ~0.5% of visible range, clamped to [5ms, 100ms]
        handle_width = max(0.005, min(0.1, time_range * 0.005))
        return handle_width

    def _check_handle_hover(self, time: float, seg_index: int | None) -> str | None:
        """Check if mouse is hovering over a resize handle.

        Args:
            time: Time position.
            seg_index: Segment index to check, or None to check all.

        Returns:
            'left', 'right', or None.
        """
        if seg_index is not None:
            seg = self._segments[seg_index]
            handle_width = self._get_handle_width()
            if abs(time - seg.start) < handle_width:
                return "left"
            elif abs(time - seg.end) < handle_width:
                return "right"
        return None

    def _on_mouse_press(self, event) -> None:
        """Handle mouse press event."""
        if event.inaxes != self._ax:
            return

        if event.button == 1:  # Left button
            time = event.xdata
            if time is None:
                return

            time = max(self._start_time, min(time, self._end_time))

            # Check if clicking on a segment
            clicked_index = self._find_segment_at_time(time)
            if clicked_index is not None:
                modifiers = (
                    event.guiEvent.modifiers()
                    if getattr(event, "guiEvent", None) is not None
                    else Qt.KeyboardModifier.NoModifier
                )
                ctrl_pressed = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
                shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

                self.handle_selection_click(
                    clicked_index,
                    ctrl=ctrl_pressed,
                    shift=shift_pressed,
                )

                # Check if clicking on resize handle
                seg = self._segments[clicked_index]
                # Store original segment values for ESC cancellation
                self._original_segment_start = seg.start
                self._original_segment_end = seg.end
                handle_width = self._get_handle_width()

                # Cancel any pending drag timer
                if self._drag_start_timer is not None:
                    self._drag_start_timer.stop()
                    self._drag_start_timer = None

                # Determine operation type and start timer
                if abs(time - seg.start) < handle_width:
                    # Will resize left edge
                    self._pending_drag_operation = "resize_left"
                    self._pending_drag_index = clicked_index
                    self._pending_drag_click_time = time
                    # Start timer to delay actual resize start
                    self._drag_start_timer = QTimer(self)
                    self._drag_start_timer.setSingleShot(True)
                    self._drag_start_timer.timeout.connect(self._on_drag_timer_expired)
                    self._drag_start_timer.start(self._min_hold_duration_ms)
                elif abs(time - seg.end) < handle_width:
                    # Will resize right edge
                    self._pending_drag_operation = "resize_right"
                    self._pending_drag_index = clicked_index
                    self._pending_drag_click_time = time
                    # Start timer to delay actual resize start
                    self._drag_start_timer = QTimer(self)
                    self._drag_start_timer.setSingleShot(True)
                    self._drag_start_timer.timeout.connect(self._on_drag_timer_expired)
                    self._drag_start_timer.start(self._min_hold_duration_ms)
                else:
                    # Will drag segment
                    self._pending_drag_operation = "drag"
                    self._pending_drag_index = clicked_index
                    self._pending_drag_click_time = time
                    # Start timer to delay actual drag start
                    self._drag_start_timer = QTimer(self)
                    self._drag_start_timer.setSingleShot(True)
                    self._drag_start_timer.timeout.connect(self._on_drag_timer_expired)
                    self._drag_start_timer.start(self._min_hold_duration_ms)
            else:
                # Start creating new sample (no delay needed)
                if self._selected_indexes:
                    self._apply_selection(set(), None, None)
                self.sample_create_started.emit()
                self._creating_sample = True
                self._create_start_time = time
                # Clear any pending create state
                self._pending_create_start = None
                self._pending_create_end = None

            self._update_display()

    def _on_drag_timer_expired(self) -> None:
        """Handle drag start timer expiration - actually start the drag/resize operation."""
        if (
            self._pending_drag_operation is None
            or self._pending_drag_index is None
            or self._pending_drag_click_time is None
        ):
            return

        clicked_index = self._pending_drag_index
        time = self._pending_drag_click_time
        seg = self._segments[clicked_index]

        if self._pending_drag_operation == "resize_left":
            self.sample_resize_started.emit(clicked_index)
            self._resizing_left = True
            self._drag_start_time = time
            self._resize_initial_start = seg.start
        elif self._pending_drag_operation == "resize_right":
            self.sample_resize_started.emit(clicked_index)
            self._resizing_right = True
            self._drag_start_time = time
            self._resize_initial_end = seg.end
        elif self._pending_drag_operation == "drag":
            self.sample_drag_started.emit(clicked_index)
            self._dragging = True
            self._drag_start_time = time

        # Clear pending state
        self._pending_drag_operation = None
        self._pending_drag_index = None
        self._pending_drag_click_time = None
        self._drag_start_timer = None

    def _on_mouse_release(self, event) -> None:
        """Handle mouse release event."""
        if event.button == 1:  # Left button
            # Cancel pending drag timer if released before hold duration
            if self._drag_start_timer is not None and self._drag_start_timer.isActive():
                self._drag_start_timer.stop()
                self._drag_start_timer = None
                self._pending_drag_operation = None
                self._pending_drag_index = None
                self._pending_drag_click_time = None

            # Apply pending changes and emit signals
            if (
                self._dragging
                and self._selected_index is not None
                and self._pending_drag_start is not None
                and self._pending_drag_end is not None
            ):
                # Restore original segment position first
                if (
                    self._original_segment_start is not None
                    and self._original_segment_end is not None
                ):
                    seg = self._segments[self._selected_index]
                    seg.start = self._original_segment_start
                    seg.end = self._original_segment_end
                # Apply pending changes
                seg.start = self._pending_drag_start
                seg.end = self._pending_drag_end
                # Emit signal
                self.sample_moved.emit(
                    self._selected_index, self._pending_drag_start, self._pending_drag_end
                )
                # Clear pending state
                self._pending_drag_start = None
                self._pending_drag_end = None
            elif (
                self._resizing_left
                and self._selected_index is not None
                and self._pending_resize_start is not None
            ):
                # Restore original segment position first
                if self._original_segment_start is not None:
                    seg = self._segments[self._selected_index]
                    seg.start = self._original_segment_start
                # Apply pending changes
                seg.start = self._pending_resize_start
                # Emit signal
                self.sample_resized.emit(self._selected_index, self._pending_resize_start, seg.end)
                # Clear pending state
                self._pending_resize_start = None
                self._pending_resize_end = None
            elif (
                self._resizing_right
                and self._selected_index is not None
                and self._pending_resize_end is not None
            ):
                # Restore original segment position first
                if self._original_segment_end is not None:
                    seg = self._segments[self._selected_index]
                    seg.end = self._original_segment_end
                # Apply pending changes
                seg.end = self._pending_resize_end
                # Emit signal
                self.sample_resized.emit(self._selected_index, seg.start, self._pending_resize_end)
                # Clear pending state
                self._pending_resize_start = None
                self._pending_resize_end = None
            elif self._creating_sample and event.xdata is not None:
                time = max(self._start_time, min(event.xdata, self._end_time))
                if abs(time - self._create_start_time) > 0.01:  # Minimum 10ms
                    start = min(self._create_start_time, time)
                    end = max(self._create_start_time, time)
                    # Snap to grid if enabled
                    if self._grid_manager.settings.enabled:
                        start = self._grid_manager.snap_time(start)
                        end = self._grid_manager.snap_time(end)
                    self.sample_created.emit(start, end)
                # Clear pending state
                self._pending_create_start = None
                self._pending_create_end = None

            # Reset all interaction states
            self._dragging = False
            self._resizing_left = False
            self._resizing_right = False
            self._creating_sample = False
            self._drag_start_pos = None
            self._original_segment_start = None
            self._original_segment_end = None
            self._update_overlays_only()
        elif event.button == 2:  # Middle button
            if event.xdata is not None:
                time = max(self._start_time, min(event.xdata, self._end_time))
                self.time_clicked.emit(time)
        elif event.button == 3:  # Right button
            # Show context menu
            if event.inaxes == self._ax and event.xdata is not None:
                time = max(self._start_time, min(event.xdata, self._end_time))
                clicked_index = self._find_segment_at_time(time)
                if clicked_index is not None:
                    # Convert matplotlib figure coordinates to widget coordinates
                    from PySide6.QtCore import QPoint

                    canvas_pos = self._canvas.mapToGlobal(QPoint(0, 0))
                    widget_pos = canvas_pos + QPoint(int(event.x), int(event.y))
                    self._show_context_menu(clicked_index, widget_pos)

    def _on_mouse_move(self, event) -> None:
        """Handle mouse move event."""
        if event.inaxes != self._ax:
            # Update cursor when not in axes
            if self._hover_handle:
                self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
                self._hover_handle = None
            return

        if event.xdata is None:
            return

        time = max(self._start_time, min(event.xdata, self._end_time))

        # Update cursor based on hover
        if not (
            self._dragging or self._resizing_left or self._resizing_right or self._creating_sample
        ):
            clicked_index = self._find_segment_at_time(time)
            handle = self._check_handle_hover(time, clicked_index)
            if handle != self._hover_handle:
                self._hover_handle = handle
                if handle == "left" or handle == "right":
                    self._canvas.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self._canvas.setCursor(Qt.CursorShape.ArrowCursor)

        if self._dragging and self._selected_index is not None:
            # Move segment (visual preview only, no signal emission)
            seg = self._segments[self._selected_index]
            # Calculate delta based on initial click position (time-based for accurate cursor tracking)
            dt = time - self._drag_start_time
            # Calculate new position from original segment position, preserving duration
            original_start = (
                self._original_segment_start
                if self._original_segment_start is not None
                else seg.start
            )
            original_end = (
                self._original_segment_end if self._original_segment_end is not None else seg.end
            )
            dur = max(0.01, original_end - original_start)
            proposed_start = original_start + dt
            # Snap start to grid if enabled; end follows to preserve duration
            if self._grid_manager.settings.enabled:
                proposed_start = self._grid_manager.snap_time(proposed_start)
            # Clamp so the full duration remains within audio bounds
            max_start = max(0.0, self._duration - dur)
            new_start = max(0.0, min(proposed_start, max_start))
            new_end = new_start + dur
            # Store pending changes and update visual preview
            self._pending_drag_start = new_start
            self._pending_drag_end = new_end
            seg.start = new_start  # Update visual preview
            seg.end = new_end  # Update visual preview
            self._update_overlays_only()
        elif self._resizing_left and self._selected_index is not None:
            # Resize left edge (visual preview only, no signal emission)
            seg = self._segments[self._selected_index]
            # Calculate delta from initial click position
            dt = time - self._drag_start_time
            new_start = self._resize_initial_start + dt
            # Snap to grid if enabled
            if self._grid_manager.settings.enabled:
                new_start = self._grid_manager.snap_time(new_start)
            # Clamp to valid range
            new_start = max(0.0, min(new_start, seg.end - 0.01))
            # Store pending changes and update visual preview
            self._pending_resize_start = new_start
            self._pending_resize_end = seg.end
            seg.start = new_start  # Update visual preview
            self._update_overlays_only()
        elif self._resizing_right and self._selected_index is not None:
            # Resize right edge (visual preview only, no signal emission)
            seg = self._segments[self._selected_index]
            # Calculate delta from initial click position
            dt = time - self._drag_start_time
            new_end = self._resize_initial_end + dt
            # Snap to grid if enabled
            if self._grid_manager.settings.enabled:
                new_end = self._grid_manager.snap_time(new_end)
            # Clamp to valid range
            new_end = max(seg.start + 0.01, min(new_end, self._duration))
            # Store pending changes and update visual preview
            self._pending_resize_start = seg.start
            self._pending_resize_end = new_end
            seg.end = new_end  # Update visual preview
            self._update_overlays_only()
        elif self._creating_sample:
            # Update create preview bounds
            if event.xdata is not None:
                end_time = max(self._start_time, min(event.xdata, self._end_time))
                start = min(self._create_start_time, end_time)
                end = max(self._create_start_time, end_time)
                self._pending_create_start = start
                self._pending_create_end = end
                self._update_overlays_only()

    def _on_wheel(self, event) -> None:
        """Handle mouse wheel event for zooming/panning (ALT = pan)."""
        if event.inaxes != self._ax:
            return

        # Current view window
        view_start = self._start_time
        view_end = self._end_time
        view_dur = max(1e-6, view_end - view_start)

        # ALT handling is performed in eventFilter via native Qt wheel events

        # Zoom centered on cursor position
        if event.xdata is None:
            return
        cursor_time = max(view_start, min(float(event.xdata), view_end))
        step = 1.2
        is_zoom_in = event.button == "up"
        zoom = step if is_zoom_in else 1.0 / step
        new_dur = max(0.5, min(self._duration, view_dur / zoom))
        rel = (cursor_time - view_start) / view_dur
        rel = max(0.0, min(1.0, rel))
        new_start = cursor_time - rel * new_dur
        new_start = max(0.0, min(new_start, max(0.0, self._duration - new_dur)))
        self._start_time = new_start
        self._end_time = new_start + new_dur
        self._update_display()
        # Notify listeners
        self._emit_view_changed()

    def eventFilter(self, obj, event) -> bool:
        """Event filter for double-click detection and ESC key cancellation.

        Args:
            obj: Object that received the event.
            event: QEvent object.

        Returns:
            True if event was handled, False otherwise.
        """
        if obj == self._canvas:
            # Handle ALT + wheel panning with native Qt event for reliability
            if event.type() == QEvent.Type.Wheel:
                try:
                    modifiers = event.modifiers()
                    if modifiers & Qt.KeyboardModifier.AltModifier:
                        view_start = self._start_time
                        view_end = self._end_time
                        view_dur = max(1e-6, view_end - view_start)

                        dy = 0
                        dx = 0
                        try:
                            ad = event.angleDelta()
                            dy = int(ad.y()) if hasattr(ad, "y") else int(ad.y())
                            dx = int(ad.x()) if hasattr(ad, "x") else int(ad.x())
                        except (AttributeError, TypeError) as exc:
                            logger.debug("Wheel angleDelta unavailable: %s", exc, exc_info=exc)
                        if dy == 0 and dx == 0:
                            try:
                                pd = event.pixelDelta()
                                dy = int(pd.y()) if hasattr(pd, "y") else int(pd.y())
                                dx = int(pd.x()) if hasattr(pd, "x") else int(pd.x())
                            except (AttributeError, TypeError) as exc:
                                logger.debug("Wheel pixelDelta unavailable: %s", exc, exc_info=exc)

                        if dy != 0 or dx != 0:
                            if dy != 0:
                                direction = -1 if dy > 0 else 1  # wheel up = pan left
                            else:
                                direction = 1 if dx > 0 else -1  # right = pan right
                            shift = 0.1 * view_dur * direction
                            new_start = max(
                                0.0, min(view_start + shift, max(0.0, self._duration - view_dur))
                            )
                            self._start_time = new_start
                            self._end_time = new_start + view_dur
                            self._update_display()
                            self._emit_view_changed()
                            event.accept()
                            return True
                except (RuntimeError, ValueError, TypeError) as exc:
                    logger.debug("ALT wheel handling failed: %s", exc, exc_info=exc)

            if event.type() == QEvent.Type.MouseButtonDblClick:
                mouse_event = event
                if mouse_event.button() == Qt.MouseButton.LeftButton:
                    # Convert Qt mouse position to matplotlib coordinates
                    pos = mouse_event.position()
                    x = pos.x()
                    y = pos.y()

                    # Get data coordinates from matplotlib
                    inv = self._ax.transData.inverted()
                    try:
                        coords = inv.transform((x, y))
                        time = coords[0]

                        time = max(self._start_time, min(time, self._end_time))

                        # Check if double-clicking on a segment
                        clicked_index = self._find_segment_at_time(time)
                        if clicked_index is not None:
                            # Double-click to play
                            self._apply_selection({clicked_index}, clicked_index, clicked_index)
                            self.sample_play_requested.emit(clicked_index)
                            return True
                    except (RuntimeError, ValueError) as exc:
                        logger.debug(
                            "Double-click coordinate transform failed: %s", exc, exc_info=exc
                        )
            elif event.type() == QEvent.Type.KeyPress:
                from PySide6.QtGui import QKeyEvent

                if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Escape:
                    # Cancel any pending drag timer
                    if self._drag_start_timer is not None:
                        self._drag_start_timer.stop()
                        self._drag_start_timer = None
                        self._pending_drag_operation = None
                        self._pending_drag_index = None
                        self._pending_drag_click_time = None

                    # Cancel any ongoing drag/resize/create operation
                    if (
                        self._dragging
                        or self._resizing_left
                        or self._resizing_right
                        or self._creating_sample
                    ):
                        # Restore original segment positions if dragging/resizing
                        if (
                            self._dragging or self._resizing_left or self._resizing_right
                        ) and self._selected_index is not None:
                            if (
                                self._original_segment_start is not None
                                and self._original_segment_end is not None
                            ):
                                seg = self._segments[self._selected_index]
                                seg.start = self._original_segment_start
                                seg.end = self._original_segment_end
                        # Clear all pending state
                        self._pending_drag_start = None
                        self._pending_drag_end = None
                        self._pending_resize_start = None
                        self._pending_resize_end = None
                        self._pending_create_start = None
                        self._pending_create_end = None
                        # Reset interaction states
                        self._dragging = False
                        self._resizing_left = False
                        self._resizing_right = False
                        self._creating_sample = False
                        self._drag_start_pos = None
                        self._original_segment_start = None
                        self._original_segment_end = None
                        # Update display to show original state
                        self._update_display()
                        return True

        return super().eventFilter(obj, event)

    def _show_context_menu(self, seg_index: int, pos: QPoint) -> None:
        """Show context menu for segment.

        Args:
            seg_index: Segment index.
            pos: Global screen position.
        """
        menu = QMenu(self)

        if seg_index not in self._selected_indexes:
            self._apply_selection({seg_index}, seg_index, seg_index)

        selected_indexes = sorted(self._selected_indexes) if self._selected_indexes else [seg_index]
        selection_count = len(selected_indexes)

        play_action = menu.addAction("Play Sample")
        play_action.triggered.connect(lambda: self.sample_play_requested.emit(seg_index))

        menu.addSeparator()

        # Toggle enable/disable options
        enabled_states: list[bool] = []
        for idx in selected_indexes:
            seg = self._segments[idx]
            enabled_states.append(
                seg.attrs.get("enabled", True)
                if hasattr(seg, "attrs") and seg.attrs is not None
                else True
            )

        unique_states = set(enabled_states)
        if len(unique_states) == 1:
            state = unique_states.pop()
            mode = "disable" if state else "enable"
        else:
            mode = "toggle"

        if selection_count > 1:
            toggle_label = {
                "disable": "Disable Selected",
                "enable": "Enable Selected",
                "toggle": "Toggle Selected",
            }[mode]
        else:
            toggle_label = {
                "disable": "Disable",
                "enable": "Enable",
                "toggle": "Toggle Enabled",
            }[mode]

        toggle_action = menu.addAction(toggle_label)
        toggle_action.triggered.connect(
            lambda _checked=False, m=mode, idxs=selected_indexes: self.samples_enable_state_requested.emit(
                idxs, m
            )
        )

        # Disable others option
        disable_others_label = (
            "Disable Other Samples" if selection_count == 1 else "Disable Unselected Samples"
        )
        disable_others_action = menu.addAction(disable_others_label)
        disable_others_action.triggered.connect(
            lambda _checked=False, idxs=selected_indexes: self.samples_disable_others_requested.emit(
                idxs
            )
        )

        edit_label = "Edit Name" if selection_count == 1 else "Edit Names"
        edit_name_action = menu.addAction(edit_label)
        edit_name_action.triggered.connect(
            lambda _checked=False, idxs=selected_indexes: self.samples_name_edit_requested.emit(
                idxs
            )
        )

        menu.addSeparator()

        # Center options
        center_action = menu.addAction("Center")
        center_action.triggered.connect(lambda: self.sample_center_requested.emit(seg_index))
        center_fill_action = menu.addAction("Center Fill")
        center_fill_action.triggered.connect(
            lambda: self.sample_center_fill_requested.emit(seg_index)
        )

        menu.addSeparator()

        delete_label = "Delete Sample" if selection_count == 1 else "Delete Samples"
        delete_action = menu.addAction(delete_label)
        delete_action.triggered.connect(
            lambda _checked=False, idxs=selected_indexes: self.samples_delete_requested.emit(idxs)
        )

        menu.exec(pos)

    def _find_segment_at_time(self, time: float) -> int | None:
        """Find segment at time position.

        Args:
            time: Time in seconds.

        Returns:
            Segment index or None.
        """
        for i, seg in enumerate(self._segments):
            if seg.start <= time <= seg.end:
                return i
        return None
