"""Wrapper for pipeline processing in GUI context."""

import errno
import logging
from collections.abc import Sequence
from concurrent.futures import CancelledError, Future, ProcessPoolExecutor
from pathlib import Path
from typing import Any

from spectrosampler.audio_io import FFmpegError
from spectrosampler.detectors.base import Segment
from spectrosampler.gui.export_manager import ExportManager
from spectrosampler.gui.export_models import ExportBatchSettings, ExportSampleOverride
from spectrosampler.pipeline_settings import ProcessingSettings

logger = logging.getLogger(__name__)


def _invoke_process_file(
    input_path: Path,
    output_dir: Path,
    settings: ProcessingSettings,
    cache: Any | None = None,
) -> dict[str, Any]:
    """Load pipeline module lazily and run process_file."""
    from spectrosampler import pipeline as pipeline_module

    return pipeline_module.process_file(input_path, output_dir, settings, cache=cache)


def _detect_task(
    input_path: Path, output_dir: Path, settings: ProcessingSettings
) -> dict[str, Any]:
    """Module-level task function for async detection (must be picklable).

    Args:
        input_path: Path to input audio file.
        output_dir: Output directory for temporary files.
        settings: Processing settings.

    Returns:
        Dictionary with processing results.
    """
    return _invoke_process_file(input_path, output_dir, settings, cache=None)


class PipelineWrapper:
    """Wrapper for pipeline processing with GUI-friendly interface."""

    def __init__(self, settings: ProcessingSettings):
        """Initialize pipeline wrapper.

        Args:
            settings: Processing settings.
        """
        self.settings = settings
        self.current_audio_path: Path | None = None
        self.current_audio_info: dict[str, Any] | None = None
        self.current_segments: list[Segment] = []
        self._proc_executor: ProcessPoolExecutor | None = None

    def load_audio(self, audio_path: Path) -> dict[str, Any]:
        """Load audio file and get metadata.

        Args:
            audio_path: Path to audio file.

        Returns:
            Dictionary with audio metadata.
        """
        try:
            if not audio_path.exists() or not audio_path.is_file():
                raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(audio_path))
            from spectrosampler.audio_io import get_audio_info

            self.current_audio_path = audio_path
            self.current_audio_info = get_audio_info(audio_path)
            logger.info(f"Loaded audio: {audio_path}")
            return self.current_audio_info
        except (FFmpegError, OSError, ValueError) as exc:
            logger.error("Failed to load audio %s: %s", audio_path, exc, exc_info=exc)
            raise

    def detect_samples(self, output_dir: Path | None = None) -> dict[str, Any]:
        """Run sample detection (dry-run mode for GUI).

        Args:
            output_dir: Optional output directory for temporary files.

        Returns:
            Dictionary with processing results (segments, audio_info, etc.).
        """
        if not self.current_audio_path:
            raise ValueError("No audio file loaded")

        # Create temporary output directory if not provided
        if output_dir is None:
            import tempfile

            output_dir = Path(tempfile.mkdtemp(prefix="spectrosampler_preview_"))

        # Create dry-run settings
        preview_settings = ProcessingSettings(**self.settings.__dict__)
        preview_settings.dry_run = True
        preview_settings.spectrogram = True
        preview_settings.save_temp = True

        try:
            # Process file
            result = _invoke_process_file(
                self.current_audio_path,
                output_dir,
                preview_settings,
                cache=None,
            )

            self.current_segments = result.get("segments", [])
            logger.info(f"Detection complete: {len(self.current_segments)} segments found")
            return result
        except (FFmpegError, OSError, RuntimeError, ValueError) as exc:
            logger.error(
                "Failed to detect samples for %s: %s", self.current_audio_path, exc, exc_info=exc
            )
            raise

    def detect_samples_async(
        self, output_dir: Path | None = None, callback: Any | None = None
    ) -> Future:
        """Run sample detection in a background process and return a Future.

        Args:
            output_dir: Optional output directory for temporary files.
            callback: Optional function(result_dict) called on completion.
        """
        if not self.current_audio_path:
            raise ValueError("No audio file loaded")

        # Create temporary output directory if not provided
        if output_dir is None:
            import tempfile

            output_dir = Path(tempfile.mkdtemp(prefix="spectrosampler_preview_"))

        # Prepare settings (dry run for GUI)
        preview_settings = ProcessingSettings(**self.settings.__dict__)
        preview_settings.dry_run = True
        preview_settings.spectrogram = True
        preview_settings.save_temp = True

        # Lazy init executor with user-configurable workers if present
        if self._proc_executor is None:
            try:
                import os

                max_workers = getattr(self.settings, "max_workers", None)
                if not isinstance(max_workers, int) or max_workers <= 0:
                    max_workers = max(1, (os.cpu_count() or 4) - 1)
                self._proc_executor = ProcessPoolExecutor(max_workers=max_workers)
            except (OSError, ValueError, RuntimeError) as exc:
                logger.warning(
                    "Falling back to default process pool configuration: %s", exc, exc_info=exc
                )
                self._proc_executor = ProcessPoolExecutor()

        fut = self._proc_executor.submit(
            _detect_task, self.current_audio_path, output_dir, preview_settings
        )
        if callback is not None:

            def _done(f: Future) -> None:
                exc = f.exception()
                if exc is not None:
                    if isinstance(exc, CancelledError):
                        logger.info("Async detection task was cancelled.")
                    else:
                        logger.error("Async detection failed: %s", exc, exc_info=exc)
                    return
                try:
                    result = f.result()
                except CancelledError:
                    logger.info("Async detection task was cancelled during result retrieval.")
                    return
                self.current_segments = result.get("segments", [])
                logger.info(f"Detection complete: {len(self.current_segments)} segments found")
                if callback:
                    try:
                        callback(result)
                    except (RuntimeError, TypeError, ValueError) as cb_exc:
                        logger.error("Detection callback failed: %s", cb_exc, exc_info=cb_exc)

            fut.add_done_callback(_done)
        return fut

    def export_samples(
        self,
        output_dir: Path,
        selected_indices: list[int] | None = None,
        batch_settings: ExportBatchSettings | None = None,
        overrides: Sequence[ExportSampleOverride] | None = None,
    ) -> int:
        """Export selected samples.

        Args:
            output_dir: Output directory for samples.
            selected_indices: List of segment indices to export. If None, exports all.
            batch_settings: Export batch settings to apply. When None, derive from pipeline settings.
            overrides: Per-sample overrides to apply during export.

        Returns:
            Number of samples exported.
        """
        if not self.current_segments:
            raise ValueError("No segments available. Run process_preview first.")
        if self.current_audio_path is None:
            raise ValueError("No audio file loaded.")

        if selected_indices is None:
            selected_indices = list(range(len(self.current_segments)))

        if batch_settings is None:
            batch_settings = ExportBatchSettings(
                formats=[self.settings.format],
                sample_rate_hz=self.settings.sample_rate,
                bit_depth=self.settings.bit_depth,
                channels=self.settings.channels,
                pre_pad_ms=self.settings.export_pre_pad_ms,
                post_pad_ms=self.settings.export_post_pad_ms,
                normalize=self.settings.export_normalize,
                bandpass_low_hz=self.settings.export_bandpass_low_hz,
                bandpass_high_hz=self.settings.export_bandpass_high_hz,
                filename_template=self.settings.export_filename_template,
                output_directory=str(output_dir),
                artist=self.settings.export_artist,
                album=self.settings.export_album
                or (self.current_audio_path.stem if self.current_audio_path else None),
                year=self.settings.export_year,
            )

        manager = self.create_export_manager(
            output_dir=output_dir,
            batch_settings=batch_settings,
            overrides=overrides or [],
        )

        summary = manager.execute_blocking(selected_indices)
        logger.info(
            "Export summary: %d success, %d failed, cancelled=%s",
            summary.successful_count,
            len(summary.failed),
            summary.cancelled,
        )
        return summary.successful_count

    def create_export_manager(
        self,
        *,
        output_dir: Path,
        batch_settings: ExportBatchSettings,
        overrides: Sequence[ExportSampleOverride],
    ) -> ExportManager:
        """Instantiate an export manager for the current pipeline configuration."""

        if not self.current_segments:
            raise ValueError("No segments available. Run process_preview first.")
        if self.current_audio_path is None:
            raise ValueError("No audio file loaded.")

        manager = ExportManager(
            audio_path=self.current_audio_path,
            segments=self.current_segments,
            batch_settings=batch_settings,
            overrides=overrides,
            output_dir=output_dir,
            base_name=self.current_audio_path.stem,
        )
        return manager
