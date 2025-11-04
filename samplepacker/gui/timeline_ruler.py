"""Timeline ruler widget for DAW-style time display."""

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget


class TimelineRuler(QWidget):
    """Timeline ruler widget showing time markers."""

    time_clicked = Signal(float)  # Emitted when ruler is clicked (time in seconds)

    def __init__(self, parent: QWidget | None = None):
        """Initialize timeline ruler.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setMaximumHeight(100)
        self._duration = 0.0
        self._start_time = 0.0
        self._end_time = 0.0
        self._pixels_per_second = 100.0
        self._major_tick_interval = 60.0  # 1 minute
        self._minor_tick_interval = 10.0  # 10 seconds
        self._theme_colors = {
            "background": QColor(0x25, 0x25, 0x26),
            "text": QColor(0xCC, 0xCC, 0xCC),
            "grid": QColor(0x3C, 0x3C, 0x3C, 0x80),
            "grid_major": QColor(0x45, 0x45, 0x45, 0xA0),
        }

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
            end_time: End time in seconds.
        """
        self._start_time = max(0.0, start_time)
        self._end_time = min(self._duration, end_time)
        self.update()

    def set_pixels_per_second(self, pixels_per_second: float) -> None:
        """Set zoom level (pixels per second).

        Args:
            pixels_per_second: Pixels per second.
        """
        self._pixels_per_second = max(1.0, pixels_per_second)
        # Adjust tick intervals based on zoom
        if self._pixels_per_second > 1000:
            self._major_tick_interval = 1.0  # 1 second
            self._minor_tick_interval = 0.1  # 100ms
        elif self._pixels_per_second > 100:
            self._major_tick_interval = 10.0  # 10 seconds
            self._minor_tick_interval = 1.0  # 1 second
        elif self._pixels_per_second > 10:
            self._major_tick_interval = 60.0  # 1 minute
            self._minor_tick_interval = 10.0  # 10 seconds
        else:
            self._major_tick_interval = 300.0  # 5 minutes
            self._minor_tick_interval = 60.0  # 1 minute
        self.update()

    def set_theme_colors(self, colors: dict[str, QColor]) -> None:
        """Set theme colors.

        Args:
            colors: Dictionary with color definitions.
        """
        self._theme_colors.update(colors)
        self.update()

    def paintEvent(self, event) -> None:
        """Paint timeline ruler."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fill background
        painter.fillRect(self.rect(), self._theme_colors["background"])

        if self._duration <= 0:
            return

        # Calculate visible range
        visible_start = max(0.0, self._start_time)
        visible_end = min(self._duration, self._end_time)
        visible_duration = visible_end - visible_start

        if visible_duration <= 0:
            return

        # Calculate pixel positions
        width = self.width()
        height = self.height()

        # Draw minor ticks
        minor_pen = QPen(self._theme_colors["grid"], 1)
        painter.setPen(minor_pen)
        minor_tick = self._minor_tick_interval
        current = (visible_start // minor_tick) * minor_tick
        while current <= visible_end:
            x = int((current - visible_start) * self._pixels_per_second)
            if 0 <= x <= width:
                painter.drawLine(x, 0, x, height)
            current += minor_tick

        # Draw major ticks and labels
        major_pen = QPen(self._theme_colors["grid_major"], 2)
        painter.setPen(major_pen)
        text_pen = QPen(self._theme_colors["text"], 1)
        font = QFont("Arial", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)

        major_tick = self._major_tick_interval
        current = (visible_start // major_tick) * major_tick
        while current <= visible_end:
            x = int((current - visible_start) * self._pixels_per_second)
            if 0 <= x <= width:
                # Draw tick line
                painter.setPen(major_pen)
                painter.drawLine(x, 0, x, height)

                # Draw time label
                painter.setPen(text_pen)
                time_str = self._format_time(current)
                label_width = fm.horizontalAdvance(time_str)
                label_x = max(2, min(x - label_width // 2, width - label_width - 2))
                painter.drawText(label_x, height - 4, time_str)

            current += major_tick

        # Draw bottom border
        border_pen = QPen(self._theme_colors["grid"], 1)
        painter.setPen(border_pen)
        painter.drawLine(0, height - 1, width, height - 1)

    def _format_time(self, time_sec: float) -> str:
        """Format time as string.

        Args:
            time_sec: Time in seconds.

        Returns:
            Formatted time string.
        """
        hours = int(time_sec // 3600)
        minutes = int((time_sec % 3600) // 60)
        seconds = int(time_sec % 60)
        milliseconds = int((time_sec % 1) * 1000)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        elif minutes > 0:
            return f"{minutes:02d}:{seconds:02d}"
        else:
            if self._pixels_per_second > 100:
                return f"{seconds}.{milliseconds // 100:01d}s"
            else:
                return f"{seconds}s"

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to jump to time position."""
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().x()
            visible_start = max(0.0, self._start_time)
            time = visible_start + (x / self._pixels_per_second)
            time = max(0.0, min(time, self._duration))
            self.time_clicked.emit(time)

    def sizeHint(self):
        """Return preferred size."""
        from PySide6.QtCore import QSize

        return QSize(100, 50)

