"""Main window for SpectroSampler GUI."""

import copy
import logging
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from spectrosampler.audio_io import FFmpegError
from spectrosampler.detectors.base import Segment
from spectrosampler.gui.autosave import AutoSaveManager
from spectrosampler.gui.detection_manager import DetectionManager
from spectrosampler.gui.detection_settings import DetectionSettingsPanel
from spectrosampler.gui.grid_manager import GridManager, GridMode, GridSettings, Subdivision
from spectrosampler.gui.loading_screen import LoadingScreen
from spectrosampler.gui.navigator_scrollbar import NavigatorScrollbar
from spectrosampler.gui.overview_manager import OverviewManager
from spectrosampler.gui.pipeline_wrapper import PipelineWrapper
from spectrosampler.gui.project import (
    ProjectData,
    _dict_to_grid_settings,
    _dict_to_processing_settings,
    _dict_to_segment,
    _grid_settings_to_dict,
    _processing_settings_to_dict,
    _segment_to_dict,
    load_project,
    save_project,
)
from spectrosampler.gui.sample_player import SamplePlayerWidget
from spectrosampler.gui.sample_table_delegate import SampleTableDelegate
from spectrosampler.gui.sample_table_model import SampleTableModel
from spectrosampler.gui.settings import SettingsManager
from spectrosampler.gui.spectrogram_tiler import SpectrogramTile, SpectrogramTiler
from spectrosampler.gui.spectrogram_widget import SpectrogramWidget
from spectrosampler.gui.theme import ThemeManager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main window for SpectroSampler GUI."""

    def __init__(self, parent: QWidget | None = None):
        """Initialize main window.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        # Pipeline wrapper
        self._pipeline_wrapper: PipelineWrapper | None = None
        self._current_audio_path: Path | None = None

        # Project management
        self._project_path: Path | None = None
        self._project_modified: bool = False

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
        self._media_status_handler: Callable[[QMediaPlayer.MediaStatus], None] | None = None

        # Undo/redo stacks
        self._undo_stack: list[list[Segment]] = []
        self._redo_stack: list[list[Segment]] = []
        self._max_undo_stack_size = 50
        self._baseline_segments: list[Segment] = []  # Initial state after load/save

        # Detection manager
        self._detection_manager = DetectionManager(self)
        self._detection_manager.progress.connect(self._on_detection_progress)
        self._detection_manager.finished.connect(self._on_detection_finished)
        self._detection_manager.error.connect(self._on_detection_error)

        # Spectrogram tiler
        self._tiler = SpectrogramTiler()

        # Grid manager
        self._grid_manager = GridManager()

        # Overview manager (for background spectrogram overview generation)
        self._overview_manager = OverviewManager(self)
        self._overview_manager.progress.connect(self._on_overview_progress)
        self._overview_manager.finished.connect(self._on_overview_finished)
        self._overview_manager.error.connect(self._on_overview_error)

        # Settings manager
        self._settings_manager = SettingsManager()

        # Theme manager / preference
        self._theme_manager = ThemeManager(self)
        self._theme_actions: dict[str, QAction] = {}
        self._theme_action_group: QActionGroup | None = None
        self._theme_mode = self._settings_manager.get_theme_preference()
        self._theme_manager.apply_theme(self._theme_mode)

        # Auto-save manager
        self._autosave_manager = AutoSaveManager(self)
        self._autosave_manager.set_project_data_callback(self._collect_project_data)
        self._autosave_manager.set_project_modified_callback(lambda: self._project_modified)
        self._autosave_manager.autosave_error.connect(self._on_autosave_error)

        # Setup UI
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()

        # Loading screen
        self._loading_screen = LoadingScreen(self, "Loading...", self._theme_manager)

        # Setup auto-save (if enabled)
        self._setup_autosave()

        # Restore window geometry
        self._restore_window_geometry()

        # Apply theme
        self._apply_theme_mode(self._theme_mode, persist=False)

        # Connect signals
        self._connect_signals()

        # Setup UI refresh timer if enabled
        if self._ui_refresh_rate_enabled:
            self._setup_refresh_timer()

        # Update window title
        self._update_window_title()

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
        self._grid_settings.enabled = False

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
        self._pending_updates: dict[str, object] = {}
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
        self._spectrogram_widget.sample_disable_requested.connect(
            lambda idx, dis: self._on_disable_sample(idx, dis)
        )
        self._spectrogram_widget.sample_disable_others_requested.connect(
            self._on_disable_other_samples
        )
        self._spectrogram_widget.sample_center_requested.connect(self._on_center_clicked)
        self._spectrogram_widget.sample_center_fill_requested.connect(self._on_fill_clicked)
        # Keep navigator highlight synced to editor zoom/pan
        self._spectrogram_widget.view_changed.connect(
            lambda s, e: self._navigator.set_view_range(s, e)
        )

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
        self._navigator: NavigatorScrollbar = NavigatorScrollbar()
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

        # Sample list (bottom) - QTableView with model/delegate
        self._sample_table_view = QTableView()
        self._sample_table_model = SampleTableModel(self)
        self._sample_table_view.setModel(self._sample_table_model)
        self._sample_table_delegate = SampleTableDelegate(self)
        self._sample_table_view.setItemDelegate(self._sample_table_delegate)
        # Selection: columns
        self._sample_table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectColumns)
        self._sample_table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        # Policies
        self._sample_table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._sample_table_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Sizing: fixed column width and uniform row heights
        try:
            self._sample_table_view.verticalHeader().setDefaultSectionSize(30)
        except (AttributeError, RuntimeError) as exc:
            logger.debug("Unable to set sample table row height: %s", exc, exc_info=exc)
        fixed_col_width = 140
        # Apply a default for first few columns; more columns will use the same width
        try:
            self._sample_table_view.horizontalHeader().setDefaultSectionSize(fixed_col_width)
        except (AttributeError, RuntimeError) as exc:
            logger.debug("Unable to set sample table column width: %s", exc, exc_info=exc)
        # Calculate height: header + 8 rows * 30 + scrollbar height + small margin
        try:
            scrollbar_h = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        except RuntimeError:
            scrollbar_h = 18
        table_height = (
            self._sample_table_view.horizontalHeader().height() + (8 * 30) + scrollbar_h + 12
        )
        self._sample_table_view.setMinimumHeight(table_height)
        # Wire delegate signals
        self._sample_table_delegate.centerClicked.connect(self._on_center_clicked)
        self._sample_table_delegate.fillClicked.connect(self._on_fill_clicked)
        self._sample_table_delegate.playClicked.connect(self._on_sample_play_requested)
        self._sample_table_delegate.deleteClicked.connect(self._on_sample_deleted)
        # Model change signals to update other views
        self._sample_table_model.enabledToggled.connect(self._on_model_enabled_toggled)
        self._sample_table_model.timesEdited.connect(self._on_model_times_edited)
        self._sample_table_model.durationEdited.connect(self._on_model_duration_edited)

        # Keep spectrogram selection in sync when user selects a column
        def on_selection_changed(_selected, _deselected):
            idx = self._sample_table_view.currentIndex()
            if idx.isValid():
                self._on_sample_selected(idx.column())

        self._sample_table_view.selectionModel().selectionChanged.connect(on_selection_changed)

        # Main vertical splitter for editor/sample table
        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.addWidget(splitter)
        self._main_splitter.addWidget(self._sample_table_view)
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

        # New Project
        new_project_action = QAction("&New Project", self)
        new_project_action.setShortcut(QKeySequence.StandardKey.New)
        new_project_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_project_action)

        # Open Project
        open_project_action = QAction("&Open Project...", self)
        open_project_action.setShortcut(QKeySequence("Ctrl+O"))
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)

        # Recent Projects submenu
        self._recent_projects_menu = file_menu.addMenu("Recent &Projects")
        self._recent_projects_menu.aboutToShow.connect(self._update_recent_files_menu)
        self._clear_recent_projects_action = QAction("Clear Recent Projects", self)
        self._clear_recent_projects_action.triggered.connect(self._on_clear_recent_projects)

        # Recent Audio Files submenu
        self._recent_audio_files_menu = file_menu.addMenu("Recent &Audio Files")
        self._recent_audio_files_menu.aboutToShow.connect(self._update_recent_files_menu)
        self._clear_recent_audio_files_action = QAction("Clear Recent Audio Files", self)
        self._clear_recent_audio_files_action.triggered.connect(self._on_clear_recent_audio_files)

        file_menu.addSeparator()

        # Save Project
        save_project_action = QAction("&Save Project", self)
        save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        save_project_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_project_action)

        # Save Project As
        save_project_as_action = QAction("Save Project &As...", self)
        save_project_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_project_as_action.triggered.connect(self._on_save_project_as)
        file_menu.addAction(save_project_as_action)

        file_menu.addSeparator()

        # Open Audio File
        open_action = QAction("Open &Audio File...", self)
        open_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_action = QAction("&Export Samples...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
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
        self._export_format_wav_action.triggered.connect(
            lambda: self._on_export_format_changed("wav")
        )
        format_menu.addAction(self._export_format_wav_action)

        self._export_format_flac_action = QAction("&FLAC", self)
        self._export_format_flac_action.setCheckable(True)
        self._export_format_flac_action.triggered.connect(
            lambda: self._on_export_format_changed("flac")
        )
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

        edit_menu.addSeparator()

        # Duration Edits mode
        duration_edits_menu = edit_menu.addMenu("&Duration Edits")
        self._duration_edit_mode = "expand_contract"  # Default mode
        self._duration_edit_actions = {}

        expand_contract_action = QAction("&Expand/Contract", self)
        expand_contract_action.setCheckable(True)
        expand_contract_action.setChecked(True)
        expand_contract_action.triggered.connect(
            lambda: self._on_duration_edit_mode_changed("expand_contract")
        )
        duration_edits_menu.addAction(expand_contract_action)
        self._duration_edit_actions["expand_contract"] = expand_contract_action

        extend_from_start_action = QAction("Extend/Shorten (&From Start)", self)
        extend_from_start_action.setCheckable(True)
        extend_from_start_action.triggered.connect(
            lambda: self._on_duration_edit_mode_changed("from_start")
        )
        duration_edits_menu.addAction(extend_from_start_action)
        self._duration_edit_actions["from_start"] = extend_from_start_action

        extend_from_end_action = QAction("Extend/Shorten (From &End)", self)
        extend_from_end_action.setCheckable(True)
        extend_from_end_action.triggered.connect(
            lambda: self._on_duration_edit_mode_changed("from_end")
        )
        duration_edits_menu.addAction(extend_from_end_action)
        self._duration_edit_actions["from_end"] = extend_from_end_action

        # Add Lock Duration on Start Edit toggle (default ON)
        edit_menu.addSeparator()
        self._lock_duration_on_start_edit_action = QAction("Lock &Duration on Start Edit", self)
        self._lock_duration_on_start_edit_action.setCheckable(True)
        self._lock_duration_on_start_edit_action.setChecked(True)
        edit_menu.addAction(self._lock_duration_on_start_edit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        theme_menu = view_menu.addMenu("&Theme")
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusive(True)

        theme_options = [
            ("system", "&System"),
            ("dark", "&Dark"),
            ("light", "&Light"),
        ]

        for mode, label in theme_options:
            action = QAction(label, self)
            action.setCheckable(True)
            action.toggled.connect(
                lambda checked, m=mode: self._on_theme_mode_selected(m) if checked else None
            )
            theme_menu.addAction(action)
            self._theme_action_group.addAction(action)
            self._theme_actions[mode] = action

        self._update_theme_menu_checks()

        view_menu.addSeparator()

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
        self._ui_refresh_rate_enabled_action.toggled.connect(
            self._on_ui_refresh_rate_enabled_changed
        )
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
        self._snap_enabled_action.setChecked(False)
        self._snap_enabled_action.toggled.connect(self._on_snap_enabled_changed)
        grid_menu.addAction(self._snap_enabled_action)

        # Help menu
        # Settings menu
        settings_menu = menubar.addMenu("&Settings")

        # Auto-save settings
        autosave_menu = settings_menu.addMenu("&Auto-save")
        self._autosave_enabled_action = QAction("Enable Auto-save", self)
        self._autosave_enabled_action.setCheckable(True)
        self._autosave_enabled_action.setChecked(self._settings_manager.get_auto_save_enabled())
        self._autosave_enabled_action.toggled.connect(self._on_autosave_enabled_changed)
        autosave_menu.addAction(self._autosave_enabled_action)

        autosave_interval_action = QAction("Auto-save &Interval...", self)
        autosave_interval_action.triggered.connect(self._on_autosave_interval_settings)
        autosave_menu.addAction(autosave_interval_action)

        settings_menu.addSeparator()

        # Recent files management
        clear_recent_projects_menu_action = QAction("Clear &Recent Projects", self)
        clear_recent_projects_menu_action.triggered.connect(self._on_clear_recent_projects)
        settings_menu.addAction(clear_recent_projects_menu_action)

        clear_recent_audio_files_menu_action = QAction("Clear Recent &Audio Files", self)
        clear_recent_audio_files_menu_action.triggered.connect(self._on_clear_recent_audio_files)
        settings_menu.addAction(clear_recent_audio_files_menu_action)

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

        # Disable size grip to have full control over layout
        self._status_bar.setSizeGripEnabled(False)

        # Remove separator lines via stylesheet
        self._status_bar.setStyleSheet("QStatusBar::item { border: none; }")

        # Status label - left half with stretch
        self._status_label = QLabel("Ready")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Use addWidget with stretch to fill left half
        self._status_bar.addWidget(self._status_label, stretch=1)

        # Progress bar - right half
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMinimumWidth(100)  # Minimum width for visibility
        # Use addPermanentWidget for right side, but we'll control sizing via stretch
        # Note: addPermanentWidget doesn't support stretch directly, so we'll use addWidget instead
        self._status_bar.addWidget(self._progress_bar, stretch=1)

    def _connect_signals(self) -> None:
        """Connect signals."""
        # Settings panel
        self._settings_panel.settings_changed.connect(self._on_settings_changed)

        # Spectrogram widget - operation start signals for undo
        self._spectrogram_widget.sample_drag_started.connect(self._on_sample_drag_started)
        self._spectrogram_widget.sample_resize_started.connect(self._on_sample_resize_started)
        self._spectrogram_widget.sample_create_started.connect(self._on_sample_create_started)

    def _apply_theme_mode(self, mode: str, persist: bool) -> None:
        """Apply theme preference and optionally persist it."""
        if mode not in {"system", "dark", "light"}:
            mode = "system"

        self._theme_mode = mode
        self._theme_manager.apply_theme(mode)
        self._apply_theme()
        self._update_theme_menu_checks()

        if hasattr(self, "_loading_screen"):
            self._loading_screen.refresh_theme(mode)

        if persist:
            self._settings_manager.set_theme_preference(mode)

    def _update_theme_menu_checks(self) -> None:
        """Update theme menu action states."""
        if not self._theme_actions:
            return

        for mode, action in self._theme_actions.items():
            block = action.blockSignals(True)
            action.setChecked(mode == self._theme_mode)
            action.blockSignals(block)

    def _on_theme_mode_selected(self, mode: str) -> None:
        """Handle theme selection from the View menu."""
        self._apply_theme_mode(mode, persist=True)

    def _apply_theme(self) -> None:
        """Apply theme to application."""
        stylesheet = self._theme_manager.get_stylesheet()
        self.setStyleSheet(stylesheet)

        # Apply theme colors to widgets
        palette = self._theme_manager.palette
        self._sample_player.set_theme_colors(palette)
        self._navigator.set_theme_colors(palette)
        self._spectrogram_widget.set_theme_colors(palette)

    def _on_new_project(self) -> None:
        """Handle new project action."""
        if self._project_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before creating a new project?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if not self.save_project():
                    return  # User cancelled save
            elif reply == QMessageBox.StandardButton.Cancel:
                return  # User cancelled

        # Clear current project
        self._project_path = None
        self._project_modified = False
        self._current_audio_path = None
        if self._pipeline_wrapper:
            self._pipeline_wrapper.current_segments = []
        self._spectrogram_widget.set_segments([])
        self._update_sample_table([])
        self._update_navigator_markers()
        # Make sure any loading screen is hidden and properly cleaned up
        self._loading_screen.hide_overlay()
        # Process events to ensure UI updates
        QApplication.processEvents()
        self._update_window_title()

    def _on_open_project(self) -> None:
        """Handle open project action."""
        if self._project_modified:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before opening a project?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if not self.save_project():
                    return  # User cancelled save
            elif reply == QMessageBox.StandardButton.Cancel:
                return  # User cancelled

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "SpectroSampler Project (*.ssproj);;All Files (*)",
        )

        if file_path:
            self.load_project_file(Path(file_path))

    def _on_save_project(self) -> None:
        """Handle save project action."""
        self.save_project()

    def _on_save_project_as(self) -> None:
        """Handle save project as action."""
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            "",
            "SpectroSampler Project (*.ssproj);;All Files (*)",
        )
        if path_str:
            path = Path(path_str)
            if path.suffix != ".ssproj":
                path = path.with_suffix(".ssproj")
            self.save_project(path)

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
        # Show or update loading screen (don't create duplicate if already visible)
        if not self._loading_screen.isVisible():
            self._loading_screen.set_message(f"Loading audio: {file_path.name}...")
            self._loading_screen.show_overlay(self)
            # Process events multiple times to ensure loading screen is visible
            for _ in range(3):
                QApplication.processEvents()
        else:
            # Update existing loading screen message
            self._loading_screen.set_message(f"Loading audio: {file_path.name}...")
            QApplication.processEvents()  # Process events to update message

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

            # Load audio (this will block the UI thread, but we'll process events before)
            self._loading_screen.set_message("Loading audio file...")
            # Process events multiple times to ensure spinner is visible and animating
            for _ in range(5):
                QApplication.processEvents()

            audio_info = self._pipeline_wrapper.load_audio(file_path)
            self._current_audio_path = file_path
            # Process events after loading
            for _ in range(3):
                QApplication.processEvents()

            # Update UI
            duration = audio_info.get("duration", 0.0)
            self._spectrogram_widget.set_duration(duration)
            self._navigator.set_duration(duration)

            # Set initial time range
            self._spectrogram_widget.set_time_range(0.0, min(60.0, duration))
            self._navigator.set_view_range(0.0, min(60.0, duration))

            # Add to recent audio files
            self._settings_manager.add_recent_audio_file(file_path)
            self._update_recent_files_menu()

            # Start overview generation in background thread
            self._overview_manager.start_generation(
                self._tiler, file_path, duration, sample_rate=None
            )
            # Note: Overview will be applied to UI via _on_overview_finished signal

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

            # Mark as modified (audio file loaded)
            self._project_modified = True
            self._update_window_title()

            # Ensure main spectrogram is visible immediately on load
            try:
                self._spectrogram_widget.preload_current_view()
            except (RuntimeError, ValueError, OSError) as exc:
                logger.debug("Failed to preload spectrogram view: %s", exc, exc_info=exc)

            # Note: Loading screen will be hidden after overview generation completes
            # (via _on_overview_finished or _on_overview_error)

        except (FFmpegError, OSError, RuntimeError, ValueError) as e:
            # Cancel overview generation if it was started
            if self._overview_manager.is_generating():
                self._overview_manager.cancel()
            self._loading_screen.hide_overlay()
            QMessageBox.critical(self, "Error", f"Failed to load audio file:\n{str(e)}")
            logger.error("Failed to load audio file: %s", e, exc_info=e)

    def _collect_project_data(self) -> ProjectData:
        """Collect current project data from MainWindow.

        Returns:
            ProjectData object with current state.
        """
        from datetime import datetime

        from spectrosampler.gui.project import PROJECT_VERSION, UIState

        # Collect segments
        segments = []
        if self._pipeline_wrapper and self._pipeline_wrapper.current_segments:
            segments = [_segment_to_dict(s) for s in self._pipeline_wrapper.current_segments]

        # Collect detection settings
        detection_settings = {}
        if self._settings_panel:
            settings = self._settings_panel.get_settings()
            detection_settings = _processing_settings_to_dict(settings)

        # Collect export settings
        export_settings = {
            "export_pre_pad_ms": self._export_pre_pad_ms,
            "export_post_pad_ms": self._export_post_pad_ms,
            "export_format": self._export_format,
            "export_sample_rate": self._export_sample_rate,
            "export_bit_depth": self._export_bit_depth,
            "export_channels": self._export_channels,
        }

        # Collect grid settings
        grid_settings = {}
        if self._grid_settings:
            grid_settings = _grid_settings_to_dict(self._grid_settings)

        # Collect UI state
        ui_state = UIState(
            view_start=self._spectrogram_widget._start_time,
            view_end=self._spectrogram_widget._end_time,
            zoom_level=self._spectrogram_widget._zoom_level,
        )

        # Create project data
        now = datetime.utcnow().isoformat() + "Z"
        project_data = ProjectData(
            version=PROJECT_VERSION,
            created=now if not self._project_path else "",  # Will be set from existing file on save
            modified=now,
            audio_path=str(self._current_audio_path) if self._current_audio_path else "",
            segments=segments,
            detection_settings=detection_settings,
            export_settings=export_settings,
            grid_settings=grid_settings,
            ui_state=ui_state,
        )

        return project_data

    def _restore_project_data(self, data: ProjectData) -> None:
        """Restore project data to MainWindow.

        Args:
            data: ProjectData to restore.
        """
        # Validate audio file exists
        audio_path = Path(data.audio_path) if data.audio_path else None
        if audio_path and not audio_path.exists():
            # Try to prompt user to locate the file
            reply = QMessageBox.question(
                self,
                "Audio File Not Found",
                f"The audio file referenced in this project could not be found:\n{data.audio_path}\n\n"
                "Would you like to locate it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                file_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Locate Audio File",
                    str(audio_path.parent) if audio_path.parent.exists() else "",
                    "Audio Files (*.wav *.flac *.mp3 *.m4a *.aac);;All Files (*)",
                )
                if file_path:
                    audio_path = Path(file_path)
                else:
                    QMessageBox.warning(
                        self, "Cannot Load Project", "Audio file is required to load project."
                    )
                    return
            else:
                QMessageBox.warning(
                    self, "Cannot Load Project", "Audio file is required to load project."
                )
                return

        # Load audio file if path is provided
        if audio_path:
            try:
                # Update loading message (loading screen should already be visible from load_project_file)
                self._loading_screen.set_message(f"Loading project audio: {audio_path.name}...")
                # Process events multiple times to ensure loading screen is visible and animating
                for _ in range(3):
                    QApplication.processEvents()
                self.load_audio_file(audio_path)
                # Note: Loading screen will be hidden after overview generation completes
                # (via _on_overview_finished or _on_overview_error)
            except (FFmpegError, OSError, RuntimeError, ValueError) as e:
                # Cancel overview generation if it was started
                if self._overview_manager.is_generating():
                    self._overview_manager.cancel()
                self._loading_screen.hide_overlay()
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to load audio file:\n{str(e)}\n\nProject could not be loaded.",
                )
                logger.error("Failed to load audio file for project: %s", e, exc_info=e)
                return

        # Restore detection settings
        if data.detection_settings:
            try:
                settings = _dict_to_processing_settings(data.detection_settings)
                # Update settings panel (this is tricky - we need to set values directly)
                # The settings panel doesn't have a set_settings method, so we'll need to
                # update the underlying _settings object
                self._settings_panel._settings = settings
                # Update UI controls to match settings
                self._settings_panel._mode_combo.setCurrentText(settings.mode)
                self._settings_panel._threshold_spin.setValue(
                    float(settings.threshold)
                    if isinstance(settings.threshold, (int, float))
                    else 50.0
                )
                # Sync the max-sample control so saved projects reopen with the same cap.
                self._settings_panel.apply_max_samples(getattr(settings, "max_samples", 256))
                # Update other settings controls...
                # For now, we'll just update the mode and threshold as examples
                # A more complete implementation would update all controls
            except (ValueError, TypeError, KeyError, RuntimeError) as e:
                logger.warning("Failed to restore detection settings: %s", e, exc_info=e)

        # Restore export settings
        if data.export_settings:
            self._export_pre_pad_ms = float(data.export_settings.get("export_pre_pad_ms", 0.0))
            self._export_post_pad_ms = float(data.export_settings.get("export_post_pad_ms", 0.0))
            self._export_format = str(data.export_settings.get("export_format", "wav"))
            self._export_sample_rate = (
                int(data.export_settings["export_sample_rate"])
                if data.export_settings.get("export_sample_rate") is not None
                else None
            )
            self._export_bit_depth = (
                str(data.export_settings["export_bit_depth"])
                if data.export_settings.get("export_bit_depth") is not None
                else None
            )
            self._export_channels = (
                str(data.export_settings["export_channels"])
                if data.export_settings.get("export_channels") is not None
                else None
            )
            # Update export format menu actions
            if self._export_format == "wav":
                if hasattr(self, "_export_format_wav_action"):
                    self._export_format_wav_action.setChecked(True)
                    self._export_format_flac_action.setChecked(False)
            elif self._export_format == "flac":
                if hasattr(self, "_export_format_flac_action"):
                    self._export_format_flac_action.setChecked(True)
                    self._export_format_wav_action.setChecked(False)

        # Restore grid settings
        if data.grid_settings:
            try:
                self._grid_settings = _dict_to_grid_settings(data.grid_settings)
                self._grid_manager.settings = self._grid_settings
                self._spectrogram_widget.set_grid_manager(self._grid_manager)
                # Update grid menu actions
                if hasattr(self, "_grid_mode_free_action") and hasattr(
                    self, "_grid_mode_musical_action"
                ):
                    if self._grid_settings.mode == GridMode.FREE_TIME:
                        self._grid_mode_free_action.setChecked(True)
                        self._grid_mode_musical_action.setChecked(False)
                    elif self._grid_settings.mode == GridMode.MUSICAL_BAR:
                        self._grid_mode_musical_action.setChecked(True)
                        self._grid_mode_free_action.setChecked(False)
            except (ValueError, TypeError, KeyError) as e:
                logger.warning("Failed to restore grid settings: %s", e, exc_info=e)

        # Restore segments
        if self._pipeline_wrapper:
            if data.segments:
                try:
                    segments = [_dict_to_segment(s) for s in data.segments]
                    self._pipeline_wrapper.current_segments = segments
                    self._spectrogram_widget.set_segments(self._get_display_segments())
                    self._update_sample_table(segments)
                    self._update_navigator_markers()
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning("Failed to restore segments: %s", e, exc_info=e)
            else:
                # No segments in project - clear segments
                self._pipeline_wrapper.current_segments = []
                self._spectrogram_widget.set_segments([])
                self._update_sample_table([])
                self._update_navigator_markers()

        # Restore UI state
        if data.ui_state:
            try:
                # Restore view range
                if hasattr(data.ui_state, "view_start") and hasattr(data.ui_state, "view_end"):
                    view_start = data.ui_state.view_start
                    view_end = data.ui_state.view_end
                    # Ensure view is within audio duration
                    if self._spectrogram_widget._duration > 0:
                        view_end = min(view_end, self._spectrogram_widget._duration)
                        view_start = max(0.0, min(view_start, view_end - 0.1))
                        self._spectrogram_widget.set_time_range(view_start, view_end)
                        self._navigator.set_view_range(view_start, view_end)
                # Restore zoom level
                if hasattr(data.ui_state, "zoom_level"):
                    self._spectrogram_widget.set_zoom_level(data.ui_state.zoom_level)
            except (AttributeError, ValueError, TypeError) as e:
                logger.warning("Failed to restore UI state: %s", e, exc_info=e)

        # Clear modified flag, clear undo/redo stacks, and set baseline
        self._project_modified = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        if self._pipeline_wrapper:
            self._baseline_segments = copy.deepcopy(self._pipeline_wrapper.current_segments)
        else:
            self._baseline_segments = []
        self._update_window_title()

    def save_project(self, path: Path | None = None) -> bool:
        """Save current project to file.

        Args:
            path: Path to save project. If None, uses current project path or prompts.

        Returns:
            True if saved successfully, False otherwise.
        """
        if path is None:
            path = self._project_path
            if path is None:
                # Generate recommended filename based on date and audio file
                from datetime import datetime

                recommended_name = "project.ssproj"
                if self._current_audio_path:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    audio_name = self._current_audio_path.stem
                    recommended_name = f"{date_str}_{audio_name}.ssproj"

                # Prompt for save location
                path_str, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Project",
                    recommended_name,
                    "SpectroSampler Project (*.ssproj);;All Files (*)",
                )
                if not path_str:
                    return False
                path = Path(path_str)
                # Ensure .ssproj extension
                if path.suffix != ".ssproj":
                    path = path.with_suffix(".ssproj")

        try:
            # Collect project data
            project_data = self._collect_project_data()

            # If this is a new project, set created timestamp
            if not self._project_path or self._project_path != path:
                from datetime import datetime

                project_data.created = datetime.utcnow().isoformat() + "Z"
            else:
                # Preserve created timestamp from existing project
                try:
                    existing_data = load_project(path)
                    project_data.created = existing_data.created
                except (OSError, ValueError) as exc:
                    # If we can't load existing, use current time
                    from datetime import datetime

                    logger.warning(
                        "Could not load existing project metadata: %s", exc, exc_info=exc
                    )
                    project_data.created = datetime.utcnow().isoformat() + "Z"

            # Save project
            save_project(project_data, path)

            # Update project path, clear modified flag, clear undo/redo stacks, and set baseline
            self._project_path = path
            self._project_modified = False
            self._undo_stack.clear()
            self._redo_stack.clear()
            if self._pipeline_wrapper:
                self._baseline_segments = copy.deepcopy(self._pipeline_wrapper.current_segments)
            else:
                self._baseline_segments = []
            self._update_window_title()

            # Add to recent projects
            self._settings_manager.add_recent_project(path)
            self._update_recent_files_menu()

            # Clean up auto-save files (project is now saved)
            self._autosave_manager.cleanup_old_autosaves(keep_count=0)

            logger.info(f"Project saved to {path}")
            return True

        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Failed to save project:\n{str(e)}")
            logger.error("Failed to save project: %s", e, exc_info=e)
            return False

    def load_project_file(self, path: Path) -> bool:
        """Load project from file.

        Args:
            path: Path to project file.

        Returns:
            True if loaded successfully, False otherwise.
        """
        # Show loading screen and ensure it's visible
        self._loading_screen.set_message(f"Loading project: {path.name}...")
        self._loading_screen.show_overlay(self)
        # Process events multiple times to ensure loading screen is shown
        for _ in range(3):
            QApplication.processEvents()

        try:
            # Load project data
            project_data = load_project(path)

            # Restore project data (this also sets baseline)
            self._restore_project_data(project_data)

            # Update project path
            self._project_path = path
            # Baseline is already set in _restore_project_data()
            self._update_window_title()

            # Add to recent projects
            self._settings_manager.add_recent_project(path)
            self._update_recent_files_menu()

            # Note: Loading screen will be hidden after overview generation completes
            # (via _on_overview_finished or _on_overview_error)
            # If no audio file was loaded, hide it now
            if not self._current_audio_path:
                self._loading_screen.hide_overlay()

            logger.info(f"Project loaded from {path}")
            return True

        except FileNotFoundError:
            self._loading_screen.hide_overlay()
            QMessageBox.critical(self, "Error", f"Project file not found:\n{path}")
            return False
        except ValueError as e:
            self._loading_screen.hide_overlay()
            QMessageBox.critical(self, "Error", f"Invalid project file:\n{str(e)}")
            logger.error(f"Invalid project file: {e}")
            return False
        except (FFmpegError, OSError, RuntimeError) as e:
            self._loading_screen.hide_overlay()
            QMessageBox.critical(self, "Error", f"Failed to load project:\n{str(e)}")
            logger.error("Failed to load project: %s", e, exc_info=e)
            return False

    def closeEvent(self, event) -> None:
        """Handle window close event.

        Args:
            event: Close event.
        """
        if self._project_modified:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Unsaved Changes")
            msg_box.setText("You have unsaved changes. Do you want to save them before closing?")

            # Create custom buttons
            save_button = msg_box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
            discard_button = msg_box.addButton(
                "Discard Changes", QMessageBox.ButtonRole.DestructiveRole
            )
            cancel_button = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

            # Set default button
            msg_box.setDefaultButton(cancel_button)

            msg_box.exec()

            clicked_button = msg_box.clickedButton()

            if clicked_button == save_button:
                if not self.save_project():
                    event.ignore()  # User cancelled save, don't close
                    return
            elif clicked_button == discard_button:
                # Delete autosaves before closing to prevent recovery dialog
                self._autosave_manager.cleanup_old_autosaves(keep_count=0)
                self._project_modified = False
                self._update_window_title()
                # Allow close to proceed without auto-save
            elif clicked_button == cancel_button:
                event.ignore()  # User cancelled close
                return

        # Cancel overview generation if in progress
        if self._overview_manager.is_generating():
            self._overview_manager.cancel()

        # Auto-save on close if enabled and modified
        if self._settings_manager.get_auto_save_enabled() and self._project_modified:
            self._autosave_manager.save_now()

        # Save window geometry
        self._save_window_geometry()

        event.accept()

    def _update_window_title(self) -> None:
        """Update window title with project name and modified indicator."""
        title = "SpectroSampler"
        if self._project_path:
            title = f"{self._project_path.stem} - {title}"
        if self._project_modified:
            title = f"*{title}"
        self.setWindowTitle(title)

    def _setup_autosave(self) -> None:
        """Setup auto-save timer based on settings."""
        if self._settings_manager.get_auto_save_enabled():
            interval = self._settings_manager.get_auto_save_interval()
            self._autosave_manager.start(interval)
        else:
            self._autosave_manager.stop()

    def _on_autosave_error(self, error_msg: str) -> None:
        """Handle auto-save error.

        Args:
            error_msg: Error message.
        """
        # Log error but don't interrupt user
        logger.warning(f"Auto-save error: {error_msg}")

    def _restore_window_geometry(self) -> None:
        """Restore window geometry from settings."""
        geometry = self._settings_manager.get_window_geometry()

        # Restore window size
        if geometry.get("size"):
            size = geometry["size"]
            if isinstance(size, QSize):
                self.resize(size)
            elif isinstance(size, (list, tuple)) and len(size) == 2:
                # Convert to int in case QSettings returns strings
                try:
                    width = int(size[0]) if size[0] else 1400
                    height = int(size[1]) if size[1] else 900
                    self.resize(width, height)
                except (ValueError, TypeError):
                    # Default size if conversion fails
                    self.resize(1400, 900)

        # Restore window position
        if geometry.get("position"):
            pos = geometry["position"]
            if isinstance(pos, QPoint):
                self.move(pos)
            elif isinstance(pos, (list, tuple)) and len(pos) == 2:
                # Convert to int in case QSettings returns strings
                try:
                    x = int(pos[0]) if pos[0] else 100
                    y = int(pos[1]) if pos[1] else 100
                    self.move(x, y)
                except (ValueError, TypeError):
                    # Default position if conversion fails
                    pass

        # Restore splitter sizes
        if geometry.get("mainSplitterSizes"):
            sizes = geometry["mainSplitterSizes"]
            if isinstance(sizes, list) and len(sizes) >= 2:
                # Convert to int in case QSettings returns strings
                try:
                    sizes_int = [int(s) if s else 0 for s in sizes]
                    self._main_splitter.setSizes(sizes_int)
                except (ValueError, TypeError):
                    pass

        if geometry.get("editorSplitterSizes"):
            sizes = geometry["editorSplitterSizes"]
            if isinstance(sizes, list) and len(sizes) >= 2:
                pass

        if geometry.get("playerSplitterSizes"):
            sizes = geometry["playerSplitterSizes"]
            if isinstance(sizes, list) and len(sizes) >= 2:
                # Convert to int in case QSettings returns strings
                try:
                    sizes_int = [int(s) if s else 0 for s in sizes]
                    self._player_spectro_splitter.setSizes(sizes_int)
                except (ValueError, TypeError):
                    pass

        # Restore panel visibility
        if "infoTableVisible" in geometry:
            self._sample_table_view.setVisible(geometry["infoTableVisible"])
        if "playerVisible" in geometry:
            self._sample_player.setVisible(geometry["playerVisible"])

    def _save_window_geometry(self) -> None:
        """Save window geometry to settings."""
        geometry = {}

        # Save window size
        geometry["size"] = [self.width(), self.height()]

        # Save window position
        geometry["position"] = [self.x(), self.y()]

        # Save splitter sizes
        geometry["mainSplitterSizes"] = self._main_splitter.sizes()
        geometry["playerSplitterSizes"] = self._player_spectro_splitter.sizes()

        # Save panel visibility
        geometry["infoTableVisible"] = self._sample_table_view.isVisible()
        geometry["playerVisible"] = self._sample_player.isVisible()

        self._settings_manager.set_window_geometry(geometry)

    def _update_recent_files_menu(self) -> None:
        """Update recent files menus."""
        # Update recent projects menu
        self._recent_projects_menu.clear()
        projects = self._settings_manager.get_recent_projects(
            max_count=self._settings_manager.get_max_recent_projects()
        )
        if projects:
            for i, (path, _timestamp) in enumerate(projects, 1):
                action = QAction(f"{i}. {path.stem}", self)
                action.setData(path)
                action.triggered.connect(lambda checked, p=path: self.load_project_file(p))
                self._recent_projects_menu.addAction(action)
            self._recent_projects_menu.addSeparator()
            self._recent_projects_menu.addAction(self._clear_recent_projects_action)
        else:
            no_projects_action = QAction("No recent projects", self)
            no_projects_action.setEnabled(False)
            self._recent_projects_menu.addAction(no_projects_action)

        # Update recent audio files menu
        self._recent_audio_files_menu.clear()
        audio_files = self._settings_manager.get_recent_audio_files(
            max_count=self._settings_manager.get_max_recent_audio_files()
        )
        if audio_files:
            for i, (path, _timestamp) in enumerate(audio_files, 1):
                action = QAction(f"{i}. {path.name}", self)
                action.setData(path)
                action.triggered.connect(lambda checked, p=path: self.load_audio_file(p))
                self._recent_audio_files_menu.addAction(action)
            self._recent_audio_files_menu.addSeparator()
            self._recent_audio_files_menu.addAction(self._clear_recent_audio_files_action)
        else:
            no_audio_action = QAction("No recent audio files", self)
            no_audio_action.setEnabled(False)
            self._recent_audio_files_menu.addAction(no_audio_action)

    def _on_clear_recent_projects(self) -> None:
        """Handle clear recent projects action."""
        self._settings_manager.clear_recent_projects()
        self._update_recent_files_menu()

    def _on_clear_recent_audio_files(self) -> None:
        """Handle clear recent audio files action."""
        self._settings_manager.clear_recent_audio_files()
        self._update_recent_files_menu()

    def _on_autosave_enabled_changed(self, enabled: bool) -> None:
        """Handle auto-save enabled toggle.

        Args:
            enabled: True if auto-save is enabled, False otherwise.
        """
        self._settings_manager.set_auto_save_enabled(enabled)
        self._setup_autosave()

    def _on_autosave_interval_settings(self) -> None:
        """Handle auto-save interval settings dialog."""
        from PySide6.QtWidgets import QInputDialog

        current_interval = self._settings_manager.get_auto_save_interval()
        interval, ok = QInputDialog.getInt(
            self,
            "Auto-save Interval",
            "Auto-save interval (minutes):",
            current_interval,
            1,
            60,
            1,
        )
        if ok:
            self._settings_manager.set_auto_save_interval(interval)
            self._setup_autosave()

    def _on_overview_progress(self, message: str) -> None:
        """Handle overview generation progress.

        Args:
            message: Progress message.
        """
        # Update loading screen message
        self._loading_screen.set_message(message)

    def _on_overview_finished(self, tile: SpectrogramTile) -> None:
        """Handle overview generation finished.

        Args:
            tile: Generated overview tile.
        """
        # Update UI with overview tile (this happens on main thread via Qt signals)
        self._navigator.set_overview_tile(tile)
        try:
            self._spectrogram_widget.set_overview_tile(tile)
        except (RuntimeError, ValueError) as exc:
            logger.debug("Failed to apply overview tile: %s", exc, exc_info=exc)

        # Hide loading screen
        self._loading_screen.hide_overlay()

        logger.info(f"Overview generation completed for: {self._current_audio_path}")

    def _on_overview_error(self, error_msg: str) -> None:
        """Handle overview generation error.

        Args:
            error_msg: Error message.
        """
        logger.error(f"Overview generation error: {error_msg}")

        # Hide loading screen even if overview generation failed
        # UI can still function with detail tiles only
        self._loading_screen.hide_overlay()

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

            # Preserve existing segments before re-detect (for overlap workflow)
            try:
                existing = getattr(self._pipeline_wrapper, "current_segments", [])
                if existing:
                    # Deep-copy to avoid in-place mutations during UI updates
                    self._existing_segments_buffer = copy.deepcopy(existing)
                else:
                    self._existing_segments_buffer = []
            except (AttributeError, TypeError) as exc:
                logger.debug("Failed to copy existing segments buffer: %s", exc, exc_info=exc)
                self._existing_segments_buffer = []

        # Show loading screen for detection
        self._loading_screen.set_message("Detecting samples...")
        self._loading_screen.show_overlay(self)
        # Process events to ensure loading screen is visible
        for _ in range(3):
            QApplication.processEvents()

        # Start detection processing
        self._detection_manager.start_detection()

    def _on_detection_progress(self, message: str) -> None:
        """Handle detection progress.

        Args:
            message: Progress message.
        """
        # Update loading screen message
        self._loading_screen.set_message(message)

    def _on_detection_finished(self, result: dict[str, Any]) -> None:
        """Handle detection finished.

        Args:
            result: Processing results.
        """
        # Hide loading screen
        self._loading_screen.hide_overlay()

        # Update segments
        segments = result.get("segments", [])
        # Ensure enabled flag defaults to True
        for s in segments:
            if not hasattr(s, "attrs") or s.attrs is None:
                s.attrs = {}
            s.attrs.setdefault("enabled", True)
        # If we have existing segments preserved before detection, resolve overlaps
        existing_segments = getattr(self, "_existing_segments_buffer", []) or []
        final_segments = segments
        if existing_segments:
            try:
                from spectrosampler.gui.overlap_detector import find_overlaps
                from spectrosampler.gui.overlap_resolution_dialog import (
                    OverlapResolutionDialog,
                )

                report = find_overlaps(existing_segments, segments, tolerance_ms=5.0)
                has_conflict = bool(report.overlaps or report.duplicates)
                behavior = None
                remember_choice = False
                if has_conflict:
                    # Determine behavior via settings or dialog
                    try:
                        default_behavior = self._settings_manager.get_overlap_default_behavior()
                        show_dialog = self._settings_manager.get_show_overlap_dialog()
                    except (RuntimeError, ValueError, TypeError) as exc:
                        logger.debug("Overlap settings unavailable: %s", exc, exc_info=exc)
                        default_behavior = "discard_duplicates"
                        show_dialog = True

                    if show_dialog:
                        dlg = OverlapResolutionDialog(
                            overlaps_count=len(report.overlaps),
                            duplicates_count=len(report.duplicates),
                            parent=self,
                        )
                        # Preselect based on current default
                        if default_behavior == "discard_overlaps":
                            dlg._rb_discard_overlaps.setChecked(True)
                        elif default_behavior == "keep_all":
                            dlg._rb_keep_all.setChecked(True)
                        else:
                            dlg._rb_discard_duplicates.setChecked(True)

                        if dlg.exec() == OverlapResolutionDialog.Accepted:
                            res = dlg.result_choice()
                            if res is None:
                                # Aborted
                                return
                            behavior, remember_choice = res
                        else:
                            # User canceled
                            return
                    else:
                        behavior = default_behavior

                    # Apply resolution
                    def overlaps_with_existing(idx_new: int) -> bool:
                        for _i, j in report.overlaps:
                            if j == idx_new:
                                return True
                        return False

                    def duplicate_with_existing(idx_new: int) -> bool:
                        for _i, j in report.duplicates:
                            if j == idx_new:
                                return True
                        return False

                    filtered_new: list = []
                    if behavior == "discard_overlaps":
                        for j, seg in enumerate(segments):
                            if not overlaps_with_existing(j):
                                filtered_new.append(seg)
                    elif behavior == "keep_all":
                        filtered_new = list(segments)
                    else:  # discard_duplicates (default)
                        for j, seg in enumerate(segments):
                            if not duplicate_with_existing(j):
                                filtered_new.append(seg)

                    # Update settings if user asked to remember
                    if remember_choice:
                        try:
                            self._settings_manager.set_show_overlap_dialog(False)
                            self._settings_manager.set_overlap_default_behavior(
                                behavior or "discard_duplicates"
                            )
                        except (RuntimeError, ValueError) as exc:
                            logger.debug(
                                "Failed to persist overlap dialog preference: %s", exc, exc_info=exc
                            )

                    final_segments = existing_segments + filtered_new
                else:
                    # No conflicts; simple merge
                    final_segments = existing_segments + segments
            except (RuntimeError, ValueError) as exc:
                # Fallback: simple merge on error
                logger.warning(
                    "Overlap reconciliation failed, merging segments: %s", exc, exc_info=exc
                )
                final_segments = existing_segments + segments

        if self._pipeline_wrapper:
            self._pipeline_wrapper.current_segments = final_segments
        # Apply auto-order if enabled (after merging new segments with existing)
        self._maybe_auto_reorder()
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_sample_table(
            self._pipeline_wrapper.current_segments if self._pipeline_wrapper else final_segments
        )

        # Don't update player widget - player should only show info for currently playing sample

        # Update navigator with sample markers (enabled only)
        self._update_navigator_markers()

        # Push initial undo state so users can undo back to original detected segments
        if self._pipeline_wrapper:
            self._push_undo_state()

        # Mark as modified (samples detected)
        self._project_modified = True
        self._update_window_title()

    def _on_detection_error(self, error: str) -> None:
        """Handle detection error.

        Args:
            error: Error message.
        """
        # Hide loading screen
        self._loading_screen.hide_overlay()
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

        # Mark as modified (settings changed)
        self._project_modified = True
        self._update_window_title()

    def _on_sample_selected(self, index: int) -> None:
        """Handle sample selection.

        Args:
            index: Sample index.
        """
        # Update table selection (column-based)
        try:
            if self._sample_table_model.columnCount() > index:
                self._sample_table_view.setCurrentIndex(self._sample_table_model.index(0, index))
        except (RuntimeError, AttributeError) as exc:
            logger.debug("Failed to update sample table selection: %s", exc, exc_info=exc)
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
            # Fast path: notify model for this column only
            self._sample_table_model.update_segment_times(index, seg.start, seg.end)

            self._maybe_auto_reorder()
            # Update overlays only in spectrogram; no tile requests
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
                self._sample_player.set_sample(
                    seg, index, len(self._pipeline_wrapper.current_segments)
                )

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

            # Mark as modified (sample moved)
            self._project_modified = True
            self._update_window_title()

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
            # Fast path: notify model for this column only
            self._sample_table_model.update_segment_times(index, seg.start, seg.end)

            self._maybe_auto_reorder()
            # Update overlays only in spectrogram; no tile requests
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
                self._sample_player.set_sample(
                    seg, index, len(self._pipeline_wrapper.current_segments)
                )

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

            # Mark as modified (sample resized)
            self._project_modified = True
            self._update_window_title()

    def _on_sample_created(self, start: float, end: float) -> None:
        """Handle sample created.

        Args:
            start: Start time.
            end: End time.
        """
        from spectrosampler.detectors.base import Segment

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

            # Mark as modified (sample created)
            self._project_modified = True
            self._update_window_title()

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

            # Mark as modified (sample deleted)
            self._project_modified = True
            self._update_window_title()

    def _update_navigator_markers(self) -> None:
        """Update navigator markers from current segments."""
        if not self._pipeline_wrapper:
            return
        show_disabled = (
            getattr(self, "_show_disabled_action", None) is None
            or self._show_disabled_action.isChecked()
        )
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

    def _disconnect_media_status_handler(self) -> None:
        """Disconnect any cached mediaStatusChanged handler without spamming warnings."""
        if self._media_status_handler is None:
            return
        try:
            self._media_player.mediaStatusChanged.disconnect(self._media_status_handler)
        except (TypeError, RuntimeError) as exc:
            logger.debug("mediaStatusChanged disconnect failed: %s", exc, exc_info=exc)
        finally:
            self._media_status_handler = None

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
            self._disconnect_media_status_handler()

            # Clean up previous temp file
            if self._temp_playback_file and self._temp_playback_file.exists():
                try:
                    self._temp_playback_file.unlink()
                except OSError as exc:
                    logger.debug(
                        "Failed to remove temporary playback file %s: %s",
                        self._temp_playback_file,
                        exc,
                        exc_info=exc,
                    )
                self._temp_playback_file = None

            # Extract segment to temporary file with unique filename
            temp_dir = Path(tempfile.gettempdir())
            unique_id = uuid.uuid4().hex
            self._temp_playback_file = temp_dir / f"spectrosampler_playback_{unique_id}.wav"

            duration = end_time - start_time

            # Use FFmpeg to extract segment
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "+genpts",
                "-avoid_negative_ts",
                "make_zero",
                "-y",
                "-i",
                str(self._current_audio_path),
                "-ss",
                f"{start_time:.6f}",
                "-t",
                f"{duration:.6f}",
                # Ensure presentation timestamps are generated so Qt's FFmpeg backend
                # does not complain about AV_NOPTS_VALUE packets when demuxing.
                "-af",
                "asetpts=PTS-STARTPTS",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "44100",
                "-ac",
                "2",
                str(self._temp_playback_file),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg extraction failed: {result.stderr}")
                QMessageBox.warning(
                    self, "Playback Error", f"Failed to extract audio segment:\n{result.stderr}"
                )
                return

            # Store current playing info for looping
            self._current_playing_start = start_time
            self._current_playing_end = end_time
            self._playback_stopped = False  # Reset stop flag when starting new playback

            # Store paused position for resume (if applicable)
            seek_position = (
                self._paused_position if self._is_paused and self._paused_position > 0 else 0
            )
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
                        # Restart playback of the same segment without regenerating audio.
                        self._media_player.setPosition(0)
                        self._media_player.play()
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
                        except OSError as exc:
                            logger.debug(
                                "Failed to remove temporary playback file %s: %s",
                                self._temp_playback_file,
                                exc,
                                exc_info=exc,
                            )

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
            self._media_status_handler = on_media_status_changed

            # Load the extracted segment
            url = QUrl.fromLocalFile(str(self._temp_playback_file))
            self._media_player.setSource(url)

        except (subprocess.SubprocessError, OSError, RuntimeError, ValueError) as e:
            logger.error("Failed to play segment: %s", e, exc_info=e)
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
        new_start = max(
            0.0, min(time - view_duration / 2, self._spectrogram_widget._duration - view_duration)
        )
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
        self._disconnect_media_status_handler()

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
        self._sample_player.set_position(
            0, self._sample_player._duration if hasattr(self._sample_player, "_duration") else 0
        )

    def _on_player_next_requested(self) -> None:
        """Handle player next request."""
        if not self._pipeline_wrapper or not self._pipeline_wrapper.current_segments:
            return

        idx = self._sample_table_view.currentIndex()
        current_col = idx.column() if idx.isValid() else -1
        if current_col < 0:
            current_col = 0

        next_col = min(current_col + 1, len(self._pipeline_wrapper.current_segments) - 1)
        if next_col != current_col:
            self._sample_table_view.setCurrentIndex(self._sample_table_model.index(0, next_col))
            self._on_sample_selected(next_col)

    def _on_player_previous_requested(self) -> None:
        """Handle player previous request."""
        if not self._pipeline_wrapper or not self._pipeline_wrapper.current_segments:
            return

        idx = self._sample_table_view.currentIndex()
        current_col = idx.column() if idx.isValid() else -1
        if current_col < 0:
            current_col = len(self._pipeline_wrapper.current_segments) - 1

        prev_col = max(0, current_col - 1)
        if prev_col != current_col:
            self._sample_table_view.setCurrentIndex(self._sample_table_model.index(0, prev_col))
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
        if hasattr(self._sample_player, "_duration") and self._sample_player._duration > 0:
            duration = self._sample_player._duration
        if duration > 0:
            self._sample_player.set_position(position, duration)

    def _on_media_duration_changed(self, duration: int) -> None:
        """Handle media player duration change.

        Args:
            duration: Duration in milliseconds.
        """
        # Use player widget's duration if available (from actual segment), otherwise fall back to media player duration
        if hasattr(self._sample_player, "_duration") and self._sample_player._duration > 0:
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

    def _on_sample_table_changed(self, item):
        # Legacy handler removed with model/view refactor
        return

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
        view_duration = max(
            0.01, self._spectrogram_widget._end_time - self._spectrogram_widget._start_time
        )
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
        """Update sample table model with new segments."""
        # Ensure enabled flag exists
        for seg in segments:
            if not hasattr(seg, "attrs") or seg.attrs is None:
                seg.attrs = {}
            seg.attrs.setdefault("enabled", True)
        self._sample_table_model.set_segments(segments)

    def _on_zoom_in(self) -> None:
        """Handle zoom in."""
        self._spectrogram_widget.set_zoom_level(self._spectrogram_widget._zoom_level * 1.5)

    def _on_zoom_out(self) -> None:
        """Handle zoom out."""
        self._spectrogram_widget.set_zoom_level(self._spectrogram_widget._zoom_level / 1.5)

    def _on_fit_to_window(self) -> None:
        """Handle fit to window."""
        if self._spectrogram_widget._duration > 0:
            view_duration = (
                self._spectrogram_widget._end_time - self._spectrogram_widget._start_time
            )
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

        # Mark as modified (all samples deleted)
        self._project_modified = True
        self._update_window_title()

    def _on_reorder_samples(self) -> None:
        """Manually reorder samples chronologically."""
        if not self._pipeline_wrapper:
            return
        self._pipeline_wrapper.current_segments.sort(key=lambda s: s.start)
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_sample_table(self._pipeline_wrapper.current_segments)
        self._update_navigator_markers()

        # Mark as modified (samples reordered)
        self._project_modified = True
        self._update_window_title()

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

        # Mark as modified (sample disabled/enabled)
        self._project_modified = True
        self._update_window_title()

    def _on_disable_sample(self, index: int, disabled: bool) -> None:
        """Disable/enable single sample from context menu."""
        if not self._pipeline_wrapper:
            return
        if 0 <= index < len(self._pipeline_wrapper.current_segments):
            seg = self._pipeline_wrapper.current_segments[index]
            if not hasattr(seg, "attrs") or seg.attrs is None:
                seg.attrs = {}
            seg.attrs["enabled"] = False if disabled else True
            # Notify model
            try:
                self._sample_table_model.setData(
                    self._sample_table_model.index(0, index),
                    Qt.Checked if seg.attrs["enabled"] else Qt.Unchecked,
                    Qt.CheckStateRole,
                )
            except (RuntimeError, ValueError) as exc:
                logger.debug("Failed to update sample enabled state: %s", exc, exc_info=exc)
            self._spectrogram_widget.set_segments(self._get_display_segments())
            self._update_navigator_markers()

            # Mark as modified (sample disabled/enabled)
            self._project_modified = True
            self._update_window_title()

    def _on_disable_other_samples(self, index: int) -> None:
        """Disable all samples except the given index."""
        if not self._pipeline_wrapper:
            return
        for i, s in enumerate(self._pipeline_wrapper.current_segments):
            if not hasattr(s, "attrs") or s.attrs is None:
                s.attrs = {}
            s.attrs["enabled"] = i == index
            try:
                self._sample_table_model.setData(
                    self._sample_table_model.index(0, i),
                    Qt.Checked if s.attrs["enabled"] else Qt.Unchecked,
                    Qt.CheckStateRole,
                )
            except (RuntimeError, ValueError) as exc:
                logger.debug("Failed to update sample enabled state: %s", exc, exc_info=exc)
        self._spectrogram_widget.set_segments(self._get_display_segments())
        self._update_navigator_markers()

        # Mark as modified (samples disabled/enabled)
        self._project_modified = True
        self._update_window_title()

    def _on_export_samples(self) -> None:
        """Handle export samples action."""
        if not self._pipeline_wrapper or not self._pipeline_wrapper.current_segments:
            QMessageBox.warning(
                self, "No Samples", "No samples to export. Please process preview first."
            )
            return

        # Get output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")

        if output_dir:
            # Get selected indices (row 0 checkboxes represented by segment enabled flag)
            selected_indices = []
            for i, seg in enumerate(self._pipeline_wrapper.current_segments):
                enabled = True
                if hasattr(seg, "attrs") and seg.attrs is not None:
                    enabled = seg.attrs.get("enabled", True)
                if enabled:
                    selected_indices.append(i)

            if not selected_indices:
                QMessageBox.warning(self, "No Selection", "Please select samples to export.")
                return

            # Export samples
            try:
                count = self._pipeline_wrapper.export_samples(Path(output_dir), selected_indices)
                QMessageBox.information(
                    self, "Export Complete", f"Exported {count} samples to:\n{output_dir}"
                )
                self._status_label.setText(f"Exported {count} samples")
            except (FFmpegError, OSError, ValueError, RuntimeError) as e:
                logger.error("Failed to export samples: %s", e, exc_info=e)
                QMessageBox.critical(self, "Export Error", f"Failed to export samples:\n{str(e)}")

    def _on_about(self) -> None:
        """Handle about action."""
        QMessageBox.about(
            self,
            "About SpectroSampler",
            "SpectroSampler GUI\n\nTurn long field recordings into usable sample packs.",
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
        except (AttributeError, ValueError, RuntimeError) as e:
            logger.error("Failed to toggle verbose log: %s", e, exc_info=e)

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

        # Check if we've returned to baseline state
        self._check_baseline_state()

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

        # Check if we've returned to baseline state
        self._check_baseline_state()

    def _check_baseline_state(self) -> None:
        """Check if current state matches baseline and update modified flag accordingly."""
        if not self._pipeline_wrapper:
            return

        # If undo stack is empty, we're at the "beginning" of history - check if it matches baseline
        # (redo stack may have items, but that's fine - we're checking if we've undone back to baseline)
        if len(self._undo_stack) == 0:
            # Compare current segments with baseline
            current_segments = self._pipeline_wrapper.current_segments

            # Handle empty baseline case (project loaded/saved with no segments)
            if len(self._baseline_segments) == 0:
                if len(current_segments) == 0:
                    # Both empty - clear modified flag
                    self._project_modified = False
                    self._update_window_title()
                return

            # If lengths don't match, not at baseline
            if len(current_segments) != len(self._baseline_segments):
                return

            # Check if segments match (deep comparison with epsilon for floats)
            matches = True
            for curr, base in zip(current_segments, self._baseline_segments, strict=True):
                # Compare basic attributes with epsilon for float comparison
                if (
                    abs(curr.start - base.start) > 1e-6
                    or abs(curr.end - base.end) > 1e-6
                    or curr.detector != base.detector
                    or abs(curr.score - base.score) > 1e-6
                ):
                    matches = False
                    break

                # Compare enabled state (handle missing attrs)
                curr_enabled = (
                    curr.attrs.get("enabled", True)
                    if hasattr(curr, "attrs") and curr.attrs
                    else True
                )
                base_enabled = (
                    base.attrs.get("enabled", True)
                    if hasattr(base, "attrs") and base.attrs
                    else True
                )
                if curr_enabled != base_enabled:
                    matches = False
                    break

            if matches:
                # Segments match baseline - clear modified flag
                # Note: This doesn't check settings, but undoing all segment changes
                # should reset modified status per user request
                self._project_modified = False
                self._update_window_title()

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

    # Model-view callbacks
    def _on_model_enabled_toggled(self, column: int, enabled: bool) -> None:
        if not self._pipeline_wrapper or not (
            0 <= column < len(self._pipeline_wrapper.current_segments)
        ):
            return
        # Push undo state before change
        self._push_undo_state()
        # Update the segment in pipeline_wrapper to match model
        seg = self._pipeline_wrapper.current_segments[column]
        if not hasattr(seg, "attrs") or seg.attrs is None:
            seg.attrs = {}
        seg.attrs["enabled"] = enabled
        # Reflect enabled update into other views
        self._spectrogram_widget.set_segments(self._get_display_segments())
        # Force spectrogram canvas to refresh
        self._spectrogram_widget._canvas.draw_idle()
        self._update_navigator_markers()
        # Mark as modified
        self._project_modified = True
        self._update_window_title()

    def _on_model_times_edited(self, column: int, start: float, end: float) -> None:
        if not self._pipeline_wrapper or not (
            0 <= column < len(self._pipeline_wrapper.current_segments)
        ):
            return
        # Push undo state before change
        self._push_undo_state()
        # Update the segment in pipeline_wrapper to match model
        seg = self._pipeline_wrapper.current_segments[column]
        seg.start = start
        seg.end = end
        # Notify model that times were updated (in case it needs to refresh display)
        self._sample_table_model.update_segment_times(column, seg.start, seg.end)
        # After start/end edits, reorder and refresh overlays
        self._maybe_auto_reorder()
        self._spectrogram_widget.set_segments(self._get_display_segments())
        # Force spectrogram canvas to refresh
        self._spectrogram_widget._canvas.draw_idle()
        self._update_navigator_markers()
        # Mark as modified
        self._project_modified = True
        self._update_window_title()

    def _on_model_duration_edited(self, column: int, new_duration: float) -> None:
        if not self._pipeline_wrapper or not (
            0 <= column < len(self._pipeline_wrapper.current_segments)
        ):
            return
        # Push undo state before change
        self._push_undo_state()
        seg = self._pipeline_wrapper.current_segments[column]
        # Apply duration change according to current mode (this also updates the model)
        self._apply_duration_change(seg, new_duration, column)
        self._maybe_auto_reorder()
        self._spectrogram_widget.set_segments(self._get_display_segments())
        # Force spectrogram canvas to refresh
        self._spectrogram_widget._canvas.draw_idle()
        self._update_navigator_markers()
        # Mark as modified
        self._project_modified = True
        self._update_window_title()

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
        show_disabled = (
            getattr(self, "_show_disabled_action", None) is None
            or self._show_disabled_action.isChecked()
        )
        if show_disabled:
            return list(self._pipeline_wrapper.current_segments) if self._pipeline_wrapper else []
        return self._get_enabled_segments()

    def _maybe_auto_reorder(self) -> None:
        """Re-order samples by start if Auto Sample Order is enabled."""
        try:
            if (
                getattr(self, "_auto_order_action", None)
                and self._auto_order_action.isChecked()
                and self._pipeline_wrapper
            ):
                self._pipeline_wrapper.current_segments.sort(key=lambda s: s.start)
        except (AttributeError, TypeError) as exc:
            logger.debug("Auto reorder failed: %s", exc, exc_info=exc)

    # Export menu handlers
    def _on_export_pre_pad_settings(self) -> None:
        """Handle export pre-padding settings dialog."""
        from PySide6.QtWidgets import QInputDialog

        value, ok = QInputDialog.getDouble(
            self,
            "Export Pre-padding",
            "Pre-padding (ms):",
            self._export_pre_pad_ms,
            0.0,
            50000.0,
            0,
        )
        if ok:
            self._export_pre_pad_ms = value
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.export_pre_pad_ms = value
            # Mark as modified (export settings changed)
            self._project_modified = True
            self._update_window_title()

    def _on_export_post_pad_settings(self) -> None:
        """Handle export post-padding settings dialog."""
        from PySide6.QtWidgets import QInputDialog

        value, ok = QInputDialog.getDouble(
            self,
            "Export Post-padding",
            "Post-padding (ms):",
            self._export_post_pad_ms,
            0.0,
            50000.0,
            0,
        )
        if ok:
            self._export_post_pad_ms = value
            # Update settings if pipeline wrapper exists
            if self._pipeline_wrapper:
                self._pipeline_wrapper.settings.export_post_pad_ms = value
            # Mark as modified (export settings changed)
            self._project_modified = True
            self._update_window_title()

    def _on_export_format_changed(self, format: str) -> None:
        """Handle export format change."""
        self._export_format = format
        # Update action states
        self._export_format_wav_action.setChecked(format == "wav")
        self._export_format_flac_action.setChecked(format == "flac")
        # Update settings if pipeline wrapper exists
        if self._pipeline_wrapper:
            self._pipeline_wrapper.settings.format = format
        # Mark as modified (export settings changed)
        self._project_modified = True
        self._update_window_title()

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
            # Mark as modified (export settings changed)
            self._project_modified = True
            self._update_window_title()

    def _on_export_bit_depth_settings(self) -> None:
        """Handle export bit depth settings dialog."""
        from PySide6.QtWidgets import QInputDialog

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
            # Mark as modified (export settings changed)
            self._project_modified = True
            self._update_window_title()

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
            # Mark as modified (export settings changed)
            self._project_modified = True
            self._update_window_title()

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

    def _on_duration_edit_mode_changed(self, mode: str) -> None:
        """Handle duration edit mode change.

        Args:
            mode: One of "expand_contract", "from_start", "from_end"
        """
        self._duration_edit_mode = mode
        # Update action states
        for m, action in self._duration_edit_actions.items():
            action.setChecked(m == mode)

    def _apply_duration_change(self, seg: Segment, new_duration: float, col: int) -> None:
        """Apply duration change to segment based on selected mode.

        Args:
            seg: Segment to modify.
            new_duration: New duration in seconds.
            col: Column index (for updating table cells).
        """
        old_start = seg.start
        old_end = seg.end
        audio_duration = (
            self._spectrogram_widget._duration
            if hasattr(self._spectrogram_widget, "_duration")
            else float("inf")
        )

        if self._duration_edit_mode == "expand_contract":
            # Expand/contract equally on both sides from middle
            center = (old_start + old_end) / 2.0
            half_duration = new_duration / 2.0
            new_start = max(0.0, center - half_duration)
            new_end = min(audio_duration, center + half_duration)
            # If clamping occurred, adjust the other side to maintain duration
            if new_start == 0.0:
                new_end = min(audio_duration, new_start + new_duration)
            elif new_end == audio_duration:
                new_start = max(0.0, new_end - new_duration)
            seg.start = new_start
            seg.end = new_end
        elif self._duration_edit_mode == "from_start":
            # Adjust end time based on start time
            new_end = min(audio_duration, old_start + new_duration)
            seg.start = old_start  # Keep start unchanged
            seg.end = new_end
        elif self._duration_edit_mode == "from_end":
            # Adjust start time based on end time
            new_start = max(0.0, old_end - new_duration)
            seg.start = new_start
            seg.end = old_end  # Keep end unchanged

        # Update model to reflect changes (model will emit dataChanged signals)
        self._sample_table_model.update_segment_times(col, seg.start, seg.end)
