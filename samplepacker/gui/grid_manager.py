"""Grid management system for musical and time-based snapping."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GridMode(Enum):
    """Grid snapping modes."""

    FREE_TIME = "free_time"
    MUSICAL_BAR = "musical_bar"


class Subdivision(Enum):
    """Musical subdivisions."""

    WHOLE = 1  # 1 bar
    HALF = 2  # 1/2 bar
    QUARTER = 4  # 1/4 bar
    EIGHTH = 8  # 1/8 bar
    SIXTEENTH = 16  # 1/16 bar
    THIRTY_SECOND = 32  # 1/32 bar


@dataclass
class GridSettings:
    """Grid settings configuration."""

    mode: GridMode = GridMode.FREE_TIME
    enabled: bool = False
    visible: bool = True
    # Free time mode
    snap_interval_sec: float = 0.1
    # Musical bar mode
    bpm: float = 120.0
    subdivision: Subdivision = Subdivision.QUARTER
    time_signature_numerator: int = 4
    time_signature_denominator: int = 4


class GridManager:
    """Manages grid calculations and snapping."""

    def __init__(self, settings: GridSettings | None = None):
        """Initialize grid manager.

        Args:
            settings: Grid settings. If None, uses defaults.
        """
        self.settings = settings or GridSettings()

    def set_mode(self, mode: GridMode) -> None:
        """Set grid mode.

        Args:
            mode: Grid mode (FREE_TIME or MUSICAL_BAR).
        """
        self.settings.mode = mode

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable grid snapping.

        Args:
            enabled: True to enable snapping.
        """
        self.settings.enabled = enabled

    def set_visible(self, visible: bool) -> None:
        """Show or hide grid lines.

        Args:
            visible: True to show grid.
        """
        self.settings.visible = visible

    def snap_time(self, time: float) -> float:
        """Snap time to nearest grid position.

        Args:
            time: Time in seconds.

        Returns:
            Snapped time in seconds.
        """
        if not self.settings.enabled:
            return time

        if self.settings.mode == GridMode.FREE_TIME:
            interval = self.settings.snap_interval_sec
            return round(time / interval) * interval
        elif self.settings.mode == GridMode.MUSICAL_BAR:
            # Calculate beat duration
            beat_duration = 60.0 / self.settings.bpm
            # Calculate subdivision duration
            subdivision_duration = beat_duration / self.settings.subdivision.value
            # Snap to nearest subdivision
            return round(time / subdivision_duration) * subdivision_duration
        else:
            return time

    def get_grid_positions(self, start_time: float, end_time: float) -> list[float]:
        """Get grid positions within a time range.

        Args:
            start_time: Start time in seconds.
            end_time: End time in seconds.

        Returns:
            List of grid positions in seconds.
        """
        positions: list[float] = []

        if self.settings.mode == GridMode.FREE_TIME:
            interval = self.settings.snap_interval_sec
            current = (start_time // interval) * interval
            while current <= end_time:
                positions.append(current)
                current += interval
        elif self.settings.mode == GridMode.MUSICAL_BAR:
            # Calculate beat duration
            beat_duration = 60.0 / self.settings.bpm
            # Calculate subdivision duration
            subdivision_duration = beat_duration / self.settings.subdivision.value
            # Calculate bar duration
            bar_duration = beat_duration * self.settings.time_signature_numerator
            # Start from beginning of nearest bar
            start_bar = (start_time // bar_duration) * bar_duration
            current = start_bar
            while current <= end_time:
                positions.append(current)
                current += subdivision_duration

        return positions

    def get_major_grid_positions(self, start_time: float, end_time: float) -> list[float]:
        """Get major grid positions (for visual emphasis).

        Args:
            start_time: Start time in seconds.
            end_time: End time in seconds.

        Returns:
            List of major grid positions in seconds.
        """
        major_positions: list[float] = []

        if self.settings.mode == GridMode.FREE_TIME:
            # Major positions every 10x the interval
            interval = self.settings.snap_interval_sec * 10
            current = (start_time // interval) * interval
            while current <= end_time:
                major_positions.append(current)
                current += interval
        elif self.settings.mode == GridMode.MUSICAL_BAR:
            # Major positions at bar boundaries
            beat_duration = 60.0 / self.settings.bpm
            bar_duration = beat_duration * self.settings.time_signature_numerator
            current = (start_time // bar_duration) * bar_duration
            while current <= end_time:
                major_positions.append(current)
                current += bar_duration

        return major_positions

    def get_closest_grid_position(self, time: float) -> float:
        """Get closest grid position to a time.

        Args:
            time: Time in seconds.

        Returns:
            Closest grid position in seconds.
        """
        if not self.settings.enabled:
            return time
        return self.snap_time(time)

    def get_snap_distance(self, time: float, pixel_per_second: float) -> float:
        """Calculate snap distance in pixels.

        Args:
            time: Time in seconds.
            pixel_per_second: Pixels per second (zoom level).

        Returns:
            Distance to nearest grid position in pixels.
        """
        snapped = self.snap_time(time)
        return abs(time - snapped) * pixel_per_second

    def is_near_snap_point(self, time: float, pixel_per_second: float, tolerance_px: float = 5.0) -> bool:
        """Check if time is near a snap point.

        Args:
            time: Time in seconds.
            pixel_per_second: Pixels per second (zoom level).
            tolerance_px: Snap tolerance in pixels.

        Returns:
            True if near a snap point.
        """
        distance = self.get_snap_distance(time, pixel_per_second)
        return distance <= tolerance_px

