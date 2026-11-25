from __future__ import annotations

import os
import re
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QStatusBar,
    QSystemTrayIcon, QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout,
    QWidget, QApplication, QStyle,
)

from app.cloud_sync import CloudSync
from app.manager import DownloadManager
from app.models import Status
from app.storage import Settings
from app.utils import format_eta, format_size, format_speed
from ui.add_dialog import AddDownloadDialog
from ui.quality_dialog import QualityDialog
from ui.settings_dialog import SettingsDialog

COLUMNS = ["Name", "Size", "Progress", "Status", "Speed", "Time Left", "Added"]

URL_RE = re.compile(r"https?://\S+\.\S+", re.IGNORECASE)
DOWNLOADABLE_EXT = (
    ".zip", ".rar", ".7z", ".exe", ".msi", ".iso", ".mp4", ".mkv", ".avi",
    ".mp3", ".flac", ".pdf", ".docx", ".xlsx", ".pptx", ".tar", ".gz", ".dmg",
    ".apk", ".csv", ".json",
)


class MainWindow(QMainWindow):
    updated = Signal()
    quality_needed = Signal(str)

    def __init__(self, settings: Settings, manager: DownloadManager, cloud_sync: CloudSync):
        super().__init__()
        self.setWindowTitle("X Downloader")
        self.resize(980, 560)

        self.settings = settings
        self.manager = manager
        self.cloud_sync = cloud_sync
        self.manager.add_listener(self._on_manager_update)
        self.manager.add_quality_listener(self._on_quality_needed)
        self.updated.connect(self._refresh_table, Qt.QueuedConnection)
        self.quality_needed.connect(self._show_quality_dialog, Qt.QueuedConnection)

        self._build_ui()
        self._build_tray()

        self._last_clipboard_text = ""
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self._check_clipboard)
        self.clipboard_timer.start(1500)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_table)
        self.refresh_timer.start(1000)

        self._refresh_table()
        self.manager._try_start_queued()
        for task in list(self.manager.tasks):
            if task.status == Status.SELECT_QUALITY:
                self._show_quality_dialog(task.id)

    # -------------------------------------------------------------- build
    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(toolbar)

        style = self.style()

        def act(text: str, icon: QStyle.StandardPixmap, slot):
            a = QAction(style.standardIcon(icon), text, self)
            a.triggered.connect(slot)
            toolbar.addAction(a)
            return a

        act("Add URL", QStyle.SP_FileDialogNewFolder, lambda: self.add_download())
        toolbar.addSeparator()
        act("Resume", QStyle.SP_MediaPlay, self.resume_selected)
        act("Pause", QStyle.SP_MediaPause, self.pause_selected)
        act("Cancel", QStyle.SP_MediaStop, self.cancel_selected)
        act("Delete", QStyle.SP_TrashIcon, self.delete_selected)
        toolbar.addSeparator()
        act("Open File", QStyle.SP_FileIcon, self.open_selected_file)
        act("Open Folder", QStyle.SP_DirOpenIcon, self.open_selected_folder)
        toolbar.addSeparator()
        act("Settings", QStyle.SP_FileDialogDetailedView, self.open_settings)

        toolbar.addSeparator()
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            ["All", "Select Quality", "Downloading", "Queued", "Paused", "Completed", "Error"])
        self.filter_combo.currentTextChanged.connect(self._refresh_table)
        toolbar.addWidget(QLabel("  Filter: "))
        toolbar.addWidget(self.filter_combo)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(lambda _index: self._on_row_double_clicked())

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.account_label = QLabel()
        self.account_label.setStyleSheet("color: #57606a; padding: 0 8px;")
        self.status_bar.addPermanentWidget(self.account_label)
        self._update_account_label()

    def _build_tray(self):
        icon = self.style().standardIcon(QStyle.SP_ArrowDown)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("X Downloader")
        menu = QMenu()
        show_action = menu.addAction("Show")
        show_action.triggered.connect(self.showNormal)
        quit_action = menu.addAction("Exit")
        quit_action.triggered.connect(QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.showNormal() if reason == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    # ------------------------------------------------------------- actions
    def add_download(self, url: str = ""):
        dlg = AddDownloadDialog(self.settings.download_dir, self, initial_url=url)
        if dlg.exec():
            data = dlg.result_data()
            self.manager.add(data["url"], dest_folder=data["folder"],
                              filename=data["filename"], start=data["start"])

    def _selected_ids(self) -> list[str]:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        ids = []
        for row in rows:
            item = self.table.item(row, 0)
            if item:
                ids.append(item.data(Qt.UserRole))
        return ids

    def resume_selected(self):
        for tid in self._selected_ids():
            self.manager.resume(tid)

    def pause_selected(self):
        ids = self._selected_ids()
        has_stream = any(
            (t := self.manager.get(tid)) and t.kind == "stream" and t.status == Status.DOWNLOADING
            for tid in ids
        )
        if has_stream:
            resp = QMessageBox.question(
                self, "Can't pause a stream",
                "Video/audio streams can't be paused mid-download — pausing will "
                "cancel it instead (you can restart it from scratch with Resume). Continue?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return
        for tid in ids:
            self.manager.pause(tid)

    def cancel_selected(self):
        for tid in self._selected_ids():
            self.manager.cancel(tid)

    def delete_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        resp = QMessageBox.question(
            self, "Delete downloads",
            f"Remove {len(ids)} download(s) from the list? Also delete the file(s) on disk?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if resp == QMessageBox.Cancel:
            return
        delete_file = resp == QMessageBox.Yes
        for tid in ids:
            self.manager.remove(tid, delete_file=delete_file)

    def _on_row_double_clicked(self):
        ids = self._selected_ids()
        if ids:
            task = self.manager.get(ids[0])
            if task and task.status == Status.SELECT_QUALITY:
                self._show_quality_dialog(task.id)
                return
        self.open_selected_folder()

    def open_selected_file(self):
        for tid in self._selected_ids():
            task = self.manager.get(tid)
            if task and os.path.exists(task.dest_path):
                os.startfile(task.dest_path)  # noqa: S606 - user-initiated, local file

    def open_selected_folder(self):
        for tid in self._selected_ids():
            task = self.manager.get(tid)
            if task and os.path.isdir(task.dest_folder):
                subprocess.Popen(["explorer", task.dest_folder])
            break

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self, cloud_sync=self.cloud_sync)
        if dlg.exec():
            dlg.apply()
        self._update_account_label()

    def _show_context_menu(self, pos):
        if not self.table.itemAt(pos):
            return
        menu = QMenu(self)
        menu.addAction("Resume", self.resume_selected)
        menu.addAction("Pause", self.pause_selected)
        menu.addAction("Cancel", self.cancel_selected)
        menu.addAction("Delete", self.delete_selected)
        menu.addSeparator()
        menu.addAction("Open File", self.open_selected_file)
        menu.addAction("Open Containing Folder", self.open_selected_folder)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _update_account_label(self):
        if self.cloud_sync.is_signed_in:
            self.account_label.setText(f"☁ Synced as {self.cloud_sync.email}")
        elif self.cloud_sync.is_configured:
            self.account_label.setText("☁ Not signed in")
        else:
            self.account_label.setText("")

    # --------------------------------------------------------------- table
    def _on_manager_update(self):
        self.updated.emit()

    def _on_quality_needed(self, task):
        self.quality_needed.emit(task.id)

    def _show_quality_dialog(self, task_id: str):
        task = self.manager.get(task_id)
        if not task or task.status != Status.SELECT_QUALITY:
            return
        dlg = QualityDialog(task.filename, task.url, self)
        if dlg.exec() and dlg.selected_selector:
            self.manager.set_format_and_start(task_id, dlg.selected_selector)
        else:
            self.manager.remove(task_id)

    def _refresh_table(self):
        filt = self.filter_combo.currentText()
        tasks = self.manager.tasks
        if filt != "All":
            tasks = [t for t in tasks if t.status.value == filt]
        tasks = sorted(tasks, key=lambda t: t.created_at, reverse=True)

        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            name_item = QTableWidgetItem(task.filename or task.url)
            name_item.setData(Qt.UserRole, task.id)
            self.table.setItem(row, 0, name_item)

            if task.kind == "stream":
                size_text = format_eta(task.stream_duration) if task.stream_duration > 0 else "Live/Unknown"
            else:
                size_text = format_size(task.total_size)
            self.table.setItem(row, 1, QTableWidgetItem(size_text))

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(task.progress * 100))
            bar.setTextVisible(True)
            self.table.setCellWidget(row, 2, bar)

            status_item = QTableWidgetItem(task.status.value if not task.error else f"Error: {task.error[:40]}")
            status_item.setForeground(self._status_color(task.status))
            self.table.setItem(row, 3, status_item)

            if task.kind == "stream":
                speed_text = task.extra_info or ("Working…" if task.status in
                                                  (Status.CONNECTING, Status.DOWNLOADING) else "-")
                eta_text = "-"
            else:
                speed_text = format_speed(task.speed_bps) if task.status == Status.DOWNLOADING else "-"
                eta_text = format_eta(task.eta_seconds) if task.status == Status.DOWNLOADING else "-"
            self.table.setItem(row, 4, QTableWidgetItem(speed_text))
            self.table.setItem(row, 5, QTableWidgetItem(eta_text))
            from datetime import datetime
            self.table.setItem(row, 6, QTableWidgetItem(
                datetime.fromtimestamp(task.created_at).strftime("%Y-%m-%d %H:%M")))

        active = self.manager.active_count()
        total_speed = sum(w.current_speed() for w in self.manager.workers.values())
        self.status_bar.showMessage(
            f"{len(self.manager.tasks)} total   |   {active} active   |   {format_speed(total_speed)}"
        )
        self._update_account_label()

    @staticmethod
    def _status_color(status: Status) -> QColor:
        return {
            Status.COMPLETED: QColor("#1a7f37"),
            Status.ERROR: QColor("#cf222e"),
            Status.CANCELLED: QColor("#57606a"),
            Status.DOWNLOADING: QColor("#0969da"),
            Status.PAUSED: QColor("#9a6700"),
            Status.SELECT_QUALITY: QColor("#8250df"),
        }.get(status, QColor("#24292f"))

    # ----------------------------------------------------------- clipboard
    def _check_clipboard(self):
        if not self.settings.clipboard_monitor:
            return
        text = QApplication.clipboard().text().strip()
        if not text or text == self._last_clipboard_text:
            return
        self._last_clipboard_text = text
        match = URL_RE.search(text)
        if not match:
            return
        url = match.group(0)
        if not url.lower().endswith(DOWNLOADABLE_EXT):
            return
        if any(t.url == url for t in self.manager.tasks):
            return
        resp = QMessageBox.question(
            self, "Download link detected",
            f"Clipboard contains a downloadable link:\n\n{url}\n\nAdd it to Download Manager?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.add_download(url)

    # ------------------------------------------------------------- closing
    def closeEvent(self, event):
        self.manager.shutdown()
        self.tray.hide()
        event.accept()
