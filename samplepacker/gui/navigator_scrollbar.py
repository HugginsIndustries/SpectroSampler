"""Navigator scrollbar widget (Bitwig-style) showing spectrogram overview."""

import numpy as np
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from samplepacker.gui.spectrogram_tiler import SpectrogramTile


class NavigatorScrollbar(QWidget):
    """Navigator scrollbar widget with spectrogram preview."""

    view_changed = Signal(float, float)  # Emitted when view changes (start_time, end_time)
    view_resized = Signal(float, float)  # Emitted when view is resized (start_time, end_time)

    def __init__(self, parent: QWidget | None = None):
        """Initialize navigator scrollbar.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setMinimumHeight(40)
        self._duration = 0.0
        self._view_start_time = 0.0
        self._view_end_time = 0.0
        self._overview_tile: SpectrogramTile | None = None
        self._overview_image: QImage | None = None
        self._sample_markers: list[tuple[float, float, QColor]] = []  # (start, end, color)
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_view_start = 0.0
        self._resizing_left = False
        self._resizing_right = False
        self._resize_handle_width = 8
        self._theme_colors = {
            "background": QColor(0x1E, 0x1E, 0x1E),
            "overview": QColor(0x25, 0x25, 0x26),
            "view_indicator": QColor(0xFF, 0xFF, 0xFF, 0x40),  # Semi-transparent white
            "view_border": QColor(0xFF, 0xFF, 0xFF, 0x80),
            "handle": QColor(0xFF, 0xFF, 0xFF, 0xA0),
            "marker": QColor(0x00, 0xFF, 0x6A, 0x80),
        }

    def set_duration(self, duration: float) -> None:
        """Set total audio duration.

        Args:
            duration: Duration in seconds.
        """
        self._duration = max(0.0, duration)
        self.update()

    def set_view_range(self, start_time: float, end_time: float) -> None:
        """Set visible view range.

        Args:
            start_time: Start time in seconds.
            end_time: End time in seconds.
        """
        self._view_start_time = max(0.0, min(start_time, self._duration))
        self._view_end_time = max(self._view_start_time, min(end_time, self._duration))
        self.update()

    def set_overview_tile(self, tile: SpectrogramTile | None) -> None:
        """Set overview spectrogram tile.

        Args:
            tile: SpectrogramTile with overview data.
        """
        self._overview_tile = tile
        self._update_overview_image()
        self.update()

    def _update_overview_image(self) -> None:
        """Update overview image from tile."""
        if self._overview_tile is None:
            self._overview_image = None
            return

        tile = self._overview_tile
        width = self.width()
        height = self.height()

        if width <= 0 or height <= 0:
            return

        # Convert spectrogram to image
        spec = tile.spectrogram
        if spec.size == 0:
            self._overview_image = None
            return

        # Normalize spectrogram
        spec_min = np.nanmin(spec)
        spec_max = np.nanmax(spec)
        if spec_max > spec_min:
            spec_norm = (spec - spec_min) / (spec_max - spec_min)
        else:
            spec_norm = np.zeros_like(spec)

        # Create QImage
        # Transpose to get (time, frequency) for display
        spec_display = np.flipud(spec_norm)  # Flip vertically (low freq at bottom)
        spec_display = np.transpose(spec_display)  # Transpose to (time, frequency)

        # Resize to widget dimensions
        from scipy.ndimage import zoom

        if spec_display.shape[0] > 0 and spec_display.shape[1] > 0:
            time_zoom = width / spec_display.shape[0]
            freq_zoom = height / spec_display.shape[1]
            spec_resized = zoom(spec_display, (time_zoom, freq_zoom), order=1)
        else:
            spec_resized = spec_display

        # Apply viridis colormap to normalized spectrogram values
        from matplotlib.cm import get_cmap
        viridis = get_cmap('viridis')
        
        # Apply colormap: takes normalized values (0-1) and returns RGBA (0-1)
        # spec_resized is (time, frequency) with values in [0, 1]
        rgba = viridis(spec_resized)  # Shape: (time, frequency, 4) where 4 is RGBA
        
        # Convert RGBA from [0, 1] to [0, 255] and remove alpha channel for RGB
        rgb = (rgba[:, :, :3] * 255).astype(np.uint8)  # Shape: (time, frequency, 3)
        
        # Create QImage with RGB32 format
        image = QImage(rgb.shape[0], rgb.shape[1], QImage.Format.Format_RGB32)
        for y in range(rgb.shape[1]):
            for x in range(rgb.shape[0]):
                r, g, b = rgb[x, y]
                # QImage.Format_RGB32 uses 0xAARRGGBB format
                pixel_value = (0xFF << 24) | (r << 16) | (g << 8) | b
                image.setPixel(x, y, pixel_value)

        self._overview_image = image

    def set_sample_markers(self, markers: list[tuple[float, float, QColor]]) -> None:
        """Set sample markers to display.

        Args:
            markers: List of (start_time, end_time, color) tuples.
        """
        self._sample_markers = markers
        self.update()

    def set_theme_colors(self, colors: dict[str, QColor]) -> None:
        """Set theme colors.

        Args:
            colors: Dictionary with color definitions.
        """
        self._theme_colors.update(colors)
        self.update()

    def paintEvent(self, event) -> None:
        """Paint navigator scrollbar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Fill background
        painter.fillRect(self.rect(), self._theme_colors["background"])

        if self._duration <= 0:
            return

        # Draw overview spectrogram
        if self._overview_image and not self._overview_image.isNull():
            # Scale image to fit widget
            image_rect = QRectF(0, 0, width, height)
            painter.drawImage(image_rect, self._overview_image)
        else:
            # Draw placeholder
            painter.fillRect(self.rect(), self._theme_colors["overview"])

        # Draw sample markers
        if self._sample_markers:
            pixels_per_second = width / self._duration
            marker_pen = QPen()
            marker_pen.setWidth(2)
            for start_time, end_time, color in self._sample_markers:
                x1 = int(start_time * pixels_per_second)
                x2 = int(end_time * pixels_per_second)
                x1 = max(0, min(x1, width))
                x2 = max(x1, min(x2, width))
                if x2 > x1:
                    painter.setPen(color)
                    painter.drawRect(x1, 0, x2 - x1, height)

        # Draw view indicator
        pixels_per_second = width / self._duration
        view_x1 = int(self._view_start_time * pixels_per_second)
        view_x2 = int(self._view_end_time * pixels_per_second)
        view_x1 = max(0, min(view_x1, width))
        view_x2 = max(view_x1, min(view_x2, width))

        if view_x2 > view_x1:
            # Draw view indicator rectangle
            view_rect = QRect(view_x1, 0, view_x2 - view_x1, height)
            painter.fillRect(view_rect, self._theme_colors["view_indicator"])
            painter.setPen(QPen(self._theme_colors["view_border"], 2))
            painter.drawRect(view_rect)

            # Draw resize handles
            handle_color = self._theme_colors["handle"]
            handle_width = self._resize_handle_width
            # Left handle
            left_handle = QRect(view_x1, 0, handle_width, height)
            painter.fillRect(left_handle, handle_color)
            # Right handle
            right_handle = QRect(view_x2 - handle_width, 0, handle_width, height)
            painter.fillRect(right_handle, handle_color)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press for dragging/resizing."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        x = int(event.position().x())
        width = self.width()
        pixels_per_second = width / self._duration if self._duration > 0 else 0

        view_x1 = int(self._view_start_time * pixels_per_second)
        view_x2 = int(self._view_end_time * pixels_per_second)
        handle_width = self._resize_handle_width

        # Check if clicking on resize handles
        if abs(x - view_x1) < handle_width:
            self._resizing_left = True
            self._dragging = False
            self._drag_start_x = x
            self._drag_start_view_start = self._view_start_time
        elif abs(x - view_x2) < handle_width:
            self._resizing_right = True
            self._dragging = False
            self._drag_start_x = x
            self._drag_start_view_start = self._view_end_time
        elif view_x1 <= x <= view_x2:
            # Clicking in view indicator - drag view
            self._dragging = True
            self._resizing_left = False
            self._resizing_right = False
            self._drag_start_x = x
            self._drag_start_view_start = self._view_start_time
        else:
            # Clicking outside view - jump to position
            time = (x / pixels_per_second) if pixels_per_second > 0 else 0.0
            time = max(0.0, min(time, self._duration))
            view_duration = self._view_end_time - self._view_start_time
            new_start = max(0.0, min(time - view_duration / 2, self._duration - view_duration))
            new_end = new_start + view_duration
            self.set_view_range(new_start, new_end)
            self.view_changed.emit(new_start, new_end)

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move for dragging/resizing."""
        if not (self._dragging or self._resizing_left or self._resizing_right):
            return

        x = int(event.position().x())
        width = self.width()
        pixels_per_second = width / self._duration if self._duration > 0 else 0

        if pixels_per_second <= 0:
            return

        dx = x - self._drag_start_x
        dt = dx / pixels_per_second

        if self._resizing_left:
            # Resize left edge
            new_start = max(0.0, min(self._drag_start_view_start + dt, self._view_end_time - 0.1))
            self.set_view_range(new_start, self._view_end_time)
            self.view_resized.emit(new_start, self._view_end_time)
        elif self._resizing_right:
            # Resize right edge
            new_end = max(self._view_start_time + 0.1, min(self._drag_start_view_start + dt, self._duration))
            self.set_view_range(self._view_start_time, new_end)
            self.view_resized.emit(self._view_start_time, new_end)
        elif self._dragging:
            # Drag view
            view_duration = self._view_end_time - self._view_start_time
            new_start = max(0.0, min(self._drag_start_view_start + dt, self._duration - view_duration))
            new_end = new_start + view_duration
            self.set_view_range(new_start, new_end)
            self.view_changed.emit(new_start, new_end)

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release."""
        self._dragging = False
        self._resizing_left = False
        self._resizing_right = False

    def resizeEvent(self, event) -> None:
        """Handle widget resize."""
        super().resizeEvent(event)
        self._update_overview_image()
        self.update()

    def sizeHint(self):
        """Return preferred size."""
        from PySide6.QtCore import QSize

        return QSize(100, 80)

