"""Settings manager for persistent application preferences."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manages persistent application settings using QSettings."""

    def __init__(self):
        """Initialize settings manager."""
        # Use QSettings with organization and application name
        self._settings = QSettings("SpectroSampler", "SpectroSampler")

    def get_recent_projects(self, max_count: int = 10) -> list[tuple[Path, datetime]]:
        """Get list of recent projects.

        Args:
            max_count: Maximum number of recent projects to return.

        Returns:
            List of tuples (path, timestamp), sorted by most recent first.
        """
        projects = []
        paths = self._settings.value("recentProjects", [])
        timestamps = self._settings.value("recentProjectsTimestamps", [])

        if not isinstance(paths, list):
            paths = []
        if not isinstance(timestamps, list):
            timestamps = []

        # Pair up paths and timestamps
        for path_str, ts_str in zip(paths[:max_count], timestamps[:max_count], strict=True):
            try:
                path = Path(path_str)
                if path.exists():  # Only include if file still exists
                    timestamp = datetime.fromisoformat(ts_str)
                    projects.append((path, timestamp))
            except (ValueError, TypeError, OSError):
                continue

        # Sort by timestamp (most recent first)
        projects.sort(key=lambda x: x[1], reverse=True)
        return projects[:max_count]

    def add_recent_project(self, path: Path, max_count: int = 10) -> None:
        """Add project to recent projects list.

        Args:
            path: Path to project file.
            max_count: Maximum number of recent projects to keep.
        """
        if not path.exists():
            return

        # Get current list
        projects = self.get_recent_projects(max_count=max_count + 1)

        # Remove if already exists
        path_str = str(path)
        projects = [(p, ts) for p, ts in projects if str(p) != path_str]

        # Add new entry at beginning
        projects.insert(0, (path, datetime.now()))

        # Limit to max_count
        projects = projects[:max_count]

        # Save back to settings
        paths = [str(p) for p, _ in projects]
        timestamps = [ts.isoformat() for _, ts in projects]
        self._settings.setValue("recentProjects", paths)
        self._settings.setValue("recentProjectsTimestamps", timestamps)
        self._settings.sync()

    def clear_recent_projects(self) -> None:
        """Clear all recent projects."""
        self._settings.remove("recentProjects")
        self._settings.remove("recentProjectsTimestamps")
        self._settings.sync()

    def get_recent_audio_files(self, max_count: int = 10) -> list[tuple[Path, datetime]]:
        """Get list of recent audio files.

        Args:
            max_count: Maximum number of recent audio files to return.

        Returns:
            List of tuples (path, timestamp), sorted by most recent first.
        """
        files = []
        paths = self._settings.value("recentAudioFiles", [])
        timestamps = self._settings.value("recentAudioFilesTimestamps", [])

        if not isinstance(paths, list):
            paths = []
        if not isinstance(timestamps, list):
            timestamps = []

        # Pair up paths and timestamps
        for path_str, ts_str in zip(paths[:max_count], timestamps[:max_count], strict=True):
            try:
                path = Path(path_str)
                if path.exists():  # Only include if file still exists
                    timestamp = datetime.fromisoformat(ts_str)
                    files.append((path, timestamp))
            except (ValueError, TypeError, OSError):
                continue

        # Sort by timestamp (most recent first)
        files.sort(key=lambda x: x[1], reverse=True)
        return files[:max_count]

    def add_recent_audio_file(self, path: Path, max_count: int = 10) -> None:
        """Add audio file to recent files list.

        Args:
            path: Path to audio file.
            max_count: Maximum number of recent audio files to keep.
        """
        if not path.exists():
            return

        # Get current list
        files = self.get_recent_audio_files(max_count=max_count + 1)

        # Remove if already exists
        path_str = str(path)
        files = [(p, ts) for p, ts in files if str(p) != path_str]

        # Add new entry at beginning
        files.insert(0, (path, datetime.now()))

        # Limit to max_count
        files = files[:max_count]

        # Save back to settings
        paths = [str(p) for p, _ in files]
        timestamps = [ts.isoformat() for _, ts in files]
        self._settings.setValue("recentAudioFiles", paths)
        self._settings.setValue("recentAudioFilesTimestamps", timestamps)
        self._settings.sync()

    def clear_recent_audio_files(self) -> None:
        """Clear all recent audio files."""
        self._settings.remove("recentAudioFiles")
        self._settings.remove("recentAudioFilesTimestamps")
        self._settings.sync()

    def get_detection_max_samples(self, default: int = 256) -> int:
        """Return the stored max-sample cap for detection, clamped to the UI bounds."""
        value = self._settings.value("detection/maxSamples", default)
        try:
            max_samples = int(value)
        except (TypeError, ValueError):
            max_samples = int(default)
        # Clamp so corrupted settings never break the slider.
        return max(1, min(10_000, max_samples))

    def set_detection_max_samples(self, max_samples: int) -> None:
        """Persist the detection max-sample cap so the slider restores on restart."""
        clamped = max(1, min(10_000, int(max_samples)))
        self._settings.setValue("detection/maxSamples", clamped)
        self._settings.sync()

    # Overlap dialog settings
    def get_show_overlap_dialog(self) -> bool:
        """Return True to show overlap dialog on conflicts (default True)."""
        value = self._settings.value("showOverlapDialog", True, type=bool)
        if value is None:
            return True
        return bool(value)

    def set_show_overlap_dialog(self, enabled: bool) -> None:
        """Enable/disable showing the overlap dialog on conflicts."""
        self._settings.setValue("showOverlapDialog", bool(enabled))
        self._settings.sync()

    def get_overlap_default_behavior(self) -> str:
        """Get default overlap behavior: discard_duplicates|discard_overlaps|keep_all."""
        val = self._settings.value("overlapDefaultBehavior", "discard_duplicates")
        try:
            s = str(val)
        except (TypeError, ValueError) as exc:
            logger.debug("Invalid overlap behavior setting %s: %s", val, exc, exc_info=exc)
            s = "discard_duplicates"
        if s not in ("discard_duplicates", "discard_overlaps", "keep_all"):
            s = "discard_duplicates"
        return s

    def set_overlap_default_behavior(self, behavior: str) -> None:
        """Set default overlap behavior.

        behavior must be one of: discard_duplicates, discard_overlaps, keep_all.
        """
        if behavior not in ("discard_duplicates", "discard_overlaps", "keep_all"):
            behavior = "discard_duplicates"
        self._settings.setValue("overlapDefaultBehavior", behavior)
        self._settings.sync()

    def get_auto_save_enabled(self) -> bool:
        """Get auto-save enabled setting.

        Returns:
            True if auto-save is enabled, False otherwise. Default: True.
        """
        value = self._settings.value("autoSaveEnabled", True, type=bool)
        if value is None:
            return True
        return bool(value)

    def set_auto_save_enabled(self, enabled: bool) -> None:
        """Set auto-save enabled setting.

        Args:
            enabled: True to enable auto-save, False to disable.
        """
        self._settings.setValue("autoSaveEnabled", enabled)
        self._settings.sync()

    def get_auto_save_interval(self) -> int:
        """Get auto-save interval in minutes.

        Returns:
            Auto-save interval in minutes. Default: 5.
        """
        value = self._settings.value("autoSaveInterval", 5, type=int)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 5

    def set_auto_save_interval(self, minutes: int) -> None:
        """Set auto-save interval in minutes.

        Args:
            minutes: Auto-save interval in minutes (1-60).
        """
        minutes = max(1, min(60, minutes))  # Clamp to 1-60
        self._settings.setValue("autoSaveInterval", minutes)
        self._settings.sync()

    def get_max_recent_projects(self) -> int:
        """Get maximum number of recent projects to keep.

        Returns:
            Maximum number of recent projects. Default: 10.
        """
        value = self._settings.value("maxRecentProjects", 10, type=int)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10

    def set_max_recent_projects(self, count: int) -> None:
        """Set maximum number of recent projects to keep.

        Args:
            count: Maximum number of recent projects (1-20).
        """
        count = max(1, min(20, count))  # Clamp to 1-20
        self._settings.setValue("maxRecentProjects", count)
        self._settings.sync()

    def get_max_recent_audio_files(self) -> int:
        """Get maximum number of recent audio files to keep.

        Returns:
            Maximum number of recent audio files. Default: 10.
        """
        value = self._settings.value("maxRecentAudioFiles", 10, type=int)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10

    def set_max_recent_audio_files(self, count: int) -> None:
        """Set maximum number of recent audio files to keep.

        Args:
            count: Maximum number of recent audio files (1-20).
        """
        count = max(1, min(20, count))  # Clamp to 1-20
        self._settings.setValue("maxRecentAudioFiles", count)
        self._settings.sync()

    def get_theme_preference(self) -> str:
        """Return stored theme preference ('system', 'dark', or 'light')."""
        value = self._settings.value("themePreference", "system")
        try:
            pref = str(value)
        except (TypeError, ValueError):
            pref = "system"
        if pref not in {"system", "dark", "light"}:
            pref = "system"
        return pref

    def set_theme_preference(self, preference: str) -> None:
        """Persist theme preference."""
        if preference not in {"system", "dark", "light"}:
            preference = "system"
        self._settings.setValue("themePreference", preference)
        self._settings.sync()

    def get_window_geometry(self) -> dict[str, Any]:
        """Get saved window geometry.

        Returns:
            Dictionary with window geometry (size, position, splitter sizes, etc.).
        """
        geometry = {}

        # Get size as list of ints
        size = self._settings.value("windowSize", None)
        if size is not None:
            if isinstance(size, list):
                geometry["size"] = [
                    int(s) if s is not None else 1400 if i == 0 else 900 for i, s in enumerate(size)
                ]
            else:
                geometry["size"] = size

        # Get position as list of ints
        pos = self._settings.value("windowPosition", None)
        if pos is not None:
            if isinstance(pos, list):
                geometry["position"] = [int(p) if p is not None else 100 for p in pos]
            else:
                geometry["position"] = pos

        # Get splitter sizes as lists of ints
        main_splitter = self._settings.value("mainSplitterSizes", None)
        if main_splitter is not None:
            if isinstance(main_splitter, list):
                geometry["mainSplitterSizes"] = [
                    int(s) if s is not None else 0 for s in main_splitter
                ]
            else:
                geometry["mainSplitterSizes"] = main_splitter

        editor_splitter = self._settings.value("editorSplitterSizes", None)
        if editor_splitter is not None:
            if isinstance(editor_splitter, list):
                geometry["editorSplitterSizes"] = [
                    int(s) if s is not None else 0 for s in editor_splitter
                ]
            else:
                geometry["editorSplitterSizes"] = editor_splitter

        player_splitter = self._settings.value("playerSplitterSizes", None)
        if player_splitter is not None:
            if isinstance(player_splitter, list):
                geometry["playerSplitterSizes"] = [
                    int(s) if s is not None else 0 for s in player_splitter
                ]
            else:
                geometry["playerSplitterSizes"] = player_splitter

        geometry["infoTableVisible"] = self._settings.value("infoTableVisible", True, type=bool)
        geometry["playerVisible"] = self._settings.value("playerVisible", True, type=bool)
        return geometry

    def set_window_geometry(self, geometry: dict[str, Any]) -> None:
        """Set window geometry.

        Args:
            geometry: Dictionary with window geometry to save.
        """
        if "size" in geometry:
            self._settings.setValue("windowSize", geometry["size"])
        if "position" in geometry:
            self._settings.setValue("windowPosition", geometry["position"])
        if "mainSplitterSizes" in geometry:
            self._settings.setValue("mainSplitterSizes", geometry["mainSplitterSizes"])
        if "editorSplitterSizes" in geometry:
            self._settings.setValue("editorSplitterSizes", geometry["editorSplitterSizes"])
        if "playerSplitterSizes" in geometry:
            self._settings.setValue("playerSplitterSizes", geometry["playerSplitterSizes"])
        if "infoTableVisible" in geometry:
            self._settings.setValue("infoTableVisible", geometry["infoTableVisible"])
        if "playerVisible" in geometry:
            self._settings.setValue("playerVisible", geometry["playerVisible"])
        self._settings.sync()
