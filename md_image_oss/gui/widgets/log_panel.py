"""Read-only, auto-scrolling log panel with timestamps."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LogPanel(QPlainTextEdit):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(10000)
        font = QFont("Menlo")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.setFont(font)

    def append_line(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        for line in text.rstrip("\n").splitlines():
            self.appendPlainText(f"[{ts}] {line}")
        self.moveCursor(QTextCursor.End)

    def append_plain(self, text: str) -> None:
        self.appendPlainText(text)
        self.moveCursor(QTextCursor.End)
