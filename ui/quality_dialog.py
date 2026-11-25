from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout,
)

from app.utils import format_size


class FormatProbeThread(QThread):
    done = Signal(list, str)   # choices, title
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
            choices = build_quality_choices(info)
            self.done.emit(choices, info.get("title") or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def build_quality_choices(info: dict) -> list[dict]:
    """Turn yt-dlp's format list into a small set of (label, selector, size) picks."""
    formats = info.get("formats") or []

    video_by_height: dict[int, int] = {}   # height -> best filesize seen
    best_audio_size = 0
    for f in formats:
        size = f.get("filesize") or f.get("filesize_approx") or 0
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        height = f.get("height")
        if vcodec and vcodec != "none" and height:
            if size > video_by_height.get(height, 0):
                video_by_height[height] = size
        elif (not vcodec or vcodec == "none") and acodec and acodec != "none":
            best_audio_size = max(best_audio_size, size)

    heights = sorted(video_by_height.keys(), reverse=True)
    choices = []
    for i, h in enumerate(heights):
        total = video_by_height[h] + best_audio_size
        label = f"{h}p" + (" (recommended)" if i == 0 else "")
        selector = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"
        choices.append({"label": label, "selector": selector, "size": total})

    if not choices:
        # Fall back to yt-dlp's own "best" resolution when no per-height
        # breakdown is available (e.g. some formats omit height metadata).
        choices.append({"label": "Best available", "selector": "bestvideo+bestaudio/best", "size": 0})

    if best_audio_size:
        choices.append({"label": "Audio only (M4A)", "selector": "bestaudio/best", "size": best_audio_size})

    return choices


class QualityDialog(QDialog):
    def __init__(self, task_title_hint: str, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Quality")
        self.setMinimumWidth(360)
        self.selected_selector: str | None = None

        self.info_label = QLabel(f"Fetching available qualities for:\n{task_title_hint or url}")
        self.info_label.setWordWrap(True)

        self.list_widget = QListWidget()
        self.list_widget.setEnabled(False)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.buttons)

        self._probe = FormatProbeThread(url, self)
        self._probe.done.connect(self._on_probed)
        self._probe.failed.connect(self._on_failed)
        self._probe.start()

    def _on_probed(self, choices: list[dict], title: str):
        if title:
            self.info_label.setText(f"Choose a quality for:\n{title}")
        self.list_widget.clear()
        for c in choices:
            size_txt = format_size(c["size"]) if c["size"] else "size unknown"
            item = QListWidgetItem(f"{c['label']}  —  {size_txt}")
            item.setData(1000, c["selector"])
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self.list_widget.setEnabled(True)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)

    def _on_failed(self, err: str):
        self.info_label.setText(f"Could not read video info:\n{err}")

    def _on_accept(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_selector = item.data(1000)
        self.accept()
