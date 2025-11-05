"""Delegates for painting lightweight buttons and handling clicks.

Handles rows:
- Row 1: Center/Fill (two small buttons)
- Row 6: Play
- Row 7: Delete

Row 0 (checkbox) is handled by the model via CheckStateRole.
Numeric editors use default delegate editors.
"""

from __future__ import annotations

from typing import Tuple

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal, QPoint
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QWidget


class SampleTableDelegate(QStyledItemDelegate):
    centerClicked = Signal(int)  # column
    fillClicked = Signal(int)  # column
    playClicked = Signal(int)  # column
    deleteClicked = Signal(int)  # column

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:  # type: ignore[override]
        row = index.row()
        if row not in (0, 1, 6, 7):
            return super().paint(painter, option, index)

        painter.save()
        try:
            rect = option.rect
            if row == 0:
                # Custom checkbox with white outline/check, centered
                self._paint_checkbox(painter, rect, index.data(Qt.CheckStateRole) == Qt.Checked)
            elif row == 1:
                self._paint_dual_button(painter, rect, "Center", "Fill")
            elif row == 6:
                self._paint_single_button(painter, rect, "▶")
            elif row == 7:
                self._paint_single_button(painter, rect, "×")
        finally:
            painter.restore()

    def editorEvent(self, event, model, option, index: QModelIndex):  # type: ignore[override]
        from PySide6.QtCore import QEvent
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            return super().editorEvent(event, model, option, index)
        if event.type() == QEvent.MouseButtonRelease:
            row = index.row()
            col = index.column()
            rect = option.rect
            if row == 0:
                # Toggle checkbox when released inside
                if rect.contains(event.position().toPoint()):  # type: ignore[attr-defined]
                    current = index.data(Qt.CheckStateRole) == Qt.Checked
                    model.setData(index, Qt.Unchecked if current else Qt.Checked, Qt.CheckStateRole)
                    return True
            elif row == 1:
                left, right = self._dual_button_rects(rect)
                pos = event.position().toPoint()  # type: ignore[attr-defined]
                if left.contains(pos):
                    self.centerClicked.emit(col)
                    return True
                if right.contains(pos):
                    self.fillClicked.emit(col)
                    return True
            elif row == 6:
                if rect.contains(event.position().toPoint()):  # type: ignore[attr-defined]
                    self.playClicked.emit(col)
                    return True
            elif row == 7:
                if rect.contains(event.position().toPoint()):  # type: ignore[attr-defined]
                    self.deleteClicked.emit(col)
                    return True
        return super().editorEvent(event, model, option, index)

    # Painting helpers
    def _paint_dual_button(self, painter: QPainter, rect: QRect, left_text: str, right_text: str) -> None:
        left, right = self._dual_button_rects(rect)
        self._draw_button(painter, left, left_text)
        self._draw_button(painter, right, right_text)

    def _paint_single_button(self, painter: QPainter, rect: QRect, text: str) -> None:
        self._draw_button(painter, rect.adjusted(6, 4, -6, -4), text)

    def _dual_button_rects(self, rect: QRect) -> Tuple[QRect, QRect]:
        inner = rect.adjusted(4, 4, -4, -4)
        mid_x = inner.x() + inner.width() // 2
        left = QRect(inner.x(), inner.y(), mid_x - inner.x() - 2, inner.height())
        right = QRect(mid_x + 2, inner.y(), inner.right() - (mid_x + 2) + 1, inner.height())
        return left, right

    def _draw_button(self, painter: QPainter, rect: QRect, text: str) -> None:
        radius = 4
        pen = QPen(QColor(180, 180, 180))
        brush = QBrush(QColor(60, 60, 60))
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(QColor(230, 230, 230))
        painter.drawText(rect, int(Qt.AlignCenter), text)

    def _paint_checkbox(self, painter: QPainter, rect: QRect, checked: bool) -> None:
        size = 18
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        box = QRect(x, y, size, size)
        radius = 4
        # Base button-like box (matches buttons style)
        painter.setPen(QPen(QColor(180, 180, 180)))
        painter.setBrush(QBrush(QColor(60, 60, 60)))
        painter.drawRoundedRect(box, radius, radius)
        # Thin white outline inside to make it visible on dark theme
        inner = box.adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(inner, radius - 1, radius - 1)
        if checked:
            # Draw white check mark
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            p1 = QPoint(inner.left() + 4, inner.top() + inner.height() // 2)
            p2 = QPoint(inner.left() + inner.width() // 2 - 1, inner.bottom() - 4)
            p3 = QPoint(inner.right() - 3, inner.top() + 4)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)


