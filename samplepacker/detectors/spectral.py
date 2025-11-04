"""Spectral interestingness detection using multiple features."""


import numpy as np
from samplepacker.detectors.base import BaseDetector, Segment
from samplepacker.dsp import (
    percentile_threshold,
    spectral_centroid,
    spectral_flatness,
    spectral_rolloff,
    z_score_normalize,
)


class SpectralInterestingnessDetector(BaseDetector):
    """Detects spectrally interesting regions using weighted feature combination.

    Combines flux, centroid, rolloff, flatness, and RMS to find regions
    with dynamic spectral content.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold_percentile: float = 85.0,
        min_duration_ms: float = 400.0,
        fft_size: int = 2048,
        hop_size: int = 512,
        weights: dict[str, float] | None = None,
        **kwargs,
    ):
        """Initialize Spectral Interestingness detector.

        Args:
            sample_rate: Audio sample rate.
            threshold_percentile: Percentile for adaptive threshold (0-100).
            min_duration_ms: Minimum segment duration in milliseconds.
            fft_size: FFT size for spectral analysis.
            hop_size: Hop size for spectral analysis.
            weights: Optional weights for features: flux, centroid, rolloff,
                     flatness, rms. Defaults to equal weights.
            **kwargs: Additional base class parameters.
        """
        super().__init__(sample_rate=sample_rate, **kwargs)
        self.threshold_percentile = threshold_percentile
        self.min_duration_ms = min_duration_ms
        self.fft_size = fft_size
        self.hop_size = hop_size

        default_weights = {
            "flux": 0.25,
            "centroid": 0.2,
            "rolloff": 0.2,
            "flatness": 0.15,
            "rms": 0.2,
        }
        self.weights = weights if weights else default_weights

    def detect(self, audio: np.ndarray) -> list[Segment]:
        """Detect spectrally interesting segments.

        Args:
            audio: Mono audio signal at self.sample_rate.

        Returns:
            List of detected interesting segments.
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

        freqs = np.fft.rfftfreq(n_fft, d=1.0 / self.sample_rate)

        flux = np.concatenate([[0.0], np.sum(np.maximum(np.diff(spec, axis=1), 0), axis=0)])
        centroids = np.array([spectral_centroid(freqs, spec[:, i]) for i in range(n_frames)])
        rolloffs = np.array([spectral_rolloff(freqs, spec[:, i]) for i in range(n_frames)])
        flatness = np.array([spectral_flatness(spec[:, i]) for i in range(n_frames)])
        rms = np.sqrt(np.mean(spec * spec, axis=0) + 1e-12)

        z_flux = z_score_normalize(flux)
        z_cent = z_score_normalize(centroids)
        z_roll = z_score_normalize(rolloffs)
        z_flat = -z_score_normalize(flatness)
        z_rms = z_score_normalize(rms)

        w = self.weights
        score = (
            w.get("flux", 1.0) * z_flux
            + w.get("centroid", 0.6) * z_cent
            + w.get("rolloff", 0.4) * z_roll
            + w.get("flatness", -0.5) * (-z_flat)
            + w.get("rms", 0.8) * z_rms
        )
        score_z = z_score_normalize(score)
        thr = percentile_threshold(score_z, self.threshold_percentile)
        mask = score_z >= thr

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
                if (seg_end - seg_start) * 1000.0 >= self.min_duration_ms:
                    segments.append(
                        Segment(
                            seg_start,
                            seg_end,
                            "spectral_interestingness",
                            float(np.max(score_z[max(0, i - 4) : i + 1])),
                        )
                    )
        if in_seg:
            seg_end = len(mask) * frame_sec
            if (seg_end - seg_start) * 1000.0 >= self.min_duration_ms:
                segments.append(
                    Segment(
                        seg_start, seg_end, "spectral_interestingness", float(np.max(score_z))
                    )
                )
        return segments
