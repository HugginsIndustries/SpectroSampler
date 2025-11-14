"""Shared UI utility functions for consistent styling across the application."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QCheckBox, QComboBox


def apply_combo_styling(widget: QComboBox | None = None) -> str:
    """Apply consistent dropdown arrow styling to QComboBox widgets.

    This function generates a stylesheet that can be applied to QComboBox widgets
    to ensure consistent dropdown arrow appearance using the down.svg icon.

    Args:
        widget: Optional QComboBox widget to apply styling to directly.
               If None, returns the stylesheet string for manual application.

    Returns:
        Stylesheet string for QComboBox widgets. If widget is provided,
        applies the stylesheet and returns empty string.
    """
    # Get absolute path to SVG icon for dropdown arrow
    # Assuming this file is in spectrosampler/gui/, assets is at spectrosampler/../assets
    assets_dir = Path(__file__).parent.parent.parent / "assets"
    down_icon_path = assets_dir / "down.svg"

    # Use stylesheet with SVG icon - convert to absolute path with forward slashes
    if down_icon_path.exists():
        icon_path_str = str(down_icon_path.resolve()).replace("\\", "/")
    else:
        # Fallback if SVG doesn't exist
        icon_path_str = ""

    combo_style = f"""
        QComboBox {{
            border: 1px solid #3C3C3C;
            border-radius: 3px;
            padding: 3px 18px 3px 5px;
            background-color: #252526;
        }}
        QComboBox:hover {{
            border-color: #4A4A4A;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 15px;
            border-left-width: 1px;
            border-left-color: #3C3C3C;
            border-left-style: solid;
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
            background-color: #2D2D30;
        }}
        QComboBox::drop-down:hover {{
            background-color: #3E3E42;
        }}
        QComboBox::down-arrow {{
            image: url({icon_path_str if icon_path_str else "none"});
            width: 12px;
            height: 12px;
        }}
        QComboBox::down-arrow:hover {{
            image: url({icon_path_str if icon_path_str else "none"});
        }}
        QComboBox QAbstractItemView {{
            border: 1px solid #3C3C3C;
            background-color: #252526;
            selection-background-color: #EF7F22;
            selection-color: #FFFFFF;
        }}
    """

    if widget is not None:
        widget.setStyleSheet(combo_style)
        return ""

    return combo_style


def apply_combo_styling_to_widget(widget: QComboBox) -> None:
    """Apply dropdown styling to a specific QComboBox widget.

    Convenience function that applies the shared combo styling to a single widget.

    Args:
        widget: QComboBox widget to style.
    """
    apply_combo_styling(widget)


def apply_combo_styling_to_all_combos(parent_widget) -> None:
    """Apply dropdown styling to all QComboBox widgets within a parent widget.

    Recursively finds all QComboBox widgets within the parent and applies
    consistent styling to each.

    Args:
        parent_widget: Parent widget containing QComboBox widgets to style.
    """
    combo_style = apply_combo_styling()
    for widget in parent_widget.findChildren(QComboBox):
        widget.setStyleSheet(combo_style)


def apply_checkbox_styling(widget: QCheckBox | None = None) -> str:
    """Apply consistent checkbox styling with custom checkmark icon.

    This function generates a stylesheet that can be applied to QCheckBox widgets
    to ensure consistent checkbox appearance using the checkmark.svg icon.

    Args:
        widget: Optional QCheckBox widget to apply styling to directly.
               If None, returns the stylesheet string for manual application.

    Returns:
        Stylesheet string for QCheckBox widgets. If widget is provided,
        applies the stylesheet and returns empty string.
    """
    # Get absolute path to SVG icon for checkmark
    assets_dir = Path(__file__).parent.parent.parent / "assets"
    checkmark_icon_path = assets_dir / "checkmark.svg"

    # Render SVG to pixmap for use in stylesheet
    icon_path_str = ""
    if checkmark_icon_path.exists():
        # Render the SVG to a pixmap
        renderer = QSvgRenderer(str(checkmark_icon_path))
        # Use a reasonable size for the checkbox indicator
        size = 16
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        # Save to a temporary location or use data URI
        # For stylesheet, we'll use the file path approach
        icon_path_str = str(checkmark_icon_path.resolve()).replace("\\", "/")

    checkbox_style = f"""
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid #3C3C3C;
            border-radius: 3px;
            background-color: #252526;
        }}
        QCheckBox::indicator:hover {{
            border-color: #4A4A4A;
            background-color: #2D2D30;
        }}
        QCheckBox::indicator:checked {{
            background-color: #252526;
            border-color: #EF7F22;
            image: url({icon_path_str if icon_path_str else "none"});
        }}
        QCheckBox::indicator:checked:hover {{
            border-color: #EF7F22;
            background-color: #2D2D30;
        }}
        QCheckBox::indicator:disabled {{
            background-color: #1A1A1A;
            border-color: #2A2A2A;
        }}
    """

    if widget is not None:
        widget.setStyleSheet(checkbox_style)
        return ""

    return checkbox_style


def apply_checkbox_styling_to_widget(widget: QCheckBox) -> None:
    """Apply checkbox styling to a specific QCheckBox widget.

    Convenience function that applies the shared checkbox styling to a single widget.

    Args:
        widget: QCheckBox widget to style.
    """
    apply_checkbox_styling(widget)


def apply_checkbox_styling_to_all_checkboxes(parent_widget) -> None:
    """Apply checkbox styling to all QCheckBox widgets within a parent widget.

    Recursively finds all QCheckBox widgets within the parent and applies
    consistent styling to each.

    Args:
        parent_widget: Parent widget containing QCheckBox widgets to style.
    """
    checkbox_style = apply_checkbox_styling()
    for widget in parent_widget.findChildren(QCheckBox):
        widget.setStyleSheet(checkbox_style)
