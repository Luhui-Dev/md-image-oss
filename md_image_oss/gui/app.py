"""GUI entry point. Run via ``md-oss-gui`` (registered in pyproject.toml)."""

from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from .audit_log import AuditLogger
from .main_window import MainWindow
from . import settings_store
from .settings_dialog import SettingsDialog


def main() -> int:
    QCoreApplication.setOrganizationName(settings_store.ORG_NAME)
    QCoreApplication.setApplicationName(settings_store.APP_NAME)

    app = QApplication(sys.argv)
    # Allow Ctrl+C in terminal to quit
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    audit = AuditLogger()
    audit.app_start()

    # First-run wizard: if no usable config, prompt before showing main window
    if settings_store.load_config() is None:
        dlg = SettingsDialog(parent=None, first_run=True, audit=audit)
        dlg.exec()
        # User may have cancelled; main window still opens but Start will warn.

    window = MainWindow(audit=audit)
    window.show()

    rc = app.exec()
    audit.app_end()
    return rc


if __name__ == "__main__":
    sys.exit(main())
