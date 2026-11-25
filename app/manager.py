"""Queue and lifecycle management for download tasks."""
from __future__ import annotations

import os
import threading
from typing import Callable, Optional

from .engine import is_youtube_url, make_worker
from .models import DownloadTask, Status
from .storage import Settings, load_tasks, save_tasks
from .utils import unique_path

Listener = Callable[[], None]

STREAM_EXTENSIONS = (".m3u8", ".mpd")


def _infer_kind(url: str) -> str:
    if is_youtube_url(url):
        return "ytdlp"
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    return "stream" if path.endswith(STREAM_EXTENSIONS) else "http"


class DownloadManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.RLock()
        self.tasks: list[DownloadTask] = load_tasks()
        self.workers: dict[str, object] = {}
        self._listeners: list[Listener] = []
        self._quality_listeners: list[Callable[[DownloadTask], None]] = []

    # ------------------------------------------------------------ observer
    def add_listener(self, fn: Listener):
        self._listeners.append(fn)

    def add_quality_listener(self, fn: Callable[[DownloadTask], None]):
        """fn is called when a new YouTube task needs a quality choice before
        it can start. The listener is responsible for eventually calling
        set_format_and_start() (or remove()) for that task."""
        self._quality_listeners.append(fn)

    def _notify(self):
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass

    def _notify_quality_needed(self, task: DownloadTask):
        for fn in list(self._quality_listeners):
            try:
                fn(task)
            except Exception:
                pass

    def _persist(self):
        with self._lock:
            save_tasks(self.tasks)

    # ------------------------------------------------------------------ add
    def add(self, url: str, dest_folder: Optional[str] = None,
            filename: Optional[str] = None, start: bool = True,
            kind: Optional[str] = None, stream_headers: Optional[dict] = None,
            format_selector: Optional[str] = None) -> DownloadTask:
        folder = dest_folder or self.settings.download_dir
        os.makedirs(folder, exist_ok=True)
        if filename:
            folder, filename = unique_path(folder, filename)
        resolved_kind = kind or _infer_kind(url)
        needs_quality = resolved_kind == "ytdlp" and format_selector is None and self._quality_listeners
        task = DownloadTask(
            url=url,
            dest_folder=folder,
            filename=filename or "",
            num_connections=self.settings.max_connections_per_download,
            status=Status.SELECT_QUALITY if needs_quality else Status.QUEUED,
            kind=resolved_kind,
            stream_headers=stream_headers or {},
            format_selector=format_selector,
        )
        with self._lock:
            self.tasks.append(task)
            self._persist()
        self._notify()
        if needs_quality:
            self._notify_quality_needed(task)
        elif start:
            self._try_start_queued()
        return task

    def set_format_and_start(self, task_id: str, format_selector: str):
        task = self.get(task_id)
        if not task or task.status != Status.SELECT_QUALITY:
            return
        task.format_selector = format_selector
        task.status = Status.QUEUED
        self._persist()
        self._notify()
        self._try_start_queued()

    # --------------------------------------------------------------- lookup
    def get(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return next((t for t in self.tasks if t.id == task_id), None)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for t in self.tasks if t.status in (Status.DOWNLOADING, Status.CONNECTING))

    # ---------------------------------------------------------------- start
    def _try_start_queued(self):
        with self._lock:
            slots = self.settings.max_concurrent_downloads - self.active_count()
            if slots <= 0:
                return
            queued = [t for t in self.tasks if t.status == Status.QUEUED]
            to_start = queued[:slots]
        for task in to_start:
            self._start_worker(task)

    def _start_worker(self, task: DownloadTask):
        def on_update(t: DownloadTask):
            self._persist()
            self._notify()

        def on_finished(t: DownloadTask):
            with self._lock:
                self.workers.pop(t.id, None)
            self._persist()
            self._notify()
            self._try_start_queued()

        worker = make_worker(task, on_update=on_update, on_finished=on_finished)
        with self._lock:
            self.workers[task.id] = worker
        worker.start()

    # -------------------------------------------------------------- control
    def pause(self, task_id: str):
        with self._lock:
            worker = self.workers.get(task_id)
            task = self.get(task_id)
        if worker:
            worker.request_pause()
        elif task and task.status == Status.QUEUED:
            task.status = Status.PAUSED
            self._persist()
            self._notify()

    def resume(self, task_id: str):
        task = self.get(task_id)
        if not task:
            return
        if task.status in (Status.PAUSED, Status.ERROR, Status.CANCELLED):
            if task.status == Status.CANCELLED:
                # Cancelling clears segments/file, so a restart is a clean
                # redownload rather than a byte-resume.
                task.segments = []
                task.stream_progress = 0.0
            task.status = Status.QUEUED
            task.error = ""
            self._persist()
            self._notify()
            self._try_start_queued()

    def cancel(self, task_id: str):
        with self._lock:
            worker = self.workers.get(task_id)
            task = self.get(task_id)
        if worker:
            worker.request_cancel()
        elif task:
            task.status = Status.CANCELLED
            task.segments = []
            task.stream_progress = 0.0
            for path in (task.dest_path, task.part_meta_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            self._persist()
            self._notify()

    def remove(self, task_id: str, delete_file: bool = False):
        self.cancel(task_id)
        task = self.get(task_id)
        with self._lock:
            self.tasks = [t for t in self.tasks if t.id != task_id]
            self._persist()
        if delete_file and task:
            for path in (task.dest_path, task.part_meta_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        self._notify()

    def pause_all(self):
        with self._lock:
            ids = [t.id for t in self.tasks]
        for tid in ids:
            self.pause(tid)

    def shutdown(self):
        """Pause every active download so state is resumable on next launch."""
        with self._lock:
            workers = list(self.workers.values())
        for w in workers:
            w.request_pause()
        for w in workers:
            w.join(timeout=10)
