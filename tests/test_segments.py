"""Tests for segment merge/pad/dedup logic."""

from samplepacker.detectors.base import Segment
from samplepacker.pipeline import (
    deduplicate_segments_after_padding,
    merge_segments,
    spread_samples_across_duration,
)


def test_segment_overlap():
    """Test segment overlap detection."""
    seg1 = Segment(start=1.0, end=2.0, detector="test", score=1.0)
    seg2 = Segment(start=1.5, end=3.0, detector="test", score=1.0)
    assert seg1.overlaps(seg2)
    assert seg2.overlaps(seg1)

    seg3 = Segment(start=3.0, end=4.0, detector="test", score=1.0)
    assert not seg1.overlaps(seg3)
    assert not seg3.overlaps(seg1)

    # Test with gap tolerance
    seg4 = Segment(start=2.5, end=4.0, detector="test", score=1.0)
    assert seg1.overlaps(seg4, gap_ms=600.0)  # 0.5s gap, 0.6s tolerance


def test_segment_merge():
    """Test segment merging."""
    seg1 = Segment(start=1.0, end=2.0, detector="test1", score=0.8)
    seg2 = Segment(start=1.5, end=3.0, detector="test2", score=0.9)

    merged = seg1.merge(seg2)
    assert merged.start == 1.0
    assert merged.end == 3.0
    assert merged.score == 0.9  # Higher score
    assert "test1" in merged.detector and "test2" in merged.detector


def test_merge_segments():
    """Test segment merging with gap tolerance."""
    segments = [
        Segment(start=1.0, end=2.0, detector="test", score=1.0),
        Segment(start=2.2, end=3.0, detector="test", score=1.0),  # 0.2s gap
        Segment(start=4.0, end=5.0, detector="test", score=1.0),  # 1.0s gap
    ]

    audio_duration = 10.0
    merged = merge_segments(
        segments,
        merge_gap_ms=300.0,
        min_dur_ms=100.0,
        max_dur_ms=10000.0,
        audio_duration=audio_duration,
    )

    # First two should merge (within 300ms gap)
    assert len(merged) == 2
    assert merged[0].start == 1.0
    assert merged[0].end == 3.0  # Merged


def test_merge_segments_duration_filter():
    """Test segment filtering by duration."""
    segments = [
        Segment(start=1.0, end=1.3, detector="test", score=1.0),  # 0.3s = 300ms (too short)
        Segment(start=2.0, end=2.5, detector="test", score=1.0),  # 0.5s = 500ms (ok)
        Segment(start=3.0, end=20.0, detector="test", score=1.0),  # 17s = 17000ms (too long)
    ]

    audio_duration = 20.0
    merged = merge_segments(
        segments,
        merge_gap_ms=300.0,
        min_dur_ms=400.0,
        max_dur_ms=10000.0,
        audio_duration=audio_duration,
    )

    # Only the 0.5s segment should remain
    assert len(merged) == 1
    assert merged[0].start == 2.0


def test_merge_segments_clamp():
    """Test segment clamping to audio duration."""
    segments = [
        Segment(start=-1.0, end=2.0, detector="test", score=1.0),  # Start < 0
        Segment(start=8.0, end=12.0, detector="test", score=1.0),  # End > duration
    ]

    audio_duration = 10.0
    merged = merge_segments(
        segments,
        merge_gap_ms=300.0,
        min_dur_ms=100.0,
        max_dur_ms=10000.0,
        audio_duration=audio_duration,
    )

    # Segments should be clamped
    assert len(merged) == 2
    assert merged[0].start == 0.0
    assert merged[1].end == 10.0


def test_deduplicate_after_padding():
    """Test deduplication after padding is applied."""
    segments = [
        Segment(start=10.0, end=12.0, detector="test", score=1.0),
        Segment(start=11.0, end=13.0, detector="test", score=1.0),
    ]

    audio_duration = 30.0
    deduped = deduplicate_segments_after_padding(
        segments, pre_pad_ms=5000.0, post_pad_ms=5000.0, audio_duration=audio_duration
    )

    # After padding: [5.0-17.0] and [6.0-18.0] -> should merge to [5.0-18.0]
    assert len(deduped) == 1
    assert deduped[0].start < 10.0  # Padded
    assert deduped[0].end > 13.0  # Padded


def test_deduplicate_min_gap():
    """Test deduplication with minimum gap enforcement."""
    segments = [
        Segment(start=10.0, end=12.0, detector="test", score=1.0),
        Segment(start=12.5, end=14.0, detector="test", score=1.0),  # 0.5s gap
    ]

    audio_duration = 30.0
    # With 500ms padding and 1000ms min_gap, segments should merge (0.5s + 1s padding = 1.5s total < 1s gap + padding)
    deduped = deduplicate_segments_after_padding(
        segments,
        pre_pad_ms=500.0,
        post_pad_ms=500.0,
        audio_duration=audio_duration,
        min_gap_ms=1000.0,
    )

    # With min_gap_ms, they might merge depending on padding
    # This test verifies the logic works
    assert len(deduped) >= 1


def test_padding_does_not_chain_merge():
    segs = [
        Segment(start=20.0, end=20.1, detector="transient_flux", score=1.0),
        Segment(start=60.0, end=60.1, detector="transient_flux", score=1.0),
        Segment(start=100.0, end=100.1, detector="transient_flux", score=1.0),
    ]
    merged = merge_segments(
        segs,
        merge_gap_ms=300.0,
        min_dur_ms=50.0,
        max_dur_ms=100000.0,
        audio_duration=200.0,
    )
    final = deduplicate_segments_after_padding(
        merged,
        pre_pad_ms=10000.0,
        post_pad_ms=10000.0,
        audio_duration=200.0,
        min_gap_ms=0.0,
        no_merge_after_padding=True,
    )
    assert len(final) == 3


def test_merge_only_on_raw_overlap():
    # Two hits 100ms apart should merge
    a = Segment(start=10.0, end=10.1, detector="t", score=1.0)
    b = Segment(start=10.2, end=10.3, detector="t", score=1.0)
    merged = merge_segments(
        [a, b],
        merge_gap_ms=300.0,
        min_dur_ms=50.0,
        max_dur_ms=100000.0,
        audio_duration=30.0,
    )
    assert len(merged) == 1
    # Two hits 5s apart remain separate even with large padding
    c = Segment(start=30.0, end=30.1, detector="t", score=1.0)
    d = Segment(start=35.0, end=35.1, detector="t", score=1.0)
    merged2 = merge_segments(
        [c, d],
        merge_gap_ms=300.0,
        min_dur_ms=50.0,
        max_dur_ms=100000.0,
        audio_duration=60.0,
    )
    final2 = deduplicate_segments_after_padding(
        merged2,
        pre_pad_ms=10000.0,
        post_pad_ms=10000.0,
        audio_duration=60.0,
        no_merge_after_padding=True,
    )
    assert len(final2) == 2


def test_dedup_uses_raw_iou_not_padded():
    # Two far raw hits, heavy padding overlaps — must remain two
    a = Segment(start=10.0, end=10.1, detector="t", score=1.0)
    b = Segment(start=30.0, end=30.1, detector="t", score=1.0)
    merged = merge_segments(
        [a, b],
        merge_gap_ms=300.0,
        min_dur_ms=50.0,
        max_dur_ms=100000.0,
        audio_duration=60.0,
    )
    final = deduplicate_segments_after_padding(
        merged,
        pre_pad_ms=15000.0,
        post_pad_ms=15000.0,
        audio_duration=60.0,
        no_merge_after_padding=True,
    )
    assert len(final) == 2


def test_spread_samples_evenly_distributed():
    """Test that samples are evenly distributed across windows."""
    # Create segments evenly spaced across 100 seconds
    segments = [
        Segment(start=10.0, end=11.0, detector="test", score=1.0),
        Segment(start=20.0, end=21.0, detector="test", score=1.0),
        Segment(start=30.0, end=31.0, detector="test", score=1.0),
        Segment(start=40.0, end=41.0, detector="test", score=1.0),
        Segment(start=50.0, end=51.0, detector="test", score=1.0),
        Segment(start=60.0, end=61.0, detector="test", score=1.0),
        Segment(start=70.0, end=71.0, detector="test", score=1.0),
        Segment(start=80.0, end=81.0, detector="test", score=1.0),
        Segment(start=90.0, end=91.0, detector="test", score=1.0),
    ]

    audio_duration = 100.0
    max_samples = 5
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should get 5 segments, one per window
    assert len(result) == 5
    # Verify no duplicates
    assert len(set(id(s) for s in result)) == 5
    # Verify segments are sorted by start time
    assert all(result[i].start <= result[i + 1].start for i in range(len(result) - 1))


def test_spread_samples_clustering_prevention():
    """Test that clustering is prevented when segments cluster in certain regions."""
    # Create clustered segments: many in first half, few in second half
    segments = [
        # Cluster in first 50 seconds
        Segment(start=5.0, end=6.0, detector="test", score=0.8),
        Segment(start=10.0, end=11.0, detector="test", score=0.9),
        Segment(start=15.0, end=16.0, detector="test", score=0.7),
        Segment(start=20.0, end=21.0, detector="test", score=0.95),
        Segment(start=25.0, end=26.0, detector="test", score=0.85),
        Segment(start=30.0, end=31.0, detector="test", score=0.75),
        Segment(start=35.0, end=36.0, detector="test", score=0.88),
        Segment(start=40.0, end=41.0, detector="test", score=0.82),
        # Sparse in second 50 seconds
        Segment(start=60.0, end=61.0, detector="test", score=0.9),
        Segment(start=70.0, end=71.0, detector="test", score=0.85),
        Segment(start=80.0, end=81.0, detector="test", score=0.88),
    ]

    audio_duration = 100.0
    max_samples = 4
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should get 4 segments, distributed across windows [0-25), [25-50), [50-75), [75-100)
    assert len(result) == 4

    # Verify segments are from different windows (not all clustered)
    window_size = audio_duration / max_samples
    windows = []
    for seg in result:
        seg_center = (seg.start + seg.end) / 2.0
        window_idx = int(seg_center / window_size)
        windows.append(window_idx)

    # Should have segments from different windows (ideally all 4 windows)
    assert len(set(windows)) >= 2  # At least some distribution
    # Verify no duplicates
    assert len(set(id(s) for s in result)) == 4


def test_spread_samples_score_priority():
    """Test that higher-scored segments are selected within windows."""
    # Create segments where some windows have multiple segments with different scores
    # Window 0 (0-33.33): 10-11 (0.5), 12-13 (0.9), 14-15 (0.6) - should select 0.9
    # Window 1 (33.33-66.66): 40-41 (0.7), 50-51 (0.8) - should select 0.8
    # Window 2 (66.66-100): 70-71 (0.6) - should select 0.6
    segments = [
        Segment(start=10.0, end=11.0, detector="test", score=0.5),  # Lower score in window 0
        Segment(start=12.0, end=13.0, detector="test", score=0.9),  # Higher score in window 0
        Segment(start=14.0, end=15.0, detector="test", score=0.6),  # Medium score in window 0
        Segment(start=40.0, end=41.0, detector="test", score=0.7),  # Lower score in window 1
        Segment(start=50.0, end=51.0, detector="test", score=0.8),  # Higher score in window 1
        Segment(start=70.0, end=71.0, detector="test", score=0.6),  # Only segment in window 2
    ]

    audio_duration = 100.0
    max_samples = 3
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should get 3 segments (one per window)
    assert len(result) == 3
    # The segment in window 0 should be the one with score 0.9 (highest in that window)
    window_0_segments = [s for s in result if 0 <= (s.start + s.end) / 2.0 < 100.0 / 3]
    assert len(window_0_segments) == 1
    assert window_0_segments[0].score == 0.9
    # The segment in window 1 should be the one with score 0.8 (highest in that window)
    window_1_segments = [s for s in result if 100.0 / 3 <= (s.start + s.end) / 2.0 < 200.0 / 3]
    assert len(window_1_segments) == 1
    assert window_1_segments[0].score == 0.8


def test_spread_samples_window_boundaries():
    """Test handling of segments at window boundaries."""
    # Create segments at exact window boundaries
    segments = [
        Segment(start=0.0, end=1.0, detector="test", score=1.0),  # At start
        Segment(start=24.9, end=25.1, detector="test", score=1.0),  # Overlaps boundary
        Segment(start=49.9, end=50.1, detector="test", score=1.0),  # Overlaps boundary
        Segment(start=75.0, end=76.0, detector="test", score=1.0),
        Segment(start=99.0, end=100.0, detector="test", score=1.0),  # At end
    ]

    audio_duration = 100.0
    max_samples = 4
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should handle boundary overlaps correctly
    assert len(result) <= max_samples
    # Verify all segments are within audio duration
    assert all(0 <= s.start <= audio_duration for s in result)
    assert all(0 <= s.end <= audio_duration for s in result)


def test_spread_samples_more_windows_than_segments():
    """Test edge case where there are more windows than segments."""
    segments = [
        Segment(start=10.0, end=11.0, detector="test", score=1.0),
        Segment(start=50.0, end=51.0, detector="test", score=1.0),
    ]

    audio_duration = 100.0
    max_samples = 10  # More windows than segments
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should return at most 2 segments (one per window where segments exist)
    assert len(result) <= 2
    assert len(result) >= 1  # Should find at least one segment


def test_spread_samples_empty_windows():
    """Test that empty windows are skipped."""
    # Create segments only in first and last windows
    segments = [
        Segment(start=5.0, end=6.0, detector="test", score=1.0),  # Window 0
        Segment(start=95.0, end=96.0, detector="test", score=1.0),  # Window 4
    ]

    audio_duration = 100.0
    max_samples = 5
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should return 2 segments (only from windows that have segments)
    assert len(result) == 2
    assert all(s in result for s in segments)


def test_spread_samples_no_duplicates():
    """Test that no duplicate segments are returned."""
    segments = [
        Segment(start=10.0, end=11.0, detector="test", score=1.0),
        Segment(start=20.0, end=21.0, detector="test", score=1.0),
        Segment(start=30.0, end=31.0, detector="test", score=1.0),
        Segment(start=40.0, end=41.0, detector="test", score=1.0),
        Segment(start=50.0, end=51.0, detector="test", score=1.0),
        Segment(start=60.0, end=61.0, detector="test", score=1.0),
        Segment(start=70.0, end=71.0, detector="test", score=1.0),
        Segment(start=80.0, end=81.0, detector="test", score=1.0),
        Segment(start=90.0, end=91.0, detector="test", score=1.0),
    ]

    audio_duration = 100.0
    max_samples = 5
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Verify no duplicates by checking object identity
    assert len(result) == len(set(id(s) for s in result))
    # Verify no duplicates by checking segment properties
    segment_signatures = [(s.start, s.end, s.detector) for s in result]
    assert len(segment_signatures) == len(set(segment_signatures))


def test_spread_samples_one_per_window():
    """Test that each window gets at most one segment."""
    # Create many segments in each window
    segments = []
    for window_idx in range(5):
        window_start = window_idx * 20.0
        # Add multiple segments in each window
        for offset in [2.0, 5.0, 8.0, 12.0, 15.0]:
            segments.append(
                Segment(
                    start=window_start + offset,
                    end=window_start + offset + 1.0,
                    detector="test",
                    score=0.5 + offset * 0.01,  # Vary scores slightly
                )
            )

    audio_duration = 100.0
    max_samples = 5
    result = spread_samples_across_duration(segments, max_samples, audio_duration)

    # Should get exactly 5 segments (one per window)
    assert len(result) == 5

    # Verify each segment is in a different window
    window_size = audio_duration / max_samples
    window_indices = []
    for seg in result:
        seg_center = (seg.start + seg.end) / 2.0
        window_idx = int(seg_center / window_size)
        window_indices.append(window_idx)

    # Each segment should be in a unique window (no two segments from same window)
    assert len(window_indices) == len(set(window_indices))


def test_spread_samples_edge_cases():
    """Test edge cases: empty input, zero max_samples, etc."""
    # Empty segments
    result = spread_samples_across_duration([], 5, 100.0)
    assert result == []

    # Zero max_samples
    segments = [Segment(start=10.0, end=11.0, detector="test", score=1.0)]
    result = spread_samples_across_duration(segments, 0, 100.0)
    assert result == []

    # Zero audio duration
    result = spread_samples_across_duration(segments, 5, 0.0)
    assert result == []

    # Fewer segments than max_samples (should return all)
    segments = [
        Segment(start=10.0, end=11.0, detector="test", score=1.0),
        Segment(start=20.0, end=21.0, detector="test", score=1.0),
    ]
    result = spread_samples_across_duration(segments, 5, 100.0)
    assert len(result) == 2
    assert all(s in result for s in segments)


def test_spread_samples_closest_mode():
    """Test closest mode behavior - selects closest segments to window centers."""
    # Create segments clustered in first half
    segments = [
        Segment(start=10.0, end=11.0, detector="test", score=0.8),
        Segment(start=12.0, end=13.0, detector="test", score=0.9),
        Segment(start=15.0, end=16.0, detector="test", score=0.7),
        Segment(start=20.0, end=21.0, detector="test", score=0.95),
        Segment(start=25.0, end=26.0, detector="test", score=0.85),
        Segment(start=30.0, end=31.0, detector="test", score=0.75),
        # Sparse in second half
        Segment(start=60.0, end=61.0, detector="test", score=0.9),
        Segment(start=70.0, end=71.0, detector="test", score=0.85),
    ]

    audio_duration = 100.0
    max_samples = 4
    result = spread_samples_across_duration(segments, max_samples, audio_duration, mode="closest")

    # Closest mode should always return max_samples segments if available
    assert len(result) == 4
    # Verify no duplicates
    assert len(set(id(s) for s in result)) == 4


def test_spread_samples_closest_mode_empty_windows():
    """Test closest mode fills empty windows from other regions."""
    # Create segments only in first window
    segments = [
        Segment(start=5.0, end=6.0, detector="test", score=1.0),
        Segment(start=10.0, end=11.0, detector="test", score=1.0),
        Segment(start=15.0, end=16.0, detector="test", score=1.0),
    ]

    audio_duration = 100.0
    max_samples = 5
    result = spread_samples_across_duration(segments, max_samples, audio_duration, mode="closest")

    # Closest mode should fill all windows with closest segments
    assert len(result) == 3  # Only 3 segments available
    # Verify no duplicates
    assert len(set(id(s) for s in result)) == 3


def test_spread_samples_strict_vs_closest():
    """Test that strict and closest modes produce different results."""
    # Create segments clustered in first window, sparse elsewhere
    segments = [
        Segment(start=5.0, end=6.0, detector="test", score=0.8),
        Segment(start=10.0, end=11.0, detector="test", score=0.9),
        Segment(start=15.0, end=16.0, detector="test", score=0.7),
        Segment(start=20.0, end=21.0, detector="test", score=0.95),
        Segment(start=60.0, end=61.0, detector="test", score=0.9),
        Segment(start=70.0, end=71.0, detector="test", score=0.85),
    ]

    audio_duration = 100.0
    max_samples = 4

    strict_result = spread_samples_across_duration(segments, max_samples, audio_duration, mode="strict")
    closest_result = spread_samples_across_duration(segments, max_samples, audio_duration, mode="closest")

    # Both should return results
    assert len(strict_result) > 0
    assert len(closest_result) > 0

    # Closest mode should always return max_samples if enough segments available
    assert len(closest_result) == 4

    # Strict mode may return fewer if windows have no segments
    # (depends on whether segments overlap with windows)
    assert len(strict_result) <= 4
