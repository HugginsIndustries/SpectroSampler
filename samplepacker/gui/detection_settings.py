"""Detection settings panel widget for processing parameters."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from samplepacker.pipeline import ProcessingSettings


class DetectionSettingsPanel(QWidget):
    """Detection settings panel widget."""

    settings_changed = Signal()  # Emitted when settings change
    detect_samples_requested = Signal()  # Emitted when detection is requested

    def __init__(self, parent: QWidget | None = None):
        """Initialize detection settings panel.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Create settings
        self._settings = ProcessingSettings()

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
        self._threshold_spin.valueChanged.connect(self._on_settings_changed)
        layout.addRow("Threshold:", self._threshold_spin)

        # CPU workers for background processing
        self._workers_spin = QSpinBox()
        self._workers_spin.setRange(1, 64)
        try:
            import os

            default_workers = max(1, (os.cpu_count() or 4) - 1)
        except Exception:
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
            1, 1024, int(self._settings.max_samples), ""
        )
        self._max_samples_slider["slider"].valueChanged.connect(self._on_max_samples_changed)
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
        self._sample_spread_mode_combo.currentTextChanged.connect(self._on_sample_spread_mode_changed)
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
        self.settings_changed.emit()

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
