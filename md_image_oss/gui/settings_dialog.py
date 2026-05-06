"""Settings dialog with three tabs and a 'Test connection' button.

On first launch (no saved config) the dialog shows a banner welcoming the
user and explaining the four required fields. Sensitive values flow through
``settings_store.save_config`` which writes them to the OS keyring.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Config, load_env_file
from . import settings_store
from .audit_log import AuditLogger

COMMON_ENDPOINTS = [
    "oss-cn-hangzhou.aliyuncs.com",
    "oss-cn-shanghai.aliyuncs.com",
    "oss-cn-beijing.aliyuncs.com",
    "oss-cn-shenzhen.aliyuncs.com",
    "oss-cn-guangzhou.aliyuncs.com",
    "oss-cn-chengdu.aliyuncs.com",
    "oss-cn-hongkong.aliyuncs.com",
    "oss-ap-southeast-1.aliyuncs.com",
    "oss-us-west-1.aliyuncs.com",
]

ALIYUN_RAM_HELP_URL = "https://ram.console.aliyun.com/manage/ak"


class SettingsDialog(QDialog):
    """Modal settings dialog. ``first_run=True`` shows a welcome banner."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        first_run: bool = False,
        audit: Optional[AuditLogger] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings — md-image-oss")
        self.setMinimumWidth(560)
        self._audit = audit

        layout = QVBoxLayout(self)

        if first_run:
            banner = QLabel(
                "<b>Welcome!</b><br>"
                "Before processing files, please fill in your Aliyun OSS credentials. "
                "Click <b>Test connection</b> at the bottom to verify."
            )
            banner.setWordWrap(True)
            banner.setStyleSheet(
                "QLabel { background: #fff7d6; padding: 10px; border-radius: 4px; }"
            )
            layout.addWidget(banner)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_credentials_tab(), "Credentials")
        tabs.addTab(self._build_bucket_tab(), "Bucket")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        layout.addWidget(tabs, 1)

        # Test connection row
        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(self._on_test_connection)
        self.test_status = QLabel("")
        self.test_status.setWordWrap(True)
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_status, 1)
        layout.addLayout(test_row)

        # Import / export
        io_row = QHBoxLayout()
        import_btn = QPushButton("Import .env…")
        import_btn.clicked.connect(self._on_import_env)
        export_btn = QPushButton("Export .env…")
        export_btn.clicked.connect(self._on_export_env)
        io_row.addWidget(import_btn)
        io_row.addWidget(export_btn)
        io_row.addStretch(1)
        layout.addLayout(io_row)

        # Standard buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_existing()

    # ----------------------------------------------------------------- tabs
    def _build_credentials_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.access_key_id_edit = QLineEdit()
        self.access_key_id_edit.setPlaceholderText("LTAI...")
        form.addRow("AccessKey ID *", self.access_key_id_edit)

        secret_row = QHBoxLayout()
        self.access_key_secret_edit = QLineEdit()
        self.access_key_secret_edit.setEchoMode(QLineEdit.Password)
        self.access_key_secret_edit.setPlaceholderText("(stored in system keychain)")
        toggle = QPushButton("Show")
        toggle.setCheckable(True)
        toggle.setFixedWidth(60)

        def _toggle(checked: bool) -> None:
            self.access_key_secret_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
            toggle.setText("Hide" if checked else "Show")

        toggle.toggled.connect(_toggle)
        secret_row.addWidget(self.access_key_secret_edit, 1)
        secret_row.addWidget(toggle)
        form.addRow("AccessKey Secret *", secret_row)

        help_link = QLabel(
            f'<a href="{ALIYUN_RAM_HELP_URL}">How do I get an AccessKey?</a>'
        )
        help_link.setOpenExternalLinks(True)
        form.addRow("", help_link)

        return w

    def _build_bucket_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.endpoint_combo = QComboBox()
        self.endpoint_combo.setEditable(True)
        self.endpoint_combo.addItems(COMMON_ENDPOINTS)
        self.endpoint_combo.setCurrentText("")
        form.addRow("Endpoint *", self.endpoint_combo)

        self.bucket_edit = QLineEdit()
        self.bucket_edit.setPlaceholderText("my-bucket")
        form.addRow("Bucket *", self.bucket_edit)

        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("e.g. images (optional)")
        form.addRow("Object prefix", self.prefix_edit)

        return w

    def _build_advanced_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignRight)

        self.custom_domain_edit = QLineEdit()
        self.custom_domain_edit.setPlaceholderText("https://cdn.example.com (optional)")
        form.addRow("Custom CDN domain", self.custom_domain_edit)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(85)
        form.addRow("Default JPEG/WebP quality", self.quality_spin)

        self.process_remote_check = QCheckBox(
            "Re-upload remote (http://, https://) image URLs as well"
        )
        form.addRow("", self.process_remote_check)

        self.no_compress_check = QCheckBox("Skip compression by default")
        form.addRow("", self.no_compress_check)

        self.backup_check = QCheckBox(
            "Auto-create .bak backup when overwriting original files"
        )
        self.backup_check.setChecked(True)
        form.addRow("", self.backup_check)

        return w

    # ------------------------------------------------------------- behaviour
    def _load_existing(self) -> None:
        cfg = settings_store.load_config()
        if cfg is not None:
            self.access_key_id_edit.setText(cfg.access_key_id)
            self.access_key_secret_edit.setText(cfg.access_key_secret)
            self.endpoint_combo.setCurrentText(cfg.endpoint)
            self.bucket_edit.setText(cfg.bucket)
            self.prefix_edit.setText(cfg.prefix)
            self.custom_domain_edit.setText(cfg.custom_domain)

        prefs = settings_store.load_preferences()
        self.quality_spin.setValue(prefs.quality)
        self.process_remote_check.setChecked(prefs.process_remote)
        self.no_compress_check.setChecked(prefs.no_compress)
        self.backup_check.setChecked(prefs.backup_on_overwrite)

    def _collect_config(self) -> Optional[Config]:
        access_key_id = self.access_key_id_edit.text().strip()
        access_key_secret = self.access_key_secret_edit.text().strip()
        endpoint = self.endpoint_combo.currentText().strip()
        bucket = self.bucket_edit.text().strip()
        prefix = self.prefix_edit.text().strip().strip("/")
        custom_domain = self.custom_domain_edit.text().strip().strip("/")
        if not (access_key_id and access_key_secret and endpoint and bucket):
            QMessageBox.warning(
                self,
                "Missing fields",
                "AccessKey ID, AccessKey Secret, Endpoint and Bucket are all required.",
            )
            return None
        return Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            endpoint=endpoint,
            bucket=bucket,
            prefix=prefix,
            custom_domain=custom_domain,
        )

    def _collect_preferences(self) -> settings_store.Preferences:
        prefs = settings_store.load_preferences()
        prefs.quality = int(self.quality_spin.value())
        prefs.process_remote = self.process_remote_check.isChecked()
        prefs.no_compress = self.no_compress_check.isChecked()
        prefs.backup_on_overwrite = self.backup_check.isChecked()
        return prefs

    # -------------------------------------------------------------- actions
    def _on_test_connection(self) -> None:
        cfg = self._collect_config()
        if cfg is None:
            return
        self.test_status.setText("Testing…")
        self.test_button.setEnabled(False)
        try:
            from ..uploader import OSSUploader
            uploader = OSSUploader(cfg)
            list(uploader.bucket.list_objects(max_keys=1).object_list)
            self.test_status.setText(
                "<span style='color:#1a7f37;'>✓ Connection successful</span>"
            )
            if self._audit:
                self._audit.connection_test(success=True)
        except Exception as e:
            self.test_status.setText(
                f"<span style='color:#cf222e;'>✗ {type(e).__name__}: {e}</span>"
            )
            if self._audit:
                self._audit.connection_test(success=False, error=str(e))
        finally:
            self.test_button.setEnabled(True)

    def _on_save(self) -> None:
        cfg = self._collect_config()
        if cfg is None:
            return
        prev = settings_store.load_config()
        settings_store.save_config(cfg)
        settings_store.save_preferences(self._collect_preferences())
        if self._audit:
            updated = []
            for field in ("access_key_id", "endpoint", "bucket", "prefix", "custom_domain"):
                if prev is None or getattr(prev, field) != getattr(cfg, field):
                    updated.append(field)
            if prev is None or prev.access_key_secret != cfg.access_key_secret:
                if "access_key_secret" not in updated:
                    updated.append("access_key_secret")
            self._audit.config_changed(fields_updated=updated)
        self.accept()

    def _on_import_env(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import .env file", "", "Env files (*.env);;All files (*)"
        )
        if not path:
            return
        try:
            load_env_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        if os.getenv("OSS_ACCESS_KEY_ID"):
            self.access_key_id_edit.setText(os.environ["OSS_ACCESS_KEY_ID"])
        if os.getenv("OSS_ACCESS_KEY_SECRET"):
            self.access_key_secret_edit.setText(os.environ["OSS_ACCESS_KEY_SECRET"])
        if os.getenv("OSS_ENDPOINT"):
            self.endpoint_combo.setCurrentText(os.environ["OSS_ENDPOINT"])
        if os.getenv("OSS_BUCKET"):
            self.bucket_edit.setText(os.environ["OSS_BUCKET"])
        if os.getenv("OSS_PREFIX"):
            self.prefix_edit.setText(os.environ["OSS_PREFIX"])
        if os.getenv("OSS_CUSTOM_DOMAIN"):
            self.custom_domain_edit.setText(os.environ["OSS_CUSTOM_DOMAIN"])
        QMessageBox.information(self, "Import complete", f"Loaded fields from {path}.")

    def _on_export_env(self) -> None:
        cfg = self._collect_config()
        if cfg is None:
            return
        confirm = QMessageBox.warning(
            self,
            "Export .env (plaintext)",
            "The exported file will contain your AccessKey Secret in plaintext. "
            "Store it securely.\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export .env file", "md-image-oss.env", "Env files (*.env);;All files (*)"
        )
        if not path:
            return
        lines = [
            f"OSS_ACCESS_KEY_ID={cfg.access_key_id}",
            f"OSS_ACCESS_KEY_SECRET={cfg.access_key_secret}",
            f"OSS_ENDPOINT={cfg.endpoint}",
            f"OSS_BUCKET={cfg.bucket}",
        ]
        if cfg.prefix:
            lines.append(f"OSS_PREFIX={cfg.prefix}")
        if cfg.custom_domain:
            lines.append(f"OSS_CUSTOM_DOMAIN={cfg.custom_domain}")
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        QMessageBox.information(self, "Export complete", f"Wrote {path}")
