"""Tests for overlap and duplicate detection within segment lists."""

from spectrosampler.detectors.base import Segment
from spectrosampler.gui.overlap_detector import (
    find_duplicates_within_segments,
    find_overlaps_within_segments,
)


def test_find_overlaps_within_segments_empty():
    """Test finding overlaps in empty list."""
    result = find_overlaps_within_segments([])
    assert result == []


def test_find_overlaps_within_segments_no_overlaps():
    """Test finding overlaps when none exist."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=3.0, end=4.0, detector="test", score=1.0),
        Segment(start=5.0, end=6.0, detector="test", score=1.0),
    ]
    result = find_overlaps_within_segments(segments)
    assert result == []


def test_find_overlaps_within_segments_simple_overlap():
    """Test finding a simple overlap between two segments."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=1.5, end=3.0, detector="test", score=1.0),
    ]
    result = find_overlaps_within_segments(segments)
    assert len(result) == 1
    assert set(result[0]) == {0, 1}


def test_find_overlaps_within_segments_multiple_groups():
    """Test finding multiple overlapping groups."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),  # Group 1
        Segment(start=1.5, end=2.5, detector="test", score=1.0),  # Group 1
        Segment(start=5.0, end=6.0, detector="test", score=1.0),  # Group 2
        Segment(start=5.5, end=6.5, detector="test", score=1.0),  # Group 2
        Segment(start=5.8, end=7.0, detector="test", score=1.0),  # Group 2
    ]
    result = find_overlaps_within_segments(segments)
    assert len(result) == 2
    # First group should have indices 0, 1
    assert set(result[0]) == {0, 1}
    # Second group should have indices 2, 3, 4
    assert set(result[1]) == {2, 3, 4}


def test_find_overlaps_within_segments_nested_overlap():
    """Test finding nested overlaps."""
    segments = [
        Segment(start=1.0, end=5.0, detector="test", score=1.0),  # Contains others
        Segment(start=2.0, end=3.0, detector="test", score=1.0),  # Nested
        Segment(start=3.5, end=4.5, detector="test", score=1.0),  # Nested
    ]
    result = find_overlaps_within_segments(segments)
    assert len(result) == 1
    # All three should be in the same group
    assert set(result[0]) == {0, 1, 2}


def test_find_overlaps_within_segments_adjacent_no_overlap():
    """Test that adjacent segments (touching) are considered overlapping."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=2.0, end=3.0, detector="test", score=1.0),  # Touches - considered overlapping
    ]
    result = find_overlaps_within_segments(segments)
    # Segments that touch are considered overlapping (gap_ms=0.0 means no gap tolerance)
    assert len(result) == 1
    assert set(result[0]) == {0, 1}


def test_find_overlaps_within_segments_transitive():
    """Test that overlap detection is transitive (if A overlaps B and B overlaps C, all are grouped)."""
    segments = [
        Segment(start=1.0, end=3.0, detector="test", score=1.0),  # A: overlaps B
        Segment(start=2.0, end=4.0, detector="test", score=1.0),  # B: overlaps A and C
        Segment(start=3.5, end=5.0, detector="test", score=1.0),  # C: overlaps B but not A
    ]
    result = find_overlaps_within_segments(segments)
    # All three should be in the same group (transitive closure)
    assert len(result) == 1
    assert set(result[0]) == {0, 1, 2}


def test_find_duplicates_within_segments_empty():
    """Test finding duplicates in empty list."""
    result = find_duplicates_within_segments([])
    assert result == []


def test_find_duplicates_within_segments_no_duplicates():
    """Test finding duplicates when none exist."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=3.0, end=4.0, detector="test", score=1.0),
        Segment(start=5.0, end=6.0, detector="test", score=1.0),
    ]
    result = find_duplicates_within_segments(segments)
    assert result == []


def test_find_duplicates_within_segments_exact_duplicates():
    """Test finding exact duplicates."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test1", score=1.0),
        Segment(start=1.0, end=2.0, detector="test2", score=0.8),  # Same times, different detector
        Segment(start=3.0, end=4.0, detector="test", score=1.0),
    ]
    result = find_duplicates_within_segments(segments, tolerance_ms=5.0)
    assert len(result) == 1
    assert set(result[0]) == {0, 1}


def test_find_duplicates_within_segments_within_tolerance():
    """Test finding duplicates within tolerance."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=1.003, end=2.003, detector="test", score=1.0),  # Within 5ms tolerance
        Segment(start=1.01, end=2.01, detector="test", score=1.0),  # Outside 5ms tolerance
    ]
    result = find_duplicates_within_segments(segments, tolerance_ms=5.0)
    assert len(result) == 1
    assert set(result[0]) == {0, 1}


def test_find_duplicates_within_segments_multiple_groups():
    """Test finding multiple duplicate groups."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),  # Group 1
        Segment(start=1.0, end=2.0, detector="test", score=1.0),  # Group 1
        Segment(start=5.0, end=6.0, detector="test", score=1.0),  # Group 2
        Segment(start=5.0, end=6.0, detector="test", score=1.0),  # Group 2
        Segment(start=5.0, end=6.0, detector="test", score=1.0),  # Group 2
    ]
    result = find_duplicates_within_segments(segments, tolerance_ms=5.0)
    assert len(result) == 2
    # First group should have indices 0, 1
    assert set(result[0]) == {0, 1}
    # Second group should have indices 2, 3, 4
    assert set(result[1]) == {2, 3, 4}


def test_find_duplicates_within_segments_custom_tolerance():
    """Test finding duplicates with custom tolerance."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=1.01, end=2.01, detector="test", score=1.0),  # 10ms difference
    ]
    # With 5ms tolerance, should not be duplicates
    result_5ms = find_duplicates_within_segments(segments, tolerance_ms=5.0)
    assert result_5ms == []
    # With 20ms tolerance, should be duplicates
    result_20ms = find_duplicates_within_segments(segments, tolerance_ms=20.0)
    assert len(result_20ms) == 1
    assert set(result_20ms[0]) == {0, 1}


def test_find_duplicates_vs_overlaps_distinction():
    """Test that duplicates and overlaps are distinct concepts."""
    # Overlapping but not duplicate
    segments_overlap = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=1.5, end=3.0, detector="test", score=1.0),  # Overlaps but different times
    ]
    overlaps = find_overlaps_within_segments(segments_overlap)
    duplicates = find_duplicates_within_segments(segments_overlap, tolerance_ms=5.0)
    assert len(overlaps) == 1
    assert duplicates == []

    # Duplicate but not overlapping (same times, but that's still overlap technically)
    # Actually, if start/end are the same, they overlap AND are duplicates
    segments_duplicate = [
        Segment(start=1.0, end=2.0, detector="test1", score=1.0),
        Segment(start=1.0, end=2.0, detector="test2", score=1.0),  # Exact duplicate
    ]
    overlaps2 = find_overlaps_within_segments(segments_duplicate)
    duplicates2 = find_duplicates_within_segments(segments_duplicate, tolerance_ms=5.0)
    assert len(overlaps2) == 1  # They also overlap
    assert len(duplicates2) == 1  # And are duplicates


def test_find_duplicates_screenshot_scenario():
    """Test the exact scenario from the screenshot: samples 15 and 16 with identical times."""
    segments = [
        Segment(start=1060.770, end=1061.340, detector="manual", score=1.0),
        Segment(start=1060.770, end=1061.340, detector="voice_vad", score=1.0),
    ]
    result = find_duplicates_within_segments(segments, tolerance_ms=5.0)
    # These should be detected as duplicates
    assert len(result) == 1
    assert set(result[0]) == {0, 1}


def test_find_duplicates_transitive():
    """Test that duplicate detection is transitive (if A=B and B=C, then A, B, C are all duplicates)."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test1", score=1.0),  # A
        Segment(
            start=1.001, end=2.001, detector="test2", score=1.0
        ),  # B (duplicate of A, within 5ms)
        Segment(
            start=1.002, end=2.002, detector="test3", score=1.0
        ),  # C (duplicate of B, within 5ms, but 2ms from A)
    ]
    result = find_duplicates_within_segments(segments, tolerance_ms=5.0)
    # All three should be in the same group (transitive)
    assert len(result) == 1
    assert set(result[0]) == {0, 1, 2}
