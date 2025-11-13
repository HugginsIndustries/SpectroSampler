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
    start_diff = abs(a.start - b.start)
    end_diff = abs(a.end - b.end)
    # Use a small epsilon to handle floating point precision issues
    epsilon = 1e-9
    return (start_diff <= tol + epsilon) and (end_diff <= tol + epsilon)


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


def find_overlaps_within_segments(segments: list[Segment]) -> list[list[int]]:
    """Find all overlapping groups within a single segment list.

    Uses a union-find approach to ensure all transitive overlaps are grouped together.

    Args:
        segments: List of segments to check for overlaps.

    Returns:
        List of groups, where each group is a list of indices that overlap with each other.
    """
    if not segments:
        return []

    # Build overlap pairs first
    overlap_pairs: list[tuple[int, int]] = []
    for i, seg_a in enumerate(segments):
        for j in range(i + 1, len(segments)):
            seg_b = segments[j]
            if is_overlap(seg_a, seg_b):
                overlap_pairs.append((i, j))

    if not overlap_pairs:
        return []

    # Union-find to group all transitive overlaps
    parent = list(range(len(segments)))

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]

    def union(x: int, y: int) -> None:
        root_x = find(x)
        root_y = find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    # Union all overlap pairs
    for i, j in overlap_pairs:
        union(i, j)

    # Group indices by their root
    groups_dict: dict[int, list[int]] = {}
    for i in range(len(segments)):
        root = find(i)
        if root not in groups_dict:
            groups_dict[root] = []
        groups_dict[root].append(i)

    # Return only groups with more than one element
    overlap_groups = [sorted(group) for group in groups_dict.values() if len(group) > 1]
    return overlap_groups


def find_duplicates_within_segments(
    segments: list[Segment], tolerance_ms: float = 5.0
) -> list[list[int]]:
    """Find all duplicate groups within a single segment list.

    Uses a union-find approach to ensure all transitive duplicates are grouped together.

    Args:
        segments: List of segments to check for duplicates.
        tolerance_ms: Milliseconds tolerance for start/end equality.

    Returns:
        List of groups, where each group is a list of indices that are duplicates of each other.
    """
    if not segments:
        return []

    # Build duplicate pairs first
    # Check all pairs to ensure we catch all duplicates, even with floating point precision issues
    duplicate_pairs: list[tuple[int, int]] = []
    for i, seg_a in enumerate(segments):
        for j in range(i + 1, len(segments)):
            seg_b = segments[j]
            if is_duplicate(seg_a, seg_b, tolerance_ms):
                duplicate_pairs.append((i, j))

    if not duplicate_pairs:
        return []

    # Union-find to group all transitive duplicates
    parent = list(range(len(segments)))

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]

    def union(x: int, y: int) -> None:
        root_x = find(x)
        root_y = find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    # Union all duplicate pairs
    for i, j in duplicate_pairs:
        union(i, j)

    # Group indices by their root
    groups_dict: dict[int, list[int]] = {}
    for i in range(len(segments)):
        root = find(i)
        if root not in groups_dict:
            groups_dict[root] = []
        groups_dict[root].append(i)

    # Return only groups with more than one element
    duplicate_groups = [sorted(group) for group in groups_dict.values() if len(group) > 1]
    return duplicate_groups
