"""Progress dialog for monitoring batch exports."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from spectrosampler.gui.export_manager import ExportManager, ExportSampleResult, ExportSummary


class ExportProgressDialog(QDialog):
    """Modal dialog that tracks export progress and exposes pause/resume controls."""

    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Progress")
        self.setModal(True)
        self.resize(520, 320)

        self._manager: ExportManager | None = None
        self._summary: ExportSummary | None = None

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)

        self._status_label = QLabel("Preparing export…")

        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumBlockCount(1000)

        button_layout = QHBoxLayout()
        self._pause_button = QPushButton("Pause")
        self._pause_button.clicked.connect(self._on_pause_clicked)
        self._resume_button = QPushButton("Resume")
        self._resume_button.clicked.connect(self._on_resume_clicked)
        self._resume_button.setEnabled(False)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self._pause_button)
        button_layout.addWidget(self._resume_button)
        button_layout.addWidget(self._cancel_button)
        button_layout.addStretch()

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._button_box.rejected.connect(self.reject)
        self._button_box.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(self._log_area, stretch=1)
        layout.addLayout(button_layout)
        layout.addWidget(self._button_box)
        self.setLayout(layout)

    # ------------------------------------------------------------------ #
    # Binding and signal handlers
    # ------------------------------------------------------------------ #

    def bind_manager(self, manager: ExportManager) -> None:
        """Attach to an :class:`ExportManager` and mirror its state."""

        self._manager = manager
        manager.progress.connect(self._on_progress)
        manager.sample_started.connect(self._on_sample_started)
        manager.sample_finished.connect(self._on_sample_finished)
        manager.state_changed.connect(self._on_state_changed)
        manager.completed.connect(self._on_completed)
        manager.error.connect(self._on_error)

    def _on_progress(self, percent: float, processed: int, total: int) -> None:
        self._progress_bar.setValue(int(percent * 100))
        self._status_label.setText(f"Exported {processed} of {total} sample(s)")

    def _on_sample_started(self, sample_id: str, index: int) -> None:
        self._append_log(f"Starting sample {index + 1} ({sample_id})")

    def _on_sample_finished(self, result: ExportSampleResult) -> None:
        if result.success:
            self._append_log(
                f"✔ Sample {result.index + 1} ({result.sample_id}) exported "
                f"({', '.join(result.formats)})"
            )
        else:
            message = result.message or "Unknown error"
            self._append_log(f"✖ Sample {result.index + 1} ({result.sample_id}) failed: {message}")

    def _on_state_changed(self, state: str) -> None:
        if state == "paused":
            self._append_log("Export paused.")
            self._pause_button.setEnabled(False)
            self._resume_button.setEnabled(True)
        elif state == "running":
            self._append_log("Export resumed.")
            self._pause_button.setEnabled(True)
            self._resume_button.setEnabled(False)

    def _on_completed(self, summary: ExportSummary) -> None:
        self._summary = summary
        self._append_log("Export finished.")
        if summary.cancelled:
            self._append_log("Export cancelled before completion.")
        if summary.failed:
            self._append_log(f"{len(summary.failed)} sample(s) failed.")
        self._pause_button.setEnabled(False)
        self._resume_button.setEnabled(False)
        self._cancel_button.setEnabled(False)
        self._button_box.setEnabled(True)
        self._status_label.setText(
            f"Completed {summary.successful_count} of {summary.total_samples} sample(s)."
        )

    def _on_error(self, message: str) -> None:
        self._append_log(f"Export failed: {message}")
        self._pause_button.setEnabled(False)
        self._resume_button.setEnabled(False)
        self._cancel_button.setEnabled(False)
        self._button_box.setEnabled(True)
        self._status_label.setText("Export encountered an error.")

    # ------------------------------------------------------------------ #
    # Button handlers
    # ------------------------------------------------------------------ #

    def _on_pause_clicked(self) -> None:
        if self._manager:
            self._manager.pause()

    def _on_resume_clicked(self) -> None:
        if self._manager:
            self._manager.resume()

    def _on_cancel_clicked(self) -> None:
        if self._manager:
            self._append_log("Cancelling export…")
            self._manager.cancel()
            self._cancel_button.setEnabled(False)

    # ------------------------------------------------------------------ #
    # Utilities
    # ------------------------------------------------------------------ #

    def _append_log(self, message: str) -> None:
        self._log_area.appendPlainText(message)

    @property
    def summary(self) -> ExportSummary | None:
        """Return the final export summary, when available."""

        return self._summary
