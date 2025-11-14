"""Dialog for resolving overlaps between existing and newly detected segments."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


class OverlapResolutionDialog(QDialog):
    """Modal dialog to choose how to resolve overlaps and duplicates."""

    def __init__(self, overlaps_count: int, duplicates_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Overlap Resolution")
        self.setModal(True)

        main_layout = QVBoxLayout()

        # Summary label
        summary = QLabel(
            f"Detected {overlaps_count} overlap(s) and {duplicates_count} duplicate(s).\n"
            f"Choose how to handle new detections that conflict with existing samples."
        )
        summary.setWordWrap(True)
        main_layout.addWidget(summary)

        # Options group
        options_group = QGroupBox("When new detections conflict with existing")
        options_layout = QVBoxLayout()

        self._rb_discard_overlaps = QRadioButton("Discard Overlaps")
        self._rb_discard_overlaps.setToolTip(
            "Remove all new segments that overlap any existing segment."
        )
        self._rb_discard_duplicates = QRadioButton("Discard Duplicates")
        self._rb_discard_duplicates.setToolTip(
            "Remove only new segments that exactly match existing (start/end within 5 ms)."
        )
        self._rb_keep_all = QRadioButton("Keep All")
        self._rb_keep_all.setToolTip("Keep all new segments even if they overlap existing ones.")

        # Default selection: Discard Duplicates (caller may adjust before exec)
        self._rb_discard_duplicates.setChecked(True)

        options_layout.addWidget(self._rb_discard_overlaps)
        options_layout.addWidget(self._rb_discard_duplicates)
        options_layout.addWidget(self._rb_keep_all)
        options_group.setLayout(options_layout)
        main_layout.addWidget(options_group)

        # Remember my choice
        self._remember_checkbox = QCheckBox("Remember my choice")
        self._remember_checkbox.setToolTip(
            "Disable this dialog in the future and use the selected option by default."
        )
        main_layout.addWidget(self._remember_checkbox)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self.setLayout(main_layout)

        # Apply checkbox styling
        from spectrosampler.gui.ui_utils import apply_checkbox_styling_to_all_checkboxes

        apply_checkbox_styling_to_all_checkboxes(self)

    def result_choice(self) -> tuple[str, bool] | None:
        """Return (behavior, remember) or None if canceled.

        behavior is one of: "discard_overlaps" | "discard_duplicates" | "keep_all".
        """
        if self.result() != QDialog.Accepted:
            return None
        if self._rb_discard_overlaps.isChecked():
            choice = "discard_overlaps"
        elif self._rb_keep_all.isChecked():
            choice = "keep_all"
        else:
            choice = "discard_duplicates"
        return choice, bool(self._remember_checkbox.isChecked())
