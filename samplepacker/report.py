"""Report generation: spectrograms (PNG/MP4) and HTML reports."""

import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt

from samplepacker.detectors.base import Segment
from samplepacker.utils import ensure_dir


def create_annotated_spectrogram(
    audio_path: Path,
    output_path: Path,
    segments: list[Segment],
    pre_pad_ms: float = 0.0,
    post_pad_ms: float = 0.0,
    size: tuple[int, int] = (4096, 1024),
    sample_rate: int | None = None,
    background_png: Path | None = None,
    duration: float | None = None,
) -> None:
    """Create annotated spectrogram PNG with segment overlays.

    Args:
        audio_path: Path to audio file for spectrogram.
        output_path: Output PNG path.
        segments: List of segments to overlay as rectangles.
        pre_pad_ms: Pre-padding used (for overlay visualization).
        post_pad_ms: Post-padding used (for overlay visualization).
        size: Image size (width, height).
        sample_rate: Audio sample rate (for time axis).

    Raises:
        ValueError: If audio cannot be loaded.
    """
    ensure_dir(output_path.parent)
    logging.debug(
        f"Creating annotated spectrogram: {audio_path} -> {output_path} ({len(segments)} segments)"
    )
    fig, ax = plt.subplots(figsize=(size[0] / 100, size[1] / 100))
    ax.set_facecolor("black")
    dur = max(duration or 0.0, max((s.end for s in segments), default=0.0))
    dur = dur if dur > 0 else 1.0
    if background_png and background_png.exists():
        import matplotlib.image as mpimg
        import numpy as np
        img = mpimg.imread(str(background_png))
        # FFmpeg showspectrumpic typically outputs with low freq at bottom, high at top
        # Flip the image vertically to match matplotlib's expected orientation
        img = np.flipud(img)
        ax.imshow(img, extent=[0, dur, 0, 1], origin="lower", aspect="auto", zorder=0)
    ax.set_xlim(0, dur)
    ax.set_ylim(0, 1)
    # Time axis: major ticks every 60s (labeled), medium ticks every 10s (lines only), minor ticks every 2s
    try:
        import numpy as np
        from matplotlib.ticker import MultipleLocator, FixedLocator, FixedFormatter

        span = max(dur, 0.0)
        major_ticks = np.arange(0.0, span + 1e-9, 60.0)
        medium_ticks = np.arange(0.0, span + 1e-9, 10.0)

        # Locators and formatter for ticks (ensure labels are fixed and visible)
        ax.xaxis.set_major_locator(FixedLocator(major_ticks))
        ax.xaxis.set_major_formatter(FixedFormatter([f"{int(t):d}" for t in major_ticks]))
        ax.xaxis.set_minor_locator(MultipleLocator(2.0))

        # Draw medium tick markers as faint vertical lines (exclude positions that are also major)
        for t in medium_ticks:
            if (t % 60.0) != 0.0:
                ax.axvline(t, color="black", alpha=0.12, linewidth=0.7, zorder=0)

        # Gridlines and tick styling
        ax.grid(which="major", color="black", alpha=0.15, linestyle="-")
        ax.grid(which="minor", color="black", alpha=0.05, linestyle=":")

        # Ensure ticks are visible and sized distinctly
        ax.tick_params(axis="x", which="major", length=10, width=1.2, colors="black")
        ax.tick_params(axis="x", which="minor", length=4, width=0.8, colors="black")
        ax.spines["bottom"].set_color("black")
        ax.xaxis.label.set_color("black")
    except Exception:
        pass
    colors = {
        "voice_vad": "#00FFAA",
        "transient_flux": "#FFCC00",
        "nonsilence_energy": "#FF66AA",
        "spectral_interestingness": "#66AAFF",
    }
    for i, seg in enumerate(segments):
        c = colors.get(seg.detector, "#FFFFFF")
        # Clamp to [0, dur]
        seg_start = max(0.0, min(seg.start, dur))
        seg_end = max(0.0, min(seg.end, dur))
        if seg_end <= seg_start:
            continue
        width = max(1e-6, seg_end - seg_start)
        rect = plt.Rectangle(
            (seg_start, 0.0),
            width,
            1.0,
            facecolor="#15ff6a",  # high-contrast green
            edgecolor="white",
            linewidth=1.2,
            alpha=0.35,
            zorder=1,
        )
        ax.add_patch(rect)
        label_x = seg_start + 0.5 * width
        ax.text(label_x, 0.95, f"{i}", color="white", fontsize=8, ha="center", va="top", zorder=2)
    ax.set_xlabel("Time (s)")
    ax.set_yticks([])
    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close()


def create_html_report(
    base_name: str,
    output_dir: Path,
    segments: list[Segment],
    audio_info: dict,
    settings: dict,
    detector_stats: dict,
) -> None:
    """Create HTML report with links to samples, spectrograms, and markers.

    Args:
        base_name: Base name for the recording.
        output_dir: Output directory containing samples/, spectrograms/, etc.
        segments: List of detected segments.
        audio_info: Audio metadata (duration, sample_rate, etc.).
        settings: Processing settings used.
        detector_stats: Statistics from detectors (e.g., counts per detector).
    """
    # TODO: Implement HTML report
    # Structure:
    # - Header with file info and settings summary
    # - Table of segments (id, start, end, duration, detector, score)
    # - Links to:
    #   - samples/*.wav
    #   - spectrograms/*.png
    #   - markers/*.txt, *.csv
    #   - data/summary.json
    # Use simple HTML/CSS, no external dependencies
    ensure_dir(output_dir)
    html_path = output_dir / f"{base_name}_report.html"
    logging.debug(f"Creating HTML report: {html_path}")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>SamplePacker Report: {base_name}</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>SamplePacker Report: {base_name}</h1>
    <h2>Audio Info</h2>
    <ul>
        <li>Duration: {audio_info.get('duration', 'N/A')}s</li>
        <li>Sample Rate: {audio_info.get('sample_rate', 'N/A')} Hz</li>
        <li>Channels: {audio_info.get('channels', 'N/A')}</li>
    </ul>
    <h2>Detected Segments ({len(segments)})</h2>
    <table>
        <tr>
            <th>ID</th>
            <th>Start (s)</th>
            <th>End (s)</th>
            <th>Duration (s)</th>
            <th>Detector</th>
            <th>Score</th>
        </tr>
"""
    for i, seg in enumerate(segments):
        html_content += f"""        <tr>
            <td>{i}</td>
            <td>{seg.start:.3f}</td>
            <td>{seg.end:.3f}</td>
            <td>{seg.duration():.3f}</td>
            <td>{seg.detector}</td>
            <td>{seg.score:.3f}</td>
        </tr>
"""

    html_content += """    </table>
    <h2>Links</h2>
    <ul>
        <li><a href="samples/">Samples</a></li>
        <li><a href="spectrograms/">Spectrograms</a></li>
        <li><a href="markers/">Markers</a></li>
        <li><a href="data/summary.json">Summary JSON</a></li>
    </ul>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logging.info(f"Created HTML report: {html_path}")


def save_summary_json(
    output_path: Path,
    audio_info: dict,
    settings: dict,
    segments: list[Segment],
    detector_stats: dict,
    versions: dict,
) -> None:
    """Save summary JSON with all processing information.

    Args:
        output_path: Output JSON file path.
        audio_info: Audio metadata.
        settings: Processing settings.
        segments: List of detected segments.
        detector_stats: Statistics per detector.
        versions: Version information (ffmpeg, samplepacker, etc.).
    """
    summary = {
        "versions": versions,
        "audio_info": audio_info,
        "settings": settings,
        "detector_stats": detector_stats,
        "segments_summary": {
            "total": len(segments),
            "by_detector": {},
            "total_duration_sec": sum(s.duration() for s in segments),
        },
        "segments": [
            {
                "id": i,
                "start_sec": seg.start,
                "end_sec": seg.end,
                "duration_sec": seg.duration(),
                "detector": seg.detector,
                "score": seg.score,
                "attrs": seg.attrs,
            }
            for i, seg in enumerate(segments)
        ],
    }
    # Count by detector
    for seg in segments:
        det = seg.detector
        summary["segments_summary"]["by_detector"][det] = (
            summary["segments_summary"]["by_detector"].get(det, 0) + 1
        )

    ensure_dir(output_path.parent)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logging.debug(f"Saved summary JSON: {output_path}")
