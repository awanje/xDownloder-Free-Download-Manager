from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from app.cloud_sync import CloudSync
from app.storage import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, cloud_sync: CloudSync | None = None):
        super().__init__(parent)
        self.settings = settings
        self.cloud_sync = cloud_sync
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_cloud_tab(), "Cloud Sync")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # -------------------------------------------------------------- general
    def _build_general_tab(self) -> QWidget:
        self.dir_edit = QLineEdit(self.settings.download_dir)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        dir_row = QWidget()
        h = QHBoxLayout(dir_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.dir_edit)
        h.addWidget(browse_btn)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(self.settings.max_connections_per_download)

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.settings.max_concurrent_downloads)

        self.clipboard_check = QCheckBox("Monitor clipboard for downloadable links")
        self.clipboard_check.setChecked(self.settings.clipboard_monitor)

        form = QFormLayout()
        form.addRow("Default download folder:", dir_row)
        form.addRow("Connections per download:", self.conn_spin)
        form.addRow("Max simultaneous downloads:", self.concurrent_spin)
        form.addRow("", self.clipboard_check)

        w = QWidget()
        w.setLayout(form)
        return w

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    # ---------------------------------------------------------------- cloud
    def _build_cloud_tab(self) -> QWidget:
        outer = QVBoxLayout()

        config_box = QGroupBox("Supabase project")
        self.supabase_url_edit = QLineEdit(self.settings.supabase_url)
        self.supabase_url_edit.setPlaceholderText("https://xxxx.supabase.co")
        self.supabase_key_edit = QLineEdit(self.settings.supabase_anon_key)
        self.supabase_key_edit.setPlaceholderText("anon/public API key")
        config_form = QFormLayout(config_box)
        config_form.addRow("Project URL:", self.supabase_url_edit)
        config_form.addRow("Anon key:", self.supabase_key_edit)
        hint = QLabel(
            "Run supabase_schema.sql in your project's SQL Editor once, then paste\n"
            "the URL and anon key from Project Settings → API here."
        )
        hint.setStyleSheet("color: #666; font-size: 11px;")
        config_form.addRow("", hint)

        account_box = QGroupBox("Account")
        self.status_label = QLabel()
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("email@example.com")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("password")
        self.password_edit.setEchoMode(QLineEdit.Password)

        self.sign_in_btn = QPushButton("Sign In")
        self.sign_up_btn = QPushButton("Create Account")
        self.sign_out_btn = QPushButton("Sign Out")
        self.sign_in_btn.clicked.connect(self._do_sign_in)
        self.sign_up_btn.clicked.connect(self._do_sign_up)
        self.sign_out_btn.clicked.connect(self._do_sign_out)

        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.addWidget(self.sign_in_btn)
        brl.addWidget(self.sign_up_btn)
        brl.addWidget(self.sign_out_btn)

        account_form = QFormLayout(account_box)
        account_form.addRow("", self.status_label)
        account_form.addRow("Email:", self.email_edit)
        account_form.addRow("Password:", self.password_edit)
        account_form.addRow("", btn_row)

        outer.addWidget(config_box)
        outer.addWidget(account_box)
        outer.addStretch(1)

        w = QWidget()
        w.setLayout(outer)
        self._refresh_account_status()
        return w

    def _refresh_account_status(self):
        if not self.cloud_sync:
            self.status_label.setText("Cloud sync unavailable.")
            for b in (self.sign_in_btn, self.sign_up_btn, self.sign_out_btn):
                b.setEnabled(False)
            return
        if self.cloud_sync.is_signed_in:
            self.status_label.setText(f"Signed in as {self.cloud_sync.email}")
            self.sign_in_btn.setEnabled(False)
            self.sign_up_btn.setEnabled(False)
            self.sign_out_btn.setEnabled(True)
        else:
            self.status_label.setText("Not signed in — downloads stay local only.")
            self.sign_in_btn.setEnabled(True)
            self.sign_up_btn.setEnabled(True)
            self.sign_out_btn.setEnabled(False)

    def _apply_cloud_config(self):
        self.settings.supabase_url = self.supabase_url_edit.text().strip()
        self.settings.supabase_anon_key = self.supabase_key_edit.text().strip()
        self.settings.save()

    def _do_sign_in(self):
        self._apply_cloud_config()
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        if not email or not password:
            QMessageBox.warning(self, "Sign In", "Enter your email and password.")
            return
        err = self.cloud_sync.sign_in(email, password)
        if err:
            QMessageBox.warning(self, "Sign In Failed", err)
        else:
            self._refresh_account_status()

    def _do_sign_up(self):
        self._apply_cloud_config()
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        if not email or not password:
            QMessageBox.warning(self, "Create Account", "Enter an email and password.")
            return
        err = self.cloud_sync.sign_up(email, password)
        if err:
            QMessageBox.warning(self, "Create Account Failed", err)
        else:
            QMessageBox.information(
                self, "Almost there",
                "Account created. If your Supabase project requires email confirmation, "
                "check your inbox, then sign in.")
            self._refresh_account_status()

    def _do_sign_out(self):
        self.cloud_sync.sign_out()
        self._refresh_account_status()

    # ---------------------------------------------------------------- apply
    def apply(self):
        self.settings.download_dir = self.dir_edit.text().strip() or self.settings.download_dir
        self.settings.max_connections_per_download = self.conn_spin.value()
        self.settings.max_concurrent_downloads = self.concurrent_spin.value()
        self.settings.clipboard_monitor = self.clipboard_check.isChecked()
        self._apply_cloud_config()
