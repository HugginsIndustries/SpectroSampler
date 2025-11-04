"""Settings panel widget for processing parameters."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from samplepacker.gui.grid_manager import GridMode, GridSettings, Subdivision
from samplepacker.pipeline import ProcessingSettings


class SettingsPanel(QWidget):
    """Settings panel widget."""

    settings_changed = Signal()  # Emitted when settings change
    update_preview_requested = Signal()  # Emitted when update preview is requested

    def __init__(self, parent: QWidget | None = None):
        """Initialize settings panel.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Create settings
        self._settings = ProcessingSettings()
        self._grid_settings = GridSettings()

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

        # Grid settings
        grid_group = self._create_grid_group()
        content_layout.addWidget(grid_group)

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

        group.setLayout(layout)
        return group

    def _create_timing_group(self) -> QGroupBox:
        """Create timing parameters group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Timing Parameters")
        layout = QFormLayout()

        # Pre-padding
        self._pre_pad_slider = self._create_slider_spin(0, 50000, int(self._settings.pre_pad_ms), "ms")
        self._pre_pad_slider["slider"].valueChanged.connect(self._on_pre_pad_changed)
        layout.addRow("Pre-padding:", self._pre_pad_slider["widget"])

        # Post-padding
        self._post_pad_slider = self._create_slider_spin(0, 50000, int(self._settings.post_pad_ms), "ms")
        self._post_pad_slider["slider"].valueChanged.connect(self._on_post_pad_changed)
        layout.addRow("Post-padding:", self._post_pad_slider["widget"])

        # Merge gap
        self._merge_gap_slider = self._create_slider_spin(0, 1000, int(self._settings.merge_gap_ms), "ms")
        self._merge_gap_slider["slider"].valueChanged.connect(self._on_merge_gap_changed)
        layout.addRow("Merge gap:", self._merge_gap_slider["widget"])

        # Min duration
        self._min_dur_slider = self._create_slider_spin(0, 5000, int(self._settings.min_dur_ms), "ms")
        self._min_dur_slider["slider"].valueChanged.connect(self._on_min_dur_changed)
        layout.addRow("Min duration:", self._min_dur_slider["widget"])

        # Max duration
        self._max_dur_slider = self._create_slider_spin(0, 120000, int(self._settings.max_dur_ms), "ms")
        self._max_dur_slider["slider"].valueChanged.connect(self._on_max_dur_changed)
        layout.addRow("Max duration:", self._max_dur_slider["widget"])

        # Min gap
        self._min_gap_slider = self._create_slider_spin(0, 5000, int(self._settings.min_gap_ms), "ms")
        self._min_gap_slider["slider"].valueChanged.connect(self._on_min_gap_changed)
        layout.addRow("Min gap:", self._min_gap_slider["widget"])

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

        # Output format
        self._format_combo = QComboBox()
        self._format_combo.addItems(["wav", "flac"])
        self._format_combo.setCurrentText(self._settings.format)
        self._format_combo.currentTextChanged.connect(self._on_format_changed)
        layout.addRow("Format:", self._format_combo)

        group.setLayout(layout)
        return group

    def _create_grid_group(self) -> QGroupBox:
        """Create grid settings group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Grid Settings")
        layout = QVBoxLayout()

        # Grid mode
        mode_layout = QVBoxLayout()
        self._grid_mode_free = QRadioButton("Free Time")
        self._grid_mode_free.setChecked(self._grid_settings.mode == GridMode.FREE_TIME)
        self._grid_mode_free.toggled.connect(self._on_grid_mode_changed)
        mode_layout.addWidget(self._grid_mode_free)

        self._grid_mode_musical = QRadioButton("Musical Bar")
        self._grid_mode_musical.setChecked(self._grid_settings.mode == GridMode.MUSICAL_BAR)
        self._grid_mode_musical.toggled.connect(self._on_grid_mode_changed)
        mode_layout.addWidget(self._grid_mode_musical)

        layout.addLayout(mode_layout)

        # Free time settings
        free_time_layout = QFormLayout()
        self._snap_interval_slider = self._create_slider_spin(1, 10000, int(self._grid_settings.snap_interval_sec * 1000), "ms")
        self._snap_interval_slider["slider"].valueChanged.connect(self._on_snap_interval_changed)
        free_time_layout.addRow("Snap interval:", self._snap_interval_slider["widget"])

        # Musical bar settings
        musical_layout = QFormLayout()
        self._bpm_spin = QSpinBox()
        self._bpm_spin.setRange(60, 200)
        self._bpm_spin.setValue(int(self._grid_settings.bpm))
        self._bpm_spin.valueChanged.connect(self._on_bpm_changed)
        musical_layout.addRow("BPM:", self._bpm_spin)

        self._subdivision_combo = QComboBox()
        self._subdivision_combo.addItems(["Whole", "Half", "Quarter", "Eighth", "Sixteenth", "Thirty-second"])
        self._subdivision_combo.setCurrentIndex(2)  # Quarter
        self._subdivision_combo.currentTextChanged.connect(self._on_subdivision_changed)
        musical_layout.addRow("Subdivision:", self._subdivision_combo)

        # Grid visibility
        self._grid_visible_check = QCheckBox("Show grid")
        self._grid_visible_check.setChecked(self._grid_settings.visible)
        self._grid_visible_check.toggled.connect(self._on_grid_visible_changed)
        layout.addWidget(self._grid_visible_check)

        # Snap to grid
        self._snap_enabled_check = QCheckBox("Snap to grid")
        self._snap_enabled_check.setChecked(self._grid_settings.enabled)
        self._snap_enabled_check.toggled.connect(self._on_snap_enabled_changed)
        layout.addWidget(self._snap_enabled_check)

        layout.addLayout(free_time_layout)
        layout.addLayout(musical_layout)

        group.setLayout(layout)
        return group

    def _create_update_group(self) -> QGroupBox:
        """Create update controls group.

        Returns:
            QGroupBox widget.
        """
        group = QGroupBox("Update Controls")
        layout = QVBoxLayout()

        # Update preview button
        self._update_button = QPushButton("Update Preview")
        self._update_button.clicked.connect(self._on_update_clicked)
        layout.addWidget(self._update_button)

        # Auto-update checkbox
        self._auto_update_check = QCheckBox("Auto-update on change")
        self._auto_update_check.setChecked(False)
        layout.addWidget(self._auto_update_check)

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
        if self._auto_update_check.isChecked():
            self.update_preview_requested.emit()

    def _on_pre_pad_changed(self, value: int) -> None:
        """Handle pre-padding change."""
        self._settings.pre_pad_ms = float(value)
        self._on_settings_changed()

    def _on_post_pad_changed(self, value: int) -> None:
        """Handle post-padding change."""
        self._settings.post_pad_ms = float(value)
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

    def _on_format_changed(self, format: str) -> None:
        """Handle format change."""
        self._settings.format = format
        self._on_settings_changed()

    def _on_grid_mode_changed(self) -> None:
        """Handle grid mode change."""
        if self._grid_mode_free.isChecked():
            self._grid_settings.mode = GridMode.FREE_TIME
        elif self._grid_mode_musical.isChecked():
            self._grid_settings.mode = GridMode.MUSICAL_BAR
        self.settings_changed.emit()

    def _on_snap_interval_changed(self, value: int) -> None:
        """Handle snap interval change."""
        self._grid_settings.snap_interval_sec = value / 1000.0
        self.settings_changed.emit()

    def _on_bpm_changed(self, value: int) -> None:
        """Handle BPM change."""
        self._grid_settings.bpm = float(value)
        self.settings_changed.emit()

    def _on_subdivision_changed(self, text: str) -> None:
        """Handle subdivision change."""
        subdivision_map = {
            "Whole": Subdivision.WHOLE,
            "Half": Subdivision.HALF,
            "Quarter": Subdivision.QUARTER,
            "Eighth": Subdivision.EIGHTH,
            "Sixteenth": Subdivision.SIXTEENTH,
            "Thirty-second": Subdivision.THIRTY_SECOND,
        }
        self._grid_settings.subdivision = subdivision_map.get(text, Subdivision.QUARTER)
        self.settings_changed.emit()

    def _on_grid_visible_changed(self, checked: bool) -> None:
        """Handle grid visibility change."""
        self._grid_settings.visible = checked
        self.settings_changed.emit()

    def _on_snap_enabled_changed(self, checked: bool) -> None:
        """Handle snap enabled change."""
        self._grid_settings.enabled = checked
        self.settings_changed.emit()

    def _on_update_clicked(self) -> None:
        """Handle update button click."""
        self.update_preview_requested.emit()

    def get_settings(self) -> ProcessingSettings:
        """Get processing settings.

        Returns:
            ProcessingSettings object.
        """
        return self._settings

    def get_grid_settings(self) -> GridSettings:
        """Get grid settings.

        Returns:
            GridSettings object.
        """
        return self._grid_settings

