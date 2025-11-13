"""Sample export: naming, cutting, format conversion, normalization."""

import logging
from pathlib import Path

from spectrosampler.audio_io import extract_sample, get_audio_info
from spectrosampler.detectors.base import Segment
from spectrosampler.utils import ensure_dir, sanitize_filename


def build_sample_filename(
    base_name: str,
    segment: Segment,
    index: int,
    total: int,
    zero_pad: int = 4,
    normalize: bool = False,
) -> str:
    """Build deterministic sample filename.

    Args:
        base_name: Base name (sanitized source filename without extension).
        segment: Segment object.
        index: Sample index (0-based).
        total: Total number of samples.
        zero_pad: Number of digits for zero-padding index.
        normalize: Whether peak normalization is enabled (adds "_norm" suffix).

    Returns:
        Filename (without extension) for the sample.
    """
    # Format: {basename}_sample_{index:04d}_{start}s-{end}s_detector-{detector}.wav
    # Round start/end to 0.1s precision (or 0.01s if < 1s)
    start_rounded = round(segment.start, 1) if segment.start >= 1.0 else round(segment.start, 2)
    end_rounded = round(segment.end, 1) if segment.end >= 1.0 else round(segment.end, 2)
    index_str = str(index).zfill(zero_pad)
    # Prefer primary detector if present, otherwise collapse labels
    primary = segment.attrs.get("primary_detector")
    if primary:
        label = str(primary)
    else:
        parts = [p for p in str(segment.detector).split("+") if p]
        uniq = sorted(set(parts))
        if len(uniq) == 0:
            label = "unknown"
        elif len(uniq) == 1:
            label = uniq[0]
        elif len(uniq) == 2:
            label = "+".join(uniq)
        else:
            label = "multi"
    custom_name_fragment = ""
    raw_custom_name = ""
    if hasattr(segment, "attrs") and segment.attrs is not None:
        raw_custom_name = str(segment.attrs.get("name", "")).strip()
    if raw_custom_name:
        sanitized_custom = sanitize_filename(raw_custom_name)
        # Replace whitespace and dot separators to keep the slug compact and extension-free.
        custom_name_fragment = sanitized_custom.replace(" ", "_").replace(".", "_")
        # Guard against an empty fragment after sanitisation.
        if not custom_name_fragment:
            custom_name_fragment = ""

    filename_parts = [
        base_name,
        "sample",
        index_str,
    ]
    if custom_name_fragment:
        filename_parts.append(custom_name_fragment)
    filename_parts.append(f"{start_rounded}s-{end_rounded}s")
    filename_parts.append(f"detector-{label}")
    if normalize:
        filename_parts.append("norm")
    name = "_".join(filename_parts)
    return sanitize_filename(name)


def export_sample(
    input_path: Path,
    output_path: Path,
    segment: Segment,
    pre_pad_ms: float = 0.0,
    post_pad_ms: float = 0.0,
    fade_in_ms: float = 5.0,
    fade_out_ms: float = 5.0,
    format: str = "wav",
    sample_rate: int | None = None,
    bit_depth: str | None = None,
    channels: str | None = None,
    normalize: bool = False,
    lufs_target: float | None = None,
    duration: float | None = None,
    run_log: Path | None = None,
) -> None:
    """Export a single sample segment.

    Args:
        input_path: Source audio file.
        output_path: Output sample file path.
        segment: Segment to export.
        pre_pad_ms: Padding before segment start (milliseconds).
        post_pad_ms: Padding after segment end (milliseconds).
        duration: Optional duration constraint (if None, use full segment + padding).

    Raises:
        ValueError: If calculated times are invalid.
    """
    info = get_audio_info(input_path)
    total_dur = float(info.get("duration", 0.0))
    start_padded = max(0.0, segment.start - (pre_pad_ms / 1000.0))
    end_padded = min(total_dur, segment.end + (post_pad_ms / 1000.0))
    logging.debug(f"Exporting sample: {start_padded:.3f}s-{end_padded:.3f}s -> {output_path}")
    if end_padded <= start_padded:
        raise ValueError("Invalid segment after padding")
    extract_sample(
        input_path=input_path,
        output_path=output_path,
        start_sec=start_padded,
        end_sec=end_padded,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        format=format,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        channels=channels,
        normalize=normalize,
        lufs_target=lufs_target,
    )


def export_markers_audacity(
    segments: list[Segment],
    output_path: Path,
    include_padding: bool = False,
    pre_pad_ms: float = 0.0,
    post_pad_ms: float = 0.0,
) -> None:
    """Export segments as Audacity label file.

    Args:
        segments: List of segments.
        output_path: Output .txt file path.
        include_padding: Whether to include padding in timestamps.
        pre_pad_ms: Pre-padding in milliseconds (if include_padding).
        post_pad_ms: Post-padding in milliseconds (if include_padding).
    """
    ensure_dir(output_path.parent)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments):
            start = seg.start - (pre_pad_ms / 1000.0) if include_padding else seg.start
            end = seg.end + (post_pad_ms / 1000.0) if include_padding else seg.end
            label = f"sample_{i:03d} {seg.detector}"
            f.write(f"{start:.3f}\t{end:.3f}\t{label}\n")
    logging.debug(f"Exported {len(segments)} markers to {output_path}")


def export_markers_reaper(
    segments: list[Segment],
    output_path: Path,
    include_padding: bool = False,
    pre_pad_ms: float = 0.0,
    post_pad_ms: float = 0.0,
) -> None:
    """Export segments as REAPER regions CSV.

    Args:
        segments: List of segments.
        output_path: Output .csv file path.
        include_padding: Whether to include padding in timestamps.
        pre_pad_ms: Pre-padding in milliseconds (if include_padding).
        post_pad_ms: Post-padding in milliseconds (if include_padding).
    """
    ensure_dir(output_path.parent)
    import csv

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Start", "End", "Length"])
        for i, seg in enumerate(segments):
            start = seg.start - (pre_pad_ms / 1000.0) if include_padding else seg.start
            end = seg.end + (post_pad_ms / 1000.0) if include_padding else seg.end
            duration = end - start
            name = f"sample_{i:03d} {seg.detector}"
            writer.writerow([name, f"{start:.6f}", f"{end:.6f}", f"{duration:.6f}"])
    logging.debug(f"Exported {len(segments)} regions to {output_path}")


def export_timestamps_csv(
    segments: list[Segment],
    output_path: Path,
    include_padding: bool = False,
    pre_pad_ms: float = 0.0,
    post_pad_ms: float = 0.0,
) -> None:
    """Export segments as timestamps CSV.

    Args:
        segments: List of segments.
        output_path: Output .csv file path.
        include_padding: Whether to include padding in timestamps.
        pre_pad_ms: Pre-padding in milliseconds (if include_padding).
        post_pad_ms: Post-padding in milliseconds (if include_padding).
    """
    ensure_dir(output_path.parent)
    import csv

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "start_sec", "end_sec", "duration_sec", "detector", "score"])
        for i, seg in enumerate(segments):
            start = seg.start - (pre_pad_ms / 1000.0) if include_padding else seg.start
            end = seg.end + (post_pad_ms / 1000.0) if include_padding else seg.end
            duration = end - start
            writer.writerow(
                [
                    i,
                    f"{start:.3f}",
                    f"{end:.3f}",
                    f"{duration:.3f}",
                    seg.detector,
                    f"{seg.score:.3f}",
                ]
            )
    logging.debug(f"Exported {len(segments)} timestamps to {output_path}")
