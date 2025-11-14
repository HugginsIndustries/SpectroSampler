"""Data models for advanced export configuration and per-sample overrides."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from spectrosampler.detectors.base import Segment
from spectrosampler.export import build_sample_filename
from spectrosampler.utils import sanitize_filename

SupportedExportFormat = str
DEFAULT_FILENAME_TEMPLATE = "{id}_{title}_{start}_{duration}"


def _format_list(value: Iterable[str] | None) -> list[str]:
    """Coerce an iterable of strings into a unique, ordered list."""
    if not value:
        return ["wav"]
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        lowered = item.strip().lower()
        if not lowered or lowered in seen:
            continue
        seen.add(lowered)
        result.append(lowered)
    return result or ["wav"]


def compute_sample_id(index: int, segment: Segment) -> str:
    """Return a stable identifier for a segment."""

    attrs = getattr(segment, "attrs", {}) or {}
    for key in ("id", "uuid", "guid", "uid"):
        token = attrs.get(key)
        if token:
            return str(token)
    return f"{index}-{segment.start:.6f}-{segment.end:.6f}"


class _SafeDict(dict[str, Any]):
    """Dictionary that returns template placeholders verbatim when missing."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def derive_sample_title(index: int, segment: Segment, fallback: str = "sample") -> str:
    """Return the human-friendly title for a segment."""

    attrs = getattr(segment, "attrs", {}) or {}
    raw_name = str(attrs.get("name", "")).strip()
    if raw_name:
        return raw_name
    return fallback


def _format_maybe(value: Any) -> Any:
    """Ensure floats are rendered with consistent formatting when used as tokens."""

    if isinstance(value, float):
        return f"{value:.3f}"
    return value


def build_template_context(
    *,
    base_name: str,
    sample_id: str,
    index: int,
    total: int,
    segment: Segment,
    fmt: str,
    normalize: bool,
    pre_pad_ms: float,
    post_pad_ms: float,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    year: int | None = None,
    sample_rate_hz: int | None = None,
    bit_depth: str | None = None,
    channels: str | None = None,
) -> dict[str, Any]:
    """Construct the token context used for templating filenames and notes."""

    attrs = getattr(segment, "attrs", {}) or {}
    start = float(segment.start)
    end = float(segment.end)
    duration = max(0.0, end - start)
    resolved_title = title or derive_sample_title(index, segment)
    enabled = attrs.get("enabled")
    score = getattr(segment, "score", None)

    context: dict[str, Any] = {
        "basename": base_name,
        "sample_id": sample_id,
        "id": f"{index + 1:04d}",
        "index": index + 1,
        "zero_index": index,
        "total": total,
        "title": resolved_title,
        "artist": artist or "",
        "album": album or "",
        "year": str(year) if year is not None else "",
        "format": fmt.lower(),
        "format_upper": fmt.upper(),
        "normalize": normalize,
        "normalize_suffix": "norm" if normalize else "",
        "pre_pad_ms": f"{pre_pad_ms:.1f}",
        "post_pad_ms": f"{post_pad_ms:.1f}",
        "pre_pad_ms_float": float(pre_pad_ms),
        "post_pad_ms_float": float(post_pad_ms),
        "start": f"{start:.3f}",
        "end": f"{end:.3f}",
        "duration": f"{duration:.3f}",
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": duration,
        "start_ms": int(round(start * 1000)),
        "end_ms": int(round(end * 1000)),
        "duration_ms": int(round(duration * 1000)),
        "detector": segment.detector or "",
        "score": score if score is not None else "",
        "enabled": True if enabled is None else bool(enabled),
        "sample_rate_hz": sample_rate_hz or "",
        "bit_depth": bit_depth or "",
        "channels": channels or "",
    }
    # Merge arbitrary attrs (excluding name to avoid conflicts with title token)
    for key, value in attrs.items():
        if key in {"name"}:
            continue
        token_key = f"attr_{key}"
        if token_key not in context:
            context[token_key] = _format_maybe(value)

    return context


def apply_template(template: str, context: Mapping[str, Any]) -> str:
    """Safely render a template against the provided context."""

    return template.format_map(_SafeDict(context))


def render_filename_from_template(
    *,
    template: str,
    base_name: str,
    sample_id: str,
    index: int,
    total: int,
    segment: Segment,
    fmt: str,
    normalized: bool,
    pre_pad_ms: float = 0.0,
    post_pad_ms: float = 0.0,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    year: int | None = None,
    sample_rate_hz: int | None = None,
    bit_depth: str | None = None,
    channels: str | None = None,
) -> str:
    """Render a filename from the export template, falling back to legacy naming."""

    try:
        context = build_template_context(
            base_name=base_name,
            sample_id=sample_id,
            index=index,
            total=total,
            segment=segment,
            fmt=fmt,
            normalize=normalized,
            pre_pad_ms=pre_pad_ms,
            post_pad_ms=post_pad_ms,
            title=title,
            artist=artist,
            album=album,
            year=year,
            sample_rate_hz=sample_rate_hz,
            bit_depth=bit_depth,
            channels=channels,
        )
        rendered = apply_template(template, context)
        rendered = rendered.strip()
    except Exception:
        rendered = ""

    if not rendered:
        rendered = build_sample_filename(
            base_name,
            segment,
            index,
            total,
            normalize=normalized,
        )
    return sanitize_filename(rendered)


@dataclass(slots=True)
class ExportBatchSettings:
    """Global export configuration shared across the batch."""

    formats: list[SupportedExportFormat] = field(default_factory=lambda: ["wav"])
    sample_rate_hz: int | None = None
    bit_depth: str | None = None
    channels: str | None = None
    pre_pad_ms: float = 0.0
    post_pad_ms: float = 0.0
    normalize: bool = False
    bandpass_low_hz: float | None = None
    bandpass_high_hz: float | None = None
    filename_template: str = DEFAULT_FILENAME_TEMPLATE
    output_directory: str | None = None
    artist: str = "SpectroSampler"
    album: str | None = None
    year: int | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExportBatchSettings:
        """Construct settings from a serialized dictionary."""
        if not isinstance(data, dict):
            data = {}
        formats = _format_list(data.get("formats"))
        sample_rate = data.get("sample_rate_hz")
        if isinstance(sample_rate, str) and sample_rate.isdigit():
            sample_rate = int(sample_rate)
        elif not isinstance(sample_rate, int):
            sample_rate = None
        bit_depth = data.get("bit_depth")
        if bit_depth not in {None, "16", "24", "32f"}:
            bit_depth = None
        channels = data.get("channels")
        if channels not in {None, "mono", "stereo"}:
            channels = None
        pre_pad = float(data.get("pre_pad_ms", 0.0) or 0.0)
        post_pad = float(data.get("post_pad_ms", 0.0) or 0.0)
        normalize = bool(data.get("normalize", False))
        bandpass_low = data.get("bandpass_low_hz")
        if bandpass_low is not None:
            try:
                bandpass_low = float(bandpass_low)
            except (TypeError, ValueError):
                bandpass_low = None
        bandpass_high = data.get("bandpass_high_hz")
        if bandpass_high is not None:
            try:
                bandpass_high = float(bandpass_high)
            except (TypeError, ValueError):
                bandpass_high = None
        filename_template_raw = data.get("filename_template")
        if filename_template_raw in (None, "", "{basename}_sample_{index:04d}"):
            filename_template = DEFAULT_FILENAME_TEMPLATE
        else:
            filename_template = str(filename_template_raw)
        output_directory = data.get("output_directory")
        if output_directory is not None:
            output_directory = str(output_directory)
        artist = str(data.get("artist", "SpectroSampler") or "SpectroSampler")
        album = data.get("album")
        if album is not None:
            album = str(album)
        year = data.get("year")
        try:
            year_value: int | None
            if year in (None, "", 0):
                year_value = None
            else:
                year_value = int(year)
        except (TypeError, ValueError):
            year_value = None

        return cls(
            formats=formats,
            sample_rate_hz=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            pre_pad_ms=pre_pad,
            post_pad_ms=post_pad,
            normalize=normalize,
            bandpass_low_hz=bandpass_low,
            bandpass_high_hz=bandpass_high,
            filename_template=filename_template,
            output_directory=output_directory,
            artist=artist,
            album=album,
            year=year_value,
            notes=str(data.get("notes")) if data.get("notes") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise settings to a JSON-friendly dictionary."""
        return {
            "formats": list(self.formats) or ["wav"],
            "sample_rate_hz": self.sample_rate_hz,
            "bit_depth": self.bit_depth,
            "channels": self.channels,
            "pre_pad_ms": float(self.pre_pad_ms),
            "post_pad_ms": float(self.post_pad_ms),
            "normalize": bool(self.normalize),
            "bandpass_low_hz": self.bandpass_low_hz,
            "bandpass_high_hz": self.bandpass_high_hz,
            "filename_template": self.filename_template,
            "output_directory": self.output_directory,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "notes": self.notes,
        }


@dataclass(slots=True)
class ExportSampleOverride:
    """Per-sample export overrides that supplement global batch settings."""

    sample_id: str
    formats: list[SupportedExportFormat] | None = None
    sample_rate_hz: int | None = None
    bit_depth: str | None = None
    channels: str | None = None
    pre_pad_ms: float | None = None
    post_pad_ms: float | None = None
    normalize: bool | None = None
    bandpass_low_hz: float | None = None
    bandpass_high_hz: float | None = None
    filename: str | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExportSampleOverride:
        """Create an override instance from a dictionary."""
        if not isinstance(data, dict):
            raise ValueError("ExportSampleOverride requires a mapping payload.")
        sample_id = str(data.get("sample_id") or "")
        if not sample_id:
            raise ValueError("ExportSampleOverride.sample_id cannot be empty.")

        def _opt_int(value: Any) -> int | None:
            if value in (None, "", 0):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def _opt_float(value: Any) -> float | None:
            if value in (None, ""):
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        formats = data.get("formats")
        if formats is not None:
            formats = _format_list(formats)

        return cls(
            sample_id=sample_id,
            formats=formats,
            sample_rate_hz=_opt_int(data.get("sample_rate_hz")),
            bit_depth=data.get("bit_depth") if isinstance(data.get("bit_depth"), str) else None,
            channels=data.get("channels") if isinstance(data.get("channels"), str) else None,
            pre_pad_ms=_opt_float(data.get("pre_pad_ms")),
            post_pad_ms=_opt_float(data.get("post_pad_ms")),
            normalize=bool(data["normalize"]) if "normalize" in data else None,
            bandpass_low_hz=_opt_float(data.get("bandpass_low_hz")),
            bandpass_high_hz=_opt_float(data.get("bandpass_high_hz")),
            filename=str(data.get("filename")) if data.get("filename") else None,
            title=str(data.get("title")) if data.get("title") else None,
            artist=str(data.get("artist")) if data.get("artist") else None,
            album=str(data.get("album")) if data.get("album") else None,
            year=_opt_int(data.get("year")),
            notes=str(data.get("notes")) if data.get("notes") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise override into a JSON-friendly dictionary."""
        payload: dict[str, Any] = {"sample_id": self.sample_id}
        if self.formats:
            payload["formats"] = list(self.formats)
        if self.sample_rate_hz is not None:
            payload["sample_rate_hz"] = self.sample_rate_hz
        if self.bit_depth is not None:
            payload["bit_depth"] = self.bit_depth
        if self.channels is not None:
            payload["channels"] = self.channels
        if self.pre_pad_ms is not None:
            payload["pre_pad_ms"] = self.pre_pad_ms
        if self.post_pad_ms is not None:
            payload["post_pad_ms"] = self.post_pad_ms
        if self.normalize is not None:
            payload["normalize"] = self.normalize
        if self.bandpass_low_hz is not None:
            payload["bandpass_low_hz"] = self.bandpass_low_hz
        if self.bandpass_high_hz is not None:
            payload["bandpass_high_hz"] = self.bandpass_high_hz
        if self.filename:
            payload["filename"] = self.filename
        if self.title:
            payload["title"] = self.title
        if self.artist:
            payload["artist"] = self.artist
        if self.album:
            payload["album"] = self.album
        if self.year is not None:
            payload["year"] = self.year
        if self.notes:
            payload["notes"] = self.notes
        return payload

    def is_empty(self) -> bool:
        """Return True when no override fields are set."""

        return all(
            getattr(self, field) in (None, [], "")
            for field in (
                "formats",
                "sample_rate_hz",
                "bit_depth",
                "channels",
                "pre_pad_ms",
                "post_pad_ms",
                "normalize",
                "bandpass_low_hz",
                "bandpass_high_hz",
                "filename",
                "title",
                "artist",
                "album",
                "year",
                "notes",
            )
        )


def serialise_overrides(overrides: Iterable[ExportSampleOverride]) -> list[dict[str, Any]]:
    """Serialise a sequence of overrides to a list of dictionaries."""
    return [override.to_dict() for override in overrides]


def parse_overrides(payload: Any) -> list[ExportSampleOverride]:
    """Parse overrides from a JSON-derived payload."""
    if not payload:
        return []
    if not isinstance(payload, list):
        raise ValueError("Overrides payload must be a list.")
    result: list[ExportSampleOverride] = []
    for item in payload:
        try:
            result.append(ExportSampleOverride.from_dict(item))
        except ValueError:
            continue
    return result
