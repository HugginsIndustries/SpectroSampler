"""Wrapper for pipeline processing in GUI context."""

import logging
from pathlib import Path
from typing import Any
from concurrent.futures import ProcessPoolExecutor, Future

from samplepacker.detectors.base import Segment
from samplepacker.pipeline import ProcessingSettings, process_file

logger = logging.getLogger(__name__)


def _detect_task(input_path: Path, output_dir: Path, settings: ProcessingSettings) -> dict[str, Any]:
    """Module-level task function for async detection (must be picklable).
    
    Args:
        input_path: Path to input audio file.
        output_dir: Output directory for temporary files.
        settings: Processing settings.
        
    Returns:
        Dictionary with processing results.
    """
    return process_file(input_path, output_dir, settings, cache=None)


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
            from samplepacker.audio_io import get_audio_info

            self.current_audio_path = audio_path
            self.current_audio_info = get_audio_info(audio_path)
            logger.info(f"Loaded audio: {audio_path}")
            return self.current_audio_info
        except Exception as e:
            logger.error(f"Failed to load audio: {e}")
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

            output_dir = Path(tempfile.mkdtemp(prefix="samplepacker_preview_"))

        # Create dry-run settings
        preview_settings = ProcessingSettings(**self.settings.__dict__)
        preview_settings.dry_run = True
        preview_settings.spectrogram = True
        preview_settings.save_temp = True

        try:
            # Process file
            result = process_file(
                self.current_audio_path,
                output_dir,
                preview_settings,
                cache=None,
            )

            self.current_segments = result.get("segments", [])
            logger.info(f"Detection complete: {len(self.current_segments)} segments found")
            return result
        except Exception as e:
            logger.error(f"Failed to detect samples: {e}")
            raise

    def detect_samples_async(self, output_dir: Path | None = None, callback: Any | None = None) -> Future:
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
            output_dir = Path(tempfile.mkdtemp(prefix="samplepacker_preview_"))

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
            except Exception:
                self._proc_executor = ProcessPoolExecutor()

        fut = self._proc_executor.submit(_detect_task, self.current_audio_path, output_dir, preview_settings)

        def _done(f: Future) -> None:
            try:
                result = f.result()
                self.current_segments = result.get("segments", [])
                logger.info(f"Detection complete: {len(self.current_segments)} segments found")
                if callback:
                    try:
                        callback(result)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Async detection failed: {e}")

        fut.add_done_callback(_done)
        return fut

    def export_samples(self, output_dir: Path, selected_indices: list[int] | None = None) -> int:
        """Export selected samples.

        Args:
            output_dir: Output directory for samples.
            selected_indices: List of segment indices to export. If None, exports all.

        Returns:
            Number of samples exported.
        """
        if not self.current_segments:
            raise ValueError("No segments available. Run process_preview first.")

        if selected_indices is None:
            selected_indices = list(range(len(self.current_segments)))

        # Export selected segments
        from samplepacker.export import build_sample_filename, export_sample

        exported_count = 0
        for idx in selected_indices:
            if idx < 0 or idx >= len(self.current_segments):
                continue

            segment = self.current_segments[idx]
            base_name = self.current_audio_path.stem if self.current_audio_path else "sample"
            filename = build_sample_filename(base_name, segment, idx, len(self.current_segments)) + ".wav"
            output_path = output_dir / filename

            try:
                export_sample(
                    input_path=self.current_audio_path,
                    output_path=output_path,
                    segment=segment,
                    pre_pad_ms=self.settings.export_pre_pad_ms,
                    post_pad_ms=self.settings.export_post_pad_ms,
                    format=self.settings.format,
                    sample_rate=self.settings.sample_rate,
                    bit_depth=self.settings.bit_depth,
                    channels=self.settings.channels,
                )
                exported_count += 1
            except Exception as e:
                logger.error(f"Failed to export sample {idx}: {e}")

        logger.info(f"Exported {exported_count} samples")
        return exported_count

