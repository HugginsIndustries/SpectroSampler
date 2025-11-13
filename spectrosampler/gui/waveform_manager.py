"""Background waveform generation utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf
from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WaveformData:
    """Container for downsampled waveform data."""

    times: npt.NDArray[np.float32]
    peak_positive: npt.NDArray[np.float32]
    peak_negative: npt.NDArray[np.float32]
    duration: float
    sample_rate: int
    max_abs: float


class WaveformWorker(QThread):
    """Worker thread that downsamples audio into a drawable waveform envelope."""

    finished = Signal(WaveformData)
    error = Signal(str)

    def __init__(
        self,
        audio_path: Path,
        *,
        max_bins: int = 200_000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._audio_path = audio_path
        self._max_bins = max(1000, max_bins)
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the worker."""
        self._cancelled = True

    def run(self) -> None:
        """Generate waveform envelope data."""
        try:
            with sf.SoundFile(self._audio_path) as sf_file:
                sample_rate = int(sf_file.samplerate)
                total_frames = int(sf_file.frames)
                duration = total_frames / sample_rate if sample_rate > 0 else 0.0

                if total_frames == 0 or sample_rate <= 0:
                    dtype = np.float32
                    empty = np.empty(0, dtype=dtype)
                    data = WaveformData(empty, empty, empty, duration, sample_rate, 1.0)
                    if not self._cancelled:
                        self.finished.emit(data)
                    return

                # Determine aggregation size so we cap the total number of bins.
                samples_per_bin = max(1, total_frames // self._max_bins)
                block_size = samples_per_bin * 1024
                if block_size < samples_per_bin:
                    block_size = samples_per_bin

                peaks_pos: list[np.float32] = []
                peaks_neg: list[np.float32] = []
                times: list[np.float32] = []

                frame_cursor = 0
                buffer = np.empty(0, dtype=np.float32)

                while not self._cancelled:
                    block = sf_file.read(block_size, dtype="float32", always_2d=False)
                    if block.size == 0:
                        break
                    if block.ndim > 1:
                        block = np.mean(block, axis=1, dtype=np.float32)

                    data = np.concatenate([buffer, block.astype(np.float32, copy=False)])
                    if data.size < samples_per_bin:
                        buffer = data
                        continue

                    bin_count = data.size // samples_per_bin
                    usable = bin_count * samples_per_bin
                    reshaped = data[:usable].reshape(bin_count, samples_per_bin)
                    peaks_pos.extend(np.max(reshaped, axis=1).astype(np.float32, copy=False))
                    peaks_neg.extend(np.min(reshaped, axis=1).astype(np.float32, copy=False))

                    start_indices = (
                        frame_cursor + np.arange(bin_count, dtype=np.float32) * samples_per_bin
                    )
                    bin_centers = (start_indices + samples_per_bin / 2.0) / sample_rate
                    times.extend(bin_centers.astype(np.float32, copy=False))

                    frame_cursor += usable
                    buffer = data[usable:]

                if not self._cancelled and buffer.size:
                    max_val = float(np.max(buffer))
                    min_val = float(np.min(buffer))
                    peaks_pos.append(np.float32(max_val))
                    peaks_neg.append(np.float32(min_val))
                    center = (frame_cursor + buffer.size / 2.0) / sample_rate
                    times.append(np.float32(center))

                if self._cancelled:
                    return

                dtype = np.float32
                pos_arr = np.array(peaks_pos, dtype=dtype, copy=False)
                neg_arr = np.array(peaks_neg, dtype=dtype, copy=False)
                time_arr = np.array(times, dtype=dtype, copy=False)

                if time_arr.size == 0:
                    # Ensure arrays are consistently empty
                    pos_arr = np.empty(0, dtype=dtype)
                    neg_arr = np.empty(0, dtype=dtype)
                    time_arr = np.empty(0, dtype=dtype)

                max_abs = float(
                    max(
                        np.max(pos_arr) if pos_arr.size else 0.0,
                        abs(np.min(neg_arr)) if neg_arr.size else 0.0,
                        1e-6,
                    )
                )

                payload = WaveformData(
                    times=time_arr,
                    peak_positive=pos_arr,
                    peak_negative=neg_arr,
                    duration=duration,
                    sample_rate=sample_rate,
                    max_abs=max_abs,
                )
                self.finished.emit(payload)
        except (RuntimeError, ValueError, OSError) as exc:
            if self._cancelled:
                return
            logger.error(
                "Waveform generation failed for %s: %s", self._audio_path, exc, exc_info=exc
            )
            self.error.emit(str(exc))


class WaveformManager(QObject):
    """Manage waveform generation in a background worker thread."""

    finished = Signal(WaveformData)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: WaveformWorker | None = None

    def start_generation(self, audio_path: Path, *, max_bins: int = 200_000) -> None:
        """Start waveform generation for the provided audio file."""
        if self._worker and self._worker.isRunning():
            self.cancel()

        self._worker = WaveformWorker(audio_path, max_bins=max_bins, parent=self)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._worker.start()

    def cancel(self) -> None:
        """Cancel any in-flight waveform generation."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            if not self._worker.wait(2000):
                logger.warning("Waveform worker did not finish in time; terminating thread")
                self._worker.terminate()
                self._worker.wait(1000)
            self._worker.deleteLater()
            self._worker = None

    def is_generating(self) -> bool:
        """Return True when a waveform is currently being generated."""
        return self._worker is not None and self._worker.isRunning()

    def _on_worker_finished(self, data: WaveformData) -> None:
        self._worker = None
        self.finished.emit(data)

    def _on_worker_error(self, message: str) -> None:
        self._worker = None
        self.error.emit(message)
