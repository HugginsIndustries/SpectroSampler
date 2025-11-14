"""Theme system with dark theme and system integration."""

import logging
import platform
import subprocess
from typing import Any

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor

logger = logging.getLogger(__name__)


class ThemeManager(QObject):
    """Manages application theme with system integration."""

    theme_changed = Signal(str)  # Emitted when theme changes ('dark' or 'light')

    def __init__(self, parent: QObject | None = None):
        """Initialize theme manager.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._current_theme = "dark"
        self._palette = self._create_dark_palette()
        self._current_preference = self._load_preference()

    @property
    def current_theme(self) -> str:
        """Get current theme name."""
        return self._current_theme

    @property
    def palette(self) -> dict[str, Any]:
        """Get current color palette."""
        return self._palette

    @property
    def preference(self) -> str:
        """Return current preference ('system', 'dark', or 'light')."""
        return self._current_preference

    def _create_dark_palette(self) -> dict[str, Any]:
        """Create dark theme color palette.

        Returns:
            Dictionary with color definitions.
        """
        return {
            # Background colors
            "background": QColor(0x1E, 0x1E, 0x1E),
            "background_secondary": QColor(0x25, 0x25, 0x26),
            "background_tertiary": QColor(0x2D, 0x2D, 0x30),
            # Accent colors
            "accent": QColor(0xEF, 0x7F, 0x22),
            "accent_secondary": QColor(0x00, 0xFF, 0x6A),
            "accent_hover": QColor(0xFF, 0x9F, 0x42),
            # Text colors
            "text": QColor(0xCC, 0xCC, 0xCC),
            "text_secondary": QColor(0x99, 0x99, 0x99),
            "text_bright": QColor(0xFF, 0xFF, 0xFF),
            # Border colors
            "border": QColor(0x3C, 0x3C, 0x3C),
            "border_light": QColor(0x45, 0x45, 0x45),
            # Selection colors
            "selection": QColor(0xEF, 0x7F, 0x22, 0x80),
            "selection_border": QColor(0xEF, 0x7F, 0x22),
            # Grid colors
            "grid": QColor(0x3C, 0x3C, 0x3C, 0x80),
            "grid_major": QColor(0x45, 0x45, 0x45, 0xA0),
            # Marker colors
            "marker_voice": QColor(0x00, 0xFF, 0xAA),
            "marker_transient": QColor(0xFF, 0xCC, 0x00),
            "marker_nonsilence": QColor(0xFF, 0x66, 0xAA),
            "marker_spectral": QColor(0x66, 0xAA, 0xFF),
        }

    def _create_light_palette(self) -> dict[str, Any]:
        """Create light theme color palette."""
        return {
            # Background colors
            "background": QColor(0xF4, 0xF5, 0xF7),
            "background_secondary": QColor(0xFF, 0xFF, 0xFF),
            "background_tertiary": QColor(0xEB, 0xEC, 0xEF),
            # Accent colors
            "accent": QColor(0xEF, 0x7F, 0x22),
            "accent_secondary": QColor(0x00, 0x8A, 0x5C),
            "accent_hover": QColor(0xFF, 0x9F, 0x42),
            # Text colors
            "text": QColor(0x25, 0x25, 0x25),
            "text_secondary": QColor(0x55, 0x55, 0x55),
            "text_bright": QColor(0x00, 0x00, 0x00),
            # Border colors
            "border": QColor(0xC9, 0xCC, 0xD1),
            "border_light": QColor(0xD9, 0xDC, 0xE0),
            # Selection colors
            "selection": QColor(0xEF, 0x7F, 0x22, 0x40),
            "selection_border": QColor(0xEF, 0x7F, 0x22),
            # Grid colors
            "grid": QColor(0xB0, 0xB5, 0xBC, 0x80),
            "grid_major": QColor(0x90, 0x96, 0x9E, 0xA0),
            # Marker colors
            "marker_voice": QColor(0x00, 0x8A, 0x5C),
            "marker_transient": QColor(0xD9, 0x87, 0x00),
            "marker_nonsilence": QColor(0xC0, 0x33, 0x69),
            "marker_spectral": QColor(0x36, 0x70, 0xC0),
        }

    def detect_system_theme(self) -> str:
        """Detect system theme preference.

        Returns:
            'dark' or 'light' based on system settings.
        """
        system = platform.system()

        if system == "Windows":
            detected = self._detect_windows_theme()
            if detected:
                return detected

        elif system == "Darwin":  # macOS
            try:
                import ctypes
                from ctypes import Structure, c_void_p

                class NSAppearance(Structure):
                    _fields_ = [("dummy", c_void_p)]

                # Try to get system appearance
                app = ctypes.objc_getClass("NSApplication").sharedApplication()
                appearance = app.effectiveAppearance()
                name = appearance.name()
                if "Dark" in str(name):
                    return "dark"
            except (ImportError, AttributeError, OSError) as exc:
                logger.debug("Failed to detect macOS theme preference: %s", exc, exc_info=exc)

        elif system == "Linux":
            # Check GTK settings
            try:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if result.returncode == 0 and "dark" in result.stdout.lower():
                    return "dark"
            except (
                ImportError,
                FileNotFoundError,
                subprocess.SubprocessError,
                subprocess.TimeoutExpired,
            ) as exc:
                logger.debug("Failed to detect Linux theme preference: %s", exc, exc_info=exc)

        # Default to dark theme
        return "dark"

    def _load_preference(self) -> str:
        """Load stored theme preference from QSettings."""
        try:
            settings = QSettings("SpectroSampler", "SpectroSampler")
            stored = str(settings.value("themePreference", "system"))
        except (TypeError, ValueError):
            stored = "system"
        if stored not in {"system", "dark", "light"}:
            stored = "system"
        return stored

    def _detect_windows_theme(self) -> str | None:
        """Attempt to detect Windows theme using Qt hints or registry fallback."""
        try:
            from PySide6.QtGui import QGuiApplication
        except ImportError as exc:
            logger.debug("QGuiApplication unavailable: %s", exc, exc_info=exc)
        else:
            app = QGuiApplication.instance()
            if app:
                try:
                    hints = app.styleHints()
                    if hasattr(hints, "colorScheme") and hasattr(Qt, "ColorScheme"):
                        scheme = hints.colorScheme()
                        if scheme == Qt.ColorScheme.Dark:
                            return "dark"
                        if scheme == Qt.ColorScheme.Light:
                            return "light"
                except (RuntimeError, AttributeError, TypeError) as exc:
                    logger.debug("Failed to read Qt color scheme hints: %s", exc, exc_info=exc)

        # Registry fallback for Windows versions without Qt colorScheme support
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                if isinstance(value, int):
                    return "light" if value else "dark"
        except OSError as exc:
            logger.debug("Failed to read Windows theme from registry: %s", exc, exc_info=exc)

        return None

    def apply_theme(self, theme: str | None = None) -> str:
        """Apply theme to application.

        Args:
            theme: Theme preference ('system', 'dark', or 'light'). If None, uses stored preference.

        Returns:
            Applied theme name.
        """
        preference = theme or self._current_preference
        if preference not in {"system", "dark", "light"}:
            preference = "system"

        self._current_preference = preference

        resolved = self.detect_system_theme() if preference == "system" else preference

        if resolved == "light":
            self._current_theme = "light"
            self._palette = self._create_light_palette()
        else:
            self._current_theme = "dark"
            self._palette = self._create_dark_palette()

        self.theme_changed.emit(self._current_theme)
        return self._current_theme

    def get_stylesheet(self) -> str:
        """Get Qt stylesheet for current theme.

        Returns:
            CSS-like stylesheet string.
        """
        p = self._palette
        return f"""
            QWidget {{
                background-color: {p['background'].name()};
                color: {p['text'].name()};
            }}
            QMainWindow {{
                background-color: {p['background'].name()};
            }}
            QMenuBar {{
                background-color: {p['background_secondary'].name()};
                border-bottom: 1px solid {p['border'].name()};
            }}
            QMenuBar::item {{
                padding: 4px 8px;
            }}
            QMenuBar::item:selected {{
                background-color: {p['background_tertiary'].name()};
            }}
            QMenu {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
            }}
            QMenu::item:selected {{
                background-color: {p['selection'].name()};
            }}
            QMenu::item:disabled {{
                color: {p['text_secondary'].name()};
            }}
            QPushButton {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {p['background_tertiary'].name()};
                border-color: {p['border_light'].name()};
            }}
            QPushButton:pressed {{
                background-color: {p['accent'].name()};
            }}
            QPushButton:disabled {{
                background-color: {p['background'].name()};
                color: {p['text_secondary'].name()};
            }}
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background-color: {p['background'].name()};
                border: 1px solid {p['border'].name()};
                padding: 4px;
                border-radius: 2px;
            }}
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {p['accent'].name()};
            }}
            QSlider::groove:horizontal {{
                background: {p['background_secondary'].name()};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {p['accent'].name()};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {p['accent_hover'].name()};
            }}
            QComboBox {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
                padding: 4px;
                border-radius: 2px;
            }}
            QComboBox:focus {{
                border-color: {p['accent'].name()};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
                selection-background-color: {p['selection'].name()};
            }}
            QCheckBox, QRadioButton {{
                color: {p['text'].name()};
            }}
            QCheckBox::indicator:checked {{
                background-color: {p['accent'].name()};
                border: 1px solid {p['accent'].name()};
            }}
            QRadioButton::indicator:checked {{
                background-color: {p['accent'].name()};
                border: 1px solid {p['accent'].name()};
                border-radius: 8px;
            }}
            QScrollBar:vertical {{
                background: {p['background_secondary'].name()};
                width: 12px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {p['border'].name()};
                min-height: 20px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {p['border_light'].name()};
            }}
            QScrollBar:horizontal {{
                background: {p['background_secondary'].name()};
                height: 12px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {p['border'].name()};
                min-width: 20px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {p['border_light'].name()};
            }}
            QTabWidget::pane {{
                border: 1px solid {p['border'].name()};
                background-color: {p['background'].name()};
            }}
            QTabBar::tab {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
                padding: 6px 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {p['background'].name()};
                border-bottom: 2px solid {p['accent'].name()};
            }}
            QTableWidget {{
                background-color: {p['background'].name()};
                gridline-color: {p['border'].name()};
                border: 1px solid {p['border'].name()};
            }}
            QTableWidget::item:selected {{
                background-color: {p['selection'].name()};
            }}
            QHeaderView::section {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
                padding: 4px;
            }}
            QStatusBar {{
                background-color: {p['background_secondary'].name()};
                border-top: 1px solid {p['border'].name()};
            }}
            QProgressBar {{
                background-color: {p['background_secondary'].name()};
                border: 1px solid {p['border'].name()};
                border-radius: 2px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {p['accent'].name()};
            }}
            QSplitter::handle {{
                background-color: {p['border'].name()};
            }}
            QSplitter::handle:horizontal {{
                width: 6px;
                border-left: 1px solid {p['border_light'].name()};
                border-right: 1px solid {p['border_light'].name()};
            }}
            QSplitter::handle:vertical {{
                height: 6px;
                border-top: 1px solid {p['border_light'].name()};
                border-bottom: 1px solid {p['border_light'].name()};
            }}
            QSplitter::handle:hover {{
                background-color: {p['border_light'].name()};
            }}
        """
