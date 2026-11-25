from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.engine import DownloadError, probe_url
from app.utils import filename_from_url, format_size


class ProbeThread(QThread):
    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            info = probe_url(self.url)
            self.done.emit(info)
        except DownloadError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class AddDownloadDialog(QDialog):
    def __init__(self, default_dir: str, parent=None, initial_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Add New Download")
        self.setMinimumWidth(460)
        self._probe_thread: ProbeThread | None = None
        self.probed_info: dict | None = None

        self.url_edit = QLineEdit(initial_url)
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        self.url_edit.textChanged.connect(self._reset_probe)

        self.filename_edit = QLineEdit()
        self.folder_edit = QLineEdit(default_dir)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)

        folder_row = QWidget()
        folder_layout = QVBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        from PySide6.QtWidgets import QHBoxLayout
        h = QHBoxLayout(inner)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.folder_edit)
        h.addWidget(browse_btn)
        folder_layout.addWidget(inner)

        self.info_label = QLabel("File size: checking…")
        self.info_label.setStyleSheet("color: #666;")

        self.start_now_check = QCheckBox("Start downloading now")
        self.start_now_check.setChecked(True)

        form = QFormLayout()
        form.addRow("URL:", self.url_edit)
        form.addRow("Save to:", folder_row)
        form.addRow("File name:", self.filename_edit)
        form.addRow("", self.info_label)
        form.addRow("", self.start_now_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if initial_url:
            self._start_probe()

        self.url_edit.editingFinished.connect(self._start_probe)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder", self.folder_edit.text())
        if d:
            self.folder_edit.setText(d)

    def _reset_probe(self):
        self.probed_info = None

    def _start_probe(self):
        url = self.url_edit.text().strip()
        if not url or not url.lower().startswith(("http://", "https://")):
            return
        self.info_label.setText("File size: checking…")
        self._probe_thread = ProbeThread(url, self)
        self._probe_thread.done.connect(self._on_probed)
        self._probe_thread.failed.connect(self._on_probe_failed)
        self._probe_thread.start()

    def _on_probed(self, info: dict):
        self.probed_info = info
        if not self.filename_edit.text().strip():
            self.filename_edit.setText(info["filename"])
        size_txt = format_size(info["size"]) if info["size"] > 0 else "Unknown"
        ranges_txt = "supports resume & multi-connection" if info["supports_ranges"] else "single connection only"
        self.info_label.setText(f"File size: {size_txt} ({ranges_txt})")

    def _on_probe_failed(self, err: str):
        self.info_label.setText(f"Could not read file info: {err}")

    def accept(self):
        url = self.url_edit.text().strip()
        if not url.lower().startswith(("http://", "https://")):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid http:// or https:// URL.")
            return
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "Missing folder", "Please choose a destination folder.")
            return
        if not self.filename_edit.text().strip():
            self.filename_edit.setText(filename_from_url(url))
        super().accept()

    def result_data(self) -> dict:
        return {
            "url": self.url_edit.text().strip(),
            "folder": self.folder_edit.text().strip(),
            "filename": self.filename_edit.text().strip(),
            "start": self.start_now_check.isChecked(),
        }
