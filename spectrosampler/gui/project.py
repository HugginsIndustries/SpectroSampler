"""Project file serialization and deserialization for SpectroSampler."""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spectrosampler import __version__
from spectrosampler.detectors.base import Segment
from spectrosampler.gui.grid_manager import GridMode, GridSettings, Subdivision
from spectrosampler.pipeline_settings import ProcessingSettings

logger = logging.getLogger(__name__)

# Project file format version
PROJECT_VERSION = "1.0"


@dataclass
class UIState:
    """UI state for restoration."""

    view_start: float = 0.0
    view_end: float = 60.0
    zoom_level: float = 1.0
    editor_splitter_sizes: list[int] = field(default_factory=list)
    player_splitter_sizes: list[int] = field(default_factory=list)
    main_splitter_sizes: list[int] = field(default_factory=list)
    timeline_splitter_sizes: list[int] = field(default_factory=list)
    player_visible: bool = True
    info_table_visible: bool = True
    waveform_visible: bool = True


@dataclass
class ProjectData:
    """Complete project data structure."""

    version: str = PROJECT_VERSION
    spectrosampler_version: str = __version__
    created: str = ""
    modified: str = ""
    audio_path: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    detection_settings: dict[str, Any] = field(default_factory=dict)
    export_settings: dict[str, Any] = field(default_factory=dict)
    grid_settings: dict[str, Any] = field(default_factory=dict)
    ui_state: UIState = field(default_factory=UIState)


def _segment_to_dict(segment: Segment) -> dict[str, Any]:
    """Convert Segment to dictionary.

    Args:
        segment: Segment to convert.

    Returns:
        Dictionary representation of segment.
    """
    return {
        "start": segment.start,
        "end": segment.end,
        "detector": segment.detector,
        "score": segment.score,
        "attrs": segment.attrs,
    }


def _dict_to_segment(data: dict[str, Any]) -> Segment:
    """Convert dictionary to Segment.

    Args:
        data: Dictionary representation of segment.

    Returns:
        Segment object.
    """
    return Segment(
        start=float(data["start"]),
        end=float(data["end"]),
        detector=str(data["detector"]),
        score=float(data.get("score", 0.0)),
        attrs=dict(data.get("attrs", {})),
    )


def _processing_settings_to_dict(settings: ProcessingSettings) -> dict[str, Any]:
    """Convert ProcessingSettings to dictionary.

    Args:
        settings: ProcessingSettings to convert.

    Returns:
        Dictionary representation of settings.
    """
    return settings.to_dict()


def _dict_to_processing_settings(data: dict[str, Any]) -> ProcessingSettings:
    """Convert dictionary to ProcessingSettings.

    Args:
        data: Dictionary representation of settings.

    Returns:
        ProcessingSettings object.
    """
    return ProcessingSettings.from_dict(data)


def _grid_settings_to_dict(settings: GridSettings) -> dict[str, Any]:
    """Convert GridSettings to dictionary.

    Args:
        settings: GridSettings to convert.

    Returns:
        Dictionary representation of settings.
    """
    return {
        "mode": settings.mode.value if isinstance(settings.mode, GridMode) else settings.mode,
        "enabled": settings.enabled,
        "visible": settings.visible,
        "snap_interval_sec": settings.snap_interval_sec,
        "bpm": settings.bpm,
        "subdivision": (
            settings.subdivision.value
            if isinstance(settings.subdivision, Subdivision)
            else settings.subdivision
        ),
        "time_signature_numerator": settings.time_signature_numerator,
        "time_signature_denominator": settings.time_signature_denominator,
    }


def _dict_to_grid_settings(data: dict[str, Any]) -> GridSettings:
    """Convert dictionary to GridSettings.

    Args:
        data: Dictionary representation of settings.

    Returns:
        GridSettings object.
    """
    # Handle enum values
    mode = data.get("mode", "free_time")
    if isinstance(mode, str):
        mode = GridMode(mode)
    elif isinstance(mode, GridMode):
        pass
    else:
        mode = GridMode.FREE_TIME

    subdivision = data.get("subdivision", 4)
    if isinstance(subdivision, int):
        subdivision = Subdivision(subdivision)
    elif isinstance(subdivision, str):
        subdivision = Subdivision(int(subdivision))
    elif isinstance(subdivision, Subdivision):
        pass
    else:
        subdivision = Subdivision.QUARTER

    return GridSettings(
        mode=mode,
        enabled=bool(data.get("enabled", False)),
        visible=bool(data.get("visible", True)),
        snap_interval_sec=float(data.get("snap_interval_sec", 0.1)),
        bpm=float(data.get("bpm", 120.0)),
        subdivision=subdivision,
        time_signature_numerator=int(data.get("time_signature_numerator", 4)),
        time_signature_denominator=int(data.get("time_signature_denominator", 4)),
    )


def _coerce_splitter_sizes(raw: Any) -> list[int]:
    """Convert persisted splitter sizes into a clean integer list."""
    if not isinstance(raw, list):
        return []
    result: list[int] = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        result.append(max(0, value))
    return result


def save_project(project_data: ProjectData, path: Path) -> None:
    """Save project data to file.

    Args:
        project_data: Project data to save.
        path: Path to save project file.

    Raises:
        IOError: If file cannot be written.
        ValueError: If project data is invalid.
    """
    # Update modified timestamp
    project_data.modified = datetime.now(UTC).isoformat()

    # Convert ProjectData to dictionary
    data_dict = {
        "version": project_data.version,
        "spectrosampler_version": project_data.spectrosampler_version,
        "created": project_data.created,
        "modified": project_data.modified,
        "audio_path": project_data.audio_path,
        "segments": project_data.segments,
        "detection_settings": project_data.detection_settings,
        "export_settings": project_data.export_settings,
        "grid_settings": project_data.grid_settings,
        "ui_state": {
            "view_start": project_data.ui_state.view_start,
            "view_end": project_data.ui_state.view_end,
            "zoom_level": project_data.ui_state.zoom_level,
            "editor_splitter_sizes": project_data.ui_state.editor_splitter_sizes,
            "player_splitter_sizes": project_data.ui_state.player_splitter_sizes,
            "main_splitter_sizes": project_data.ui_state.main_splitter_sizes,
            "timeline_splitter_sizes": project_data.ui_state.timeline_splitter_sizes,
            "player_visible": project_data.ui_state.player_visible,
            "info_table_visible": project_data.ui_state.info_table_visible,
            "waveform_visible": project_data.ui_state.waveform_visible,
        },
    }

    # Write to file
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, indent=2, ensure_ascii=False)
        logger.info(f"Project saved to {path}")
    except OSError as exc:
        logger.error("Failed to save project to %s: %s", path, exc, exc_info=exc)
        raise OSError(f"Failed to save project file: {exc}") from exc
    except (TypeError, ValueError) as exc:
        logger.error("Project data serialisation failed for %s: %s", path, exc, exc_info=exc)
        raise ValueError(f"Project data could not be serialised: {exc}") from exc


def load_project(path: Path) -> ProjectData:
    """Load project data from file.

    Args:
        path: Path to project file.

    Returns:
        ProjectData object.

    Raises:
        FileNotFoundError: If project file does not exist.
        ValueError: If project file is invalid or incompatible.
        json.JSONDecodeError: If project file is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Project file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            data_dict = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in project file %s: %s", path, exc, exc_info=exc)
        raise ValueError(f"Invalid project file format: {exc}") from exc
    except OSError as exc:
        logger.error("Failed to read project file %s: %s", path, exc, exc_info=exc)
        raise OSError(f"Failed to read project file: {exc}") from exc

    # Validate version
    version = data_dict.get("version", "0.0")
    if version != PROJECT_VERSION:
        logger.warning(
            f"Project file version {version} differs from current version {PROJECT_VERSION}"
        )
        # For now, we'll allow loading but warn
        # In the future, we could add version migration logic here

    # Extract UI state
    ui_state_data = data_dict.get("ui_state", {})
    ui_state = UIState(
        view_start=float(ui_state_data.get("view_start", 0.0)),
        view_end=float(ui_state_data.get("view_end", 60.0)),
        zoom_level=float(ui_state_data.get("zoom_level", 1.0)),
        editor_splitter_sizes=_coerce_splitter_sizes(ui_state_data.get("editor_splitter_sizes")),
        player_splitter_sizes=_coerce_splitter_sizes(ui_state_data.get("player_splitter_sizes")),
        main_splitter_sizes=_coerce_splitter_sizes(ui_state_data.get("main_splitter_sizes")),
        timeline_splitter_sizes=_coerce_splitter_sizes(
            ui_state_data.get("timeline_splitter_sizes")
        ),
        player_visible=bool(ui_state_data.get("player_visible", True)),
        info_table_visible=bool(ui_state_data.get("info_table_visible", True)),
        waveform_visible=bool(ui_state_data.get("waveform_visible", True)),
    )

    project_data = ProjectData(
        version=version,
        spectrosampler_version=data_dict.get("spectrosampler_version", "0.1.0"),
        created=data_dict.get("created", ""),
        modified=data_dict.get("modified", ""),
        audio_path=str(data_dict.get("audio_path", "")),
        segments=list(data_dict.get("segments", [])),
        detection_settings=dict(data_dict.get("detection_settings", {})),
        export_settings=dict(data_dict.get("export_settings", {})),
        grid_settings=dict(data_dict.get("grid_settings", {})),
        ui_state=ui_state,
    )

    logger.info(f"Project loaded from {path}")
    return project_data
