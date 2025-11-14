"""Advanced export dialog with global batch controls and per-sample overrides."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spectrosampler.detectors.base import Segment
from spectrosampler.dsp import bandpass_filter
from spectrosampler.gui.export_models import (
    DEFAULT_FILENAME_TEMPLATE,
    ExportBatchSettings,
    ExportSampleOverride,
    compute_sample_id,
    derive_sample_title,
    parse_overrides,
    render_filename_from_template,
)
from spectrosampler.utils import sanitize_filename

AVAILABLE_EXPORT_FORMATS: tuple[str, ...] = ("wav", "flac", "mp3")
SAMPLE_RATE_CHOICES: tuple[int, ...] = (0, 44100, 48000, 88200, 96000, 192000)
PREVIEW_WAVEFORM_SIZE: tuple[int, int] = (520, 140)
PREVIEW_SPECTROGRAM_SIZE: tuple[int, int] = (520, 220)
PREVIEW_REFRESH_DELAY_MS = 120
NORMALIZE_TARGET_DBFS = -0.1
NORMALIZE_TARGET_AMPLITUDE = float(10.0 ** (NORMALIZE_TARGET_DBFS / 20.0))


class ExportDialog(QDialog):
    """Modal dialog that presents advanced export controls."""

    export_requested = Signal()

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        batch_settings: ExportBatchSettings | None = None,
        overrides: Sequence[ExportSampleOverride] | None = None,
        segments: Sequence[Segment] | None = None,
        audio_path: Path | str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Samples")
        self.setModal(True)
        self.resize(1080, 720)

        self._segments: list[Segment] = list(segments or [])
        self._current_index: int = 0

        self._batch_settings = replace(batch_settings) if batch_settings else ExportBatchSettings()
        self._overrides_by_id: dict[str, ExportSampleOverride] = {}
        if overrides:
            for override in overrides:
                self._overrides_by_id[override.sample_id] = replace(override)

        if not (self._batch_settings.filename_template or "").strip():
            self._batch_settings.filename_template = DEFAULT_FILENAME_TEMPLATE

        self._audio_path: Path | None = Path(audio_path) if audio_path else None
        self._base_name = self._audio_path.stem if self._audio_path else "sample"
        if not self._batch_settings.album:
            self._batch_settings.album = self._base_name
        if not self._batch_settings.year or self._batch_settings.year <= 0:
            self._batch_settings.year = datetime.now().year
        if not self._batch_settings.artist:
            self._batch_settings.artist = "SpectroSampler"
        if self._batch_settings.notes is None:
            self._batch_settings.notes = ""
        self._audio_sample_rate: int | None = None
        self._audio_total_frames: int | None = None
        self._audio_duration: float | None = None
        self._ensure_audio_metadata()

        self._tabs = QTabWidget()
        self._global_page = QWidget()
        self._samples_page = QWidget()
        self._tabs.addTab(self._global_page, "Global")
        self._tabs.addTab(self._samples_page, "Samples")

        self._button_box = QDialogButtonBox()
        self._cancel_button = self._button_box.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._export_button = self._button_box.addButton(
            "Export Sample(s)", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._export_button.setDefault(True)
        self._button_box.rejected.connect(self.reject)
        self._button_box.accepted.connect(self._on_export_clicked)

        dialog_layout = QVBoxLayout()
        dialog_layout.addWidget(self._tabs)
        dialog_layout.addWidget(self._button_box)
        self.setLayout(dialog_layout)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._refresh_sample_preview)
        self._updating_controls = False

        self._build_global_page()
        self._build_samples_page()

        # Apply dropdown arrow styling to all QComboBox widgets (after pages are built)
        from spectrosampler.gui.ui_utils import (
            apply_checkbox_styling_to_all_checkboxes,
            apply_combo_styling_to_all_combos,
        )

        apply_combo_styling_to_all_combos(self)
        apply_checkbox_styling_to_all_checkboxes(self)

        self._apply_batch_settings_to_ui()
        self._update_navigation_state()
        self._schedule_preview_refresh()

    # ------------------------------------------------------------------ #
    # Global tab construction and bindings
    # ------------------------------------------------------------------ #

    def _build_global_page(self) -> None:
        """Construct the widgets rendered on the Global tab."""

        layout = QVBoxLayout()

        audio_group = QGroupBox("Audio Settings")
        audio_layout = QGridLayout()

        self._format_checkboxes: dict[str, QCheckBox] = {}
        format_box = QGroupBox("Formats")
        format_layout = QHBoxLayout()
        for code in AVAILABLE_EXPORT_FORMATS:
            checkbox = QCheckBox(code.upper())
            checkbox.stateChanged.connect(self._on_formats_changed)
            format_layout.addWidget(checkbox)
            self._format_checkboxes[code] = checkbox
        format_layout.addStretch()
        format_box.setLayout(format_layout)

        audio_layout.addWidget(format_box, 0, 0, 1, 3)

        self._sample_rate_combo = QComboBox()
        self._populate_sample_rate_combo()
        self._sample_rate_combo.currentIndexChanged.connect(self._on_sample_rate_changed)

        self._bit_depth_combo = QComboBox()
        self._bit_depth_combo.addItem("Auto", None)
        self._bit_depth_combo.addItem("16-bit PCM", "16")
        self._bit_depth_combo.addItem("24-bit PCM", "24")
        self._bit_depth_combo.addItem("32-bit Float", "32f")
        self._bit_depth_combo.currentIndexChanged.connect(self._on_bit_depth_changed)

        self._channels_combo = QComboBox()
        self._channels_combo.addItem("Auto", None)
        self._channels_combo.addItem("Mono", "mono")
        self._channels_combo.addItem("Stereo", "stereo")
        self._channels_combo.currentIndexChanged.connect(self._on_channels_changed)

        audio_layout.addWidget(QLabel("Sample Rate"), 1, 0)
        audio_layout.addWidget(self._sample_rate_combo, 1, 1, 1, 2)

        audio_layout.addWidget(QLabel("Bit Depth"), 2, 0)
        audio_layout.addWidget(self._bit_depth_combo, 2, 1, 1, 2)

        audio_layout.addWidget(QLabel("Channels"), 3, 0)
        audio_layout.addWidget(self._channels_combo, 3, 1, 1, 2)

        self._pre_pad_spin = self._create_padding_spinbox()
        self._post_pad_spin = self._create_padding_spinbox()
        audio_layout.addWidget(QLabel("Pre-padding (ms)"), 4, 0)
        audio_layout.addWidget(self._pre_pad_spin, 4, 1)
        audio_layout.addWidget(QLabel("Post-padding (ms)"), 4, 2)
        audio_layout.addWidget(self._post_pad_spin, 4, 3)

        self._normalize_checkbox = QCheckBox("Normalize Peaks to -0.1 dBFS")
        self._normalize_checkbox.stateChanged.connect(self._on_normalize_toggled)
        audio_layout.addWidget(self._normalize_checkbox, 5, 0, 1, 4)

        bandpass_group = QGroupBox("Bandpass Filtering")
        bandpass_layout = QGridLayout()
        self._bandpass_enable_checkbox = QCheckBox("Enable bandpass filter")
        self._bandpass_enable_checkbox.stateChanged.connect(self._on_bandpass_toggled)
        bandpass_layout.addWidget(self._bandpass_enable_checkbox, 0, 0, 1, 2)

        validator = QDoubleValidator(0.0, 200000.0, 2, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)

        self._bandpass_low_edit = QLineEdit()
        self._bandpass_low_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bandpass_low_edit.setValidator(validator)
        self._bandpass_low_edit.setPlaceholderText("Low cut (Hz)")
        self._bandpass_low_edit.setText("20")
        self._bandpass_low_edit.textChanged.connect(self._on_bandpass_values_changed)

        self._bandpass_high_edit = QLineEdit()
        self._bandpass_high_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._bandpass_high_edit.setValidator(validator)
        self._bandpass_high_edit.setPlaceholderText("High cut (Hz)")
        self._bandpass_high_edit.setText("20000")
        self._bandpass_high_edit.textChanged.connect(self._on_bandpass_values_changed)

        bandpass_layout.addWidget(QLabel("Low Cut"), 1, 0)
        bandpass_layout.addWidget(self._bandpass_low_edit, 1, 1)
        bandpass_layout.addWidget(QLabel("High Cut"), 1, 2)
        bandpass_layout.addWidget(self._bandpass_high_edit, 1, 3)
        bandpass_group.setLayout(bandpass_layout)

        audio_layout.addWidget(bandpass_group, 6, 0, 1, 4)

        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)

        metadata_group = QGroupBox("Metadata")
        metadata_form = QFormLayout()
        self._artist_edit = QLineEdit()
        self._artist_edit.textChanged.connect(self._on_artist_changed)
        self._album_edit = QLineEdit()
        self._album_edit.textChanged.connect(self._on_album_changed)
        self._year_spin = QSpinBox()
        self._year_spin.setRange(1900, 9999)
        self._year_spin.valueChanged.connect(self._on_year_changed)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setPlaceholderText("Add notes here...")
        self._notes_edit.setFixedHeight(70)
        self._notes_edit.textChanged.connect(self._on_notes_changed)
        metadata_form.addRow("Artist", self._artist_edit)
        metadata_form.addRow("Album", self._album_edit)
        metadata_form.addRow("Year", self._year_spin)
        metadata_form.addRow("Notes", self._notes_edit)
        metadata_group.setLayout(metadata_form)
        layout.addWidget(metadata_group)

        destination_group = QGroupBox("Destination")
        destination_layout = QGridLayout()
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.textChanged.connect(self._on_output_directory_changed)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._choose_output_directory)
        destination_layout.addWidget(QLabel("Output Folder"), 0, 0)
        destination_layout.addWidget(self._output_dir_edit, 0, 1)
        destination_layout.addWidget(browse_button, 0, 2)

        self._filename_template_edit = QLineEdit()
        self._filename_template_edit.textChanged.connect(self._on_filename_template_changed)
        destination_layout.addWidget(QLabel("Filename Template"), 1, 0)
        destination_layout.addWidget(self._filename_template_edit, 1, 1, 1, 2)

        self._persist_defaults_checkbox = QCheckBox("Save as default export settings")
        destination_layout.addWidget(self._persist_defaults_checkbox, 2, 0, 1, 3)

        destination_group.setLayout(destination_layout)
        layout.addWidget(destination_group)

        layout.addStretch()
        self._global_page.setLayout(layout)

    def _create_padding_spinbox(self) -> QDoubleSpinBox:
        """Create a standardized spinbox for padding controls."""

        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(1)
        spinbox.setRange(0.0, 10000.0)
        spinbox.setSingleStep(10.0)
        spinbox.valueChanged.connect(self._on_padding_changed)
        return spinbox

    def _populate_sample_rate_combo(self) -> None:
        """Populate the sample rate combo with presets and a Custom entry."""

        self._sample_rate_combo.clear()
        for value in SAMPLE_RATE_CHOICES:
            label = "Original" if value == 0 else f"{value:,} Hz"
            self._sample_rate_combo.addItem(label, value)
        self._sample_rate_custom_index = self._sample_rate_combo.count()
        self._sample_rate_combo.addItem("Custom…", None)

    def _set_sample_rate_combo_value(self, value: int | None) -> None:
        """Select the combo entry matching the provided sample rate."""

        target = value or 0
        index = self._sample_rate_combo.findData(target)
        if index == -1 and target not in (0, None):
            label = f"{target:,} Hz"
            self._sample_rate_combo.insertItem(self._sample_rate_custom_index, label, target)
            self._sample_rate_custom_index += 1
            index = self._sample_rate_combo.findData(target)
        if index == -1:
            index = self._sample_rate_combo.findData(0)
        self._sample_rate_combo.blockSignals(True)
        if index != -1:
            self._sample_rate_combo.setCurrentIndex(index)
        else:
            self._sample_rate_combo.setCurrentIndex(0)
        self._sample_rate_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Samples tab construction and override wiring
    # ------------------------------------------------------------------ #

    def _build_samples_page(self) -> None:
        """Construct the Samples tab with previews and override editors."""

        layout = QVBoxLayout()

        header_layout = QHBoxLayout()
        self._sample_position_label = QLabel("No samples loaded")
        self._sample_title_label = QLabel("")
        self._sample_title_label.setStyleSheet("font-weight: bold;")
        self._sample_title_label.setWordWrap(True)
        header_layout.addWidget(self._sample_position_label)
        header_layout.addStretch()
        header_layout.addWidget(self._sample_title_label)

        nav_layout = QHBoxLayout()
        self._prev_button = QPushButton("Previous")
        self._prev_button.clicked.connect(self._on_previous_sample)
        self._next_button = QPushButton("Next")
        self._next_button.clicked.connect(self._on_next_sample)
        nav_layout.addWidget(self._prev_button)
        nav_layout.addWidget(self._next_button)
        nav_layout.addStretch()

        previews_and_controls = QHBoxLayout()

        preview_column = QVBoxLayout()
        self._spectrogram_label = QLabel("Spectrogram preview unavailable")
        self._spectrogram_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spectrogram_label.setMinimumSize(*PREVIEW_SPECTROGRAM_SIZE)
        self._spectrogram_label.setStyleSheet(
            "background-color: #1A1A1A; border: 1px solid #333333; color: #AAAAAA;"
        )

        self._waveform_label = QLabel("Waveform preview unavailable")
        self._waveform_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._waveform_label.setMinimumSize(*PREVIEW_WAVEFORM_SIZE)
        self._waveform_label.setStyleSheet(
            "background-color: #111111; border: 1px solid #333333; color: #AAAAAA;"
        )

        preview_column.addWidget(self._spectrogram_label)
        preview_column.addWidget(self._waveform_label)
        previews_and_controls.addLayout(preview_column, stretch=3)

        controls_column = QVBoxLayout()

        title_group = QGroupBox("Title")
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(8, 6, 8, 6)
        self._override_title_checkbox = QCheckBox("Custom")
        self._override_title_checkbox.stateChanged.connect(self._on_override_title_toggled)
        self._override_title_edit = QLineEdit()
        self._override_title_edit.setPlaceholderText("Custom title (no extension)")
        self._override_title_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._override_title_edit.textChanged.connect(self._on_override_title_changed)
        title_layout.addWidget(self._override_title_checkbox)
        title_layout.addWidget(self._override_title_edit)
        title_group.setLayout(title_layout)
        controls_column.addWidget(title_group)

        overrides_group = QGroupBox("Per-sample Overrides")
        overrides_form = QFormLayout()

        self._override_pre_pad_checkbox = QCheckBox("Override Global")
        self._override_pre_pad_checkbox.stateChanged.connect(self._on_override_pre_pad_toggled)
        self._override_pre_pad_spin = self._create_padding_spinbox()
        self._override_pre_pad_spin.setEnabled(True)  # Always editable
        self._override_pre_pad_spin.valueChanged.connect(self._on_override_pre_pad_changed)
        pre_pad_widget = QWidget()
        pre_pad_layout = QHBoxLayout(pre_pad_widget)
        pre_pad_layout.setContentsMargins(0, 0, 0, 0)
        pre_pad_layout.addWidget(self._override_pre_pad_checkbox)
        pre_pad_layout.addWidget(self._override_pre_pad_spin)
        overrides_form.addRow("Pre-padding (ms)", pre_pad_widget)

        self._override_post_pad_checkbox = QCheckBox("Override Global")
        self._override_post_pad_checkbox.stateChanged.connect(self._on_override_post_pad_toggled)
        self._override_post_pad_spin = self._create_padding_spinbox()
        self._override_post_pad_spin.setEnabled(True)  # Always editable
        self._override_post_pad_spin.valueChanged.connect(self._on_override_post_pad_changed)
        post_pad_widget = QWidget()
        post_pad_layout = QHBoxLayout(post_pad_widget)
        post_pad_layout.setContentsMargins(0, 0, 0, 0)
        post_pad_layout.addWidget(self._override_post_pad_checkbox)
        post_pad_layout.addWidget(self._override_post_pad_spin)
        overrides_form.addRow("Post-padding (ms)", post_pad_widget)

        self._override_normalize_combo = QComboBox()
        self._override_normalize_combo.addItems(["Use Global Setting", "Enabled", "Disabled"])
        self._override_normalize_combo.currentIndexChanged.connect(
            self._on_override_normalize_changed
        )
        overrides_form.addRow("Normalization", self._override_normalize_combo)

        validator = QDoubleValidator(0.0, 200000.0, 2, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)

        self._override_bandpass_combo = QComboBox()
        self._override_bandpass_combo.addItems(["Use Global Setting", "Enabled", "Disabled"])
        self._override_bandpass_combo.currentIndexChanged.connect(
            self._on_override_bandpass_combo_changed
        )
        bandpass_fields_widget = QWidget()
        bandpass_fields_layout = QHBoxLayout(bandpass_fields_widget)
        bandpass_fields_layout.setContentsMargins(0, 0, 0, 0)
        self._override_bandpass_low = QLineEdit()
        self._override_bandpass_low.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._override_bandpass_low.setPlaceholderText("Low (Hz)")
        self._override_bandpass_low.setValidator(validator)
        self._override_bandpass_low.setText("20")
        self._override_bandpass_low.textChanged.connect(self._on_override_bandpass_changed)
        self._override_bandpass_high = QLineEdit()
        self._override_bandpass_high.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._override_bandpass_high.setPlaceholderText("High (Hz)")
        self._override_bandpass_high.setValidator(validator)
        self._override_bandpass_high.setText("20000")
        self._override_bandpass_high.textChanged.connect(self._on_override_bandpass_changed)
        bandpass_fields_layout.addWidget(self._override_bandpass_low)
        bandpass_fields_layout.addWidget(self._override_bandpass_high)
        overrides_form.addRow("Bandpass (Hz)", self._override_bandpass_combo)
        overrides_form.addRow("", bandpass_fields_widget)

        self._sample_notes_edit = QPlainTextEdit()
        self._sample_notes_edit.setPlaceholderText("Add notes here...")
        self._sample_notes_edit.setFixedHeight(70)
        self._sample_notes_edit.textChanged.connect(self._on_sample_notes_changed)
        overrides_form.addRow("Notes", self._sample_notes_edit)

        self._clear_overrides_button = QPushButton("Clear Overrides")
        self._clear_overrides_button.clicked.connect(self._on_clear_overrides_clicked)
        overrides_form.addRow(self._clear_overrides_button)

        overrides_group.setLayout(overrides_form)
        controls_column.addWidget(overrides_group)
        controls_column.addStretch()

        previews_and_controls.addLayout(controls_column, stretch=2)

        self._sample_summary_label = QLabel(
            "Select samples to review per-sample overrides and preview exports."
        )
        self._sample_summary_label.setWordWrap(True)

        layout.addLayout(header_layout)
        layout.addLayout(nav_layout)
        layout.addLayout(previews_and_controls)
        layout.addWidget(self._sample_summary_label)
        layout.addStretch()
        self._samples_page.setLayout(layout)

    # ------------------------------------------------------------------ #
    # UI lifecycle helpers
    # ------------------------------------------------------------------ #

    def _apply_batch_settings_to_ui(self) -> None:
        """Synchronise the UI with the current batch settings."""

        for fmt, checkbox in self._format_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(fmt in self._batch_settings.formats)
            checkbox.blockSignals(False)

        self._set_sample_rate_combo_value(self._batch_settings.sample_rate_hz)

        bit_depth_value = self._batch_settings.bit_depth
        index = self._bit_depth_combo.findData(bit_depth_value)
        if index == -1:
            index = 0
        self._bit_depth_combo.blockSignals(True)
        self._bit_depth_combo.setCurrentIndex(index)
        self._bit_depth_combo.blockSignals(False)

        channels_value = self._batch_settings.channels
        index = self._channels_combo.findData(channels_value)
        if index == -1:
            index = 0
        self._channels_combo.blockSignals(True)
        self._channels_combo.setCurrentIndex(index)
        self._channels_combo.blockSignals(False)

        self._pre_pad_spin.blockSignals(True)
        self._pre_pad_spin.setValue(self._batch_settings.pre_pad_ms)
        self._pre_pad_spin.blockSignals(False)
        self._post_pad_spin.blockSignals(True)
        self._post_pad_spin.setValue(self._batch_settings.post_pad_ms)
        self._post_pad_spin.blockSignals(False)

        self._normalize_checkbox.blockSignals(True)
        self._normalize_checkbox.setChecked(self._batch_settings.normalize)
        self._normalize_checkbox.blockSignals(False)

        bandpass_enabled = (
            self._batch_settings.bandpass_low_hz is not None
            or self._batch_settings.bandpass_high_hz is not None
        )
        self._bandpass_enable_checkbox.blockSignals(True)
        self._bandpass_enable_checkbox.setChecked(bandpass_enabled)
        self._bandpass_enable_checkbox.blockSignals(False)
        self._bandpass_low_edit.setText(
            ""
            if self._batch_settings.bandpass_low_hz is None
            else str(self._batch_settings.bandpass_low_hz)
        )
        self._bandpass_high_edit.setText(
            ""
            if self._batch_settings.bandpass_high_hz is None
            else str(self._batch_settings.bandpass_high_hz)
        )
        self._toggle_bandpass_fields(bandpass_enabled)

        self._artist_edit.blockSignals(True)
        self._artist_edit.setText(self._batch_settings.artist or "SpectroSampler")
        self._artist_edit.blockSignals(False)
        self._album_edit.blockSignals(True)
        default_album = self._batch_settings.album
        if not default_album and self._audio_path:
            default_album = self._audio_path.stem
        self._batch_settings.album = default_album or None
        self._album_edit.setText(default_album or "")
        self._album_edit.blockSignals(False)
        self._year_spin.blockSignals(True)
        year_value = self._batch_settings.year or datetime.now().year
        self._batch_settings.year = year_value
        self._year_spin.setValue(year_value)
        self._year_spin.blockSignals(False)
        self._notes_edit.blockSignals(True)
        self._notes_edit.setPlainText(self._batch_settings.notes or "")
        self._notes_edit.blockSignals(False)

        self._output_dir_edit.blockSignals(True)
        self._output_dir_edit.setText(self._batch_settings.output_directory or "")
        self._output_dir_edit.blockSignals(False)
        self._filename_template_edit.blockSignals(True)
        template_text = self._batch_settings.filename_template or DEFAULT_FILENAME_TEMPLATE
        self._batch_settings.filename_template = template_text
        self._filename_template_edit.setText(template_text)
        self._filename_template_edit.blockSignals(False)

    def _toggle_bandpass_fields(self, enabled: bool) -> None:
        """Enable or disable bandpass fields."""

        if not enabled:
            self._bandpass_low_edit.clearFocus()
            self._bandpass_high_edit.clearFocus()

    def _update_navigation_state(self) -> None:
        """Refresh navigation controls for the Samples tab."""

        total = len(self._segments)
        if total == 0:
            self._sample_position_label.setText("No samples available")
            self._sample_title_label.setText("")
            self._prev_button.setEnabled(False)
            self._next_button.setEnabled(False)
            self._sample_summary_label.setText(
                "No samples selected for export. Run detection or select clips to enable preview."
            )
            self._spectrogram_label.setText("Spectrogram preview unavailable")
            self._spectrogram_label.setPixmap(QPixmap())
            self._waveform_label.setText("Waveform preview unavailable")
            self._waveform_label.setPixmap(QPixmap())
            return

        self._current_index = max(0, min(self._current_index, total - 1))
        self._sample_position_label.setText(f"Sample {self._current_index + 1} of {total}")
        self._prev_button.setEnabled(self._current_index > 0)
        self._next_button.setEnabled(self._current_index < total - 1)

        segment = self._segments[self._current_index]
        sample_id = compute_sample_id(self._current_index, segment)
        self._update_override_controls(sample_id)

        effective = self._effective_settings(sample_id)
        core_duration = max(0.0, segment.end - segment.start)
        pre_pad_ms = float(effective.get("pre_pad_ms", 0.0) or 0.0)
        post_pad_ms = float(effective.get("post_pad_ms", 0.0) or 0.0)
        padded_start = max(0.0, segment.start - (pre_pad_ms / 1000.0))
        padded_end = segment.end + (post_pad_ms / 1000.0)
        if self._audio_duration is not None:
            padded_end = min(self._audio_duration, padded_end)
        padded_duration = max(0.0, padded_end - padded_start)
        summary_parts = [
            f"{segment.detector} {segment.start:.3f}s → {segment.end:.3f}s",
            f"core {core_duration:.3f}s",
            f"padded {padded_duration:.3f}s",
        ]
        formats = self._batch_settings.formats or ["wav"]
        if formats:
            summary_parts.append("formats: " + ", ".join(fmt.upper() for fmt in formats))
        self._sample_summary_label.setText("; ".join(summary_parts))
        self._schedule_preview_refresh()

    # ------------------------------------------------------------------ #
    # Signal handlers: global controls
    # ------------------------------------------------------------------ #

    def _on_formats_changed(self) -> None:
        formats = [
            code for code, checkbox in self._format_checkboxes.items() if checkbox.isChecked()
        ]
        if not formats:
            QMessageBox.warning(self, "No Format Selected", "Select at least one export format.")
            first_key = next(iter(self._format_checkboxes))
            self._format_checkboxes[first_key].setChecked(True)
            return
        self._batch_settings.formats = formats
        self._update_navigation_state()

    def _on_sample_rate_changed(self) -> None:
        value = self._sample_rate_combo.currentData()
        if isinstance(value, int):
            self._batch_settings.sample_rate_hz = value or None
            self._refresh_current_filename_preview()

    def _on_sample_rate_edited(self, text: str) -> None:
        text = text.strip()
        if not text:
            self._batch_settings.sample_rate_hz = None
            self._refresh_current_filename_preview()
            return
        try:
            value = int(text)
        except ValueError:
            return
        self._batch_settings.sample_rate_hz = value if value > 0 else None
        self._refresh_current_filename_preview()

    def _on_bit_depth_changed(self, index: int) -> None:
        mapping = {0: None, 1: "16", 2: "24", 3: "32f"}
        self._batch_settings.bit_depth = mapping.get(index)
        self._refresh_current_filename_preview()

    def _on_channels_changed(self, index: int) -> None:
        mapping = {0: None, 1: "mono", 2: "stereo"}
        self._batch_settings.channels = mapping.get(index)
        self._refresh_current_filename_preview()

    def _on_padding_changed(self) -> None:
        self._batch_settings.pre_pad_ms = float(self._pre_pad_spin.value())
        self._batch_settings.post_pad_ms = float(self._post_pad_spin.value())
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_normalize_toggled(self, state: int) -> None:
        self._batch_settings.normalize = state == Qt.CheckState.Checked
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_bandpass_toggled(self, state: int) -> None:
        enabled = state == Qt.CheckState.Checked
        if not enabled:
            self._batch_settings.bandpass_low_hz = None
            self._batch_settings.bandpass_high_hz = None
        self._toggle_bandpass_fields(enabled)
        if enabled:
            self._on_bandpass_values_changed()
        self._schedule_preview_refresh()

    def _on_bandpass_values_changed(self) -> None:
        if not self._bandpass_enable_checkbox.isChecked():
            return
        low_text = self._bandpass_low_edit.text().strip()
        high_text = self._bandpass_high_edit.text().strip()
        self._batch_settings.bandpass_low_hz = float(low_text) if low_text else None
        self._batch_settings.bandpass_high_hz = float(high_text) if high_text else None
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_artist_changed(self, text: str) -> None:
        self._batch_settings.artist = text or "SpectroSampler"
        self._refresh_current_filename_preview()

    def _on_album_changed(self, text: str) -> None:
        self._batch_settings.album = text or None
        self._refresh_current_filename_preview()

    def _on_year_changed(self, value: int) -> None:
        self._batch_settings.year = value or None
        self._refresh_current_filename_preview()

    def _on_notes_changed(self) -> None:
        text = self._notes_edit.toPlainText().strip()
        self._batch_settings.notes = text or None

    def _on_output_directory_changed(self, text: str) -> None:
        self._batch_settings.output_directory = text or None

    def _on_filename_template_changed(self, text: str) -> None:
        self._batch_settings.filename_template = text or DEFAULT_FILENAME_TEMPLATE
        sample_id = self._current_sample_id()
        if sample_id:
            self._update_override_controls(sample_id)
        self._schedule_preview_refresh()

    def _choose_output_directory(self) -> None:
        """Prompt the user to select an export destination."""

        directory = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if directory:
            self._output_dir_edit.setText(directory)
            self._batch_settings.output_directory = directory

    # ------------------------------------------------------------------ #
    # Per-sample overrides
    # ------------------------------------------------------------------ #

    def _on_override_pre_pad_toggled(self, state: int) -> None:
        enabled = state == Qt.CheckState.Checked
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        if enabled:
            self._set_override_field(
                sample_id, "pre_pad_ms", float(self._override_pre_pad_spin.value()), prune=False
            )
        else:
            self._set_override_field(sample_id, "pre_pad_ms", None, prune=True)
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_override_pre_pad_changed(self, value: float) -> None:
        if self._updating_controls:
            return
        if not self._override_pre_pad_checkbox.isChecked():
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        self._set_override_field(sample_id, "pre_pad_ms", float(value), prune=False)
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_override_post_pad_toggled(self, state: int) -> None:
        enabled = state == Qt.CheckState.Checked
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        if enabled:
            self._set_override_field(
                sample_id, "post_pad_ms", float(self._override_post_pad_spin.value()), prune=False
            )
        else:
            self._set_override_field(sample_id, "post_pad_ms", None, prune=True)
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_override_post_pad_changed(self, value: float) -> None:
        if self._updating_controls:
            return
        if not self._override_post_pad_checkbox.isChecked():
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        self._set_override_field(sample_id, "post_pad_ms", float(value), prune=False)
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_override_normalize_changed(self, index: int) -> None:
        if self._updating_controls:
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        if index == 0:  # Use Global Setting
            self._set_override_field(sample_id, "normalize", None, prune=True)
        elif index == 1:  # Enabled
            self._set_override_field(sample_id, "normalize", True, prune=False)
        else:  # Disabled
            self._set_override_field(sample_id, "normalize", False, prune=False)
        self._schedule_preview_refresh()
        self._refresh_current_filename_preview()

    def _on_override_bandpass_combo_changed(self, index: int) -> None:
        if self._updating_controls:
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        if index == 0:  # Use Global Setting
            self._override_bandpass_low.setEnabled(False)
            self._override_bandpass_high.setEnabled(False)
            self._set_override_field(sample_id, "bandpass_low_hz", None, prune=False)
            self._set_override_field(sample_id, "bandpass_high_hz", None, prune=True)
        elif index == 1:  # Enabled
            self._override_bandpass_low.setEnabled(True)
            self._override_bandpass_high.setEnabled(True)
            self._on_override_bandpass_changed()
        else:  # Disabled - use sentinel value -1.0 to indicate disabled
            self._override_bandpass_low.setEnabled(False)
            self._override_bandpass_high.setEnabled(False)
            self._set_override_field(sample_id, "bandpass_low_hz", -1.0, prune=False)
            self._set_override_field(sample_id, "bandpass_high_hz", -1.0, prune=False)
        self._schedule_preview_refresh()

    def _on_override_bandpass_changed(self) -> None:
        if self._updating_controls:
            return
        if self._override_bandpass_combo.currentIndex() != 1:  # Only apply if "Enabled"
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        low_text = self._override_bandpass_low.text().strip()
        high_text = self._override_bandpass_high.text().strip()
        low_val = float(low_text) if low_text else None
        high_val = float(high_text) if high_text else None
        self._set_override_field(sample_id, "bandpass_low_hz", low_val, prune=False)
        self._set_override_field(sample_id, "bandpass_high_hz", high_val, prune=False)
        self._schedule_preview_refresh()

    def _on_override_title_toggled(self, state: int) -> None:
        if self._updating_controls:
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        is_custom = state == Qt.CheckState.Checked
        self._override_title_edit.blockSignals(True)
        if not is_custom:
            self._set_override_field(sample_id, "title", None, prune=True)
            self._set_override_field(sample_id, "filename", None, prune=True)
            segment = self._current_segment()
            default_title = self._default_title(self._current_index, segment) if segment else ""
            self._override_title_edit.setText(default_title)
            self._override_title_edit.clearFocus()
        else:
            sanitized = sanitize_filename(self._override_title_edit.text().strip())
            self._override_title_edit.setText(sanitized)
            # Only set title, not filename - filename uses template with {title} token
            self._set_override_field(sample_id, "title", sanitized, prune=False)
            self._override_title_edit.setFocus()
        self._override_title_edit.blockSignals(False)
        self._update_filename_preview(sample_id, self._current_segment(), self._current_index)
        self._schedule_preview_refresh()

    def _on_override_title_changed(self, text: str) -> None:
        if self._updating_controls or not self._override_title_checkbox.isChecked():
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        sanitized = sanitize_filename(text.strip())
        if sanitized != text.strip():
            self._override_title_edit.blockSignals(True)
            self._override_title_edit.setText(sanitized)
            self._override_title_edit.blockSignals(False)
        # Only set title, not filename - filename uses template with {title} token
        self._set_override_field(sample_id, "title", sanitized, prune=False)
        self._update_filename_preview(sample_id, self._current_segment(), self._current_index)
        self._schedule_preview_refresh()

    def _on_clear_overrides_clicked(self) -> None:
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        self._overrides_by_id.pop(sample_id, None)
        self._update_override_controls(sample_id)
        self._schedule_preview_refresh()

    # ------------------------------------------------------------------ #
    # Samples tab navigation
    # ------------------------------------------------------------------ #

    def _save_current_sample_state(self) -> None:
        """Save the current sample's override state before navigating away."""
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        # Save title if custom (only set title, not filename - filename uses template)
        if self._override_title_checkbox.isChecked():
            title_text = self._override_title_edit.text().strip()
            sanitized = sanitize_filename(title_text) if title_text else ""
            self._set_override_field(sample_id, "title", sanitized or None, prune=False)
            # Don't set filename - let the template use the title token
        # Save padding if override is checked
        if self._override_pre_pad_checkbox.isChecked():
            self._set_override_field(
                sample_id, "pre_pad_ms", float(self._override_pre_pad_spin.value()), prune=False
            )
        if self._override_post_pad_checkbox.isChecked():
            self._set_override_field(
                sample_id, "post_pad_ms", float(self._override_post_pad_spin.value()), prune=False
            )
        # Save bandpass if override is enabled
        bandpass_index = self._override_bandpass_combo.currentIndex()
        if bandpass_index == 0:  # Use Global Setting
            self._set_override_field(sample_id, "bandpass_low_hz", None, prune=False)
            self._set_override_field(sample_id, "bandpass_high_hz", None, prune=True)
        elif bandpass_index == 1:  # Enabled
            low_text = self._override_bandpass_low.text().strip()
            high_text = self._override_bandpass_high.text().strip()
            low_val = float(low_text) if low_text else None
            high_val = float(high_text) if high_text else None
            self._set_override_field(sample_id, "bandpass_low_hz", low_val, prune=False)
            self._set_override_field(sample_id, "bandpass_high_hz", high_val, prune=False)
        else:  # Disabled - use sentinel value -1.0
            self._set_override_field(sample_id, "bandpass_low_hz", -1.0, prune=False)
            self._set_override_field(sample_id, "bandpass_high_hz", -1.0, prune=False)
        # Notes are saved automatically via textChanged signal

    def _on_previous_sample(self) -> None:
        if self._current_index <= 0:
            return
        self._save_current_sample_state()
        self._current_index -= 1
        self._update_navigation_state()

    def _on_next_sample(self) -> None:
        if self._current_index >= len(self._segments) - 1:
            return
        self._save_current_sample_state()
        self._current_index += 1
        self._update_navigation_state()

    # ------------------------------------------------------------------ #
    # Dialog acceptance / results
    # ------------------------------------------------------------------ #

    def _on_export_clicked(self) -> None:
        if not self._batch_settings.formats:
            QMessageBox.warning(self, "No Format Selected", "Select at least one export format.")
            return
        output_dir = self._batch_settings.output_directory
        if output_dir and not Path(output_dir).exists():
            try:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(
                    self,
                    "Invalid Export Folder",
                    f"Unable to create or access the chosen export folder:\n{exc}",
                )
                return
        self.export_requested.emit()
        self.accept()

    def should_persist_defaults(self) -> bool:
        """Return True when the user asked to persist global settings."""

        return self._persist_defaults_checkbox.isChecked()

    def batch_settings(self) -> ExportBatchSettings:
        """Return the updated batch settings after dialog execution."""

        notes_value = self._notes_edit.toPlainText().strip()
        self._batch_settings.notes = notes_value if notes_value else None
        return replace(self._batch_settings)

    def overrides(self) -> list[ExportSampleOverride]:
        """Return the updated list of overrides."""

        result: list[ExportSampleOverride] = []
        for override in self._overrides_by_id.values():
            if override.is_empty():
                continue
            result.append(replace(override))
        return result

    def load_overrides(self, payload: Sequence[dict]) -> None:
        """Load overrides from a serialized payload (used by project restore)."""

        try:
            overrides = parse_overrides(list(payload))
        except ValueError:
            overrides = []
        self._overrides_by_id = {item.sample_id: item for item in overrides}
        self._update_navigation_state()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _ensure_audio_metadata(self) -> None:
        if self._audio_path is None or self._audio_sample_rate is not None:
            return
        try:
            with sf.SoundFile(self._audio_path) as handle:
                self._audio_sample_rate = int(handle.samplerate)
                self._audio_total_frames = int(handle.frames)
                self._audio_duration = (
                    float(self._audio_total_frames) / self._audio_sample_rate
                    if self._audio_sample_rate
                    else 0.0
                )
        except (RuntimeError, OSError, ValueError):
            self._audio_sample_rate = None
            self._audio_total_frames = None
            self._audio_duration = None

    def _current_segment(self) -> Segment | None:
        if 0 <= self._current_index < len(self._segments):
            return self._segments[self._current_index]
        return None

    def _current_sample_id(self) -> str | None:
        segment = self._current_segment()
        if segment is None:
            return None
        return compute_sample_id(self._current_index, segment)

    def _effective_settings(self, sample_id: str) -> dict[str, object]:
        override = self._overrides_by_id.get(sample_id)
        return {
            "pre_pad_ms": (
                override.pre_pad_ms
                if override and override.pre_pad_ms is not None
                else self._batch_settings.pre_pad_ms
            ),
            "post_pad_ms": (
                override.post_pad_ms
                if override and override.post_pad_ms is not None
                else self._batch_settings.post_pad_ms
            ),
            "normalize": (
                override.normalize
                if override and override.normalize is not None
                else self._batch_settings.normalize
            ),
            "bandpass_low_hz": (
                override.bandpass_low_hz
                if override and override.bandpass_low_hz is not None
                else self._batch_settings.bandpass_low_hz
            ),
            "bandpass_high_hz": (
                override.bandpass_high_hz
                if override and override.bandpass_high_hz is not None
                else self._batch_settings.bandpass_high_hz
            ),
            "notes": (
                override.notes
                if override and override.notes is not None
                else self._batch_settings.notes
            ),
        }

    def _effective_formats(self, sample_id: str) -> list[str]:
        override = self._overrides_by_id.get(sample_id)
        if override and override.formats:
            normalized = [
                fmt.strip().lower()
                for fmt in override.formats
                if isinstance(fmt, str) and fmt.strip()
            ]
            ordered = list(dict.fromkeys(normalized))
            if ordered:
                return ordered
        global_formats = [
            fmt.strip().lower()
            for fmt in self._batch_settings.formats or []
            if isinstance(fmt, str) and fmt.strip()
        ]
        ordered = list(dict.fromkeys(global_formats))
        return ordered or ["wav"]

    def _update_override_controls(self, sample_id: str) -> None:
        self._updating_controls = True
        override = self._overrides_by_id.get(sample_id)
        segment = self._current_segment()
        default_pre = self._batch_settings.pre_pad_ms
        default_post = self._batch_settings.post_pad_ms
        pre_pad_override = override.pre_pad_ms if override else None
        post_pad_override = override.post_pad_ms if override else None
        self._override_pre_pad_checkbox.setChecked(pre_pad_override is not None)
        self._override_pre_pad_spin.setValue(
            pre_pad_override if pre_pad_override is not None else default_pre
        )

        self._override_post_pad_checkbox.setChecked(post_pad_override is not None)
        self._override_post_pad_spin.setValue(
            post_pad_override if post_pad_override is not None else default_post
        )

        normalize_index = 0
        if override and override.normalize is not None:
            normalize_index = 1 if override.normalize else 2
        self._override_normalize_combo.setCurrentIndex(normalize_index)

        bandpass_index = 0
        if override:
            # Check for disabled sentinel (-1.0)
            if override.bandpass_low_hz == -1.0 and override.bandpass_high_hz == -1.0:
                bandpass_index = 2  # Disabled
            elif override.bandpass_low_hz is not None and override.bandpass_high_hz is not None:
                # Only treat as enabled if both values are set and not sentinel
                if override.bandpass_low_hz != -1.0 and override.bandpass_high_hz != -1.0:
                    bandpass_index = 1  # Enabled
        self._override_bandpass_combo.setCurrentIndex(bandpass_index)
        if bandpass_index == 1:  # Enabled
            self._override_bandpass_low.setEnabled(True)
            self._override_bandpass_high.setEnabled(True)
            # Show override values if they exist, otherwise global values, otherwise defaults
            low_val = None
            high_val = None
            if (
                override
                and override.bandpass_low_hz is not None
                and override.bandpass_low_hz != -1.0
            ):
                low_val = override.bandpass_low_hz
            elif self._batch_settings.bandpass_low_hz is not None:
                low_val = self._batch_settings.bandpass_low_hz
            else:
                low_val = 20.0
            if (
                override
                and override.bandpass_high_hz is not None
                and override.bandpass_high_hz != -1.0
            ):
                high_val = override.bandpass_high_hz
            elif self._batch_settings.bandpass_high_hz is not None:
                high_val = self._batch_settings.bandpass_high_hz
            else:
                high_val = 20000.0
            self._override_bandpass_low.setText(str(low_val))
            self._override_bandpass_high.setText(str(high_val))
        else:
            self._override_bandpass_low.setEnabled(False)
            self._override_bandpass_high.setEnabled(False)
            # Show global values or defaults
            global_low = self._batch_settings.bandpass_low_hz
            global_high = self._batch_settings.bandpass_high_hz
            self._override_bandpass_low.setText(str(global_low) if global_low is not None else "20")
            self._override_bandpass_high.setText(
                str(global_high) if global_high is not None else "20000"
            )

        default_title = self._default_title(self._current_index, segment) if segment else ""
        is_custom_title = bool(override and override.title is not None)
        self._override_title_checkbox.blockSignals(True)
        self._override_title_checkbox.setChecked(is_custom_title)
        self._override_title_checkbox.blockSignals(False)
        self._override_title_edit.blockSignals(True)
        if is_custom_title:
            custom_name = override.title if override and override.title else ""
            self._override_title_edit.setText(custom_name)
        else:
            self._override_title_edit.setText(default_title)
        self._override_title_edit.blockSignals(False)

        self._sample_notes_edit.blockSignals(True)
        self._sample_notes_edit.setPlainText(override.notes if override and override.notes else "")
        self._sample_notes_edit.blockSignals(False)

        self._updating_controls = False
        if segment is not None:
            self._update_filename_preview(sample_id, segment, self._current_index)

    def _set_override_field(
        self, sample_id: str, field: str, value: object, *, prune: bool = False
    ) -> None:
        override = self._overrides_by_id.get(sample_id)
        if override is None:
            if value in (None, [], "") and prune:
                return
            override = ExportSampleOverride(sample_id=sample_id)
            self._overrides_by_id[sample_id] = override
        setattr(override, field, value)
        if prune and override.is_empty():
            self._overrides_by_id.pop(sample_id, None)

    def _on_sample_notes_changed(self) -> None:
        if self._updating_controls:
            return
        sample_id = self._current_sample_id()
        if not sample_id:
            return
        text = self._sample_notes_edit.toPlainText().strip()
        self._set_override_field(sample_id, "notes", text or None, prune=True)
        self._schedule_preview_refresh()

    def _default_title(self, index: int, segment: Segment | None) -> str:
        if segment is None:
            return "sample"
        return derive_sample_title(index, segment, fallback="sample")

    def _build_sample_filenames(
        self, sample_id: str, segment: Segment | None, index: int
    ) -> list[str]:
        if segment is None:
            return []
        effective = self._effective_settings(sample_id)
        formats = self._effective_formats(sample_id)
        normalize = bool(effective["normalize"])
        pre_pad = float(effective["pre_pad_ms"])
        post_pad = float(effective["post_pad_ms"])
        title_value = self._title_value(sample_id, segment, index)

        override = self._overrides_by_id.get(sample_id)
        artist = self._batch_settings.artist
        if override and override.artist:
            artist = override.artist
        album = self._batch_settings.album
        if override and override.album:
            album = override.album
        year = self._batch_settings.year
        if override and override.year is not None:
            year = override.year

        sample_rate = self._batch_settings.sample_rate_hz
        if override and override.sample_rate_hz is not None:
            sample_rate = override.sample_rate_hz
        bit_depth = self._batch_settings.bit_depth
        if override and override.bit_depth:
            bit_depth = override.bit_depth
        channels = self._batch_settings.channels
        if override and override.channels:
            channels = override.channels

        template = self._batch_settings.filename_template or DEFAULT_FILENAME_TEMPLATE
        filenames: list[str] = []
        for fmt in formats:
            base = render_filename_from_template(
                template=template,
                base_name=self._base_name,
                sample_id=sample_id,
                index=index,
                total=len(self._segments) if self._segments else 1,
                segment=segment,
                fmt=fmt,
                normalized=normalize,
                pre_pad_ms=pre_pad,
                post_pad_ms=post_pad,
                title=title_value,
                artist=artist,
                album=album,
                year=year,
                sample_rate_hz=sample_rate,
                bit_depth=bit_depth,
                channels=channels,
            )
            filenames.append(f"{base}.{fmt}")
        return filenames

    def _update_filename_preview(self, sample_id: str, segment: Segment | None, index: int) -> None:
        filenames = self._build_sample_filenames(sample_id, segment, index)
        if filenames:
            self._sample_title_label.setText("\n".join(filenames))
        else:
            self._sample_title_label.setText("")

    def _refresh_current_filename_preview(self) -> None:
        sample_id = self._current_sample_id()
        segment = self._current_segment()
        if sample_id and segment:
            self._update_filename_preview(sample_id, segment, self._current_index)
        else:
            self._sample_title_label.setText("")

    def _title_value(self, sample_id: str, segment: Segment | None, index: int) -> str:
        """Resolve the title value for a sample, matching ExportManager._resolve_title_value logic."""
        override = self._overrides_by_id.get(sample_id)
        if override and override.title:
            return override.title
        if segment is None:
            return "sample"
        return derive_sample_title(index, segment, fallback="sample")

    def _schedule_preview_refresh(self) -> None:
        if self._preview_timer.isActive():
            self._preview_timer.stop()
        self._preview_timer.start(PREVIEW_REFRESH_DELAY_MS)

    def _refresh_sample_preview(self) -> None:
        segment = self._current_segment()
        sample_id = self._current_sample_id()
        if segment is None or sample_id is None or self._audio_path is None:
            self._spectrogram_label.setPixmap(QPixmap())
            self._spectrogram_label.setText("Spectrogram preview unavailable")
            self._waveform_label.setPixmap(QPixmap())
            self._waveform_label.setText("Waveform preview unavailable")
            return

        effective = self._effective_settings(sample_id)
        audio_data = self._read_audio_window(segment, effective)
        if audio_data is None or audio_data.size == 0 or self._audio_sample_rate is None:
            self._spectrogram_label.setPixmap(QPixmap())
            self._spectrogram_label.setText("Spectrogram preview unavailable")
            self._waveform_label.setPixmap(QPixmap())
            self._waveform_label.setText("Waveform preview unavailable")
            return

        waveform_pixmap = self._render_waveform_pixmap(audio_data)
        self._waveform_label.setPixmap(waveform_pixmap)
        self._waveform_label.setText("")

        spectrogram_pixmap = self._render_spectrogram_pixmap(audio_data, self._audio_sample_rate)
        self._spectrogram_label.setPixmap(spectrogram_pixmap)
        self._spectrogram_label.setText("")

    def _read_audio_window(
        self, segment: Segment, effective: dict[str, object]
    ) -> np.ndarray | None:
        if self._audio_path is None or self._audio_sample_rate is None:
            return None
        pre_pad_ms = float(effective["pre_pad_ms"])
        post_pad_ms = float(effective["post_pad_ms"])
        start_sec = max(0.0, segment.start - pre_pad_ms / 1000.0)
        end_sec = segment.end + post_pad_ms / 1000.0
        if self._audio_duration is not None:
            end_sec = min(self._audio_duration, end_sec)
        if end_sec <= start_sec:
            return None
        start_frame = int(round(start_sec * self._audio_sample_rate))
        end_frame = int(round(end_sec * self._audio_sample_rate))
        frame_count = max(0, end_frame - start_frame)
        if frame_count == 0:
            return None
        try:
            with sf.SoundFile(self._audio_path) as handle:
                handle.seek(start_frame)
                data = handle.read(frame_count, dtype="float32", always_2d=False)
        except (RuntimeError, OSError, ValueError):
            return None

        if data.ndim > 1:
            data = np.mean(data, axis=1, dtype=np.float32)
        audio = np.asarray(data, dtype=np.float32)

        low_hz = effective["bandpass_low_hz"]
        high_hz = effective["bandpass_high_hz"]
        # Convert sentinel value -1.0 (disabled) to None
        if low_hz == -1.0:
            low_hz = None
        if high_hz == -1.0:
            high_hz = None
        if (low_hz is not None or high_hz is not None) and audio.size > 0:
            try:
                low_val = float(low_hz) if low_hz is not None else 0.0
                high_val = float(high_hz) if high_hz is not None else self._audio_sample_rate / 2.0
                audio = bandpass_filter(audio, self._audio_sample_rate, low_val, high_val, order=4)
            except (ValueError, RuntimeError):
                pass

        if effective["normalize"] and audio.size > 0:
            peak = float(np.max(np.abs(audio)))
            if peak > 1e-6:
                scale = NORMALIZE_TARGET_AMPLITUDE / peak
                audio = (audio * scale).astype(np.float32, copy=False)

        return audio

    def _render_waveform_pixmap(self, audio: np.ndarray) -> QPixmap:
        width, height = PREVIEW_WAVEFORM_SIZE
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#111111"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        mid_y = height / 2.0
        painter.setPen(QColor("#2A2A2A"))
        painter.drawLine(0, int(mid_y), width, int(mid_y))

        if audio.size == 0:
            painter.end()
            return pixmap

        step = max(1, audio.size // width)
        peaks_pos = []
        peaks_neg = []
        for start in range(0, audio.size, step):
            chunk = audio[start : start + step]
            peaks_pos.append(float(np.max(chunk)))
            peaks_neg.append(float(np.min(chunk)))

        max_abs = max(1e-6, max(abs(max(peaks_pos, default=0.0)), abs(min(peaks_neg, default=0.0))))
        scale = (height / 2.0 - 4.0) / max_abs
        painter.setPen(QColor("#EF7F22"))
        for idx, (pos, neg) in enumerate(zip(peaks_pos, peaks_neg, strict=True)):
            x = idx
            y_high = mid_y - pos * scale
            y_low = mid_y - neg * scale
            painter.drawLine(x, int(y_high), x, int(y_low))

        painter.end()
        return pixmap

    def _build_colormap_lut(self) -> np.ndarray:
        """Build a 256-entry viridis-like RGBA lookup table matching main spectrogram."""
        # Key color stops sampled from viridis gradient (approximate)
        stops = np.array(
            [
                [68, 1, 84, 255],
                [58, 82, 139, 255],
                [32, 144, 140, 255],
                [94, 201, 97, 255],
                [253, 231, 37, 255],
            ],
            dtype=np.float32,
        )
        positions = np.linspace(0.0, 1.0, len(stops), dtype=np.float32)
        samples = np.linspace(0.0, 1.0, 256, dtype=np.float32)
        lut = np.empty((256, 4), dtype=np.uint8)
        for channel in range(4):
            channel_values = np.interp(samples, positions, stops[:, channel])
            lut[:, channel] = np.clip(channel_values, 0, 255).astype(np.uint8)
        return lut

    def _render_spectrogram_pixmap(self, audio: np.ndarray, sample_rate: int) -> QPixmap:
        width, height = PREVIEW_SPECTROGRAM_SIZE
        if audio.size == 0:
            placeholder = QPixmap(width, height)
            placeholder.fill(QColor("#1A1A1A"))
            return placeholder

        window_size = 512
        hop_size = 128
        if audio.size < window_size:
            pad_width = window_size - audio.size
            audio = np.pad(audio, (0, pad_width), mode="constant")

        window = np.hanning(window_size).astype(np.float32, copy=False)
        frames = []
        for start in range(0, audio.size - window_size + 1, hop_size):
            frame = audio[start : start + window_size]
            frames.append(frame * window)
        if not frames:
            frames.append(audio[:window_size] * window)
        matrix = np.stack(frames, axis=0)
        spectrum = np.abs(np.fft.rfft(matrix, axis=1))
        spectrum = np.maximum(spectrum, 1e-8)
        db = 20.0 * np.log10(spectrum)

        # Normalize using percentile-based scaling like main spectrogram
        try:
            lo = float(np.nanpercentile(db, 5))
            hi = float(np.nanpercentile(db, 95))
            if hi <= lo:
                lo = float(np.nanmin(db))
                hi = float(np.nanmax(db) + 1e-6)
            norm = (db - lo) / (hi - lo)
            norm = np.clip(np.nan_to_num(norm, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0)
        except (FloatingPointError, OverflowError, ValueError, ZeroDivisionError, TypeError):
            # Fallback to simple normalization
            db -= db.max()
            norm = np.clip(db / 80.0 + 1.0, 0.0, 1.0)

        frame_indices = np.clip(
            np.round(np.linspace(0, norm.shape[0] - 1, width)).astype(int), 0, norm.shape[0] - 1
        )
        freq_indices = np.clip(
            np.round(np.linspace(0, norm.shape[1] - 1, height)).astype(int), 0, norm.shape[1] - 1
        )
        sampled = norm[frame_indices][:, freq_indices]
        image_array = np.flipud(sampled.T)  # Shape: (height, width)

        # Apply colormap
        indices = np.rint(image_array * 255.0).astype(np.int16)
        indices = np.clip(indices, 0, 255).astype(np.uint8)
        colormap = self._build_colormap_lut()  # Shape: (256, 4)
        # Index into colormap: indices is (height, width), result is (height, width, 4)
        rgba = colormap[indices]

        image_data = np.ascontiguousarray(rgba, dtype=np.uint8)
        image = QImage(
            image_data.data,
            width,
            height,
            image_data.strides[0],
            QImage.Format.Format_RGBA8888,
        )
        pixmap = QPixmap.fromImage(image.copy())
        painter = QPainter(pixmap)
        painter.setPen(QColor("#303030"))
        painter.drawRect(0, 0, width - 1, height - 1)
        painter.end()
        return pixmap
