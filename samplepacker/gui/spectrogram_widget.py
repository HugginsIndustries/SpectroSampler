"""DAW-style spectrogram widget with zoom, pan, and sample markers."""

import logging
from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from samplepacker.detectors.base import Segment
from samplepacker.gui.grid_manager import GridManager
from samplepacker.gui.spectrogram_tiler import SpectrogramTiler

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

    def __init__(self, parent: QWidget | None = None):
        """Initialize spectrogram widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Create matplotlib figure
        self._figure = Figure(figsize=(10, 6), facecolor=(0x1E / 255, 0x1E / 255, 0x1E / 255))
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._ax = self._figure.add_subplot(111, facecolor=(0x1E / 255, 0x1E / 255, 0x1E / 255))
        self._ax.set_xlabel("Time (s)", color="white")
        self._ax.set_ylabel("Frequency (Hz)", color="white")
        self._ax.tick_params(colors="white")
        self._ax.spines["bottom"].set_color("white")
        self._ax.spines["top"].set_color("white")
        self._ax.spines["left"].set_color("white")
        self._ax.spines["right"].set_color("white")

        # Spectrogram data
        self._tiler = SpectrogramTiler()
        self._current_tile: Any = None
        self._audio_path: Path | None = None
        self._duration = 0.0
        self._start_time = 0.0
        self._end_time = 0.0
        self._pixels_per_second = 100.0
        self._zoom_level = 1.0

        # Segments
        self._segments: list[Segment] = []
        self._selected_index: int | None = None

        # Grid
        self._grid_manager = GridManager()

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

        # Theme colors
        self._theme_colors = {
            "background": QColor(0x1E, 0x1E, 0x1E),
            "grid": QColor(0x3C, 0x3C, 0x3C, 0x80),
            "grid_major": QColor(0x45, 0x45, 0x45, 0xA0),
            "marker_voice": QColor(0x00, 0xFF, 0xAA, 0x80),
            "marker_transient": QColor(0xFF, 0xCC, 0x00, 0x80),
            "marker_nonsilence": QColor(0xFF, 0x66, 0xAA, 0x80),
            "marker_spectral": QColor(0x66, 0xAA, 0xFF, 0x80),
            "selection": QColor(0x00, 0x78, 0xD4, 0xA0),
            "selection_border": QColor(0x00, 0x78, 0xD4),
        }

        # Setup layout
        from PySide6.QtWidgets import QVBoxLayout

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

    def set_zoom_level(self, zoom: float) -> None:
        """Set zoom level.

        Args:
            zoom: Zoom level (0.5x to 32x).
        """
        self._zoom_level = max(0.5, min(32.0, zoom))
        self._pixels_per_second = 100.0 * self._zoom_level
        self._update_display()

    def set_segments(self, segments: list[Segment]) -> None:
        """Set detected segments.

        Args:
            segments: List of segments.
        """
        self._segments = segments
        self._selected_index = None
        self._update_display()

    def set_selected_index(self, index: int | None) -> None:
        """Set selected segment index.

        Args:
            index: Segment index or None.
        """
        self._selected_index = index
        self._update_display()

    def set_grid_manager(self, grid_manager: GridManager) -> None:
        """Set grid manager.

        Args:
            grid_manager: GridManager instance.
        """
        self._grid_manager = grid_manager
        self._update_display()

    def set_audio_path(self, audio_path: Path | None) -> None:
        """Set audio file path for spectrogram generation.

        Args:
            audio_path: Path to audio file or None.
        """
        self._audio_path = audio_path
        self._update_display()

    def set_frequency_range(self, fmin: float | None = None, fmax: float | None = None) -> None:
        """Set frequency range for spectrogram.

        Args:
            fmin: Minimum frequency in Hz.
            fmax: Maximum frequency in Hz.
        """
        self._tiler.fmin = fmin
        self._tiler.fmax = fmax
        self._update_display()

    def set_theme_colors(self, colors: dict[str, QColor]) -> None:
        """Set theme colors.

        Args:
            colors: Dictionary with color definitions.
        """
        self._theme_colors.update(colors)
        self._update_display()

    def _update_display(self) -> None:
        """Update spectrogram display."""
        if self._duration <= 0:
            return

        self._ax.clear()
        self._ax.set_facecolor((0x1E / 255, 0x1E / 255, 0x1E / 255))
        self._ax.set_xlabel("Time (s)", color="white")
        self._ax.set_ylabel("Frequency (Hz)", color="white")
        self._ax.tick_params(colors="white")
        for spine in self._ax.spines.values():
            spine.set_color("white")

        # Generate spectrogram tile for visible range
        spectrogram_displayed = False
        if self._audio_path and self._audio_path.exists():
            try:
                logger.debug(f"Generating spectrogram tile: {self._audio_path} [{self._start_time:.2f}s - {self._end_time:.2f}s]")
                self._current_tile = self._tiler.generate_tile(
                    self._audio_path,
                    self._start_time,
                    self._end_time,
                )
                
                logger.debug(f"Tile generated: spectrogram.size={self._current_tile.spectrogram.size}, frequencies.len={len(self._current_tile.frequencies)}")
                
                # Display spectrogram
                if self._current_tile.spectrogram.size > 0 and len(self._current_tile.frequencies) > 0:
                    # Get frequency and time arrays
                    freq = self._current_tile.frequencies
                    spec = self._current_tile.spectrogram
                    
                    # Check data dimensions - spectrogram is (freq_bins x time_bins)
                    if len(freq) == 0 or spec.shape[0] == 0 or spec.shape[1] == 0:
                        logger.warning(f"Empty spectrogram data: freq={len(freq)}, spec.shape={spec.shape}")
                    else:
                        # Verify frequency array matches spectrogram dimensions
                        if len(freq) != spec.shape[0]:
                            logger.warning(f"Frequency array length ({len(freq)}) doesn't match spectrogram frequency dimension ({spec.shape[0]})")
                        else:
                            # Normalize spectrogram data for display
                            # dB values can be negative, need to normalize to 0-1 range for colormap
                            spec_min = np.nanmin(spec)
                            spec_max = np.nanmax(spec)
                            
                            logger.debug(f"Spectrogram data range: min={spec_min:.2f}, max={spec_max:.2f}, shape={spec.shape}")
                            
                            # If all values are the same, use a default range
                            if spec_max <= spec_min:
                                logger.warning(f"Spectrogram has constant values: {spec_min:.2f}")
                                spec_normalized = np.zeros_like(spec)
                            else:
                                # Normalize to 0-1 range
                                spec_normalized = (spec - spec_min) / (spec_max - spec_min)
                            
                            # Calculate extent for imshow
                            # extent = [xmin, xmax, ymin, ymax] where x is time, y is frequency
                            freq_min = freq[0] if len(freq) > 0 else 0
                            freq_max = freq[-1] if len(freq) > 0 else 20000
                            
                            extent = [
                                self._current_tile.start_time,
                                self._current_tile.end_time,
                                freq_min,
                                freq_max,
                            ]
                            
                            # Display using imshow with viridis colormap
                            # Note: imshow expects array in (rows x cols) format where rows correspond to y-axis
                            # scipy.signal.spectrogram returns (freq_bins x time_bins) which is correct
                            im = self._ax.imshow(
                                spec_normalized,
                                aspect="auto",
                                origin="lower",
                                extent=extent,
                                cmap="viridis",
                                interpolation="bilinear",
                                vmin=0.0,
                                vmax=1.0,
                                zorder=0,  # Ensure spectrogram is drawn first (behind everything)
                            )
                            
                            spectrogram_displayed = True
                            logger.info(f"Successfully displayed spectrogram: shape={spec.shape}, extent={extent}, freq_range=[{freq_min:.1f}, {freq_max:.1f}]")
                else:
                    logger.warning(f"Spectrogram tile has empty data: size={self._current_tile.spectrogram.size}, frequencies.len={len(self._current_tile.frequencies)}")
                    if self._tiler.fmin is not None or self._tiler.fmax is not None:
                        logger.warning(f"Tiler frequency filter: fmin={self._tiler.fmin}, fmax={self._tiler.fmax}")
                    if self._current_tile.spectrogram.size == 0 and len(self._current_tile.frequencies) == 0:
                        logger.error(f"Spectrogram tile is completely empty - this may indicate a frequency filtering issue")
            except Exception as e:
                import traceback
                logger.error(f"Failed to generate spectrogram tile: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
        else:
            if not self._audio_path:
                logger.debug("No audio path set, skipping spectrogram generation")
            elif not self._audio_path.exists():
                logger.warning(f"Audio path does not exist: {self._audio_path}")

        # Draw grid (on top of spectrogram)
        if self._grid_manager.settings.visible:
            grid_positions = self._grid_manager.get_grid_positions(self._start_time, self._end_time)
            major_positions = self._grid_manager.get_major_grid_positions(self._start_time, self._end_time)

            for pos in grid_positions:
                if pos not in major_positions:
                    self._ax.axvline(pos, color=(0x3C / 255, 0x3C / 255, 0x3C / 255, 0.5), linestyle="--", linewidth=0.5, zorder=1)

            for pos in major_positions:
                self._ax.axvline(pos, color=(0x45 / 255, 0x45 / 255, 0x45 / 255, 0.8), linestyle="-", linewidth=1, zorder=1)

        # Draw segments
        for i, seg in enumerate(self._segments):
            if seg.end < self._start_time or seg.start > self._end_time:
                continue

            # Get color based on detector
            color = self._get_segment_color(seg.detector)
            alpha = 0.3 if i == self._selected_index else 0.2
            edge_color = self._theme_colors["selection_border"].name() if i == self._selected_index else "white"

            seg_start = max(seg.start, self._start_time)
            seg_end = min(seg.end, self._end_time)
            seg_width = seg_end - seg_start

            # Draw rectangle (on top of grid and spectrogram)
            self._ax.axvspan(seg_start, seg_end, alpha=alpha, color=color, edgecolor=edge_color, linewidth=2, zorder=2)

            # Draw label
            label_x = seg_start + seg_width / 2
            self._ax.text(label_x, self._ax.get_ylim()[1] * 0.95, str(i), color="white", ha="center", va="top", fontsize=8)

        # Draw preview rectangle for sample creation
        if self._creating_sample and self._pending_create_start is not None and self._pending_create_end is not None:
            preview_start = max(self._pending_create_start, self._start_time)
            preview_end = min(self._pending_create_end, self._end_time)
            if preview_end > preview_start:
                # Draw preview rectangle with dashed border and lower opacity
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
                    zorder=2
                )
                self._ax.add_patch(rect)

        # Set axis limits
        self._ax.set_xlim(self._start_time, self._end_time)
        if self._tiler.fmin is not None and self._tiler.fmax is not None:
            self._ax.set_ylim(self._tiler.fmin, self._tiler.fmax)
        else:
            self._ax.set_ylim(0, 20000)  # Default 0-20kHz

        self._canvas.draw()

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
        # Handle should be about 2% of visible range, but at least 0.01s and at most 0.5s
        handle_width = max(0.01, min(0.5, time_range * 0.02))
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
                return 'left'
            elif abs(time - seg.end) < handle_width:
                return 'right'
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
                # Update selection
                self._selected_index = clicked_index
                self.sample_selected.emit(clicked_index)
                
                # Check if clicking on resize handle
                seg = self._segments[clicked_index]
                # Store original segment values for ESC cancellation
                self._original_segment_start = seg.start
                self._original_segment_end = seg.end
                handle_width = self._get_handle_width()
                if abs(time - seg.start) < handle_width:
                    self.sample_resize_started.emit(clicked_index)
                    self._resizing_left = True
                    self._drag_start_time = time  # Click position
                    self._resize_initial_start = seg.start  # Store initial start
                elif abs(time - seg.end) < handle_width:
                    self.sample_resize_started.emit(clicked_index)
                    self._resizing_right = True
                    self._drag_start_time = time  # Click position
                    self._resize_initial_end = seg.end  # Store initial end
                else:
                    self.sample_drag_started.emit(clicked_index)
                    self._dragging = True
                    self._drag_start_time = time
                    self._drag_start_pos = QPoint(int(event.x), int(event.y))
            else:
                # Start creating new sample
                self.sample_create_started.emit()
                self._creating_sample = True
                self._create_start_time = time
                # Clear any pending create state
                self._pending_create_start = None
                self._pending_create_end = None

            self._update_display()

    def _on_mouse_release(self, event) -> None:
        """Handle mouse release event."""
        if event.button == 1:  # Left button
            # Apply pending changes and emit signals
            if self._dragging and self._selected_index is not None and self._pending_drag_start is not None and self._pending_drag_end is not None:
                # Restore original segment position first
                if self._original_segment_start is not None and self._original_segment_end is not None:
                    seg = self._segments[self._selected_index]
                    seg.start = self._original_segment_start
                    seg.end = self._original_segment_end
                # Apply pending changes
                seg.start = self._pending_drag_start
                seg.end = self._pending_drag_end
                # Emit signal
                self.sample_moved.emit(self._selected_index, self._pending_drag_start, self._pending_drag_end)
                # Clear pending state
                self._pending_drag_start = None
                self._pending_drag_end = None
            elif self._resizing_left and self._selected_index is not None and self._pending_resize_start is not None:
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
            elif self._resizing_right and self._selected_index is not None and self._pending_resize_end is not None:
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
            self._update_display()
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
        if not (self._dragging or self._resizing_left or self._resizing_right or self._creating_sample):
            clicked_index = self._find_segment_at_time(time)
            handle = self._check_handle_hover(time, clicked_index)
            if handle != self._hover_handle:
                self._hover_handle = handle
                if handle == 'left' or handle == 'right':
                    self._canvas.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self._canvas.setCursor(Qt.CursorShape.ArrowCursor)

        if self._dragging and self._selected_index is not None:
            # Move segment (visual preview only, no signal emission)
            seg = self._segments[self._selected_index]
            # Calculate delta based on initial click position (time-based for accurate cursor tracking)
            dt = time - self._drag_start_time
            # Calculate new position from original segment position
            original_start = self._original_segment_start if self._original_segment_start is not None else seg.start
            original_end = self._original_segment_end if self._original_segment_end is not None else seg.end
            new_start = original_start + dt
            new_end = original_end + dt
            # Snap to grid if enabled
            if self._grid_manager.settings.enabled:
                new_start = self._grid_manager.snap_time(new_start)
                new_end = self._grid_manager.snap_time(new_end)
            # Clamp to valid range
            new_start = max(0.0, min(new_start, self._duration - 0.01))
            new_end = max(new_start + 0.01, min(new_end, self._duration))
            # Store pending changes and update visual preview
            self._pending_drag_start = new_start
            self._pending_drag_end = new_end
            seg.start = new_start  # Update visual preview
            seg.end = new_end  # Update visual preview
            self._update_display()
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
            self._update_display()
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
            self._update_display()
        elif self._creating_sample:
            # Update create preview bounds
            if event.xdata is not None:
                end_time = max(self._start_time, min(event.xdata, self._end_time))
                start = min(self._create_start_time, end_time)
                end = max(self._create_start_time, end_time)
                self._pending_create_start = start
                self._pending_create_end = end
                self._update_display()

    def _on_wheel(self, event) -> None:
        """Handle mouse wheel event for zooming."""
        if event.inaxes != self._ax:
            return

        if event.button == "up":
            # Zoom in
            self.set_zoom_level(self._zoom_level * 1.2)
        elif event.button == "down":
            # Zoom out
            self.set_zoom_level(self._zoom_level / 1.2)

    def eventFilter(self, obj, event) -> bool:
        """Event filter for double-click detection and ESC key cancellation.
        
        Args:
            obj: Object that received the event.
            event: QEvent object.
            
        Returns:
            True if event was handled, False otherwise.
        """
        if obj == self._canvas:
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
                            self._selected_index = clicked_index
                            self.sample_selected.emit(clicked_index)
                            self.sample_play_requested.emit(clicked_index)
                            return True
                    except Exception:
                        pass
            elif event.type() == QEvent.Type.KeyPress:
                from PySide6.QtGui import QKeyEvent
                if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Escape:
                    # Cancel any ongoing drag/resize/create operation
                    if self._dragging or self._resizing_left or self._resizing_right or self._creating_sample:
                        # Restore original segment positions if dragging/resizing
                        if (self._dragging or self._resizing_left or self._resizing_right) and self._selected_index is not None:
                            if self._original_segment_start is not None and self._original_segment_end is not None:
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
        
        play_action = menu.addAction("Play Sample")
        play_action.triggered.connect(lambda: self.sample_play_requested.emit(seg_index))
        
        menu.addSeparator()
        
        delete_action = menu.addAction("Delete Sample")
        delete_action.triggered.connect(lambda: self.sample_deleted.emit(seg_index))
        
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

