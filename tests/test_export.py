"""Regression tests covering marker export helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from spectrosampler.detectors.base import Segment
from spectrosampler.export import (
    export_markers_audacity,
    export_markers_reaper,
    export_timestamps_csv,
)


def _build_segments() -> list[Segment]:
    """Create a deterministic set of segments for export validation."""

    return [
        Segment(start=0.25, end=0.8, detector="flux", score=0.42),
        Segment(start=1.0, end=2.25, detector="vad", score=0.87),
    ]


def test_export_markers_audacity_schema(tmp_path: Path) -> None:
    """Ensure Audacity labels match the published tab-delimited format."""

    segments = _build_segments()
    output = tmp_path / "audacity_labels.txt"

    export_markers_audacity(segments, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "0.250\t0.800\tsample_000 flux",
        "1.000\t2.250\tsample_001 vad",
    ]


def test_export_markers_audacity_includes_padding(tmp_path: Path) -> None:
    """Confirm Audacity label export honors the optional padding flags."""

    segments = _build_segments()
    output = tmp_path / "audacity_labels_padded.txt"

    export_markers_audacity(
        segments,
        output,
        include_padding=True,
        pre_pad_ms=50,
        post_pad_ms=125,
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "0.200\t0.925\tsample_000 flux",
        "0.950\t2.375\tsample_001 vad",
    ]


def test_export_markers_reaper_schema(tmp_path: Path) -> None:
    """Ensure REAPER region CSV export writes the documented header and rows."""

    segments = _build_segments()
    output = tmp_path / "reaper_regions.csv"

    export_markers_reaper(segments, output)

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Name", "Start", "End", "Length"],
        ["sample_000 flux", "0.250000", "0.800000", "0.550000"],
        ["sample_001 vad", "1.000000", "2.250000", "1.250000"],
    ]


def test_export_markers_reaper_includes_padding(tmp_path: Path) -> None:
    """Confirm REAPER CSV export adjusts start/end when padding is requested."""

    segments = _build_segments()
    output = tmp_path / "reaper_regions_padded.csv"

    export_markers_reaper(
        segments,
        output,
        include_padding=True,
        pre_pad_ms=50,
        post_pad_ms=125,
    )

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Name", "Start", "End", "Length"],
        ["sample_000 flux", "0.200000", "0.925000", "0.725000"],
        ["sample_001 vad", "0.950000", "2.375000", "1.425000"],
    ]


def test_export_timestamps_csv_schema(tmp_path: Path) -> None:
    """Verify timestamp CSV export produces the documented header and values."""

    segments = _build_segments()
    output = tmp_path / "timestamps.csv"

    export_timestamps_csv(segments, output)

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["id", "start_sec", "end_sec", "duration_sec", "detector", "score"],
        ["0", "0.250", "0.800", "0.550", "flux", "0.420"],
        ["1", "1.000", "2.250", "1.250", "vad", "0.870"],
    ]


def test_export_timestamps_csv_includes_padding(tmp_path: Path) -> None:
    """Confirm timestamp CSV export applies padding adjustments when enabled."""

    segments = _build_segments()
    output = tmp_path / "timestamps_padded.csv"

    export_timestamps_csv(
        segments,
        output,
        include_padding=True,
        pre_pad_ms=50,
        post_pad_ms=125,
    )

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["id", "start_sec", "end_sec", "duration_sec", "detector", "score"],
        ["0", "0.200", "0.925", "0.725", "flux", "0.420"],
        ["1", "0.950", "2.375", "1.425", "vad", "0.870"],
    ]
