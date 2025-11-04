"""Preview manager for background processing."""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from samplepacker.gui.pipeline_wrapper import PipelineWrapper
from samplepacker.pipeline import ProcessingSettings

logger = logging.getLogger(__name__)


class PreviewWorker(QThread):
    """Worker thread for preview processing."""

    progress = Signal(str)  # Emitted with progress message
    finished = Signal(dict)  # Emitted with processing results
    error = Signal(str)  # Emitted with error message

    def __init__(self, pipeline_wrapper: PipelineWrapper, output_dir: Path | None = None):
        """Initialize preview worker.

        Args:
            pipeline_wrapper: PipelineWrapper instance.
            output_dir: Optional output directory for temporary files.
        """
        super().__init__()
        self.pipeline_wrapper = pipeline_wrapper
        self.output_dir = output_dir
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel processing."""
        self._cancelled = True

    def run(self) -> None:
        """Run preview processing."""
        try:
            self.progress.emit("Processing audio...")
            result = self.pipeline_wrapper.process_preview(self.output_dir)
            if not self._cancelled:
                self.finished.emit(result)
        except Exception as e:
            logger.error(f"Preview processing error: {e}")
            if not self._cancelled:
                self.error.emit(str(e))


class PreviewManager(QObject):
    """Manages preview processing in background thread."""

    progress = Signal(str)  # Emitted with progress message
    finished = Signal(dict)  # Emitted with processing results
    error = Signal(str)  # Emitted with error message

    def __init__(self, parent: QObject | None = None):
        """Initialize preview manager.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._worker: PreviewWorker | None = None
        self._pipeline_wrapper: PipelineWrapper | None = None

    def set_pipeline_wrapper(self, pipeline_wrapper: PipelineWrapper) -> None:
        """Set pipeline wrapper.

        Args:
            pipeline_wrapper: PipelineWrapper instance.
        """
        self._pipeline_wrapper = pipeline_wrapper

    def start_preview(self, output_dir: Path | None = None) -> None:
        """Start preview processing.

        Args:
            output_dir: Optional output directory for temporary files.
        """
        if self._pipeline_wrapper is None:
            self.error.emit("No pipeline wrapper set")
            return

        # Cancel existing worker if running
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()

        # Create and start worker
        self._worker = PreviewWorker(self._pipeline_wrapper, output_dir)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self.finished.emit)
        self._worker.error.connect(self.error.emit)
        self._worker.start()

    def cancel_preview(self) -> None:
        """Cancel preview processing."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()

    def is_processing(self) -> bool:
        """Check if processing is in progress.

        Returns:
            True if processing.
        """
        return self._worker is not None and self._worker.isRunning()

