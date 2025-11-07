"""Utilities to detect overlaps and duplicates between existing and new segments."""

from __future__ import annotations

from dataclasses import dataclass

from spectrosampler.detectors.base import Segment


@dataclass(frozen=True)
class OverlapReport:
    overlaps: list[tuple[int, int]]
    duplicates: list[tuple[int, int]]


def is_duplicate(a: Segment, b: Segment, tolerance_ms: float = 5.0) -> bool:
    """Return True if starts and ends are within tolerance regardless of detector.

    Args:
        a: First segment
        b: Second segment
        tolerance_ms: Milliseconds tolerance for start/end equality
    """
    tol = max(0.0, float(tolerance_ms)) / 1000.0
    return abs(a.start - b.start) <= tol and abs(a.end - b.end) <= tol


def is_overlap(a: Segment, b: Segment) -> bool:
    """Return True if segments overlap in time (no tolerance)."""
    return a.overlaps(b, gap_ms=0.0)


def find_overlaps(
    existing: list[Segment], new: list[Segment], tolerance_ms: float = 5.0
) -> OverlapReport:
    """Find overlaps and duplicates between existing and new segments.

    Returns lists of index pairs (existing_idx, new_idx).
    """
    overlaps: list[tuple[int, int]] = []
    duplicates: list[tuple[int, int]] = []

    if not existing or not new:
        return OverlapReport(overlaps=overlaps, duplicates=duplicates)

    for i, e in enumerate(existing):
        for j, n in enumerate(new):
            if is_duplicate(e, n, tolerance_ms=tolerance_ms):
                duplicates.append((i, j))
            elif is_overlap(e, n):
                overlaps.append((i, j))

    return OverlapReport(overlaps=overlaps, duplicates=duplicates)
