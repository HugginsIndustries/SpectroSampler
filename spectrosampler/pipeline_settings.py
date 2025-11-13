"""Shared processing settings for SpectroSampler pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Represents a single validation issue for processing settings."""

    field: str
    message: str


class ProcessingSettings:
    """Container for processing settings."""

    _SERIALIZED_FIELDS: ClassVar[tuple[str, ...]] = (
        "mode",
        "threshold",
        "detection_pre_pad_ms",
        "detection_post_pad_ms",
        "export_pre_pad_ms",
        "export_post_pad_ms",
        "pre_pad_ms",
        "post_pad_ms",
        "merge_gap_ms",
        "min_dur_ms",
        "max_dur_ms",
        "min_gap_ms",
        "no_merge_after_padding",
        "max_samples",
        "min_snr",
        "sample_spread",
        "sample_spread_mode",
        "format",
        "sample_rate",
        "bit_depth",
        "channels",
        "denoise",
        "hp",
        "lp",
        "nr",
        "analysis_sr",
        "analysis_resample_strategy",
        "analysis_mid_only",
        "spectrogram",
        "spectro_size",
        "spectro_video",
        "report",
        "chunk_sec",
        "cache",
        "dry_run",
        "save_temp",
        "verbose",
        "create_subfolders",
        "resolve_overlaps",
        "overlap_iou",
        "show_overlap_dialog",
        "overlap_default_behavior",
        "subfolder_template",
        "max_workers",
    )

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

        # Denoise/preprocessing
        self.denoise: str = kwargs.get("denoise", "afftdn")
        self.hp: float | None = kwargs.get("hp", 20.0)
        self.lp: float | None = kwargs.get("lp", 20000.0)
        self.nr: float = kwargs.get("nr", 12.0)
        self.analysis_sr: int = kwargs.get("analysis_sr", 16000)
        self.analysis_resample_strategy: str = kwargs.get("analysis_resample_strategy", "default")
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

        # Overlap dialog preferences (mirrored into projects for persistence)
        show_overlap = kwargs.get("show_overlap_dialog", True)
        self.show_overlap_dialog: bool = bool(show_overlap) if show_overlap is not None else True
        behavior = kwargs.get("overlap_default_behavior", "discard_duplicates")
        if not isinstance(behavior, str):
            behavior = "discard_duplicates"
        behavior = behavior.strip().lower()
        if behavior not in {"discard_duplicates", "discard_overlaps", "keep_all"}:
            behavior = "discard_duplicates"
        self.overlap_default_behavior: str = behavior

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

    def validate(self) -> list[ValidationIssue]:
        """Return a list of validation issues for the current settings."""

        issues: list[ValidationIssue] = []

        def _coerce_float(field: str, value: Any, *, allow_none: bool = False) -> float | None:
            if value is None:
                if allow_none:
                    return None
                issues.append(
                    ValidationIssue(field, f"{field.replace('_', ' ').capitalize()} must be set.")
                )
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        field, f"{field.replace('_', ' ').capitalize()} must be numeric."
                    )
                )
                return None

        def _coerce_int(field: str, value: Any, *, allow_none: bool = False) -> int | None:
            if value is None:
                if allow_none:
                    return None
                issues.append(
                    ValidationIssue(field, f"{field.replace('_', ' ').capitalize()} must be set.")
                )
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        field, f"{field.replace('_', ' ').capitalize()} must be an integer."
                    )
                )
                return None

        allowed_modes = {"auto", "voice", "transient", "nonsilence", "spectral"}
        if self.mode not in allowed_modes:
            issues.append(
                ValidationIssue(
                    "mode",
                    "Detection mode must be one of: auto, voice, transient, nonsilence, spectral.",
                )
            )

        if isinstance(self.threshold, str):
            if self.threshold.strip().lower() != "auto":
                try:
                    threshold_val = float(self.threshold)
                    if threshold_val < 0.0 or threshold_val > 100.0:
                        issues.append(
                            ValidationIssue(
                                "threshold",
                                "Threshold percentile must be between 0 and 100 or 'auto'.",
                            )
                        )
                except ValueError:
                    issues.append(
                        ValidationIssue("threshold", "Threshold must be numeric or 'auto'.")
                    )
        elif isinstance(self.threshold, (int, float)):
            if float(self.threshold) < 0.0 or float(self.threshold) > 100.0:
                issues.append(
                    ValidationIssue(
                        "threshold",
                        "Threshold percentile must be between 0 and 100 or 'auto'.",
                    )
                )
        elif self.threshold is not None:
            issues.append(ValidationIssue("threshold", "Threshold must be numeric or 'auto'."))

        # Timing values
        pre_pad = _coerce_float("detection_pre_pad_ms", self.detection_pre_pad_ms)
        post_pad = _coerce_float("detection_post_pad_ms", self.detection_post_pad_ms)
        export_pre = _coerce_float("export_pre_pad_ms", self.export_pre_pad_ms)
        export_post = _coerce_float("export_post_pad_ms", self.export_post_pad_ms)
        merge_gap = _coerce_float("merge_gap_ms", self.merge_gap_ms)
        min_dur = _coerce_float("min_dur_ms", self.min_dur_ms)
        max_dur = _coerce_float("max_dur_ms", self.max_dur_ms)
        min_gap = _coerce_float("min_gap_ms", self.min_gap_ms)

        for field_name, value in (
            ("detection_pre_pad_ms", pre_pad),
            ("detection_post_pad_ms", post_pad),
            ("export_pre_pad_ms", export_pre),
            ("export_post_pad_ms", export_post),
            ("merge_gap_ms", merge_gap),
            ("min_dur_ms", min_dur),
            ("max_dur_ms", max_dur),
            ("min_gap_ms", min_gap),
        ):
            if value is not None and value < 0.0:
                issues.append(ValidationIssue(field_name, "Value cannot be negative."))

        if max_dur is not None and max_dur <= 0.0:
            issues.append(
                ValidationIssue("max_dur_ms", "Maximum duration must be greater than zero.")
            )

        if min_dur is not None and max_dur is not None and min_dur > max_dur:
            issues.append(
                ValidationIssue(
                    "min_dur_ms", "Minimum duration must be less than or equal to maximum duration."
                )
            )

        if min_gap is not None and merge_gap is not None and min_gap < merge_gap:
            issues.append(
                ValidationIssue(
                    "min_gap_ms",
                    "Minimum gap must be greater than or equal to merge gap to prevent overlap.",
                )
            )

        max_samples_val = _coerce_int("max_samples", self.max_samples)
        if max_samples_val is not None and max_samples_val < 1:
            issues.append(ValidationIssue("max_samples", "Max samples must be at least 1."))

        allowed_spread_modes = {"strict", "closest"}
        if (self.sample_spread_mode or "").lower() not in allowed_spread_modes:
            issues.append(
                ValidationIssue(
                    "sample_spread_mode", "Sample spread mode must be 'strict' or 'closest'."
                )
            )

        allowed_formats = {"wav", "flac"}
        if self.format and self.format.lower() not in allowed_formats:
            issues.append(
                ValidationIssue("format", "Export format must be either 'wav' or 'flac'.")
            )

        sample_rate_val = _coerce_int("sample_rate", self.sample_rate, allow_none=True)
        if sample_rate_val is not None and sample_rate_val <= 0:
            issues.append(ValidationIssue("sample_rate", "Sample rate must be greater than zero."))

        allowed_bit_depths = {"16", "24", "32f", None}
        if self.bit_depth not in allowed_bit_depths:
            issues.append(
                ValidationIssue("bit_depth", "Bit depth must be one of: 16, 24, 32f, or unset.")
            )

        allowed_channels = {"mono", "stereo", None}
        if self.channels not in allowed_channels:
            issues.append(
                ValidationIssue("channels", "Channels must be 'mono', 'stereo', or unset.")
            )

        allowed_denoise = {"off", "afftdn", "arnndn"}
        if self.denoise not in allowed_denoise:
            issues.append(
                ValidationIssue(
                    "denoise",
                    "Denoise method must be one of: off, afftdn, arnndn.",
                )
            )

        hp_val = _coerce_float("hp", self.hp, allow_none=True)
        lp_val = _coerce_float("lp", self.lp, allow_none=True)
        if hp_val is not None and hp_val < 0.0:
            issues.append(ValidationIssue("hp", "High-pass frequency cannot be negative."))
        if lp_val is not None and lp_val < 0.0:
            issues.append(ValidationIssue("lp", "Low-pass frequency cannot be negative."))
        if hp_val is not None and hp_val > 24000.0:
            issues.append(ValidationIssue("hp", "High-pass frequency must be below 24 kHz."))
        if lp_val is not None and lp_val > 24000.0:
            issues.append(ValidationIssue("lp", "Low-pass frequency must be below 24 kHz."))
        if hp_val is not None and lp_val is not None and hp_val >= lp_val:
            issues.append(
                ValidationIssue(
                    "hp",
                    "High-pass frequency must be lower than the low-pass frequency.",
                )
            )

        nr_val = _coerce_float("nr", self.nr)
        if nr_val is not None and (nr_val < 0.0 or nr_val > 30.0):
            issues.append(
                ValidationIssue("nr", "Noise reduction strength must be between 0 and 30 dB.")
            )

        analysis_sr_val = _coerce_int("analysis_sr", self.analysis_sr)
        if analysis_sr_val is not None and analysis_sr_val <= 0:
            issues.append(
                ValidationIssue("analysis_sr", "Analysis sample rate must be greater than zero.")
            )

        strategy = (self.analysis_resample_strategy or "").strip().lower()
        if strategy not in {"default", "soxr"}:
            issues.append(
                ValidationIssue(
                    "analysis_resample_strategy",
                    "Analysis resample strategy must be 'default' or 'soxr'.",
                )
            )
        else:
            self.analysis_resample_strategy = strategy
        chunk_sec_val = _coerce_float("chunk_sec", self.chunk_sec)
        if chunk_sec_val is not None and chunk_sec_val <= 0.0:
            issues.append(
                ValidationIssue("chunk_sec", "Chunk duration must be greater than zero seconds.")
            )

        resolve_allowed = {"", "keep-highest", "merge"}
        if self.resolve_overlaps not in resolve_allowed:
            issues.append(
                ValidationIssue(
                    "resolve_overlaps",
                    "Resolve overlaps must be empty, 'keep-highest', or 'merge'.",
                )
            )

        if self.overlap_iou < 0.0 or self.overlap_iou > 1.0:
            issues.append(ValidationIssue("overlap_iou", "Overlap IoU must be between 0 and 1."))

        return issues

    def to_dict(self) -> dict[str, Any]:
        """Serialize processing settings to a plain dictionary."""
        result: dict[str, Any] = {}
        for key in self._SERIALIZED_FIELDS:
            if hasattr(self, key):
                value = getattr(self, key, None)
                if value is not None:
                    result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProcessingSettings:
        """Create processing settings from a previously serialized dictionary."""
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise TypeError("ProcessingSettings.from_dict expects a dictionary.")
        return cls(**data)
