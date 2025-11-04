"""Base classes and data structures for audio event detectors."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Segment:
    """Represents a detected audio segment.

    Attributes:
        start: Start time in seconds.
        end: End time in seconds.
        detector: Name of the detector that found this segment.
        score: Detection confidence/score (detector-dependent).
        attrs: Additional attributes specific to the detector.
    """

    start: float
    end: float
    detector: str
    score: float
    attrs: dict[str, Any] = field(default_factory=dict)

    def duration(self) -> float:
        """Return segment duration in seconds."""
        return self.end - self.start

    def overlaps(self, other: "Segment", gap_ms: float = 0.0) -> bool:
        """Check if this segment overlaps with another (within gap_ms tolerance).

        Args:
            other: Another segment to check.
            gap_ms: Gap tolerance in milliseconds (segments within this gap are
                    considered overlapping).

        Returns:
            True if segments overlap or are within gap_ms of each other.
        """
        gap_sec = gap_ms / 1000.0
        return not (self.end + gap_sec < other.start or other.end + gap_sec < self.start)

    def merge(self, other: "Segment") -> "Segment":
        """Merge this segment with another overlapping segment.

        Args:
            other: Segment to merge with.

        Returns:
            New merged segment.
        """
        merged_start = min(self.start, other.start)
        merged_end = max(self.end, other.end)
        return Segment(
            start=merged_start,
            end=merged_end,
            detector=f"{self.detector}+{other.detector}",
            score=max(self.score, other.score),
            attrs={**self.attrs, **other.attrs},
        )


class BaseDetector:
    """Abstract base class for audio event detectors.

    All detectors must implement the `detect` method that takes audio
    and returns a list of Segment objects.
    """

    def __init__(self, sample_rate: int = 16000, **kwargs):
        """Initialize detector.

        Args:
            sample_rate: Expected sample rate of input audio.
            **kwargs: Detector-specific parameters.
        """
        self.sample_rate = sample_rate
        self.name = self.__class__.__name__.replace("Detector", "").lower()

    def detect(self, audio: np.ndarray) -> list[Segment]:
        """Detect segments in audio.

        Args:
            audio: Mono audio signal at self.sample_rate.

        Returns:
            List of detected segments.
        """
        raise NotImplementedError("Subclasses must implement detect()")

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}(sr={self.sample_rate})"
