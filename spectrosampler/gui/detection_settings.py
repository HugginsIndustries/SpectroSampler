"""Detection settings panel widget for processing parameters."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spectrosampler.gui.settings import SettingsManager
from spectrosampler.pipeline_settings import ProcessingSettings

logger = logging.getLogger(__name__)


class DetectionSettingsPanel(QWidget):
    """Detection settings panel widget."""

    settings_changed = Signal()  # Emitted when settings change
    detect_samples_requested = Signal()  # Emitted when detection is requested

    _BEHAVIOR_TO_LABEL = {
        "discard_overlaps": "Discard Overlaps",
        "discard_duplicates": "Discard Duplicates",
        "keep_all": "Keep All",
    }
    _LABEL_TO_BEHAVIOR = {label: key for key, label in _BEHAVIOR_TO_LABEL.items()}

    def __init__(self, parent: QWidget | None = None):
        """Initialize detection settings panel.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Create settings
        self._settings = ProcessingSettings()
        self._settings_manager = SettingsManager()
        try:
            self._settings.show_overlap_dialog = self._settings_manager.get_show_overlap_dialog()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.debug("Failed to restore overlap dialog setting: %s", exc, exc_info=exc)
            self._settings.show_overlap_dialog = True
        try:
            behavior_pref = self._settings_manager.get_overlap_default_behavior()
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            logger.debug("Failed to restore overlap behavior setting: %s", exc, exc_info=exc)
            behavior_pref = "discard_duplicates"
        self._settings.overlap_default_behavior = (
            behavior_pref if behavior_pref in self._BEHAVIOR_TO_LABEL else "discard_duplicates"
        )
        try:
            # Restore the persisted max-sample cap so the UI starts with the last chosen value.
            self._settings.max_samples = self._settings_manager.get_detection_max_samples(
                int(self._settings.max_samples)
            )
        except (TypeError, ValueError) as exc:
            logger.debug("Falling back to default max samples: %s", exc, exc_info=exc)

        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # Detection mode
        detection_group = self._create_detection_group()
        content_layout.addWidget(detection_group)

        # Timing parameters
        timing_group = self._create_timing_group()
        content_layout.addWidget(timing_group)

        # Overlap Resolution
        overlap_group = self._create_overlap_group()
        content_layout.addWidget(overlap_group)

        # Audio processing
        audio_group = self._create_audio_group()
        content_layout.addWidget(audio_group)

        # Update controls
        update_group = self._create_update_group()
        content_layout.addWidget(update_group)

        content_layout.addStretch()

        content.setLayout(content_layout)
        scroll.setWidget(content)

        layout.addWidget(scroll)
        self.setLayout(layout)
        self._refresh_validation_state()

        # Apply dropdown arrow styling to all QComboBox widgets
        from spectrosampler.gui.ui_utils import (
            apply_checkbox_styling_to_all_checkboxes,
            apply_combo_styling_to_all_combos,
        )

        apply_combo_styling_to_all_combos(self)
        apply_checkbox_styling_to_all_checkboxes(self)
        self._load_persisted_settings()

    def _create_detection_group(self) -> QGroupBox:
        """Create detection mode group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Detection Mode")
        layout = QFormLayout()

        # Mode selector
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["auto", "voice", "transient", "nonsilence", "spectral"])
        self._mode_combo.setCurrentText(self._settings.mode)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addRow("Mode:", self._mode_combo)

        # Threshold
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.0, 100.0)
        self._threshold_spin.setValue(50.0)
        self._threshold_spin.setDecimals(1)
        self._threshold_spin.valueChanged.connect(self._on_threshold_changed)
        layout.addRow("Threshold:", self._threshold_spin)

        # CPU workers for background processing
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 64)
        try:
            import os

            default_workers = max(1, (os.cpu_count() or 4) - 1)
        except (ImportError, AttributeError, OSError, ValueError) as exc:
            logger.warning("Falling back to default worker count: %s", exc, exc_info=exc)
            default_workers = 3
        # If settings already has max_workers, honor it
        existing_workers = getattr(self._settings, "max_workers", None)
        self._workers_spin.setValue(int(existing_workers or default_workers))

        def _on_workers_changed(v: int) -> None:
            self._settings.max_workers = int(v)
            self._on_settings_changed()

        self._workers_spin.valueChanged.connect(_on_workers_changed)
        layout.addRow("CPU workers:", self._workers_spin)

        group.setLayout(layout)
        return group

    def _create_overlap_group(self) -> QGroupBox:
        """Create overlap resolution settings group."""
        group = QGroupBox("Overlap Resolution")
        layout = QFormLayout()

        # Show overlap dialog checkbox
        self._show_overlap_dialog_checkbox = QCheckBox()

        def _on_show_overlap_changed(state: int) -> None:
            self.set_overlap_preferences(
                self._show_overlap_dialog_checkbox.isChecked(),
                self._settings.overlap_default_behavior,
            )

        self._show_overlap_dialog_checkbox.stateChanged.connect(_on_show_overlap_changed)
        layout.addRow("Show overlap dialog:", self._show_overlap_dialog_checkbox)

        # Default behavior dropdown
        self._overlap_behavior_combo = QComboBox()
        self._overlap_behavior_combo.addItems(self._BEHAVIOR_TO_LABEL.values())

        def _on_behavior_changed(text: str) -> None:
            key = self._LABEL_TO_BEHAVIOR.get(text, "discard_duplicates")
            self.set_overlap_preferences(self._settings.show_overlap_dialog, key)

        self._overlap_behavior_combo.currentTextChanged.connect(_on_behavior_changed)
        layout.addRow("Default behavior:", self._overlap_behavior_combo)

        # Apply initial preferences without re-emitting signals or persisting redundantly.
        self.set_overlap_preferences(
            self._settings.show_overlap_dialog,
            self._settings.overlap_default_behavior,
            persist_manager=False,
            emit_signal=False,
        )

        group.setLayout(layout)
        return group

    def _create_timing_group(self) -> QGroupBox:
        """Create timing parameters group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Timing Parameters")
        layout = QFormLayout()

        # Detection Pre-padding
        self._detection_pre_pad_slider = self._create_slider_spin(
            0, 50000, int(self._settings.detection_pre_pad_ms), "ms"
        )
        self._detection_pre_pad_slider["slider"].valueChanged.connect(
            self._on_detection_pre_pad_changed
        )
        layout.addRow("Detection Pre-padding:", self._detection_pre_pad_slider["widget"])

        # Detection Post-padding
        self._detection_post_pad_slider = self._create_slider_spin(
            0, 50000, int(self._settings.detection_post_pad_ms), "ms"
        )
        self._detection_post_pad_slider["slider"].valueChanged.connect(
            self._on_detection_post_pad_changed
        )
        layout.addRow("Detection Post-padding:", self._detection_post_pad_slider["widget"])

        # Merge gap
        self._merge_gap_slider = self._create_slider_spin(
            0, 1000, int(self._settings.merge_gap_ms), "ms"
        )
        self._merge_gap_slider["slider"].valueChanged.connect(self._on_merge_gap_changed)
        layout.addRow("Merge gap:", self._merge_gap_slider["widget"])

        # Min duration
        self._min_dur_slider = self._create_slider_spin(
            0, 5000, int(self._settings.min_dur_ms), "ms"
        )
        self._min_dur_slider["slider"].valueChanged.connect(self._on_min_dur_changed)
        layout.addRow("Min duration:", self._min_dur_slider["widget"])

        # Max duration
        self._max_dur_slider = self._create_slider_spin(
            0, 120000, int(self._settings.max_dur_ms), "ms"
        )
        self._max_dur_slider["slider"].valueChanged.connect(self._on_max_dur_changed)
        layout.addRow("Max duration:", self._max_dur_slider["widget"])

        # Min gap
        self._min_gap_slider = self._create_slider_spin(
            0, 60000, int(self._settings.min_gap_ms), "ms"
        )
        self._min_gap_slider["slider"].valueChanged.connect(self._on_min_gap_changed)
        layout.addRow("Min gap:", self._min_gap_slider["widget"])

        # Max samples
        self._max_samples_slider = self._create_slider_spin(
            1, 10_000, int(self._settings.max_samples), ""
        )
        self._max_samples_slider["slider"].valueChanged.connect(self._on_max_samples_changed)
        # Ensure the controls reflect the clamped, restored value without emitting changes.
        self._set_max_samples_ui_value(self._settings.max_samples, persist=False)
        layout.addRow("Max samples:", self._max_samples_slider["widget"])

        # Sample spread
        self._sample_spread_checkbox = QCheckBox()
        self._sample_spread_checkbox.setChecked(getattr(self._settings, "sample_spread", True))
        self._sample_spread_checkbox.stateChanged.connect(self._on_sample_spread_changed)
        layout.addRow("Sample spread:", self._sample_spread_checkbox)

        # Sample spread mode
        self._sample_spread_mode_combo = QComboBox()
        self._sample_spread_mode_combo.addItems(["Strict", "Closest"])
        # Map settings value to combo box: "strict" -> "Strict", "closest" -> "Closest"
        mode_value = getattr(self._settings, "sample_spread_mode", "strict")
        mode_display = mode_value.capitalize() if mode_value else "Strict"
        self._sample_spread_mode_combo.setCurrentText(mode_display)
        self._sample_spread_mode_combo.currentTextChanged.connect(
            self._on_sample_spread_mode_changed
        )
        layout.addRow("Sample Spread Mode:", self._sample_spread_mode_combo)

        group.setLayout(layout)
        return group

    def _create_audio_group(self) -> QGroupBox:
        """Create audio processing group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Audio Processing")
        layout = QFormLayout()

        # Denoise method
        self._denoise_combo = QComboBox()
        self._denoise_combo.addItems(["off", "afftdn", "arnndn"])
        self._denoise_combo.setCurrentText(self._settings.denoise)
        self._denoise_combo.currentTextChanged.connect(self._on_denoise_changed)
        layout.addRow("Denoise:", self._denoise_combo)

        # High-pass filter
        self._hp_slider = self._create_slider_spin(0, 20000, int(self._settings.hp or 20), "Hz")
        self._hp_slider["slider"].valueChanged.connect(self._on_hp_changed)
        layout.addRow("High-pass:", self._hp_slider["widget"])

        # Low-pass filter
        self._lp_slider = self._create_slider_spin(0, 20000, int(self._settings.lp or 20000), "Hz")
        self._lp_slider["slider"].valueChanged.connect(self._on_lp_changed)
        layout.addRow("Low-pass:", self._lp_slider["widget"])

        # Noise reduction
        self._nr_slider = self._create_slider_spin(0, 24, int(self._settings.nr), "")
        self._nr_slider["slider"].valueChanged.connect(self._on_nr_changed)
        layout.addRow("Noise reduction:", self._nr_slider["widget"])

        group.setLayout(layout)
        return group

    def _create_update_group(self) -> QGroupBox:
        """Create update controls group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Detection")
        layout = QVBoxLayout()

        # Detect samples button
        self._detect_button = QPushButton("Detect Samples")
        self._detect_button.clicked.connect(self._on_detect_clicked)
        layout.addWidget(self._detect_button)

        group.setLayout(layout)
        return group

    def _create_slider_spin(self, min_val: int, max_val: int, value: int, unit: str) -> dict:
        """Create slider with spinbox.

        Args:
            min_val: Minimum value.
            max_val: Maximum value.
            value: Initial value.
            unit: Unit string.

        Returns:
            Dictionary with 'slider', 'spinbox', and 'widget' keys.
        """
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(value)

        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setValue(value)
        spinbox.setSuffix(f" {unit}")

        # Connect slider and spinbox
        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)

        layout.addWidget(slider)
        layout.addWidget(spinbox)

        widget.setLayout(layout)

        return {"slider": slider, "spinbox": spinbox, "widget": widget}

    def _on_mode_changed(self, mode: str) -> None:
        """Handle mode change."""
        self._settings.mode = mode
        self.settings_changed.emit()

    def _on_settings_changed(self) -> None:
        """Handle settings change."""
        self._refresh_validation_state()
        self.settings_changed.emit()

    def _on_threshold_changed(self, value: float) -> None:
        """Handle threshold percentile change."""
        self._settings.threshold = float(value)
        self._on_settings_changed()

    def _on_detection_pre_pad_changed(self, value: int) -> None:
        """Handle detection pre-padding change."""
        self._settings.detection_pre_pad_ms = float(value)
        self._on_settings_changed()

    def _on_detection_post_pad_changed(self, value: int) -> None:
        """Handle detection post-padding change."""
        self._settings.detection_post_pad_ms = float(value)
        self._on_settings_changed()

    def _on_merge_gap_changed(self, value: int) -> None:
        """Handle merge gap change."""
        self._settings.merge_gap_ms = float(value)
        self._on_settings_changed()

    def _on_min_dur_changed(self, value: int) -> None:
        """Handle min duration change."""
        self._settings.min_dur_ms = float(value)
        self._on_settings_changed()

    def _on_max_dur_changed(self, value: int) -> None:
        """Handle max duration change."""
        self._settings.max_dur_ms = float(value)
        self._on_settings_changed()

    def _on_min_gap_changed(self, value: int) -> None:
        """Handle min gap change."""
        self._settings.min_gap_ms = float(value)
        self._on_settings_changed()

    def _on_max_samples_changed(self, value: int) -> None:
        """Handle max samples change."""
        self._settings.max_samples = int(value)
        try:
            self._settings_manager.set_detection_max_samples(value)
        except (TypeError, ValueError, RuntimeError) as exc:
            logger.debug("Unable to persist max samples %s: %s", value, exc, exc_info=exc)
        self._on_settings_changed()

    def _on_sample_spread_changed(self, state: int) -> None:
        """Handle sample spread toggle change."""
        self._settings.sample_spread = self._sample_spread_checkbox.isChecked()
        self._on_settings_changed()

    def _on_sample_spread_mode_changed(self, mode: str) -> None:
        """Handle sample spread mode change."""
        # Convert display text to lowercase for settings
        self._settings.sample_spread_mode = mode.lower()
        self._on_settings_changed()

    def _on_denoise_changed(self, method: str) -> None:
        """Handle denoise method change."""
        self._settings.denoise = method
        self._on_settings_changed()

    def _on_hp_changed(self, value: int) -> None:
        """Handle high-pass filter change."""
        self._settings.hp = float(value)
        self._on_settings_changed()

    def _on_lp_changed(self, value: int) -> None:
        """Handle low-pass filter change."""
        self._settings.lp = float(value)
        self._on_settings_changed()

    def _on_nr_changed(self, value: int) -> None:
        """Handle noise reduction change."""
        self._settings.nr = float(value)
        self._on_settings_changed()

    def _on_detect_clicked(self) -> None:
        """Handle detect button click."""
        self.detect_samples_requested.emit()

    def get_settings(self) -> ProcessingSettings:
        """Get processing settings.

        Returns:
            ProcessingSettings object.
        """
        return self._settings

    def apply_max_samples(self, value: int, persist: bool = True) -> None:
        """Update the max-sample control and optionally persist the provided value."""
        self._set_max_samples_ui_value(value, persist=persist)

    def get_validation_errors(self):
        """Return current validation errors."""
        return self._settings.validate()

    def apply_settings(self, settings: ProcessingSettings, *, emit_signal: bool = True) -> None:
        """Apply processing settings to the panel controls."""
        snapshot = settings.to_dict()
        self._settings = ProcessingSettings.from_dict(snapshot)

        def _set_slider_pair(pair: dict[str, Any], value: float) -> None:
            slider = pair["slider"]
            spinbox = pair["spinbox"]
            slider.blockSignals(True)
            spinbox.blockSignals(True)
            slider.setValue(int(value))
            spinbox.setValue(int(value))
            slider.blockSignals(False)
            spinbox.blockSignals(False)

        # Mode
        self._mode_combo.blockSignals(True)
        self._mode_combo.setCurrentText(self._settings.mode)
        self._mode_combo.blockSignals(False)

        # Threshold
        threshold_value = self._settings.threshold
        if isinstance(threshold_value, str):
            try:
                threshold_numeric = float(threshold_value)
            except (TypeError, ValueError):
                threshold_numeric = 50.0
        else:
            threshold_numeric = float(threshold_value if threshold_value is not None else 50.0)
        self._threshold_spin.blockSignals(True)
        self._threshold_spin.setValue(threshold_numeric)
        self._threshold_spin.blockSignals(False)
        self._settings.threshold = (
            threshold_value if threshold_value is not None else threshold_numeric
        )

        # Worker count
        self._workers_spin.blockSignals(True)
        worker_value = max(1, int(getattr(self._settings, "max_workers", 1)))
        self._workers_spin.setValue(worker_value)
        self._workers_spin.blockSignals(False)
        self._settings.max_workers = worker_value

        # Timing sliders
        _set_slider_pair(self._detection_pre_pad_slider, self._settings.detection_pre_pad_ms)
        _set_slider_pair(self._detection_post_pad_slider, self._settings.detection_post_pad_ms)
        _set_slider_pair(self._merge_gap_slider, self._settings.merge_gap_ms)
        _set_slider_pair(self._min_dur_slider, self._settings.min_dur_ms)
        _set_slider_pair(self._max_dur_slider, self._settings.max_dur_ms)
        _set_slider_pair(self._min_gap_slider, self._settings.min_gap_ms)
        self._set_max_samples_ui_value(self._settings.max_samples, persist=False)

        # Sample spread controls
        self._sample_spread_checkbox.blockSignals(True)
        self._sample_spread_checkbox.setChecked(self._settings.sample_spread)
        self._sample_spread_checkbox.blockSignals(False)

        spread_mode_display = (self._settings.sample_spread_mode or "strict").capitalize()
        if spread_mode_display not in {"Strict", "Closest"}:
            spread_mode_display = "Strict"
        self._sample_spread_mode_combo.blockSignals(True)
        self._sample_spread_mode_combo.setCurrentText(spread_mode_display)
        self._sample_spread_mode_combo.blockSignals(False)
        self._settings.sample_spread_mode = spread_mode_display.lower()

        # Audio processing controls
        self._denoise_combo.blockSignals(True)
        self._denoise_combo.setCurrentText(self._settings.denoise)
        self._denoise_combo.blockSignals(False)
        _set_slider_pair(self._hp_slider, self._settings.hp or 0.0)
        _set_slider_pair(self._lp_slider, self._settings.lp or 0.0)
        _set_slider_pair(self._nr_slider, self._settings.nr)

        # Overlap dialog preferences
        self.set_overlap_preferences(
            self._settings.show_overlap_dialog,
            self._settings.overlap_default_behavior,
            persist_manager=True,
            emit_signal=False,
        )

        self._refresh_validation_state()
        if emit_signal:
            self.settings_changed.emit()

    def _load_persisted_settings(self) -> None:
        """Load persisted detection settings and apply them to the UI."""
        try:
            persisted = self._settings_manager.get_detection_settings()
        except (RuntimeError, OSError) as exc:
            logger.debug("Failed to load persisted detection settings: %s", exc, exc_info=exc)
            persisted = None
        if persisted:
            self.apply_settings(persisted, emit_signal=False)

    def _set_max_samples_ui_value(self, value: int, persist: bool) -> None:
        """Clamp, persist, and display the max-sample value without triggering signals."""
        clamped = max(1, min(10_000, int(value)))
        slider = self._max_samples_slider["slider"]
        spinbox = self._max_samples_slider["spinbox"]
        # Block signals so we do not re-enter the change handler while syncing UI components.
        slider.blockSignals(True)
        spinbox.blockSignals(True)
        slider.setValue(clamped)
        spinbox.setValue(clamped)
        slider.blockSignals(False)
        spinbox.blockSignals(False)
        self._settings.max_samples = clamped
        if persist:
            try:
                self._settings_manager.set_detection_max_samples(clamped)
            except (TypeError, ValueError, RuntimeError) as exc:
                logger.debug("Unable to persist max samples %s: %s", clamped, exc, exc_info=exc)

    def set_overlap_preferences(
        self,
        show_dialog: bool,
        behavior_key: str,
        *,
        persist_manager: bool = True,
        emit_signal: bool = True,
    ) -> None:
        """Update overlap dialog visibility and default behavior preferences."""
        normalized_key = (
            behavior_key if behavior_key in self._BEHAVIOR_TO_LABEL else "discard_duplicates"
        )
        self._settings.show_overlap_dialog = bool(show_dialog)
        self._settings.overlap_default_behavior = normalized_key

        if hasattr(self, "_show_overlap_dialog_checkbox"):
            self._show_overlap_dialog_checkbox.blockSignals(True)
            self._show_overlap_dialog_checkbox.setChecked(self._settings.show_overlap_dialog)
            self._show_overlap_dialog_checkbox.blockSignals(False)
        if hasattr(self, "_overlap_behavior_combo"):
            desired_label = self._BEHAVIOR_TO_LABEL[normalized_key]
            self._overlap_behavior_combo.blockSignals(True)
            self._overlap_behavior_combo.setCurrentText(desired_label)
            self._overlap_behavior_combo.blockSignals(False)

        if persist_manager:
            try:
                self._settings_manager.set_show_overlap_dialog(self._settings.show_overlap_dialog)
            except (TypeError, ValueError, RuntimeError) as exc:
                logger.debug("Unable to persist overlap dialog preference: %s", exc, exc_info=exc)
            try:
                self._settings_manager.set_overlap_default_behavior(normalized_key)
            except (TypeError, ValueError, RuntimeError) as exc:
                logger.debug("Unable to persist overlap default behavior: %s", exc, exc_info=exc)

        if emit_signal:
            self.settings_changed.emit()

    def _refresh_validation_state(self) -> None:
        """Update UI elements based on current validation errors."""
        errors = self._settings.validate()
        if not hasattr(self, "_validation_label"):
            self._validation_label = QLabel()
            self._validation_label.setWordWrap(True)
            self._validation_label.setStyleSheet("color: #d64545; font-size: 12px;")
            self._validation_label.setVisible(False)
            # Insert validation label above the detect button
            detect_parent = self._detect_button.parent()
            if isinstance(detect_parent, QWidget):
                layout = detect_parent.layout()
                if isinstance(layout, QVBoxLayout):
                    layout.insertWidget(0, self._validation_label)

        if errors:
            messages = "\n".join(issue.message for issue in errors)
            self._validation_label.setText(messages)
            self._validation_label.setVisible(True)
            self._detect_button.setEnabled(False)
        else:
            self._validation_label.setVisible(False)
            self._detect_button.setEnabled(True)
