"""Drag-and-drop file list with per-row status, used in MainWindow.

Public surface:
- ``FileEntry`` dataclass — one row's data
- ``FileListWidget(QWidget)`` — adds/clears files, emits ``files_changed``,
  exposes ``set_status(row, ...)`` for the worker to update.

Files are deduplicated by absolute path. Drops accept files or folders;
folders are recursed for ``.md / .mdx / .html / .htm``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableView,
    QVBoxLayout,
    QWidget,
)


SUPPORTED_SUFFIXES = {".md", ".mdx", ".html", ".htm"}


@dataclass
class FileEntry:
    path: Path
    status: str = "Ready"
    found: int = 0
    uploaded: int = 0
    failed: int = 0
    error: str = ""


def _expand(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for p in paths:
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in SUPPORTED_SUFFIXES:
                    f = f.resolve()
                    if f not in seen:
                        seen.add(f)
                        out.append(f)
        elif p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            f = p.resolve()
            if f not in seen:
                seen.add(f)
                out.append(f)
    return out


COLUMNS = ("File", "Path", "Status", "Found", "Uploaded", "Failed")


class _FileTableModel(QAbstractTableModel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.entries: list[FileEntry] = []

    # Qt model API
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        e = self.entries[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return e.path.name
            if col == 1:
                return str(e.path.parent)
            if col == 2:
                return e.status if not e.error else f"{e.status}: {e.error}"
            if col == 3:
                return e.found if e.status not in ("Ready",) else ""
            if col == 4:
                return e.uploaded if e.status not in ("Ready",) else ""
            if col == 5:
                return e.failed if e.status not in ("Ready",) else ""
        if role == Qt.ToolTipRole:
            if col == 1:
                return str(e.path)
            if col == 2 and e.error:
                return e.error
        return None

    # Mutators
    def add(self, paths: list[Path]) -> int:
        existing = {e.path for e in self.entries}
        new_entries = [FileEntry(path=p) for p in paths if p not in existing]
        if not new_entries:
            return 0
        first = len(self.entries)
        last = first + len(new_entries) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self.entries.extend(new_entries)
        self.endInsertRows()
        return len(new_entries)

    def clear(self) -> None:
        if not self.entries:
            return
        self.beginResetModel()
        self.entries.clear()
        self.endResetModel()

    def remove_rows(self, rows: list[int]) -> None:
        for r in sorted(rows, reverse=True):
            if 0 <= r < len(self.entries):
                self.beginRemoveRows(QModelIndex(), r, r)
                del self.entries[r]
                self.endRemoveRows()

    def update_row(self, row: int, **kwargs) -> None:
        if not (0 <= row < len(self.entries)):
            return
        e = self.entries[row]
        for k, v in kwargs.items():
            setattr(e, k, v)
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, len(COLUMNS) - 1),
        )


class FileListWidget(QWidget):
    files_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.model = _FileTableModel(self)
        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(False)
        self.view.verticalHeader().setVisible(False)
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        # Empty-state placeholder painted via setShowGrid + style
        self.view.setShowGrid(False)
        layout.addWidget(self.view, 1)

    # ----------------------------------------------------------------- DnD
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        paths = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()]
        added = self.add_paths(paths)
        if added:
            event.acceptProposedAction()

    # ----------------------------------------------------------------- API
    def add_paths(self, paths: list[Path]) -> int:
        added = self.model.add(_expand(paths))
        if added:
            self.files_changed.emit()
        return added

    def clear(self) -> None:
        had = bool(self.model.entries)
        self.model.clear()
        if had:
            self.files_changed.emit()

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.view.selectionModel().selectedRows()})
        if not rows:
            return
        self.model.remove_rows(rows)
        self.files_changed.emit()

    def entries(self) -> list[FileEntry]:
        return list(self.model.entries)

    def file_count(self) -> int:
        return len(self.model.entries)

    def reset_statuses(self) -> None:
        for i, _ in enumerate(self.model.entries):
            self.model.update_row(
                i, status="Ready", found=0, uploaded=0, failed=0, error=""
            )

    def set_status(self, row: int, **kwargs) -> None:
        self.model.update_row(row, **kwargs)
