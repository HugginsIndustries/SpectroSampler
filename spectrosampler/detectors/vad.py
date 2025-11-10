"""Voice Activity Detection using WebRTC VAD."""

import logging

import numpy as np

try:
    import webrtcvad
except ImportError:
    webrtcvad = None  # type: ignore

from spectrosampler.detectors.base import BaseDetector, Segment
from spectrosampler.dsp import bandpass_filter


class VoiceVADDetector(BaseDetector):
    """Voice Activity Detector using WebRTC VAD.

    Applies WebRTC VAD to denoised 16k mono audio with configurable
    aggressiveness and optional pre-bandpass filtering.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        aggressiveness: int = 2,
        frame_duration_ms: int = 30,
        min_duration_ms: float = 400.0,
        low_freq: float | None = 200.0,
        high_freq: float | None = 4500.0,
        **kwargs,
    ):
        """Initialize Voice VAD detector.

        Args:
            sample_rate: Audio sample rate (must be 8000, 16000, or 32000).
            aggressiveness: VAD aggressiveness (0-3, higher = more strict).
            frame_duration_ms: Frame duration for VAD (10, 20, or 30 ms).
            min_duration_ms: Minimum segment duration in milliseconds.
            low_freq: Optional low cutoff for pre-filtering (Hz).
            high_freq: Optional high cutoff for pre-filtering (Hz).
            **kwargs: Additional base class parameters.
        """
        super().__init__(sample_rate=sample_rate, **kwargs)
        if sample_rate not in (8000, 16000, 32000):
            raise ValueError(f"VAD requires sample_rate in [8000, 16000, 32000], got {sample_rate}")
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError(f"frame_duration_ms must be 10, 20, or 30, got {frame_duration_ms}")
        if aggressiveness not in (0, 1, 2, 3):
            raise ValueError(f"aggressiveness must be 0-3, got {aggressiveness}")

        self.aggressiveness = aggressiveness
        self.frame_duration_ms = frame_duration_ms
        self.min_duration_ms = min_duration_ms
        self.low_freq = low_freq
        self.high_freq = high_freq

        # Allow initialization even if webrtcvad is unavailable (tests can still run).
        # In that case, detect() will return no segments.
        self._vad_available = webrtcvad is not None
        self.vad = webrtcvad.Vad(aggressiveness) if self._vad_available else None  # type: ignore
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)

    def _prefilter_audio(self, audio: np.ndarray) -> np.ndarray:
        """Apply optional bandpass filtering ahead of VAD analysis."""
        data = np.asarray(audio)
        if data.ndim != 1:
            raise ValueError("VoiceVADDetector expects 1D mono audio.")
        if data.size == 0:
            return data

        nyquist = self.sample_rate / 2.0
        low = float(self.low_freq) if self.low_freq is not None else 0.0
        high = float(self.high_freq) if self.high_freq is not None else nyquist

        if low <= 0.0 and high >= nyquist:
            return data

        try:
            return bandpass_filter(data, self.sample_rate, low, high)
        except (ValueError, RuntimeError) as exc:
            logging.debug(
                "VoiceVADDetector bandpass filter failed (low=%s, high=%s): %s",
                self.low_freq,
                self.high_freq,
                exc,
                exc_info=exc,
            )
            return data

    def detect(self, audio: np.ndarray) -> list[Segment]:
        """Detect voice segments in audio.

        Args:
            audio: Mono audio signal at self.sample_rate.

        Returns:
            List of detected voice segments.
        """
        if not self._vad_available:
            return []

        filtered_audio = self._prefilter_audio(audio)

        # Convert to 16-bit PCM for VAD
        pcm16 = np.clip(filtered_audio, -1.0, 1.0)
        pcm16 = (pcm16 * 32768.0).astype(np.int16)
        frame_samples = self.frame_size
        bytes_per_frame = frame_samples * 2
        raw = pcm16.tobytes()
        num_frames = len(raw) // bytes_per_frame
        voiced = []
        for i in range(num_frames):
            start_b = i * bytes_per_frame
            frame = raw[start_b : start_b + bytes_per_frame]
            is_voiced = self.vad.is_speech(frame, self.sample_rate)
            voiced.append(1.0 if is_voiced else 0.0)

        # Merge consecutive voiced frames into segments
        segments: list[Segment] = []
        in_seg = False
        seg_start = 0
        for i, v in enumerate(voiced):
            t = i * (self.frame_duration_ms / 1000.0)
            if v >= 0.5 and not in_seg:
                in_seg = True
                seg_start = t
            elif v < 0.5 and in_seg:
                in_seg = False
                seg_end = t
                if (seg_end - seg_start) * 1000.0 >= self.min_duration_ms:
                    segments.append(Segment(seg_start, seg_end, "voice_vad", 1.0))
        # Tail
        if in_seg:
            seg_end = len(voiced) * (self.frame_duration_ms / 1000.0)
            if (seg_end - seg_start) * 1000.0 >= self.min_duration_ms:
                segments.append(Segment(seg_start, seg_end, "voice_vad", 1.0))

        return segments
