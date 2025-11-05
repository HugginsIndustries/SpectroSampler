"""Main processing pipeline: orchestration of denoise, detect, merge, export."""

import logging
from pathlib import Path
from typing import Any

from tqdm import tqdm

from samplepacker.audio_io import AudioCache, check_ffmpeg, denoise_audio, get_audio_info, resample_for_analysis, generate_spectrogram_png
from samplepacker.detectors import Segment, VoiceVADDetector, TransientFluxDetector, NonSilenceEnergyDetector, SpectralInterestingnessDetector
from samplepacker.export import build_sample_filename, export_markers_audacity, export_markers_reaper, export_sample, export_timestamps_csv
from samplepacker.report import create_annotated_spectrogram, create_html_report, save_summary_json
from samplepacker.utils import Timer


class ProcessingSettings:
    """Container for processing settings."""

    def __init__(self, **kwargs):
        """Initialize settings from keyword arguments."""
        # Mode and thresholds
        self.mode: str = kwargs.get("mode", "auto")
        self.threshold: Any = kwargs.get("threshold", "auto")

        # Timing (milliseconds)
        # Detection padding (used during detection/deduplication)
        self.detection_pre_pad_ms: float = kwargs.get("detection_pre_pad_ms", 0.0)
        self.detection_post_pad_ms: float = kwargs.get("detection_post_pad_ms", 0.0)
        # Export padding (used during sample export)
        self.export_pre_pad_ms: float = kwargs.get("export_pre_pad_ms", 0.0)
        self.export_post_pad_ms: float = kwargs.get("export_post_pad_ms", 0.0)
        # Legacy fields for backward compatibility - use detection padding if not set
        self.pre_pad_ms: float = kwargs.get("pre_pad_ms", kwargs.get("detection_pre_pad_ms", 0.0))
        self.post_pad_ms: float = kwargs.get("post_pad_ms", kwargs.get("detection_post_pad_ms", 0.0))
        self.merge_gap_ms: float = kwargs.get("merge_gap_ms", 0.0)
        self.min_dur_ms: float = kwargs.get("min_dur_ms", 100.0)
        self.max_dur_ms: float = kwargs.get("max_dur_ms", 60000.0)
        self.min_gap_ms: float = kwargs.get("min_gap_ms", 100.0)
        # Disable chain-merge after padding by default
        self.no_merge_after_padding: bool = kwargs.get("no_merge_after_padding", True)

        # Caps/filters
        self.max_samples: int = kwargs.get("max_samples", 200)
        self.min_snr: float = kwargs.get("min_snr", 0.0)

        # Output format
        self.format: str = kwargs.get("format", "wav")
        self.sample_rate: int | None = kwargs.get("sample_rate", None)
        self.bit_depth: str | None = kwargs.get("bit_depth", None)
        self.channels: str | None = kwargs.get("channels", None)

        # Denoise/preprocessing
        self.denoise: str = kwargs.get("denoise", "afftdn")
        self.hp: float | None = kwargs.get("hp", 20.0)
        self.lp: float | None = kwargs.get("lp", 20000.0)
        self.nr: float = kwargs.get("nr", 12.0)
        self.analysis_sr: int = kwargs.get("analysis_sr", 16000)
        self.analysis_mid_only: bool = kwargs.get("analysis_mid_only", False)

        # Spectrograms/reports
        self.spectrogram: bool = kwargs.get("spectrogram", True)
        self.spectro_size: str = kwargs.get("spectro_size", "4096x1024")
        self.spectro_video: bool = kwargs.get("spectro_video", False)
        self.report: str | None = kwargs.get("report", None)

        # Workflow
        self.chunk_sec: float = kwargs.get("chunk_sec", 600.0)
        self.cache: bool = kwargs.get("cache", False)
        self.dry_run: bool = kwargs.get("dry_run", False)
        self.save_temp: bool = kwargs.get("save_temp", False)
        self.verbose: bool = kwargs.get("verbose", False)

        # Subfolders (default on)
        self.create_subfolders: bool = kwargs.get("create_subfolders", True)
        # Overlap resolution controls
        self.resolve_overlaps: str = (kwargs.get("resolve_overlaps") or "").strip()
        self.overlap_iou: float = float(kwargs.get("overlap_iou", 0.0) or 0.0)
        self.subfolder_template: str = kwargs.get(
            "subfolder_template",
            "{basename}__{mode}__pre{pre}ms_post{post}ms_thr{thr}",
        )

        # Per-mode defaults (only if value equals non-transient default)
        if self.mode == "transient":
            # Apply transient defaults if value equals non-transient default (user didn't override)
            if self.pre_pad_ms == 10000.0:
                self.pre_pad_ms = 25.0
            if self.post_pad_ms == 10000.0:
                self.post_pad_ms = 250.0
            if self.max_dur_ms == 60000.0:
                self.max_dur_ms = 2000.0
            if self.min_gap_ms == 0.0:
                self.min_gap_ms = 50.0
            if not self.resolve_overlaps:
                self.resolve_overlaps = "keep-highest"
            if self.overlap_iou == 0.0:
                self.overlap_iou = 0.20


def merge_segments(
    segments: list[Segment],
    merge_gap_ms: float,
    min_dur_ms: float,
    max_dur_ms: float,
    audio_duration: float,
) -> list[Segment]:
    """Merge overlapping segments and filter by duration.

    Args:
        segments: List of segments to merge.
        merge_gap_ms: Gap tolerance in milliseconds (segments within this are merged).
        min_dur_ms: Minimum segment duration in milliseconds.
        max_dur_ms: Maximum segment duration in milliseconds.
        audio_duration: Total audio duration in seconds.

    Returns:
        Merged and filtered segments.
    """
    if not segments:
        return []

    gap_sec = merge_gap_ms / 1000.0

    # Sort by start time and clamp to valid range first
    sorted_segments = []
    for s in sorted(segments, key=lambda s: s.start):
        start = max(0.0, min(s.start, audio_duration))
        end = max(0.0, min(s.end, audio_duration))
        if end <= start:
            continue
        sorted_segments.append(
            Segment(start=start, end=end, detector=s.detector, score=s.score, attrs=s.attrs)
        )

    if not sorted_segments:
        return []

    # Merge with gap tolerance on RAW times only
    merged: list[Segment] = [sorted_segments[0]]
    for seg in sorted_segments[1:]:
        last = merged[-1]
        if seg.start <= last.end + gap_sec:
            # Merge raw bounds and preserve identity/labels
            detectors = set(last.attrs.get("detectors", {last.detector}))
            detectors.update(set(seg.attrs.get("detectors", {seg.detector})))
            primary_detector = last.detector if last.score >= seg.score else seg.detector
            merged[-1] = Segment(
                start=min(last.start, seg.start),
                end=max(last.end, seg.end),
                detector=primary_detector,
                score=max(last.score, seg.score),
                attrs={
                    **last.attrs,
                    **seg.attrs,
                    "detectors": sorted(detectors),
                    "primary_detector": primary_detector,
                },
            )
        else:
            merged.append(seg)

    # Duration filter
    filtered: list[Segment] = []
    for seg in merged:
        dur_ms = seg.duration() * 1000.0
        if dur_ms < min_dur_ms or dur_ms > max_dur_ms:
            continue
        filtered.append(seg)

    return filtered


def deduplicate_segments_after_padding(
    segments: list[Segment],
    pre_pad_ms: float,
    post_pad_ms: float,
    audio_duration: float,
    min_gap_ms: float = 0.0,
    no_merge_after_padding: bool = True,
) -> list[Segment]:
    """Deduplicate overlapping segments after padding is applied.

    Args:
        segments: List of segments.
        pre_pad_ms: Pre-padding in milliseconds.
        post_pad_ms: Post-padding in milliseconds.
        audio_duration: Total audio duration in seconds.
        min_gap_ms: Minimum gap between samples after padding (milliseconds).

    Returns:
        Deduplicated segments (merged overlaps).
    """
    # TODO: Implement deduplication after padding
    # 1. Compute padded start/end for each segment
    # 2. Merge overlapping padded segments
    # 3. Return merged list
    if not segments:
        return []

    padded_segments = []
    gap_sec = min_gap_ms / 1000.0

    for seg in segments:
        padded_start = max(0.0, seg.start - pre_pad_ms / 1000.0)
        padded_end = min(audio_duration, seg.end + post_pad_ms / 1000.0)
        if padded_end <= padded_start:
            continue
        # Carry RAW bounds into attrs for dedup logic
        raw_attrs = dict(seg.attrs)
        raw_attrs["raw_start"] = seg.start
        raw_attrs["raw_end"] = seg.end
        padded_segments.append(
            Segment(
                start=padded_start,
                end=padded_end,
                detector=seg.detector,
                score=seg.score,
                attrs=raw_attrs,
            )
        )

    # Merge overlapping padded segments
    if not padded_segments:
        return []

    sorted_padded = sorted(padded_segments, key=lambda s: s.start)
    if not no_merge_after_padding:
        merged = [sorted_padded[0]]
        for seg in sorted_padded[1:]:
            last = merged[-1]
            if seg.start <= last.end + gap_sec:
                merged[-1] = Segment(
                    start=last.start,
                    end=max(last.end, seg.end),
                    detector=last.attrs.get("primary_detector", last.detector),
                    score=max(last.score, seg.score),
                    attrs={**last.attrs, **seg.attrs},
                )
            else:
                merged.append(seg)
        return merged

    # IoU/containment based on RAW bounds only
    def iou_raw(a: Segment, b: Segment) -> float:
        a0, a1 = float(a.attrs.get("raw_start", a.start)), float(a.attrs.get("raw_end", a.end))
        b0, b1 = float(b.attrs.get("raw_start", b.start)), float(b.attrs.get("raw_end", b.end))
        inter = max(0.0, min(a1, b1) - max(a0, b0))
        union = (a1 - a0) + (b1 - b0) - inter
        return 0.0 if union <= 0 else inter / union

    kept: list[Segment] = []
    for cand in sorted_padded:
        drop = False
        for other in kept:
            c0, c1 = float(cand.attrs.get("raw_start", cand.start)), float(cand.attrs.get("raw_end", cand.end))
            o0, o1 = float(other.attrs.get("raw_start", other.start)), float(other.attrs.get("raw_end", other.end))
            raw_contained = (c0 >= o0 and c1 <= o1) or (o0 >= c0 and o1 <= c1)
            raw_overlap = max(0.0, min(c1, o1) - max(c0, o0)) > 0.0
            if raw_contained or raw_overlap or iou_raw(cand, other) >= 0.5:
                drop = True
                break
        if not drop:
            kept.append(cand)
    return kept


def process_file(
    input_path: Path,
    output_dir: Path,
    settings: ProcessingSettings,
    cache: AudioCache | None = None,
) -> dict[str, Any]:
    """Process a single audio file: denoise, detect, export.

    Args:
        input_path: Input audio file path.
        output_dir: Output directory.
        settings: Processing settings.
        cache: Optional audio cache.

    Returns:
        Dictionary with processing results (segments, stats, etc.).
    """
    logging.info(f"Processing: {input_path} -> {output_dir}")

    # Prepare directories
    base_name = input_path.stem
    sub_name = base_name if not settings.create_subfolders else f"{base_name}_{settings.mode}"
    out_base = output_dir / sub_name
    samples_dir = out_base / "samples"
    spectro_dir = out_base / "spectrograms"
    markers_dir = out_base / "markers"
    data_dir = out_base / "data"
    for d in [samples_dir, spectro_dir, markers_dir, data_dir]:
        d.mkdir(parents=True, exist_ok=True)
    run_log = data_dir / "run.log"

    audio_info = get_audio_info(input_path)

    # Caching
    cache_key = None
    denoised_path = out_base / "data" / f"{base_name}_denoised.wav"
    analysis_path = out_base / "data" / f"{base_name}_analysis_16k.wav"
    if cache:
        cache_key = cache.get_cache_key(
            input_path,
            {"denoise": settings.denoise, "hp": settings.hp, "lp": settings.lp, "nr": settings.nr},
            {"sr": settings.analysis_sr, "ch": 1},
        )
        denoised_path = cache.get_cached_path(cache_key, "_denoised.wav")
        analysis_path = cache.get_cached_path(cache_key, "_analysis_16k.wav")

    # Denoise
    if settings.denoise == "off":
        denoised_path = input_path
    else:
        if not denoised_path.exists() or not settings.cache:
            denoise_audio(
                input_path,
                denoised_path,
                method=settings.denoise,
                highpass_hz=settings.hp,
                lowpass_hz=settings.lp,
                nr_strength=settings.nr,
            )

    # Analysis copy
    if not analysis_path.exists() or not settings.cache:
        resample_for_analysis(denoised_path, analysis_path, target_sr=settings.analysis_sr, channels=1)

    # Load analysis audio
    import soundfile as sf
    analysis_audio, sr = sf.read(analysis_path)
    if analysis_audio.ndim > 1:
        analysis_audio = analysis_audio[:, 0]
    
    # Verify full file was processed
    analysis_dur = len(analysis_audio) / sr
    expected_dur = float(audio_info.get("duration", 0.0))
    if expected_dur > 0 and abs(analysis_dur - expected_dur) > 1.0:
        logging.warning(
            f"Analysis audio duration mismatch: expected {expected_dur:.1f}s, got {analysis_dur:.1f}s. "
            f"Check if resampling processed the full file."
        )

    # Select detectors
    detectors: list = []
    if settings.mode in ("auto", "voice"):
        try:
            detectors.append(VoiceVADDetector(sample_rate=sr, aggressiveness=3))
        except Exception:
            pass
    if settings.mode in ("auto", "transient"):
        thr_pct: float | None = None
        try:
            if isinstance(settings.threshold, (int, float)):
                thr_pct = float(settings.threshold)
        except Exception:
            thr_pct = None
        tf_kwargs: dict[str, Any] = {"sample_rate": sr}
        if thr_pct is not None and 0.0 < thr_pct < 100.0:
            tf_kwargs["threshold_percentile"] = thr_pct
        # Constrain detector durations by settings
        tf_kwargs["min_duration_ms"] = max(20.0, float(settings.min_dur_ms))
        tf_kwargs["max_duration_ms"] = float(settings.max_dur_ms)
        detectors.append(TransientFluxDetector(**tf_kwargs))
    if settings.mode in ("auto", "nonsilence"):
        detectors.append(NonSilenceEnergyDetector(sample_rate=sr))
    if settings.mode in ("auto", "spectral"):
        detectors.append(SpectralInterestingnessDetector(sample_rate=sr))

    # Detect
    all_segments: list[Segment] = []
    for det in detectors:
        all_segments.extend(det.detect(analysis_audio))

    # Merge/filter/dedup
    merged = merge_segments(
        all_segments,
        merge_gap_ms=settings.merge_gap_ms,
        min_dur_ms=settings.min_dur_ms,
        max_dur_ms=settings.max_dur_ms,
        audio_duration=float(audio_info.get("duration", 0.0)),
    )
    final_segments = deduplicate_segments_after_padding(
        merged,
        pre_pad_ms=settings.detection_pre_pad_ms,
        post_pad_ms=settings.detection_post_pad_ms,
        audio_duration=float(audio_info.get("duration", 0.0)),
        min_gap_ms=settings.min_gap_ms,
        no_merge_after_padding=settings.no_merge_after_padding,
    )
    # Overlap resolution
    if settings.resolve_overlaps in ("keep-highest", "merge"):
        if settings.resolve_overlaps == "keep-highest":
            def iou(a: Segment, b: Segment) -> float:
                inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
                union = (a.end - a.start) + (b.end - b.start) - inter
                return 0.0 if union <= 0 else inter / union
            gap_sec = settings.min_gap_ms / 1000.0
            sorted_by_score = sorted(final_segments, key=lambda s: s.score, reverse=True)
            kept: list[Segment] = []
            for cand in sorted_by_score:
                ok = True
                for other in kept:
                    if iou(cand, other) >= (settings.overlap_iou or 0.0):
                        ok = False
                        break
                    if (cand.start < other.end + gap_sec) and (other.start < cand.end + gap_sec):
                        ok = False
                        break
                if ok:
                    kept.append(cand)
            final_segments = sorted(kept, key=lambda s: (s.start, -s.score))
        # 'merge' behavior can be extended later

    if settings.max_samples and len(final_segments) > settings.max_samples:
        final_segments = final_segments[: settings.max_samples]

    # Exports
    export_timestamps_csv(final_segments, data_dir / "timestamps.csv")
    export_markers_audacity(final_segments, markers_dir / "audacity_labels.txt")
    export_markers_reaper(final_segments, markers_dir / "reaper_regions.csv")

    # Samples
    for idx, seg in enumerate(final_segments):
        name = build_sample_filename(base_name, seg, idx, len(final_segments)) + ".wav"
        export_sample(
            input_path=input_path,
            output_path=samples_dir / name,
            segment=seg,
            pre_pad_ms=settings.export_pre_pad_ms,
            post_pad_ms=settings.export_post_pad_ms,
            format=settings.format,
            sample_rate=settings.sample_rate,
            bit_depth=settings.bit_depth,
            channels=settings.channels,
        )

    # Spectrograms
    if settings.spectrogram:
        clean_png = spectro_dir / f"{base_name}_spectrogram.png"
        generate_spectrogram_png(denoised_path, clean_png, size=settings.spectro_size)
        marked_png = spectro_dir / f"{base_name}_spectrogram_marked.png"
        create_annotated_spectrogram(
            denoised_path,
            marked_png,
            final_segments,
            background_png=clean_png,
            duration=float(audio_info.get("duration", 0.0)),
        )

    # Summary
    versions = {"samplepacker": "0.1.0"}
    save_summary_json(data_dir / "summary.json", audio_info, settings.__dict__, final_segments, {}, versions)
    if settings.report == "html":
        create_html_report(base_name, out_base, final_segments, audio_info, settings.__dict__, {})

    return {
        "segments": final_segments,
        "detector_stats": {},
        "audio_info": audio_info,
        "settings": settings.__dict__,
    }


class Pipeline:
    """Main processing pipeline."""

    def __init__(self, settings: ProcessingSettings):
        """Initialize pipeline with settings.

        Args:
            settings: Processing settings.
        """
        self.settings = settings
        self.cache: AudioCache | None = None
        if settings.cache:
            # TODO: Initialize cache directory
            cache_dir = Path.home() / ".samplepacker" / "cache"
            self.cache = AudioCache(cache_dir)

        if not check_ffmpeg():
            raise RuntimeError("FFmpeg not found in PATH. Please install FFmpeg.")

    def process(
        self,
        input_path: Path,
        output_dir: Path,
        jobs: int = 1,
        resume: bool = False,
        skip_existing: bool = False,
    ) -> None:
        """Process input (file or directory).

        Args:
            input_path: Input file or directory.
            output_dir: Output directory.
            jobs: Number of parallel jobs for batch processing.
            resume: Skip already processed files.
            skip_existing: Skip samples that already exist.
        """
        # TODO: Implement batch processing
        # - Handle single file vs directory
        # - Parallelize with jobs > 1
        # - Progress bars with tqdm
        # - Resume/skip logic
        if input_path.is_file():
            process_file(input_path, output_dir, self.settings, self.cache)
        elif input_path.is_dir():
            # Batch processing
            audio_files = list(input_path.rglob("*.wav")) + list(input_path.rglob("*.flac"))
            if not audio_files:
                logging.warning(f"No audio files found in {input_path}")
                return

            for audio_file in tqdm(audio_files, desc="Processing files"):
                # TODO: Parallelize with jobs > 1
                process_file(audio_file, output_dir, self.settings, self.cache)
        else:
            raise ValueError(f"Input path does not exist: {input_path}")
