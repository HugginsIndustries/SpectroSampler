"""High-performance table model for samples (columns) and 8 logical rows.

Rows:
0 Enable (checkbox)
1 Center/Fill (painted buttons via delegate)
2 Start (editable float)
3 End (editable float)
4 Duration (editable float)
5 Detector (label)
6 Play (painted button via delegate)
7 Delete (painted button via delegate)
"""

from __future__ import annotations

from typing import Any, List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, Signal, QTimer

from samplepacker.detectors.base import Segment


class SampleTableModel(QAbstractTableModel):
    """Table model mapping one sample per column and 8 logical rows.

    Supports incremental column reveal to avoid blocking the UI on large sets.
    """

    # Emitted after data-changing edits so the view/controller can react
    enabledToggled = Signal(int, bool)  # column, enabled
    timesEdited = Signal(int, float, float)  # column, start, end
    durationEdited = Signal(int, float)  # column, duration

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._segments: List[Segment] = []
        self._visible_count: int = 0
        self._chunk_timer: QTimer | None = None
        self._chunk_size: int = 300

    # Public API
    def set_segments(self, segments: List[Segment]) -> None:
        """Set the underlying segments; reveals columns incrementally.

        For very large lists, insert columns in chunks to keep UI responsive.
        """
        # Reset model structure
        self.beginResetModel()
        self._segments = list(segments) if segments else []
        self._visible_count = 0
        self.endResetModel()

        # Start incremental reveal
        self._start_chunk_timer()

    def update_segment_times(self, column: int, start: float, end: float) -> None:
        if 0 <= column < len(self._segments):
            seg = self._segments[column]
            seg.start = start
            seg.end = end
            top_left = self.index(2, column)
            bottom_right = self.index(4, column)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])

    def segments(self) -> List[Segment]:
        return self._segments

    # QAbstractTableModel overrides
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return 8

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return self._visible_count

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(section)
        # Vertical headers: fixed row labels
        labels = [
            "Enable",
            "Center",
            "Start",
            "End",
            "Duration",
            "Detector",
            "Play",
            "Delete",
        ]
        if 0 <= section < len(labels):
            return labels[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if col >= len(self._segments):
            return None
        seg = self._segments[col]

        if row == 0:
            if role == Qt.CheckStateRole:
                enabled = seg.attrs.get("enabled", True) if hasattr(seg, "attrs") and seg.attrs is not None else True
                return Qt.Checked if enabled else Qt.Unchecked
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        if row == 1:
            # Center/Fill buttons are painted by delegate
            if role == Qt.DisplayRole:
                return "Center/Fill"
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        if row == 2:
            if role in (Qt.DisplayRole, Qt.EditRole):
                return f"{seg.start:.3f}" if role == Qt.DisplayRole else seg.start
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        if row == 3:
            if role in (Qt.DisplayRole, Qt.EditRole):
                return f"{seg.end:.3f}" if role == Qt.DisplayRole else seg.end
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        if row == 4:
            if role in (Qt.DisplayRole, Qt.EditRole):
                dur = max(0.0, seg.end - seg.start)
                return f"{dur:.3f}" if role == Qt.DisplayRole else dur
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        if row == 5:
            if role == Qt.DisplayRole:
                return seg.detector
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        if row in (6, 7):
            if role == Qt.DisplayRole:
                return "▶" if row == 6 else "×"
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # type: ignore[override]
        if not index.isValid():
            return Qt.NoItemFlags
        row = index.row()
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if row == 0:
            return base | Qt.ItemIsUserCheckable
        if row in (2, 3, 4):
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:  # type: ignore[override]
        if not index.isValid():
            return False
        row = index.row()
        col = index.column()
        if not (0 <= col < len(self._segments)):
            return False
        seg = self._segments[col]

        if row == 0 and role == Qt.CheckStateRole:
            enabled = value == Qt.Checked
            if not hasattr(seg, "attrs") or seg.attrs is None:
                seg.attrs = {}
            seg.attrs["enabled"] = enabled
            self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])
            self.enabledToggled.emit(col, enabled)
            return True
        try:
            if row == 2 and role == Qt.EditRole:
                new_start = float(value)
                seg.start = max(0.0, new_start)
                # keep end >= start + epsilon
                if seg.end <= seg.start:
                    seg.end = seg.start + 0.01
                self.dataChanged.emit(self.index(2, col), self.index(4, col), [Qt.DisplayRole, Qt.EditRole])
                self.timesEdited.emit(col, seg.start, seg.end)
                return True
            if row == 3 and role == Qt.EditRole:
                new_end = float(value)
                seg.end = max(seg.start + 0.01, new_end)
                self.dataChanged.emit(self.index(2, col), self.index(4, col), [Qt.DisplayRole, Qt.EditRole])
                self.timesEdited.emit(col, seg.start, seg.end)
                return True
            if row == 4 and role == Qt.EditRole:
                new_duration = float(value)
                if new_duration > 0:
                    # Let controller decide how to apply; keep start same and extend end for now
                    seg.end = seg.start + new_duration
                    self.dataChanged.emit(self.index(2, col), self.index(4, col), [Qt.DisplayRole, Qt.EditRole])
                    self.durationEdited.emit(col, new_duration)
                    return True
        except Exception:
            return False
        return False

    # Internal: incremental reveal
    def _start_chunk_timer(self) -> None:
        total = len(self._segments)
        if total == 0:
            return
        if self._chunk_timer is None:
            self._chunk_timer = QTimer(self)
            self._chunk_timer.timeout.connect(self._reveal_chunk)
        if self._visible_count >= total:
            return
        if not self._chunk_timer.isActive():
            self._chunk_timer.start(0)  # as fast as possible without starving event loop

    def _reveal_chunk(self) -> None:
        total = len(self._segments)
        if self._visible_count >= total:
            if self._chunk_timer:
                self._chunk_timer.stop()
            return
        next_count = min(total, self._visible_count + self._chunk_size)
        # Insert columns [self._visible_count, next_count-1]
        self.beginInsertColumns(QModelIndex(), self._visible_count, next_count - 1)
        self._visible_count = next_count
        self.endInsertColumns()
        if self._visible_count >= total and self._chunk_timer:
            self._chunk_timer.stop()


