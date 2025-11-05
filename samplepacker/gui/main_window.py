"""Main window for SamplePacker GUI."""

import copy
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from samplepacker.detectors.base import Segment
from samplepacker.gui.grid_manager import GridManager
from samplepacker.gui.navigator_scrollbar import NavigatorScrollbar
from samplepacker.gui.pipeline_wrapper import PipelineWrapper
from samplepacker.gui.detection_manager import DetectionManager
from samplepacker.gui.sample_player import SamplePlayerWidget
from samplepacker.gui.detection_settings import DetectionSettingsPanel
from samplepacker.gui.grid_manager import GridMode, GridSettings, Subdivision
from samplepacker.gui.spectrogram_tiler import SpectrogramTiler
from samplepacker.gui.spectrogram_widget import SpectrogramWidget
from samplepacker.gui.theme import ThemeManager
from samplepacker.pipeline import ProcessingSettings

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main window for SamplePacker GUI."""

    def __init__(self, parent: QWidget | None = None):
        """Initialize main window.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Theme manager
        self._theme_manager = ThemeManager(self)
        self._theme_manager.apply_theme()

        # Pipeline wrapper
        self._pipeline_wrapper: PipelineWrapper | None = None
        self._current_audio_path: Path | None = None

        # Audio playback
        self._media_player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._media_player.setAudioOutput(self._audio_output)
        self._temp_playback_file: Path | None = None
        self._loop_enabled = False
        self._current_playing_index: int | None = None
        self._current_playing_start: float | None = None
        self._current_playing_end: float | None = None
        self._is_paused = False
        self._paused_position = 0  # milliseconds
        self._playback_stopped = False  # Flag to prevent restart after explicit stop

        # Undo/redo stacks
        self._undo_stack: list[list[Segment]] = []
        self._redo_stack: list[list[Segment]] = []
        self._max_undo_stack_size = 50

        # Detection manager
        self._detection_manager = DetectionManager(self)
        self._detection_manager.progress.connect(self._on_detection_progress)
        self._detection_manager.finished.connect(self._on_detection_finished)
        self._detection_manager.error.connect(self._on_detection_error)

        # Spectrogram tiler
        self._tiler = SpectrogramTiler()

        # Grid manager
        self._grid_manager = GridManager()

        # Setup UI
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()

        # Apply theme
        self._apply_theme()

        # Connect signals
        self._connect_signals()
        
        # Setup UI refresh timer if enabled
        if self._ui_refresh_rate_enabled:
            self._setup_refresh_timer()

    def _setup_ui(self) -> None:
        """Setup UI components."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Settings panel (left)
        self._settings_panel = DetectionSettingsPanel()
        self._settings_panel.settings_changed.connect(self._on_settings_changed)
        self._settings_panel.detect_samples_requested.connect(self._on_detect_samples)
        splitter.addWidget(self._settings_panel)
        
        # Grid settings (stored in main window)
        self._grid_settings = GridSettings()
        self._grid_settings.snap_interval_sec = 1.0
        self._grid_settings.enabled = True
        
        # Export settings (stored in main window)
        self._export_pre_pad_ms = 0.0
        self._export_post_pad_ms = 0.0
        self._export_format = "wav"
        self._export_sample_rate: int | None = None
        self._export_bit_depth: str | None = None
        self._export_channels: str | None = None
        
        # UI refresh rate settings
        self._ui_refresh_rate_enabled = True
        self._ui_refresh_rate_hz = 60
        self._ui_refresh_timer = None
        self._pending_updates = {}
        splitter.setStretchFactor(0, 0)

        # Timeline view (right) - use vertical splitter for editor/navigator
        editor_widget = QWidget()
        editor_layout = QVBoxLayout()
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        # Sample player widget
        self._sample_player = SamplePlayerWidget()
        self._sample_player.play_requested.connect(self._on_player_play_requested)
        self._sample_player.pause_requested.connect(self._on_player_pause_requested)
        self._sample_player.stop_requested.connect(self._on_player_stop_requested)
        self._sample_player.next_requested.connect(self._on_player_next_requested)
        self._sample_player.previous_requested.connect(self._on_player_previous_requested)
        self._sample_player.loop_changed.connect(self._on_player_loop_changed)
        self._sample_player.seek_requested.connect(self._on_player_seek_requested)
        
        # Connect media player position updates
        self._media_player.positionChanged.connect(self._on_media_position_changed)
        self._media_player.durationChanged.connect(self._on_media_duration_changed)

        # Spectrogram widget
        self._spectrogram_widget = SpectrogramWidget()
        self._spectrogram_widget.sample_selected.connect(self._on_sample_selected)
        self._spectrogram_widget.sample_moved.connect(self._on_sample_moved)
        self._spectrogram_widget.sample_resized.connect(self._on_sample_resized)
        self._spectrogram_widget.sample_created.connect(self._on_sample_created)
        self._spectrogram_widget.sample_deleted.connect(self._on_sample_deleted)
        self._spectrogram_widget.sample_play_requested.connect(self._on_sample_play_requested)
        self._spectrogram_widget.time_clicked.connect(self._on_time_clicked)
        # New signals for context actions
        self._spectrogram_widget.sample_disable_requested.connect(lambda idx, dis: self._on_disable_sample(idx, dis))
        self._spectrogram_widget.sample_disable_others_requested.connect(self._on_disable_other_samples)
        self._spectrogram_widget.sample_center_requested.connect(self._on_center_clicked)
        self._spectrogram_widget.sample_center_fill_requested.connect(self._on_fill_clicked)

        # Vertical splitter for player and spectrogram (resizable)
        self._player_spectro_splitter = QSplitter(Qt.Orientation.Vertical)
        self._player_spectro_splitter.addWidget(self._sample_player)
        self._player_spectro_splitter.addWidget(self._spectrogram_widget)
        self._player_spectro_splitter.setStretchFactor(0, 0)  # Player doesn't stretch
        self._player_spectro_splitter.setStretchFactor(1, 1)  # Spectrogram stretches
        self._player_spectro_splitter.setCollapsible(0, True)  # Allow collapsing player
        self._player_spectro_splitter.setCollapsible(1, False)
        
        editor_layout.addWidget(self._player_spectro_splitter)

        editor_widget.setLayout(editor_layout)

        # Navigator scrollbar
        self._navigator = NavigatorScrollbar()
        self._navigator.view_changed.connect(self._on_navigator_view_changed)
        self._navigator.view_resized.connect(self._on_navigator_view_resized)
        self._navigator.setMinimumHeight(60)
        self._navigator.setMaximumHeight(300)

        # Vertical splitter for editor/navigator
        editor_splitter = QSplitter(Qt.Orientation.Vertical)
        editor_splitter.addWidget(editor_widget)
        editor_splitter.addWidget(self._navigator)
        editor_splitter.setStretchFactor(0, 1)
        editor_splitter.setStretchFactor(1, 0)
        editor_splitter.setCollapsible(0, False)
        editor_splitter.setCollapsible(1, True)

        splitter.addWidget(editor_splitter)
        splitter.setStretchFactor(1, 1)

        # Sample list (bottom) - samples as columns, fields as rows
        self._sample_table = QTableWidget()
        # Rows: Enable, Center, Start, End, Duration, Detector, Play, Delete
        self._sample_table.setRowCount(8)
        self._sample_table.setVerticalHeaderLabels(["Enable", "Center", "Start", "End", "Duration", "Detector", "Play", "Delete"])
        self._sample_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectColumns)
        self._sample_table.itemChanged.connect(self._on_sample_table_changed)
        self._sample_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._sample_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Calculate height to fit all 8 rows: header + (8 rows * row height)
        # Typical row height is ~30px, header is ~30px
        table_height = self._sample_table.horizontalHeader().height() + (8 * 30) + 10
        self._sample_table.setMinimumHeight(table_height)

        # Main vertical splitter for editor/sample table
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.addWidget(splitter)
        self._main_splitter.addWidget(self._sample_table)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 0)
        self._main_splitter.setCollapsible(0, False)
        self._main_splitter.setCollapsible(1, True)

        main_layout.addWidget(self._main_splitter)

        central.setLayout(main_layout)

        # Set initial sizes
        splitter.setSizes([300, 800])
        self._player_spectro_splitter.setSizes([120, 480])  # Player: 120px, Spectrogram: 480px
        editor_splitter.setSizes([600, 100])
        self._main_splitter.setSizes([600, 200])
        
        # Store initial sizes for restore
        self._player_initial_size = 120
        self._info_table_initial_size = 200
        
        # Connect splitter signals to update menu action states when manually collapsed/expanded
        self._main_splitter.splitterMoved.connect(self._on_info_splitter_moved)
        self._player_spectro_splitter.splitterMoved.connect(self._on_player_splitter_moved)

    def _setup_menu(self) -> None:
        """Setup menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        open_action = QAction("&Open Audio File...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_action = QAction("&Export Samples...", self)
        export_action.setShortcut(QKeySequence.StandardKey.Save)
        export_action.triggered.connect(self._on_export_samples)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Export menu
        export_menu = menubar.addMenu("&Export")
        
        # Export pre-padding
        export_pre_pad_action = QAction("Export &Pre-padding...", self)
        export_pre_pad_action.triggered.connect(self._on_export_pre_pad_settings)
        export_menu.addAction(export_pre_pad_action)
        
        # Export post-padding
        export_post_pad_action = QAction("Export &Post-padding...", self)
        export_post_pad_action.triggered.connect(self._on_export_post_pad_settings)
        export_menu.addAction(export_post_pad_action)
        
        export_menu.addSeparator()
        
        # Format
        format_menu = export_menu.addMenu("&Format")
        self._export_format_wav_action = QAction("&WAV", self)
        self._export_format_wav_action.setCheckable(True)
        self._export_format_wav_action.setChecked(True)
        self._export_format_wav_action.triggered.connect(lambda: self._on_export_format_changed("wav"))
        format_menu.addAction(self._export_format_wav_action)
        
        self._export_format_flac_action = QAction("&FLAC", self)
        self._export_format_flac_action.setCheckable(True)
        self._export_format_flac_action.triggered.connect(lambda: self._on_export_format_changed("flac"))
        format_menu.addAction(self._export_format_flac_action)
        
        # Sample rate
        sample_rate_action = QAction("&Sample Rate...", self)
        sample_rate_action.triggered.connect(self._on_export_sample_rate_settings)
        export_menu.addAction(sample_rate_action)
        
        # Bit depth
        bit_depth_action = QAction("&Bit Depth...", self)
        bit_depth_action.triggered.connect(self._on_export_bit_depth_settings)
        export_menu.addAction(bit_depth_action)
        
        # Channels
        channels_action = QAction("&Channels...", self)
        channels_action.triggered.connect(self._on_export_channels_settings)
        export_menu.addAction(channels_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self._redo_action.setEnabled(False)
        self._redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self._redo_action)

        edit_menu.addSeparator()

        # Detect Samples action
        detect_action = QAction("&Detect Samples", self)
        detect_action.setShortcut(QKeySequence("Ctrl+D"))
        detect_action.triggered.connect(self._on_detect_samples)
        edit_menu.addAction(detect_action)

        # Auto Sample Order (default ON)
        self._auto_order_action = QAction("&Auto Sample Order", self)
        self._auto_order_action.setCheckable(True)
        self._auto_order_action.setChecked(True)
        self._auto_order_action.toggled.connect(self._on_toggle_auto_order)
        edit_menu.addAction(self._auto_order_action)

        # Re-order Samples (disabled when auto-order ON)
        self._reorder_action = QAction("&Re-order Samples", self)
        self._reorder_action.setEnabled(False)
        self._reorder_action.triggered.connect(self._on_reorder_samples)
        edit_menu.addAction(self._reorder_action)

        # Delete All Samples
        delete_all_action = QAction("&Delete All Samples", self)
        delete_all_action.triggered.connect(self._on_delete_all_samples)
        edit_menu.addAction(delete_all_action)

        # Disable All Samples
        disable_all_action = QAction("&Disable All Samples", self)
        disable_all_action.triggered.connect(self._on_disable_all_samples)
        edit_menu.addAction(disable_all_action)

        # Show Disabled Samples (toggle, default true)
        self._show_disabled_action = QAction("Show &Disabled Samples", self)
        self._show_disabled_action.setCheckable(True)
        self._show_disabled_action.setChecked(True)
        self._show_disabled_action.toggled.connect(self._on_toggle_show_disabled)

        # View menu
        view_menu = menubar.addMenu("&View")
        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_action.triggered.connect(self._on_zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_action.triggered.connect(self._on_zoom_out)
        view_menu.addAction(zoom_out_action)

        view_menu.addSeparator()

        fit_action = QAction("&Fit to Window", self)
        fit_action.triggered.connect(self._on_fit_to_window)
        view_menu.addAction(fit_action)

        view_menu.addSeparator()

        # Hide Info Table action
        self._hide_info_action = QAction("Hide &Info Table", self)
        self._hide_info_action.setCheckable(True)
        self._hide_info_action.setChecked(False)
        self._hide_info_action.triggered.connect(self._on_toggle_info_table)
        view_menu.addAction(self._hide_info_action)

        # Hide Player action
        self._hide_player_action = QAction("Hide &Player", self)
        self._hide_player_action.setCheckable(True)
        self._hide_player_action.setChecked(False)
        self._hide_player_action.triggered.connect(self._on_toggle_player)
        view_menu.addAction(self._hide_player_action)

        # Show Disabled Samples toggle moved from Edit to View
        view_menu.addAction(self._show_disabled_action)

        view_menu.addSeparator()

        # UI Refresh Rate Limit
        self._ui_refresh_rate_enabled_action = QAction("Limit UI &Refresh Rate", self)
        self._ui_refresh_rate_enabled_action.setCheckable(True)
        self._ui_refresh_rate_enabled_action.setChecked(True)
        self._ui_refresh_rate_enabled_action.toggled.connect(self._on_ui_refresh_rate_enabled_changed)
        view_menu.addAction(self._ui_refresh_rate_enabled_action)
        
        refresh_rate_menu = view_menu.addMenu("Refresh &Rate")
        refresh_rates = [15, 30, 60, 75, 120, 144, 165, 240]
        self._refresh_rate_actions = {}
        for rate in refresh_rates:
            action = QAction(f"{rate} Hz", self)
            action.setCheckable(True)
            action.setChecked(rate == 60)
            action.triggered.connect(lambda checked, r=rate: self._on_refresh_rate_changed(r))
            refresh_rate_menu.addAction(action)
            self._refresh_rate_actions[rate] = action

        view_menu.addSeparator()

        # Grid Settings
        grid_menu = view_menu.addMenu("&Grid Settings")
        
        # Grid mode
        grid_mode_menu = grid_menu.addMenu("Grid &Mode")
        self._grid_mode_free_action = QAction("Free &Time", self)
        self._grid_mode_free_action.setCheckable(True)
        self._grid_mode_free_action.setChecked(True)
        self._grid_mode_free_action.triggered.connect(self._on_grid_mode_changed)
        grid_mode_menu.addAction(self._grid_mode_free_action)
        
        self._grid_mode_musical_action = QAction("&Musical Bar", self)
        self._grid_mode_musical_action.setCheckable(True)
        self._grid_mode_musical_action.triggered.connect(self._on_grid_mode_changed)
        grid_mode_menu.addAction(self._grid_mode_musical_action)
        
        # Snap interval (for free time mode)
        snap_interval_action = QAction("Snap &Interval...", self)
        snap_interval_action.triggered.connect(self._on_snap_interval_settings)
        grid_menu.addAction(snap_interval_action)
        
        # BPM (for musical bar mode)
        bpm_action = QAction("&BPM...", self)
        bpm_action.triggered.connect(self._on_bpm_settings)
        grid_menu.addAction(bpm_action)
        
        # Subdivision (for musical bar mode)
        subdivision_menu = grid_menu.addMenu("&Subdivision")
        subdivisions = ["Whole", "Half", "Quarter", "Eighth", "Sixteenth", "Thirty-second"]
        self._subdivision_actions = {}
        for sub in subdivisions:
            action = QAction(sub, self)
            action.setCheckable(True)
            action.setChecked(sub == "Quarter")
            action.triggered.connect(lambda checked, s=sub: self._on_subdivision_changed(s))
            subdivision_menu.addAction(action)
            self._subdivision_actions[sub] = action
        
        grid_menu.addSeparator()
        
        # Show grid
        self._grid_visible_action = QAction("Show &Grid", self)
        self._grid_visible_action.setCheckable(True)
        self._grid_visible_action.setChecked(True)
        self._grid_visible_action.toggled.connect(self._on_grid_visible_changed)
        grid_menu.addAction(self._grid_visible_action)
        
        # Snap to grid
        self._snap_enabled_action = QAction("Snap to &Grid", self)
        self._snap_enabled_action.setCheckable(True)
        self._snap_enabled_action.setChecked(True)
        self._snap_enabled_action.toggled.connect(self._on_snap_enabled_changed)
        grid_menu.addAction(self._snap_enabled_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        # Verbose Log toggle (default ON)
        self._verbose_log_action = QAction("Verbose &Log", self)
        self._verbose_log_action.setCheckable(True)
        self._verbose_log_action.setChecked(True)
        self._verbose_log_action.toggled.connect(self._on_toggle_verbose_log)
        help_menu.addAction(self._verbose_log_action)

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self) -> None:
        """Setup status bar."""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress_bar)

        self._status_label = QLabel("Ready")
        self._status_bar.addWidget(self._status_label)

    def _connect_signals(self) -> None:
        """Connect signals."""
        # Settings panel
        self._settings_panel.settings_changed.connect(self._on_settings_changed)
        
        # Spectrogram widget - operation start signals for undo
        self._spectrogram_widget.sample_drag_started.connect(self._on_sample_drag_started)
        self._spectrogram_widget.sample_resize_started.connect(self._on_sample_resize_started)
        self._spectrogram_widget.sample_create_started.connect(self._on_sample_create_started)

    def _apply_theme(self) -> None:
        """Apply theme to application."""
        stylesheet = self._theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)

        # Apply theme colors to widgets
        palette = self._theme_manager.palette
        self._sample_player.set_theme_colors(palette)
        self._navigator.set_theme_colors(palette)
        self._spectrogram_widget.set_theme_colors(palette)

    def _on_open_file(self) -> None:
        """Handle open file action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Audio File",
            "",
            "Audio Files (*.wav *.flac *.mp3 *.m4a *.aac);;All Files (*)",
        )

        if file_path:
            self.load_audio_file(Path(file_path))

    def load_audio_file(self, file_path: Path) -> None:
        """Load audio file.

        Args:
            file_path: Path to audio file.
        """
        try:
            # Create pipeline wrapper
            settings = self._settings_panel.get_settings()
            # Initialize export settings
            settings.export_pre_pad_ms = self._export_pre_pad_ms
            settings.export_post_pad_ms = self._export_post_pad_ms
            settings.format = self._export_format
            settings.sample_rate = self._export_sample_rate
            settings.bit_depth = self._export_bit_depth
            settings.channels = self._export_channels
            self._pipeline_wrapper = PipelineWrapper(settings)
            self._detection_manager.set_pipeline_wrapper(self._pipeline_wrapper)

            # Load audio
            audio_info = self._pipeline_wrapper.load_audio(file_path)
            self._current_audio_path = file_path

            # Update UI
            duration = audio_info.get("duration", 0.0)
            self._spectrogram_widget.set_duration(duration)
            self._navigator.set_duration(duration)

            # Set initial time range
            self._spectrogram_widget.set_time_range(0.0, min(60.0, duration))
            self._navigator.set_view_range(0.0, min(60.0, duration))

            # Generate overview for navigator and main spectrogram fallback
            overview = self._tiler.generate_overview(file_path, duration)
            self._navigator.set_overview_tile(overview)
            try:
                self._spectrogram_widget.set_overview_tile(overview)
            except Exception:
                pass

            # Update frequency range
            fmin = settings.hp
            fmax = settings.lp
            self._spectrogram_widget.set_frequency_range(fmin, fmax)
            self._spectrogram_widget.set_audio_path(file_path)
            self._tiler.fmin = fmin
            self._tiler.fmax = fmax

            self._status_label.setText(f"Loaded: {file_path.name}")
            logger.info(f"Loaded audio file: {file_path}")
            
            # Clear any existing segments and UI until detection is requested
            if self._pipeline_wrapper:
                self._pipeline_wrapper.current_segments = []
            self._spectrogram_widget.set_segments([])
            self._update_sample_table([])
            self._update_navigator_markers()

            # Ensure main spectrogram is visible immediately on load
            try:
                self._spectrogram_widget.preload_current_view()
            except Exception:
                pass

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load audio file:\n{str(e)}")
            logger.error(f"Failed to load audio file: {e}")

    def _on_detect_samples(self) -> None:
        """Handle Detect Samples request."""
        if not self._current_audio_path:
            QMessageBox.warning(self, "No File", "Please open an audio file first.")
            return

        if self._detection_manager.is_processing():
            QMessageBox.warning(self, "Processing", "Detection is already in progress.")
            return

        # Update pipeline wrapper settings
        if self._pipeline_wrapper:
            self._pipeline_wrapper.settings = self._settings_panel.get_settings()
            # Update export settings
            self._pipeline_wrapper.settings.export_pre_pad_ms = self._export_pre_pad_ms
            self._pipeline_wrapper.settings.export_post_pad_ms = self._export_post_pad_ms
            self._pipeline_wrapper.settings.format = self._export_format
            self._pipeline_wrapper.settings.sample_rate = self._export_sample_rate
            self._pipeline_wrapper.settings.bit_depth = self._export_bit_depth
            self._pipeline_wrapper.settings.channels = self._export_channels

        # Start detection processing
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # Indeterminate
        self._status_label.setText("Detecting samples...")
        self._detection_manager.start_detection()

    def _on_detection_progress(self, message: str) -> None:
        """Handle detection progress.

        Args:
            message: Progress message.
        """
        self._status_label.setText(message)

    def _on_detection_finished(self, result: dict[str, Any]) -> None:
        """Handle detection finished.

        Args:
            result: Processing results.
        """
        self._progress_bar.setVisible(False)
        self._status_label.setText("Detection complete")

        # Update segments
        segments = result.get("segments", [])
        # Ensure enabled flag defaults to True
        for s in segments:
            if not hasattr(s, "attrs") or s.attrs is None:
                s.attrs = {}
            s.attrs.setdefault("enabled", True)
        if self._pipeline_wrapper:
            self._pipeline_wrapper.current_segments = segments
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_sample_table(segments)
        
        # Don't update player widget - player should only show info for currently playing sample

        # Update navigator with sample markers (enabled only)
        self._update_navigator_markers()
        
        # Push initial undo state so users can undo back to original detected segments
        if self._pipeline_wrapper:
            self._push_undo_state()

    def _on_detection_error(self, error: str) -> None:
        """Handle detection error.

        Args:
            error: Error message.
        """
        self._progress_bar.setVisible(False)
        self._status_label.setText(f"Error: {error}")
        QMessageBox.critical(self, "Detection Error", f"Failed to detect samples:\n{error}")

    def _on_settings_changed(self) -> None:
        """Handle settings change."""
        # Update frequency range if filters changed
        settings = self._settings_panel.get_settings()
        fmin = settings.hp
        fmax = settings.lp
        self._spectrogram_widget.set_frequency_range(fmin, fmax)
        self._tiler.fmin = fmin
        self._tiler.fmax = fmax

        # Update grid manager
        self._grid_manager.settings = self._grid_settings
        self._spectrogram_widget.set_grid_manager(self._grid_manager)

    def _on_sample_selected(self, index: int) -> None:
        """Handle sample selection.

        Args:
            index: Sample index.
        """
        # Update table selection (column-based now)
        if self._sample_table.columnCount() > index:
            self._sample_table.setCurrentCell(0, index)
        self._spectrogram_widget.set_selected_index(index)
        
        # Don't update player widget - player should only show info for currently playing sample

    def _on_sample_moved(self, index: int, start: float, end: float) -> None:
        """Handle sample moved.

        Args:
            index: Sample index.
            start: New start time.
            end: New end time.
        """
        if self._pipeline_wrapper and index < len(self._pipeline_wrapper.current_segments):
            seg = self._pipeline_wrapper.current_segments[index]
            old_start = seg.start
            old_end = seg.end
            seg.start = start
            seg.end = end
            self._update_sample_table(self._pipeline_wrapper.current_segments)
            self._maybe_auto_reorder()
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_navigator_markers()
            
            # Update player widget if this is the currently playing sample
            if index == self._current_playing_index:
                # Calculate new duration in milliseconds
                new_duration = seg.duration()
                new_duration_ms = int(new_duration * 1000)
                
                # Update segment boundaries for playback
                self._current_playing_start = start
                self._current_playing_end = end
                
                # Update player widget with new segment info
                self._sample_player.set_sample(seg, index, len(self._pipeline_wrapper.current_segments))
                
                # Adjust scrub bar position based on new segment boundaries
                # Current media player position is relative to the old extracted segment
                if self._media_player.duration() > 0:
                    current_media_pos_ms = self._media_player.position()
                    old_duration = old_end - old_start
                    
                    if old_duration > 0:
                        # Calculate position as fraction of old segment duration
                        relative_position = current_media_pos_ms / (old_duration * 1000.0)
                        # Map to new segment duration
                        new_position_ms = int(relative_position * new_duration_ms)
                        # Clamp to new duration bounds
                        new_position_ms = max(0, min(new_position_ms, new_duration_ms))
                    else:
                        new_position_ms = 0
                    
                    # Update scrub bar with adjusted position and new duration
                    self._sample_player.set_position(new_position_ms, new_duration_ms)
                    
                    # Update paused position if paused
                    if self._is_paused:
                        self._paused_position = new_position_ms

    def _on_sample_resized(self, index: int, start: float, end: float) -> None:
        """Handle sample resized.

        Args:
            index: Sample index.
            start: New start time.
            end: New end time.
        """
        if self._pipeline_wrapper and index < len(self._pipeline_wrapper.current_segments):
            seg = self._pipeline_wrapper.current_segments[index]
            old_start = seg.start
            old_end = seg.end
            seg.start = start
            seg.end = end
            self._update_sample_table(self._pipeline_wrapper.current_segments)
            self._maybe_auto_reorder()
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_navigator_markers()
            
            # Update player widget if this is the currently playing sample
            if index == self._current_playing_index:
                # Calculate new duration in milliseconds
                new_duration = seg.duration()
                new_duration_ms = int(new_duration * 1000)
                
                # Update segment boundaries for playback
                self._current_playing_start = start
                self._current_playing_end = end
                
                # Update player widget with new segment info
                self._sample_player.set_sample(seg, index, len(self._pipeline_wrapper.current_segments))
                
                # Adjust scrub bar position based on new segment boundaries
                # Current media player position is relative to the old extracted segment
                if self._media_player.duration() > 0:
                    current_media_pos_ms = self._media_player.position()
                    old_duration = old_end - old_start
                    
                    if old_duration > 0:
                        # Calculate position as fraction of old segment duration
                        relative_position = current_media_pos_ms / (old_duration * 1000.0)
                        # Map to new segment duration
                        new_position_ms = int(relative_position * new_duration_ms)
                        # Clamp to new duration bounds
                        new_position_ms = max(0, min(new_position_ms, new_duration_ms))
                    else:
                        new_position_ms = 0
                    
                    # Update scrub bar with adjusted position and new duration
                    self._sample_player.set_position(new_position_ms, new_duration_ms)
                    
                    # Update paused position if paused
                    if self._is_paused:
                        self._paused_position = new_position_ms

    def _on_sample_created(self, start: float, end: float) -> None:
        """Handle sample created.

        Args:
            start: Start time.
            end: End time.
        """
        from samplepacker.detectors.base import Segment

        # Create new segment
        seg = Segment(start=start, end=end, detector="manual", score=1.0)
        if self._pipeline_wrapper:
            # Default enabled
            seg.attrs["enabled"] = True
            self._pipeline_wrapper.current_segments.append(seg)
            self._maybe_auto_reorder()
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_sample_table(self._pipeline_wrapper.current_segments)
            self._update_navigator_markers()

    def _on_sample_deleted(self, index: int) -> None:
        """Handle sample deleted.

        Args:
            index: Sample index.
        """
        if self._pipeline_wrapper and 0 <= index < len(self._pipeline_wrapper.current_segments):
            # Push undo state before deleting
            self._push_undo_state()
            del self._pipeline_wrapper.current_segments[index]
            self._maybe_auto_reorder()
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_sample_table(self._pipeline_wrapper.current_segments)
            self._update_navigator_markers()

    def _update_navigator_markers(self) -> None:
        """Update navigator markers from current segments."""
        if not self._pipeline_wrapper:
            return
        show_disabled = getattr(self, "_show_disabled_action", None) is None or self._show_disabled_action.isChecked()
        markers = []
        for seg in self._pipeline_wrapper.current_segments:
            enabled = seg.attrs.get("enabled", True)
            if enabled:
                color = self._get_segment_color(seg.detector)
                markers.append((seg.start, seg.end, color))
            elif show_disabled:
                # Dim gray for disabled markers
                from PySide6.QtGui import QColor
                markers.append((seg.start, seg.end, QColor(120, 120, 120, 160)))
        self._navigator.set_sample_markers(markers)

    def _on_sample_play_requested(self, index: int) -> None:
        """Handle sample play request.

        Args:
            index: Sample index.
        """
        if not self._pipeline_wrapper or not self._current_audio_path:
            return
        
        if 0 <= index < len(self._pipeline_wrapper.current_segments):
            self._current_playing_index = index
            seg = self._pipeline_wrapper.current_segments[index]
            # Update player widget to show playing sample
            self._sample_player.set_sample(seg, index, len(self._pipeline_wrapper.current_segments))
            self._play_segment(seg.start, seg.end)

    def _play_segment(self, start_time: float, end_time: float) -> None:
        """Play audio segment.

        Args:
            start_time: Start time in seconds.
            end_time: End time in seconds.
        """
        if not self._current_audio_path or not self._current_audio_path.exists():
            return

        try:
            # Stop any currently playing audio and clear source
            self._media_player.stop()
            self._media_player.setSource(QUrl())
            
            # Disconnect previous handlers to avoid multiple connections
            try:
                self._media_player.mediaStatusChanged.disconnect()
            except Exception:
                pass
            
            # Clean up previous temp file
            if self._temp_playback_file and self._temp_playback_file.exists():
                try:
                    self._temp_playback_file.unlink()
                except Exception:
                    pass
                self._temp_playback_file = None

            # Extract segment to temporary file with unique filename
            import subprocess
            temp_dir = Path(tempfile.gettempdir())
            unique_id = uuid.uuid4().hex
            self._temp_playback_file = temp_dir / f"samplepacker_playback_{unique_id}.wav"
            
            duration = end_time - start_time
            
            # Use FFmpeg to extract segment
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", f"{start_time:.6f}",
                "-i", str(self._current_audio_path),
                "-t", f"{duration:.6f}",
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                str(self._temp_playback_file),
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg extraction failed: {result.stderr}")
                QMessageBox.warning(self, "Playback Error", f"Failed to extract audio segment:\n{result.stderr}")
                return

            # Store current playing info for looping
            self._current_playing_start = start_time
            self._current_playing_end = end_time
            self._playback_stopped = False  # Reset stop flag when starting new playback
            
            # Store paused position for resume (if applicable)
            seek_position = self._paused_position if self._is_paused and self._paused_position > 0 else 0
            was_paused = self._is_paused
            if was_paused:
                self._is_paused = False
                self._paused_position = 0
            
            # Clean up temp file when playback finishes and handle looping
            def on_playback_finished(status):
                if status == QMediaPlayer.MediaStatus.EndOfMedia:
                    # Don't restart if playback was explicitly stopped
                    if self._playback_stopped:
                        self._playback_stopped = False
                        return
                    
                    # Check if looping is enabled
                    if self._loop_enabled and self._current_playing_index is not None:
                        # Restart playback of the same segment
                        if self._current_playing_start is not None and self._current_playing_end is not None:
                            self._play_segment(self._current_playing_start, self._current_playing_end)
                        return
                    
                    # Not looping, clean up
                    self._sample_player.set_playing(False)
                    self._current_playing_index = None
                    self._current_playing_start = None
                    self._current_playing_end = None
                    self._is_paused = False
                    self._paused_position = 0
                    
                    if self._temp_playback_file and self._temp_playback_file.exists():
                        try:
                            self._temp_playback_file.unlink()
                            self._temp_playback_file = None
                        except Exception:
                            pass
            
            # Handler to wait for media to load before playing
            def on_media_status_changed(status):
                if status == QMediaPlayer.MediaStatus.LoadedMedia:
                    # Media is loaded, now we can play
                    # If resuming from pause, seek to paused position
                    if seek_position > 0:
                        self._media_player.setPosition(seek_position)
                    
                    self._media_player.play()
                    # Update player state to show playing
                    self._sample_player.set_playing(True)
                elif status == QMediaPlayer.MediaStatus.EndOfMedia:
                    # Also handle end of media in status changed
                    on_playback_finished(status)
            
            # Connect handlers
            self._media_player.mediaStatusChanged.connect(on_media_status_changed)
            
            # Load the extracted segment
            url = QUrl.fromLocalFile(str(self._temp_playback_file))
            self._media_player.setSource(url)
            
        except Exception as e:
            logger.error(f"Failed to play segment: {e}")
            QMessageBox.warning(self, "Playback Error", f"Failed to play audio segment:\n{str(e)}")

    def _on_navigator_view_changed(self, start_time: float, end_time: float) -> None:
        """Handle navigator view change.

        Args:
            start_time: Start time.
            end_time: End time.
        """
        self._spectrogram_widget.set_time_range(start_time, end_time)

    def _on_navigator_view_resized(self, start_time: float, end_time: float) -> None:
        """Handle navigator view resize.

        Args:
            start_time: Start time.
            end_time: End time.
        """
        self._spectrogram_widget.set_time_range(start_time, end_time)

    def _on_time_clicked(self, time: float) -> None:
        """Handle time click.

        Args:
            time: Time in seconds.
        """
        # Update view to center on clicked time
        view_duration = self._spectrogram_widget._end_time - self._spectrogram_widget._start_time
        new_start = max(0.0, min(time - view_duration / 2, self._spectrogram_widget._duration - view_duration))
        new_end = new_start + view_duration
        self._spectrogram_widget.set_time_range(new_start, new_end)
        self._navigator.set_view_range(new_start, new_end)

    def _on_player_play_requested(self, index: int) -> None:
        """Handle player play request.

        Args:
            index: Sample index.
        """
        # If already playing the same sample and paused, resume
        if self._is_paused and self._current_playing_index == index:
            # Resume from paused position
            self._media_player.setPosition(self._paused_position)
            self._media_player.play()
            self._is_paused = False
            self._paused_position = 0
            self._sample_player.set_playing(True)
        else:
            # Start playing new sample
            self._current_playing_index = index
            self._on_sample_play_requested(index)
            self._sample_player.set_playing(True)

    def _on_player_pause_requested(self) -> None:
        """Handle player pause request."""
        # Store current position before pausing
        self._paused_position = self._media_player.position()
        self._is_paused = True
        self._media_player.pause()
        self._sample_player.set_playing(False)

    def _on_player_stop_requested(self) -> None:
        """Handle player stop request."""
        # Disconnect mediaStatusChanged signal to prevent restart callbacks
        try:
            self._media_player.mediaStatusChanged.disconnect()
        except Exception:
            pass
        
        # Set stop flag to prevent restart
        self._playback_stopped = True
        
        # Stop playback and clear source
        self._media_player.stop()
        self._media_player.setSource(QUrl())
        
        # Update UI state
        self._sample_player.set_playing(False)
        self._current_playing_index = None
        self._current_playing_start = None
        self._current_playing_end = None
        self._is_paused = False
        self._paused_position = 0
        
        # Reset progress bar
        self._sample_player.set_position(0, self._sample_player._duration if hasattr(self._sample_player, '_duration') else 0)

    def _on_player_next_requested(self) -> None:
        """Handle player next request."""
        if not self._pipeline_wrapper or not self._pipeline_wrapper.current_segments:
            return
        
        current_col = self._sample_table.currentColumn()
        if current_col < 0:
            current_col = 0
        
        next_col = min(current_col + 1, len(self._pipeline_wrapper.current_segments) - 1)
        if next_col != current_col:
            self._sample_table.setCurrentCell(0, next_col)
            self._on_sample_selected(next_col)

    def _on_player_previous_requested(self) -> None:
        """Handle player previous request."""
        if not self._pipeline_wrapper or not self._pipeline_wrapper.current_segments:
            return
        
        current_col = self._sample_table.currentColumn()
        if current_col < 0:
            current_col = len(self._pipeline_wrapper.current_segments) - 1
        
        prev_col = max(0, current_col - 1)
        if prev_col != current_col:
            self._sample_table.setCurrentCell(0, prev_col)
            self._on_sample_selected(prev_col)

    def _on_player_loop_changed(self, enabled: bool) -> None:
        """Handle player loop state change.

        Args:
            enabled: True if looping enabled.
        """
        # Store loop state for playback
        self._loop_enabled = enabled
    
    def _on_media_position_changed(self, position: int) -> None:
        """Handle media player position change.
        
        Args:
            position: Position in milliseconds.
        """
        # Use player widget's duration if available (from actual segment), otherwise fall back to media player duration
        duration = self._media_player.duration()
        if hasattr(self._sample_player, '_duration') and self._sample_player._duration > 0:
            duration = self._sample_player._duration
        if duration > 0:
            self._sample_player.set_position(position, duration)
    
    def _on_media_duration_changed(self, duration: int) -> None:
        """Handle media player duration change.
        
        Args:
            duration: Duration in milliseconds.
        """
        # Use player widget's duration if available (from actual segment), otherwise fall back to media player duration
        if hasattr(self._sample_player, '_duration') and self._sample_player._duration > 0:
            duration = self._sample_player._duration
        if duration > 0:
            self._sample_player.set_position(self._media_player.position(), duration)
    
    def _on_player_seek_requested(self, position_ms: int) -> None:
        """Handle player seek request.
        
        Args:
            position_ms: Position to seek to in milliseconds.
        """
        if self._media_player.duration() > 0:
            # Clamp position to valid range
            position_ms = max(0, min(position_ms, self._media_player.duration()))
            self._media_player.setPosition(position_ms)
            # If paused, update the paused position so resume uses the new scrubbed position
            if self._is_paused:
                self._paused_position = position_ms

    def _on_sample_table_changed(self, item: QTableWidgetItem) -> None:
        """Handle sample table change.

        Args:
            item: Changed item.
        """
        # Handle changes only for the Enable row (row 0)
        try:
            row = item.row()
            col = item.column()
        except Exception:
            return
        if row != 0 or not self._pipeline_wrapper:
            return
        segments = self._pipeline_wrapper.current_segments
        if 0 <= col < len(segments):
            seg = segments[col]
            enabled = item.checkState() == Qt.CheckState.Checked
            if not hasattr(seg, "attrs") or seg.attrs is None:
                seg.attrs = {}
            seg.attrs["enabled"] = enabled
            # Refresh views using enabled filter
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_navigator_markers()

    def _on_play_button_clicked(self, index: int) -> None:
        """Handle play button click.

        Args:
            index: Sample index.
        """
        self._on_sample_play_requested(index)

    def _on_delete_button_clicked(self, index: int) -> None:
        """Handle delete button click.

        Args:
            index: Sample index.
        """
        self._on_sample_deleted(index)

    def _on_center_clicked(self, index: int) -> None:
        """Center the selected sample in the main editor without changing zoom."""
        if not self._pipeline_wrapper:
            return
        segments = self._pipeline_wrapper.current_segments
        if not (0 <= index < len(segments)):
            return
        seg = segments[index]
        center = (seg.start + seg.end) / 2.0
        # Maintain current view duration
        view_duration = max(0.01, self._spectrogram_widget._end_time - self._spectrogram_widget._start_time)
        total = max(0.0, self._spectrogram_widget._duration)
        new_start = max(0.0, min(center - (view_duration / 2.0), max(0.0, total - view_duration)))
        new_end = new_start + view_duration
        self._spectrogram_widget.set_time_range(new_start, new_end)
        self._navigator.set_view_range(new_start, new_end)

    def _on_fill_clicked(self, index: int) -> None:
        """Zoom so the sample fills the editor with a small margin, then center."""
        if not self._pipeline_wrapper:
            return
        segments = self._pipeline_wrapper.current_segments
        if not (0 <= index < len(segments)):
            return
        seg = segments[index]
        seg_dur = max(0.01, seg.end - seg.start)
        # Margin is 5% of duration, clamped to [0.05s, 1.0s]
        margin = max(0.05, min(1.0, seg_dur * 0.05))
        desired_start = max(0.0, seg.start - margin)
        desired_end = seg.end + margin
        total = max(0.0, self._spectrogram_widget._duration)
        desired_end = min(desired_end, total)
        # Ensure non-empty
        if desired_end <= desired_start:
            desired_end = min(total, desired_start + seg_dur + 2 * margin)
        self._spectrogram_widget.set_time_range(desired_start, desired_end)
        self._navigator.set_view_range(desired_start, desired_end)

    def _update_sample_table(self, segments: list[Segment]) -> None:
        """Update sample table.

        Args:
            segments: List of segments.
        """
        self._sample_table.setColumnCount(len(segments))
        
        # Set column headers to sample IDs
        column_headers = [str(i) for i in range(len(segments))]
        self._sample_table.setHorizontalHeaderLabels(column_headers)

        for i, seg in enumerate(segments):
            # Ensure enabled flag exists (default True)
            if not hasattr(seg, "attrs") or seg.attrs is None:
                seg.attrs = {}
            if "enabled" not in seg.attrs:
                seg.attrs["enabled"] = True

            # Enable checkbox (row 0)
            checkbox = QTableWidgetItem()
            checkbox.setCheckState(Qt.CheckState.Checked if seg.attrs.get("enabled", True) else Qt.CheckState.Unchecked)
            checkbox.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sample_table.setItem(0, i, checkbox)

            # Center/Fill composite cell (row 1)
            from PySide6.QtWidgets import QWidget as _QW, QHBoxLayout as _QHBox
            cell = _QW()
            layout = _QHBox()
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(6)
            center_button = QPushButton("Center")
            center_button.clicked.connect(lambda checked, idx=i: self._on_center_clicked(idx))
            fill_button = QPushButton("Fill")
            fill_button.clicked.connect(lambda checked, idx=i: self._on_fill_clicked(idx))
            layout.addWidget(center_button)
            layout.addWidget(fill_button)
            cell.setLayout(layout)
            self._sample_table.setCellWidget(1, i, cell)

            # Start (row 2)
            start_item = QTableWidgetItem(f"{seg.start:.3f}")
            start_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sample_table.setItem(2, i, start_item)

            # End (row 3)
            end_item = QTableWidgetItem(f"{seg.end:.3f}")
            end_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sample_table.setItem(3, i, end_item)

            # Duration (row 4)
            duration_item = QTableWidgetItem(f"{seg.duration():.3f}")
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sample_table.setItem(4, i, duration_item)

            # Detector (row 5)
            detector_item = QTableWidgetItem(seg.detector)
            detector_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sample_table.setItem(5, i, detector_item)

            # Play button (row 6)
            play_button = QPushButton("▶")
            play_button.clicked.connect(lambda checked, idx=i: self._on_play_button_clicked(idx))
            self._sample_table.setCellWidget(6, i, play_button)

            # Delete button (row 7)
            delete_button = QPushButton("×")
            delete_button.clicked.connect(lambda checked, idx=i: self._on_delete_button_clicked(idx))
            self._sample_table.setCellWidget(7, i, delete_button)

        # Auto-resize columns to fit content
        self._sample_table.resizeColumnsToContents()

    def _on_zoom_in(self) -> None:
        """Handle zoom in."""
        self._spectrogram_widget.set_zoom_level(self._spectrogram_widget._zoom_level * 1.5)

    def _on_zoom_out(self) -> None:
        """Handle zoom out."""
        self._spectrogram_widget.set_zoom_level(self._spectrogram_widget._zoom_level / 1.5)

    def _on_fit_to_window(self) -> None:
        """Handle fit to window."""
        if self._spectrogram_widget._duration > 0:
            view_duration = self._spectrogram_widget._end_time - self._spectrogram_widget._start_time
            zoom = self._spectrogram_widget._duration / view_duration
            self._spectrogram_widget.set_zoom_level(zoom)

    def _on_toggle_info_table(self) -> None:
        """Handle toggle info table visibility."""
        sizes = self._main_splitter.sizes()
        if sizes[1] == 0:  # Info table is collapsed
            # Restore info table
            self._main_splitter.setSizes([sizes[0], self._info_table_initial_size])
            self._hide_info_action.setChecked(False)
        else:
            # Collapse info table
            self._info_table_initial_size = sizes[1]  # Store current size
            self._main_splitter.setSizes([sizes[0], 0])
            self._hide_info_action.setChecked(True)

    def _on_toggle_player(self) -> None:
        """Handle toggle player visibility."""
        sizes = self._player_spectro_splitter.sizes()
        if sizes[0] == 0:  # Player is collapsed
            # Restore player
            self._player_spectro_splitter.setSizes([self._player_initial_size, sizes[1]])
            self._hide_player_action.setChecked(False)
        else:
            # Collapse player
            self._player_initial_size = sizes[0]  # Store current size
            self._player_spectro_splitter.setSizes([0, sizes[1]])
            self._hide_player_action.setChecked(True)

    def _on_delete_all_samples(self) -> None:
        """Delete all samples."""
        if not self._pipeline_wrapper:
            return
        self._push_undo_state()
        self._pipeline_wrapper.current_segments.clear()
        self._spectrogram_widget.set_segments([])
        self._update_sample_table([])
        self._update_navigator_markers()

    def _on_reorder_samples(self) -> None:
        """Manually reorder samples chronologically."""
        if not self._pipeline_wrapper:
            return
        self._pipeline_wrapper.current_segments.sort(key=lambda s: s.start)
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_sample_table(self._pipeline_wrapper.current_segments)
        self._update_navigator_markers()

    def _on_toggle_auto_order(self, enabled: bool) -> None:
        """Toggle Auto Sample Order and update dependent UI state."""
        # Disable manual reorder when auto is enabled
        if hasattr(self, "_reorder_action"):
            self._reorder_action.setEnabled(not enabled)
        # If enabling auto-order, immediately enforce ordering
        if enabled and self._pipeline_wrapper:
            self._pipeline_wrapper.current_segments.sort(key=lambda s: s.start)
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_sample_table(self._pipeline_wrapper.current_segments)
            self._update_navigator_markers()

    def _on_info_splitter_moved(self, pos: int, index: int) -> None:
        """Handle info table splitter moved (manual resize).
        
        Args:
            pos: Splitter position.
            index: Splitter index.
        """
        sizes = self._main_splitter.sizes()
        # Update menu action checked state based on visibility
        self._hide_info_action.setChecked(sizes[1] == 0)
        if sizes[1] > 0:
            self._info_table_initial_size = sizes[1]  # Update stored size

    def _on_player_splitter_moved(self, pos: int, index: int) -> None:
        """Handle player splitter moved (manual resize).
        
        Args:
            pos: Splitter position.
            index: Splitter index.
        """
        sizes = self._player_spectro_splitter.sizes()
        # Update menu action checked state based on visibility
        self._hide_player_action.setChecked(sizes[0] == 0)
        if sizes[0] > 0:
            self._player_initial_size = sizes[0]  # Update stored size

    def _on_disable_all_samples(self) -> None:
        """Disable all samples (set enabled=False)."""
        if not self._pipeline_wrapper:
            return
        for s in self._pipeline_wrapper.current_segments:
            if not hasattr(s, "attrs") or s.attrs is None:
                s.attrs = {}
            s.attrs["enabled"] = False
        self._update_sample_table(self._pipeline_wrapper.current_segments)
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_navigator_markers()

    def _on_toggle_show_disabled(self, show: bool) -> None:
        """Toggle visibility of disabled samples in views."""
        self._spectrogram_widget.set_show_disabled(show)
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_navigator_markers()

    def _on_disable_sample(self, index: int, disabled: bool) -> None:
        """Disable/enable single sample from context menu."""
        if not self._pipeline_wrapper:
            return
        if 0 <= index < len(self._pipeline_wrapper.current_segments):
            seg = self._pipeline_wrapper.current_segments[index]
            if not hasattr(seg, "attrs") or seg.attrs is None:
                seg.attrs = {}
            seg.attrs["enabled"] = not (not disabled) if False else (not disabled)  # keep explicit assignment
            seg.attrs["enabled"] = (not disabled) is False and False or (not disabled)  # overwrite to ensure bool
            seg.attrs["enabled"] = (False if disabled else True)
            # Sync table checkbox
            item = self._sample_table.item(0, index)
            if item:
                item.setCheckState(Qt.CheckState.Checked if seg.attrs["enabled"] else Qt.CheckState.Unchecked)
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_navigator_markers()

    def _on_disable_other_samples(self, index: int) -> None:
        """Disable all samples except the given index."""
        if not self._pipeline_wrapper:
            return
        for i, s in enumerate(self._pipeline_wrapper.current_segments):
            if not hasattr(s, "attrs") or s.attrs is None:
                s.attrs = {}
            s.attrs["enabled"] = (i == index)
            # Sync table checkbox
            item = self._sample_table.item(0, i)
            if item:
                item.setCheckState(Qt.CheckState.Checked if s.attrs["enabled"] else Qt.CheckState.Unchecked)
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_navigator_markers()

    def _on_export_samples(self) -> None:
        """Handle export samples action."""
        if not self._pipeline_wrapper or not self._pipeline_wrapper.current_segments:
            QMessageBox.warning(self, "No Samples", "No samples to export. Please process preview first.")
            return

        # Get output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")

        if output_dir:
            # Get selected indices (checkboxes are in row 0, one per column)
            selected_indices = []
            for i in range(self._sample_table.columnCount()):
                item = self._sample_table.item(0, i)
                if item and item.checkState() == Qt.CheckState.Checked:
                    selected_indices.append(i)

            if not selected_indices:
                QMessageBox.warning(self, "No Selection", "Please select samples to export.")
                return

            # Export samples
            try:
                count = self._pipeline_wrapper.export_samples(Path(output_dir), selected_indices)
                QMessageBox.information(self, "Export Complete", f"Exported {count} samples to:\n{output_dir}")
                self._status_label.setText(f"Exported {count} samples")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export samples:\n{str(e)}")

    def _on_about(self) -> None:
        """Handle about action."""
        QMessageBox.about(
            self,
            "About SamplePacker",
            "SamplePacker GUI\n\nTurn long field recordings into usable sample packs.",
        )

    def _on_toggle_verbose_log(self, enabled: bool) -> None:
        """Toggle verbose logging level between DEBUG and INFO."""
        try:
            import logging
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.DEBUG if enabled else logging.INFO)
            for handler in root_logger.handlers:
                handler.setLevel(logging.DEBUG if enabled else logging.INFO)
            if hasattr(self, "_status_label"):
                self._status_label.setText("Verbose Log: ON" if enabled else "Verbose Log: OFF")
        except Exception as e:
            logger.error(f"Failed to toggle verbose log: {e}")

    def _push_undo_state(self) -> None:
        """Push current segments state to undo stack."""
        if not self._pipeline_wrapper:
            return
        
        # Create deep copy of current segments
        segments_copy = copy.deepcopy(self._pipeline_wrapper.current_segments)
        
        # Push to undo stack
        self._undo_stack.append(segments_copy)
        
        # Limit stack size
        if len(self._undo_stack) > self._max_undo_stack_size:
            self._undo_stack.pop(0)
        
        # Clear redo stack when new action is performed
        self._redo_stack.clear()
        
        # Update menu action states
        self._update_undo_redo_actions()

    def _undo(self) -> None:
        """Undo last action."""
        if not self._undo_stack or not self._pipeline_wrapper:
            return
        
        # Push current state to redo stack
        current_segments = copy.deepcopy(self._pipeline_wrapper.current_segments)
        self._redo_stack.append(current_segments)
        
        # Pop from undo stack and restore
        previous_segments = self._undo_stack.pop()
        self._pipeline_wrapper.current_segments = copy.deepcopy(previous_segments)
        
        # Update UI
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_sample_table(self._pipeline_wrapper.current_segments)
        self._update_navigator_markers()
        
        # Update menu action states
        self._update_undo_redo_actions()

    def _redo(self) -> None:
        """Redo last undone action."""
        if not self._redo_stack or not self._pipeline_wrapper:
            return
        
        # Push current state to undo stack
        current_segments = copy.deepcopy(self._pipeline_wrapper.current_segments)
        self._undo_stack.append(current_segments)
        
        # Limit stack size
        if len(self._undo_stack) > self._max_undo_stack_size:
            self._undo_stack.pop(0)
        
        # Pop from redo stack and restore
        next_segments = self._redo_stack.pop()
        self._pipeline_wrapper.current_segments = copy.deepcopy(next_segments)
        
        # Update UI
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_sample_table(self._pipeline_wrapper.current_segments)
        self._update_navigator_markers()
        
        # Update menu action states
        self._update_undo_redo_actions()

    def _update_undo_redo_actions(self) -> None:
        """Update undo/redo action enabled states."""
        self._undo_action.setEnabled(len(self._undo_stack) > 0)
        self._redo_action.setEnabled(len(self._redo_stack) > 0)

    def _on_sample_drag_started(self, index: int) -> None:
        """Handle sample drag started.
        
        Args:
            index: Sample index.
        """
        self._push_undo_state()

    def _on_sample_resize_started(self, index: int) -> None:
        """Handle sample resize started.
        
        Args:
            index: Sample index.
        """
        self._push_undo_state()

    def _on_sample_create_started(self) -> None:
        """Handle sample creation started."""
        self._push_undo_state()

    def _get_segment_color(self, detector: str) -> Any:
        """Get color for detector type.

        Args:
            detector: Detector name.

        Returns:
            QColor object.
        """
        from PySide6.QtGui import QColor

        color_map = {
            "voice_vad": QColor(0x00, 0xFF, 0xAA),
            "transient_flux": QColor(0xFF, 0xCC, 0x00),
            "nonsilence_energy": QColor(0xFF, 0x66, 0xAA),
            "spectral_interestingness": QColor(0x66, 0xAA, 0xFF),
        }
        return color_map.get(detector, QColor(0xFF, 0xFF, 0xFF))

    def _get_enabled_segments(self) -> list[Segment]:
        """Return only enabled segments from current pipeline wrapper.

        Returns:
            List of enabled segments.
        """
        if not self._pipeline_wrapper:
            return []
        result: list[Segment] = []
        for s in self._pipeline_wrapper.current_segments:
            if not hasattr(s, "attrs") or s.attrs is None:
                s.attrs = {}
            if s.attrs.get("enabled", True):
                result.append(s)
        return result

    def _get_display_segments(self) -> list[Segment]:
        """Return segments list respecting show-disabled toggle.

        When showing disabled, return all segments; otherwise only enabled.
        """
        show_disabled = getattr(self, "_show_disabled_action", None) is None or self._show_disabled_action.isChecked()
        if show_disabled:
            return list(self._pipeline_wrapper.current_segments) if self._pipeline_wrapper else []
        return self._get_enabled_segments()

    def _maybe_auto_reorder(self) -> None:
        """Re-order samples by start if Auto Sample Order is enabled."""
        try:
            if getattr(self, "_auto_order_action", None) and self._auto_order_action.isChecked() and self._pipeline_wrapper:
                self._pipeline_wrapper.current_segments.sort(key=lambda s: s.start)
        except Exception:
            pass

    # Export menu handlers
    def _on_export_pre_pad_settings(self) -> None:
        """Handle export pre-padding settings dialog."""
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getDouble(
            self, "Export Pre-padding", "Pre-padding (ms):", self._export_pre_pad_ms, 0.0, 50000.0, 0
        )
        if ok:
            self._export_pre_pad_ms = value
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.export_pre_pad_ms = value

    def _on_export_post_pad_settings(self) -> None:
        """Handle export post-padding settings dialog."""
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getDouble(
            self, "Export Post-padding", "Post-padding (ms):", self._export_post_pad_ms, 0.0, 50000.0, 0
        )
        if ok:
            self._export_post_pad_ms = value
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.export_post_pad_ms = value

    def _on_export_format_changed(self, format: str) -> None:
        """Handle export format change."""
        self._export_format = format
        # Update action states
        self._export_format_wav_action.setChecked(format == "wav")
        self._export_format_flac_action.setChecked(format == "flac")
        # Update settings if pipeline wrapper exists
        if self._pipeline_wrapper:
            self._pipeline_wrapper.settings.format = format

    def _on_export_sample_rate_settings(self) -> None:
        """Handle export sample rate settings dialog."""
        from PySide6.QtWidgets import QInputDialog
        current = self._export_sample_rate if self._export_sample_rate else 0
        value, ok = QInputDialog.getInt(
            self, "Export Sample Rate", "Sample rate (Hz, 0 for original):", current, 0, 192000, 0
        )
        if ok:
            self._export_sample_rate = value if value > 0 else None
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.sample_rate = self._export_sample_rate

    def _on_export_bit_depth_settings(self) -> None:
        """Handle export bit depth settings dialog."""
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        options = ["16", "24", "32f", "None (original)"]
        current_index = 0
        if self._export_bit_depth:
            try:
                current_index = options.index(self._export_bit_depth)
            except ValueError:
                current_index = 0
        else:
            current_index = 3  # None
        value, ok = QInputDialog.getItem(
            self, "Export Bit Depth", "Bit depth:", options, current_index, False
        )
        if ok:
            if value == "None (original)":
                self._export_bit_depth = None
            else:
                self._export_bit_depth = value
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.bit_depth = self._export_bit_depth

    def _on_export_channels_settings(self) -> None:
        """Handle export channels settings dialog."""
        from PySide6.QtWidgets import QInputDialog
        options = ["mono", "stereo", "None (original)"]
        current_index = 0
        if self._export_channels:
            try:
                current_index = options.index(self._export_channels)
            except ValueError:
                current_index = 0
        else:
            current_index = 2  # None
        value, ok = QInputDialog.getItem(
            self, "Export Channels", "Channels:", options, current_index, False
        )
        if ok:
            if value == "None (original)":
                self._export_channels = None
            else:
                self._export_channels = value
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.channels = self._export_channels

    # UI refresh rate handlers
    def _on_ui_refresh_rate_enabled_changed(self, enabled: bool) -> None:
        """Handle UI refresh rate limit toggle."""
        self._ui_refresh_rate_enabled = enabled
        if enabled:
            self._setup_refresh_timer()
        else:
            if self._ui_refresh_timer:
                self._ui_refresh_timer.stop()
                self._ui_refresh_timer = None
            # Apply all pending updates
            self._apply_pending_updates()

    def _on_refresh_rate_changed(self, rate: int) -> None:
        """Handle refresh rate change."""
        self._ui_refresh_rate_hz = rate
        # Update action states
        for r, action in self._refresh_rate_actions.items():
            action.setChecked(r == rate)
        # Restart timer if enabled
        if self._ui_refresh_rate_enabled:
            self._setup_refresh_timer()

    def _setup_refresh_timer(self) -> None:
        """Setup UI refresh timer."""
        from PySide6.QtCore import QTimer
        if self._ui_refresh_timer:
            self._ui_refresh_timer.stop()
        interval_ms = int(1000 / self._ui_refresh_rate_hz)
        self._ui_refresh_timer = QTimer(self)
        self._ui_refresh_timer.timeout.connect(self._apply_pending_updates)
        self._ui_refresh_timer.start(interval_ms)

    def _apply_pending_updates(self) -> None:
        """Apply pending UI updates."""
        # This will be called by the timer or directly when throttling is disabled
        # For now, we'll implement a simple approach - update spectrogram widget
        if hasattr(self, "_spectrogram_widget") and self._spectrogram_widget:
            # Force update of spectrogram widget
            self._spectrogram_widget.update()
        self._pending_updates.clear()

    # Grid settings handlers
    def _on_grid_mode_changed(self) -> None:
        """Handle grid mode change."""
        if self._grid_mode_free_action.isChecked():
            self._grid_settings.mode = GridMode.FREE_TIME
            self._grid_mode_musical_action.setChecked(False)
        elif self._grid_mode_musical_action.isChecked():
            self._grid_settings.mode = GridMode.MUSICAL_BAR
            self._grid_mode_free_action.setChecked(False)
        self._on_settings_changed()

    def _on_snap_interval_settings(self) -> None:
        """Handle snap interval settings dialog."""
        from PySide6.QtWidgets import QInputDialog
        value_ms = int(self._grid_settings.snap_interval_sec * 1000)
        value_ms, ok = QInputDialog.getInt(
            self, "Snap Interval", "Snap interval (ms):", value_ms, 1, 10000, 0
        )
        if ok:
            self._grid_settings.snap_interval_sec = value_ms / 1000.0
            self._on_settings_changed()

    def _on_bpm_settings(self) -> None:
        """Handle BPM settings dialog."""
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getInt(
            self, "BPM", "BPM:", int(self._grid_settings.bpm), 60, 200, 0
        )
        if ok:
            self._grid_settings.bpm = float(value)
            self._on_settings_changed()

    def _on_subdivision_changed(self, subdivision: str) -> None:
        """Handle subdivision change."""
        subdivision_map = {
            "Whole": Subdivision.WHOLE,
            "Half": Subdivision.HALF,
            "Quarter": Subdivision.QUARTER,
            "Eighth": Subdivision.EIGHTH,
            "Sixteenth": Subdivision.SIXTEENTH,
            "Thirty-second": Subdivision.THIRTY_SECOND,
        }
        self._grid_settings.subdivision = subdivision_map.get(subdivision, Subdivision.QUARTER)
        # Update action states
        for sub, action in self._subdivision_actions.items():
            action.setChecked(sub == subdivision)
        self._on_settings_changed()

    def _on_grid_visible_changed(self, checked: bool) -> None:
        """Handle grid visibility change."""
        self._grid_settings.visible = checked
        self._on_settings_changed()

    def _on_snap_enabled_changed(self, checked: bool) -> None:
        """Handle snap enabled change."""
        self._grid_settings.enabled = checked
        self._on_settings_changed()

