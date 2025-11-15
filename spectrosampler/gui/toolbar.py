"""Toolbar widget for tool mode selection."""

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ToolMode(Enum):
    """Tool mode enumeration."""

    SELECT = "select"
    EDIT = "edit"
    CREATE = "create"


class ToolbarWidget(QWidget):
    """Vertical toolbar widget with tool mode buttons."""

    mode_changed = Signal(str)  # Emitted when tool mode changes (mode name as string)

    def __init__(self, parent: QWidget | None = None):
        """Initialize toolbar widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)

        self._current_mode = ToolMode.SELECT

        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Load icons
        icon_size = 24
        assets_dir = Path(__file__).parent.parent.parent / "assets"

        def load_svg_icon(path: Path, size: int = icon_size) -> QIcon:
            """Load SVG icon preserving colors by rendering to pixmap."""
            if not path.exists():
                return QIcon()
            renderer = QSvgRenderer(str(path))
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)

        select_icon = load_svg_icon(assets_dir / "pointer.svg")
        edit_icon = load_svg_icon(assets_dir / "pencil.svg")
        create_icon = load_svg_icon(assets_dir / "add.svg")

        # Create tool mode group box
        tool_group = QGroupBox("Tool")
        tool_layout = QVBoxLayout()
        tool_layout.setContentsMargins(8, 8, 8, 8)
        tool_layout.setSpacing(8)

        # Create button group for mutually exclusive selection
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._button_group.buttonClicked.connect(self._on_button_clicked)

        # Create mode buttons
        self._select_button = QPushButton()
        self._select_button.setCheckable(True)
        self._select_button.setChecked(True)  # Default to Select mode
        self._select_button.setIcon(select_icon)
        self._select_button.setIconSize(QSize(24, 24))
        self._select_button.setMinimumHeight(40)
        self._select_button.setMinimumWidth(40)  # Reduced to fit within toolbar
        self._select_button.setToolTip("Select")
        self._button_group.addButton(self._select_button, 0)

        self._edit_button = QPushButton()
        self._edit_button.setCheckable(True)
        self._edit_button.setIcon(edit_icon)
        self._edit_button.setIconSize(QSize(24, 24))
        self._edit_button.setMinimumHeight(40)
        self._edit_button.setMinimumWidth(40)  # Reduced to fit within toolbar
        self._edit_button.setToolTip("Edit")
        self._button_group.addButton(self._edit_button, 1)

        self._create_button = QPushButton()
        self._create_button.setCheckable(True)
        self._create_button.setIcon(create_icon)
        self._create_button.setIconSize(QSize(24, 24))
        self._create_button.setMinimumHeight(40)
        self._create_button.setMinimumWidth(40)  # Reduced to fit within toolbar
        self._create_button.setToolTip("Create")
        self._button_group.addButton(self._create_button, 2)

        # Apply styling to make checked state visible
        # Use orange accent color for checked state to match theme
        button_style = """
            QPushButton {
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                background-color: transparent;
            }
            QPushButton:checked {
                background-color: rgba(239, 127, 34, 0.2);
                border: 2px solid #EF7F22;
            }
            QPushButton:hover {
                background-color: rgba(239, 127, 34, 0.1);
            }
            QPushButton:checked:hover {
                background-color: rgba(239, 127, 34, 0.3);
            }
        """
        self._select_button.setStyleSheet(button_style)
        self._edit_button.setStyleSheet(button_style)
        self._create_button.setStyleSheet(button_style)

        # Add buttons to tool group layout
        tool_layout.addWidget(self._select_button)
        tool_layout.addWidget(self._edit_button)
        tool_layout.addWidget(self._create_button)

        tool_group.setLayout(tool_layout)

        # Add tool group to main layout
        layout.addWidget(tool_group)

        layout.addStretch()

        self.setLayout(layout)

        # Set minimum width for toolbar (~75px total, half of original)
        self.setMinimumWidth(75)

    def _on_button_clicked(self, button: QPushButton) -> None:
        """Handle button click to change tool mode.

        Args:
            button: The button that was clicked.
        """
        if button == self._select_button:
            self._current_mode = ToolMode.SELECT
            self.mode_changed.emit(ToolMode.SELECT.value)
        elif button == self._edit_button:
            self._current_mode = ToolMode.EDIT
            self.mode_changed.emit(ToolMode.EDIT.value)
        elif button == self._create_button:
            self._current_mode = ToolMode.CREATE
            self.mode_changed.emit(ToolMode.CREATE.value)

    def get_current_mode(self) -> ToolMode:
        """Get current tool mode.

        Returns:
            Current ToolMode.
        """
        return self._current_mode
