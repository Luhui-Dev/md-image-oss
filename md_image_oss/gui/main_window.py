"""Main window: toolbar, file list, options row, log panel, status bar.

Wires together SettingsDialog, ProcessorWorker, FileListWidget, LogPanel
and the AuditViewer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from .audit_log import AuditLogger
from .audit_viewer import AuditViewer
from .settings_dialog import SettingsDialog
from . import settings_store
from .widgets.file_list import FileListWidget
from .widgets.log_panel import LogPanel
from .worker import ProcessOptions, ProcessorWorker


class MainWindow(QMainWindow):
    def __init__(self, audit: AuditLogger, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audit = audit
        self.worker: Optional[ProcessorWorker] = None

        self.setWindowTitle(f"md-image-oss — v{__version__}")
        self.resize(960, 720)

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._build_menu()

        self._refresh_action_state()
        prefs = settings_store.load_preferences()
        self.in_place_check.setChecked(prefs.in_place_default)

    # ----------------------------------------------------------- UI assembly
    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        act_add_files = QAction("＋ Add files", self)
        act_add_files.triggered.connect(self._on_add_files)
        tb.addAction(act_add_files)

        act_add_folder = QAction("＋ Add folder", self)
        act_add_folder.triggered.connect(self._on_add_folder)
        tb.addAction(act_add_folder)

        act_clear = QAction("Clear", self)
        act_clear.triggered.connect(self._on_clear)
        tb.addAction(act_clear)

        tb.addSeparator()

        act_settings = QAction("⚙ Settings…", self)
        act_settings.setShortcut(QKeySequence.Preferences)
        act_settings.triggered.connect(self._on_open_settings)
        tb.addAction(act_settings)

        act_audit = QAction("📋 Audit log…", self)
        act_audit.triggered.connect(self._on_open_audit)
        tb.addAction(act_audit)

        self._action_clear = act_clear
        self._action_add_files = act_add_files
        self._action_add_folder = act_add_folder

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        a_quit = QAction("Quit", self)
        a_quit.setShortcut(QKeySequence.Quit)
        a_quit.triggered.connect(self.close)
        file_menu.addAction(a_quit)

        edit_menu = menubar.addMenu("&Edit")
        a_pref = QAction("Settings…", self)
        a_pref.setShortcut(QKeySequence.Preferences)
        a_pref.triggered.connect(self._on_open_settings)
        edit_menu.addAction(a_pref)

        view_menu = menubar.addMenu("&View")
        a_audit = QAction("Audit log…", self)
        a_audit.triggered.connect(self._on_open_audit)
        view_menu.addAction(a_audit)

        help_menu = menubar.addMenu("&Help")
        a_about = QAction("About", self)
        a_about.triggered.connect(self._on_about)
        help_menu.addAction(a_about)

    def _build_central(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)

        # Top splitter: file list above, log below
        splitter = QSplitter(Qt.Vertical, central)

        self.file_list = FileListWidget()
        self.file_list.files_changed.connect(self._refresh_action_state)
        splitter.addWidget(self.file_list)

        self.log_panel = LogPanel()
        splitter.addWidget(self.log_panel)
        splitter.setSizes([460, 220])
        outer.addWidget(splitter, 1)

        # Options + start row
        opts_row = QHBoxLayout()
        self.in_place_check = QCheckBox("Overwrite original files (.bak backup is created)")
        self.dry_run_check = QCheckBox("Dry-run (don't write files)")
        opts_row.addWidget(self.in_place_check)
        opts_row.addWidget(self.dry_run_check)
        opts_row.addStretch(1)

        self.start_button = QPushButton("▶ Start")
        self.start_button.setMinimumWidth(120)
        self.start_button.clicked.connect(self._on_start_or_cancel)
        opts_row.addWidget(self.start_button)

        outer.addLayout(opts_row)

        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label, 1)

    # ----------------------------------------------------------------- DnD
    # Forward window-level drops to the file list.
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()]
        added = self.file_list.add_paths(paths)
        if added:
            event.acceptProposedAction()

    # -------------------------------------------------------- toolbar actions
    def _on_add_files(self) -> None:
        prefs = settings_store.load_preferences()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files",
            prefs.last_input_dir,
            "Documents (*.md *.mdx *.html *.htm);;All files (*)",
        )
        if not files:
            return
        paths = [Path(f) for f in files]
        self.file_list.add_paths(paths)
        prefs.last_input_dir = str(paths[0].parent)
        settings_store.save_preferences(prefs)

    def _on_add_folder(self) -> None:
        prefs = settings_store.load_preferences()
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder (recursed)", prefs.last_input_dir
        )
        if not folder:
            return
        self.file_list.add_paths([Path(folder)])
        prefs.last_input_dir = folder
        settings_store.save_preferences(prefs)

    def _on_clear(self) -> None:
        self.file_list.clear()

    def _on_open_settings(self) -> None:
        dlg = SettingsDialog(self, audit=self.audit)
        dlg.exec()
        self._refresh_action_state()

    def _on_open_audit(self) -> None:
        viewer = AuditViewer(self)
        viewer.show()

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About md-image-oss",
            f"<b>md-image-oss</b> v{__version__}<br>"
            "Upload Markdown / MDX / HTML images to Aliyun OSS.<br><br>"
            "Logs and audit records are stored under your platform's user-log "
            "directory.",
        )

    # ---------------------------------------------------------------- start
    def _on_start_or_cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            # cancel
            self.worker.cancel_requested = True
            self.start_button.setEnabled(False)
            self.start_button.setText("Cancelling…")
            self.statusBar().showMessage("Cancelling — current file will finish first")
            return

        if self.file_list.file_count() == 0:
            QMessageBox.information(self, "No files", "Add some files first.")
            return

        config = settings_store.load_config()
        if config is None:
            QMessageBox.warning(
                self,
                "Configuration required",
                "OSS credentials are not yet set. Open Settings to configure.",
            )
            self._on_open_settings()
            return

        # Confirm overwrite
        if self.in_place_check.isChecked() and not self.dry_run_check.isChecked():
            confirm = QMessageBox.question(
                self,
                "Overwrite originals?",
                f"You are about to overwrite {self.file_list.file_count()} file(s) "
                "in place. A .bak backup will be created next to each file."
                if settings_store.load_preferences().backup_on_overwrite
                else "<b>WARNING:</b> Backups are disabled in Settings. "
                f"Originals of {self.file_list.file_count()} file(s) will be replaced.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if confirm != QMessageBox.Yes:
                return

        prefs = settings_store.load_preferences()
        options = ProcessOptions(
            in_place=self.in_place_check.isChecked(),
            dry_run=self.dry_run_check.isChecked(),
            backup_on_overwrite=prefs.backup_on_overwrite,
            quality=prefs.quality,
            process_remote=prefs.process_remote,
            no_compress=prefs.no_compress,
        )

        # Persist user's in_place choice as new default
        prefs.in_place_default = options.in_place
        settings_store.save_preferences(prefs)

        self.file_list.reset_statuses()
        self.log_panel.clear()
        self.log_panel.append_plain(
            f"Starting batch: {self.file_list.file_count()} file(s)"
        )
        if options.dry_run:
            self.log_panel.append_plain("Dry-run mode: no files will be written")

        self.worker = ProcessorWorker(
            files=[e.path for e in self.file_list.entries()],
            options=options,
            config=config,
            audit=self.audit,
            parent=self,
        )
        self.worker.file_started.connect(self._on_file_started)
        self.worker.file_finished.connect(self._on_file_finished)
        self.worker.log_line.connect(self.log_panel.append_line)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.start()
        self._set_processing_ui(True)

    # ------------------------------------------------------------- callbacks
    def _on_file_started(self, row: int) -> None:
        self.file_list.set_status(row, status="Processing…")
        self.statusBar().showMessage(
            f"Processing {row + 1}/{self.file_list.file_count()}"
        )

    def _on_file_finished(self, row: int, result: dict) -> None:
        stats = result.get("stats", {}) or {}
        if result["status"] == "success":
            self.file_list.set_status(
                row,
                status="Done",
                found=stats.get("found", 0),
                uploaded=stats.get("uploaded", 0),
                failed=stats.get("failed", 0),
            )
        else:
            self.file_list.set_status(
                row,
                status="Failed",
                error=result.get("error", ""),
                found=stats.get("found", 0),
                uploaded=stats.get("uploaded", 0),
                failed=stats.get("failed", 0),
            )

    def _on_batch_finished(self, summary: dict) -> None:
        self._set_processing_ui(False)
        success = summary.get("success", 0)
        failed = summary.get("failed", 0)
        cancelled = summary.get("cancelled", 0)
        msg = f"Batch finished — {success} succeeded, {failed} failed"
        if cancelled:
            msg += f", {cancelled} cancelled"
        self.statusBar().showMessage(msg)
        self.log_panel.append_plain(msg)
        QMessageBox.information(self, "Batch complete", msg)

    # ----------------------------------------------------------------- misc
    def _set_processing_ui(self, processing: bool) -> None:
        self._action_add_files.setEnabled(not processing)
        self._action_add_folder.setEnabled(not processing)
        self._action_clear.setEnabled(not processing)
        self.in_place_check.setEnabled(not processing)
        self.dry_run_check.setEnabled(not processing)
        self.start_button.setEnabled(True)
        self.start_button.setText("⏹ Cancel" if processing else "▶ Start")

    def _refresh_action_state(self) -> None:
        has_files = self.file_list.file_count() > 0
        self.start_button.setEnabled(has_files)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            confirm = QMessageBox.question(
                self,
                "Quit while processing?",
                "Processing is in progress. Cancel and quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel_requested = True
            self.worker.wait(5000)
        super().closeEvent(event)
