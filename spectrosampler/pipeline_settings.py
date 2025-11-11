"""Shared processing settings for SpectroSampler pipelines."""

from __future__ import annotations

from typing import Any


class ProcessingSettings:
    """Container for processing settings."""

    def __init__(self, **kwargs: Any) -> None:
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
        self.post_pad_ms: float = kwargs.get(
            "post_pad_ms", kwargs.get("detection_post_pad_ms", 0.0)
        )
        self.merge_gap_ms: float = kwargs.get("merge_gap_ms", 0.0)
        self.min_dur_ms: float = kwargs.get("min_dur_ms", 100.0)
        self.max_dur_ms: float = kwargs.get("max_dur_ms", 60000.0)
        self.min_gap_ms: float = kwargs.get("min_gap_ms", 1000.0)
        # Disable chain-merge after padding by default
        self.no_merge_after_padding: bool = kwargs.get("no_merge_after_padding", True)

        # Caps/filters
        self.max_samples: int = kwargs.get("max_samples", 256)
        self.min_snr: float = kwargs.get("min_snr", 0.0)
        self.sample_spread: bool = kwargs.get("sample_spread", True)
        self.sample_spread_mode: str = kwargs.get("sample_spread_mode", "strict")

        # Output format
        self.format: str = kwargs.get("format", "wav")
        self.sample_rate: int | None = kwargs.get("sample_rate", None)
        self.bit_depth: str | None = kwargs.get("bit_depth", None)
        self.channels: str | None = kwargs.get("channels", None)
        sample_name_value = kwargs.get("sample_name")
        if isinstance(sample_name_value, str):
            sample_name_value = sample_name_value.strip()
        self.sample_name: str | None = sample_name_value if sample_name_value else None

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

        # Internal/default configuration
        self.max_workers: int = kwargs.get("max_workers", 0)

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
