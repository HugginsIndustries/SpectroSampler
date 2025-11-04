"""Non-silence detection using energy envelope."""


import numpy as np
from samplepacker.detectors.base import BaseDetector, Segment
from samplepacker.dsp import rms_envelope, z_score_normalize, percentile_threshold, apply_hysteresis


class NonSilenceEnergyDetector(BaseDetector):
    """Detects non-silent regions using z-scored RMS envelope with hysteresis.

    Useful for removing constant background (e.g., rain) by detecting
    regions with energy significantly above the mean.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold_percentile: float = 75.0,
        rise_threshold_factor: float = 1.0,
        fall_threshold_factor: float = 0.8,
        min_duration_ms: float = 400.0,
        window_size_ms: float = 100.0,
        hop_size_ms: float = 50.0,
        **kwargs,
    ):
        """Initialize Non-Silence Energy detector.

        Args:
            sample_rate: Audio sample rate.
            threshold_percentile: Percentile for adaptive threshold (0-100).
            rise_threshold_factor: Multiplier for rise threshold (hysteresis).
            fall_threshold_factor: Multiplier for fall threshold (hysteresis).
            min_duration_ms: Minimum segment duration in milliseconds.
            window_size_ms: RMS window size in milliseconds.
            hop_size_ms: RMS hop size in milliseconds.
            **kwargs: Additional base class parameters.
        """
        super().__init__(sample_rate=sample_rate, **kwargs)
        self.threshold_percentile = threshold_percentile
        self.rise_threshold_factor = rise_threshold_factor
        self.fall_threshold_factor = fall_threshold_factor
        self.min_duration_ms = min_duration_ms
        self.window_size = int(sample_rate * window_size_ms / 1000.0)
        self.hop_size = int(sample_rate * hop_size_ms / 1000.0)

    def detect(self, audio: np.ndarray) -> list[Segment]:
        """Detect non-silence segments using energy envelope.

        Args:
            audio: Mono audio signal at self.sample_rate.

        Returns:
            List of detected non-silence segments.
        """
        if len(audio) < self.window_size:
            return []
        env = rms_envelope(audio, self.window_size, self.hop_size)
        if env.size == 0:
            return []
        z = z_score_normalize(env)
        thr = percentile_threshold(z, self.threshold_percentile)
        rise = thr * self.rise_threshold_factor
        fall = thr * self.fall_threshold_factor
        mask = apply_hysteresis(z, rise, fall)

        segments: list[Segment] = []
        in_seg = False
        seg_start = 0.0
        frame_sec = self.hop_size / self.sample_rate
        for i, on in enumerate(mask):
            t = i * frame_sec
            if on and not in_seg:
                in_seg = True
                seg_start = t
            elif not on and in_seg:
                in_seg = False
                seg_end = t
                if (seg_end - seg_start) * 1000.0 >= self.min_duration_ms:
                    segments.append(
                        Segment(
                            seg_start,
                            seg_end,
                            "nonsilence_energy",
                            float(np.max(z[max(0, i - 4) : i + 1])),
                        )
                    )
        if in_seg:
            seg_end = len(mask) * frame_sec
            if (seg_end - seg_start) * 1000.0 >= self.min_duration_ms:
                segments.append(
                    Segment(seg_start, seg_end, "nonsilence_energy", float(np.max(z)))
                )
        return segments
