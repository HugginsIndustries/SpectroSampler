"""Transient detection using spectral flux."""


import numpy as np
from samplepacker.detectors.base import BaseDetector, Segment
from samplepacker.dsp import percentile_threshold, apply_hysteresis, spectral_flux


class TransientFluxDetector(BaseDetector):
    """Detects transients (impacts, clicks) using spectral flux peaks.

    Uses spectral flux with adaptive thresholding and hysteresis to find
    sharp transients suitable for impact detection.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold_percentile: float = 85.0,
        rise_threshold_factor: float = 1.0,
        fall_threshold_factor: float = 0.7,
        min_duration_ms: float = 50.0,
        max_duration_ms: float = 60000.0,
        fft_size: int = 2048,
        hop_size: int = 512,
        **kwargs,
    ):
        """Initialize Transient Flux detector.

        Args:
            sample_rate: Audio sample rate.
            threshold_percentile: Percentile for adaptive threshold (0-100).
            rise_threshold_factor: Multiplier for rise threshold (hysteresis).
            fall_threshold_factor: Multiplier for fall threshold (hysteresis).
            min_duration_ms: Minimum segment duration in milliseconds.
            max_duration_ms: Maximum segment duration in milliseconds.
            fft_size: FFT size for spectral analysis.
            hop_size: Hop size for spectral analysis.
            **kwargs: Additional base class parameters.
        """
        super().__init__(sample_rate=sample_rate, **kwargs)
        self.threshold_percentile = threshold_percentile
        self.rise_threshold_factor = rise_threshold_factor
        self.fall_threshold_factor = fall_threshold_factor
        self.min_duration_ms = min_duration_ms
        self.max_duration_ms = max_duration_ms
        self.fft_size = fft_size
        self.hop_size = hop_size

    def detect(self, audio: np.ndarray) -> list[Segment]:
        """Detect transient segments using spectral flux.

        Args:
            audio: Mono audio signal at self.sample_rate.

        Returns:
            List of detected transient segments.
        """
        hop = self.hop_size
        n_fft = self.fft_size
        if len(audio) < n_fft:
            return []
        n_frames = 1 + (len(audio) - n_fft) // hop
        window = np.hanning(n_fft)
        spec = np.empty((n_fft // 2 + 1, n_frames), dtype=float)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start : start + n_fft] * window
            mag = np.abs(np.fft.rfft(frame))
            spec[:, i] = mag

        flux = spectral_flux(spec)
        mu = np.mean(flux)
        sigma = np.std(flux) + 1e-9
        z = (flux - mu) / sigma
        thr = percentile_threshold(z, self.threshold_percentile)
        rise = thr * self.rise_threshold_factor
        fall = thr * self.fall_threshold_factor
        mask = apply_hysteresis(z, rise, fall)

        segments: list[Segment] = []
        in_seg = False
        seg_start = 0.0
        frame_sec = hop / self.sample_rate
        for i, on in enumerate(mask):
            t = i * frame_sec
            if on and not in_seg:
                in_seg = True
                seg_start = t
            elif not on and in_seg:
                in_seg = False
                seg_end = t
                dur_ms = (seg_end - seg_start) * 1000.0
                if self.min_duration_ms <= dur_ms <= self.max_duration_ms:
                    score = float(np.max(z[max(0, i - 4): i + 1]))
                    segments.append(Segment(seg_start, seg_end, "transient_flux", score))
        if in_seg:
            seg_end = len(mask) * frame_sec
            dur_ms = (seg_end - seg_start) * 1000.0
            if self.min_duration_ms <= dur_ms <= self.max_duration_ms:
                score = float(np.max(z))
                segments.append(Segment(seg_start, seg_end, "transient_flux", score))
        return segments
