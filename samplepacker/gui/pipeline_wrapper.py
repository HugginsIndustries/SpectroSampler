"""Wrapper for pipeline processing in GUI context."""

import logging
from pathlib import Path
from typing import Any

from samplepacker.detectors.base import Segment
from samplepacker.pipeline import ProcessingSettings, process_file

logger = logging.getLogger(__name__)


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

    def process_preview(self, output_dir: Path | None = None) -> dict[str, Any]:
        """Process audio for preview (dry-run mode).

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
            logger.info(f"Processed preview: {len(self.current_segments)} segments found")
            return result
        except Exception as e:
            logger.error(f"Failed to process preview: {e}")
            raise

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
                    pre_pad_ms=self.settings.pre_pad_ms,
                    post_pad_ms=self.settings.post_pad_ms,
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

