"""Audit log viewer window — table of recent file_processed records.

By design no "clear" button is provided; the audit log is meant to be
append-only. Users who need to delete records can manually remove the
files via the "Open log folder" button.
"""

from __future__ import annotations

import csv
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import audit_log

COLUMNS = ("Time", "Event", "Input", "Output", "Mode", "Found", "Uploaded", "Failed", "Status", "Error")
DEFAULT_LIMIT = 1000


class AuditViewer(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Audit log — md-image-oss")
        self.resize(1024, 600)

        layout = QVBoxLayout(self)

        # Toolbar row
        bar = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open log folder")
        self.open_folder_btn.clicked.connect(self._open_folder)
        bar.addWidget(self.open_folder_btn)

        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export_csv)
        bar.addWidget(self.export_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._reload)
        bar.addWidget(self.refresh_btn)

        bar.addStretch(1)
        self.summary_label = QLabel()
        bar.addWidget(self.summary_label)
        layout.addLayout(bar)

        # Table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self._records: list[dict] = []
        self._reload()

    # ----------------------------------------------------------------- data
    def _reload(self) -> None:
        self._records = list(audit_log.iter_records(limit=DEFAULT_LIMIT))
        rows_to_show = [r for r in self._records if r.get("event") == "file_processed"]
        self.table.setRowCount(len(rows_to_show))
        for i, rec in enumerate(rows_to_show):
            self._populate_row(i, rec)
        self.summary_label.setText(
            f"Showing {len(rows_to_show)} file events (loaded {len(self._records)} records)"
        )
        self.table.resizeColumnsToContents()

    def _populate_row(self, row: int, rec: dict) -> None:
        stats = rec.get("stats") or {}
        values = [
            rec.get("ts", ""),
            rec.get("event", ""),
            rec.get("input", "") or "",
            rec.get("output", "") or "",
            rec.get("mode", "") or "",
            str(stats.get("found", "")) if stats else "",
            str(stats.get("uploaded", "")) if stats else "",
            str(stats.get("failed", "")) if stats else "",
            rec.get("status", "") or "",
            rec.get("error", "") or "",
        ]
        for col, val in enumerate(values):
            item = QTableWidgetItem(str(val))
            if col == 8 and rec.get("status") == "error":
                item.setForeground(Qt.red)
            self.table.setItem(row, col, item)

    # -------------------------------------------------------------- actions
    def _open_folder(self) -> None:
        d = audit_log.open_log_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "audit-export.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(COLUMNS)
                for r in range(self.table.rowCount()):
                    row = [
                        self.table.item(r, c).text() if self.table.item(r, c) else ""
                        for c in range(len(COLUMNS))
                    ]
                    writer.writerow(row)
            QMessageBox.information(self, "Export complete", f"Wrote {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
