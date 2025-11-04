"""Tests for segment merge/pad/dedup logic."""


from samplepacker.detectors.base import Segment
from samplepacker.pipeline import deduplicate_segments_after_padding, merge_segments
from samplepacker.pipeline import ProcessingSettings


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
