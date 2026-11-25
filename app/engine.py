"""Segmented, resumable download engine.

Each DownloadTask is driven by one DownloadWorker thread, which in turn
spawns one worker thread per segment (HTTP Range request) when the server
supports range requests, downloading each range in parallel for speed.
Progress is periodically flushed to a ".idmpart" sidecar JSON file so a
download can resume after the app itself is closed and reopened.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import requests

from . import ffmpeg_util
from .models import DownloadTask, Segment, Status
from .utils import filename_from_url, unique_path

CHUNK_SIZE = 64 * 1024
META_FLUSH_INTERVAL = 1.5
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) XDownloader/1.0"


class DownloadError(Exception):
    pass


def probe_url(url: str) -> dict:
    """Resolve final filename/size/range-support for a URL before download starts."""
    headers = {"User-Agent": USER_AGENT}
    size = -1
    supports_ranges = False
    disposition = None
    final_url = url
    resp = None

    try:
        resp = requests.head(url, headers=headers, allow_redirects=True, timeout=CONNECT_TIMEOUT)
        final_url = resp.url
        if resp.status_code < 400:
            size = int(resp.headers.get("Content-Length", -1))
            supports_ranges = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
            disposition = resp.headers.get("Content-Disposition")
    except requests.RequestException:
        pass

    if size <= 0 or resp is None or resp.status_code >= 400:
        # Some servers reject HEAD; fall back to a ranged GET probe.
        try:
            r = requests.get(url, headers={**headers, "Range": "bytes=0-0"},
                              stream=True, timeout=CONNECT_TIMEOUT)
            final_url = r.url
            disposition = disposition or r.headers.get("Content-Disposition")
            if r.status_code == 206:
                supports_ranges = True
                content_range = r.headers.get("Content-Range", "")
                if "/" in content_range:
                    total = content_range.rsplit("/", 1)[-1]
                    if total.isdigit():
                        size = int(total)
            elif r.status_code == 200:
                cl = r.headers.get("Content-Length")
                if cl and cl.isdigit():
                    size = int(cl)
            r.close()
        except requests.RequestException as e:
            raise DownloadError(f"Could not reach URL: {e}") from e

    name = filename_from_url(final_url, disposition)
    return {"filename": name, "size": size, "supports_ranges": supports_ranges, "final_url": final_url}


class DownloadWorker(threading.Thread):
    """Owns the full lifecycle of a single DownloadTask."""

    def __init__(self, task: DownloadTask, on_update: Callable[[DownloadTask], None],
                 on_finished: Callable[[DownloadTask], None]):
        super().__init__(daemon=True)
        self.task = task
        self.on_update = on_update
        self.on_finished = on_finished
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._last_flush = 0.0
        self._speed_samples: list[tuple[float, int]] = []

    def request_pause(self):
        self.pause_event.set()

    def request_cancel(self):
        self.cancel_event.set()

    # ------------------------------------------------------------------ run
    def run(self):
        task = self.task
        try:
            task.status = Status.CONNECTING
            self.on_update(task)

            if task.total_size <= 0 or not task.segments:
                info = probe_url(task.url)
                if not task.filename:
                    os.makedirs(task.dest_folder, exist_ok=True)
                    _, task.filename = unique_path(task.dest_folder, info["filename"])
                if task.total_size <= 0:
                    task.total_size = info["size"]
                task.supports_ranges = info["supports_ranges"]

            os.makedirs(task.dest_folder, exist_ok=True)

            if not task.segments:
                task.segments = self._build_segments(task)

            self._preallocate(task)

            task.status = Status.DOWNLOADING
            self.on_update(task)

            pending = [s for s in task.segments if s.remaining > 0]
            if pending:
                workers = min(len(pending), max(1, task.num_connections))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(self._download_segment, task, seg) for seg in pending]
                    for f in futures:
                        f.result()

            if self.cancel_event.is_set():
                self._cleanup_files(task)
                task.segments = []
                task.status = Status.CANCELLED
            elif self.pause_event.is_set() and task.downloaded_bytes < task.total_size:
                task.status = Status.PAUSED
                self._save_meta(task)
            else:
                if task.total_size > 0 and task.downloaded_bytes < task.total_size:
                    raise DownloadError("Connection closed before download completed")
                task.status = Status.COMPLETED
                task.completed_at = time.time()
                self._remove_meta(task)

        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            task.status = Status.ERROR
            task.error = str(e)
            self._save_meta(task)

        self.on_update(task)
        self.on_finished(task)

    # --------------------------------------------------------------- setup
    def _build_segments(self, task: DownloadTask) -> list[Segment]:
        if task.total_size <= 0 or not task.supports_ranges:
            return [Segment(index=0, start=0, end=max(task.total_size - 1, 0))]

        n = max(1, task.num_connections)
        # Avoid pointlessly slicing small files into many tiny segments.
        min_segment_size = 1024 * 1024
        n = max(1, min(n, (task.total_size // min_segment_size) or 1))

        chunk = task.total_size // n
        segments = []
        start = 0
        for i in range(n):
            end = task.total_size - 1 if i == n - 1 else start + chunk - 1
            segments.append(Segment(index=i, start=start, end=end))
            start = end + 1
        return segments

    def _preallocate(self, task: DownloadTask):
        path = task.dest_path
        if task.total_size > 0:
            need_alloc = not os.path.exists(path) or os.path.getsize(path) != task.total_size
            if need_alloc:
                with open(path, "wb") as f:
                    if task.total_size > 0:
                        f.seek(task.total_size - 1)
                        f.write(b"\0")
        elif not os.path.exists(path):
            open(path, "wb").close()

    # ------------------------------------------------------------ segments
    def _download_segment(self, task: DownloadTask, seg: Segment):
        headers = {"User-Agent": USER_AGENT}
        start = seg.start + seg.downloaded
        if seg.remaining <= 0:
            return
        if task.supports_ranges and task.total_size > 0:
            headers["Range"] = f"bytes={start}-{seg.end}"

        try:
            with requests.get(task.url, headers=headers, stream=True,
                               timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)) as resp:
                if resp.status_code not in (200, 206):
                    raise DownloadError(f"Server returned HTTP {resp.status_code}")

                with open(task.dest_path, "r+b") as f:
                    f.seek(start)
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if self.cancel_event.is_set():
                            return
                        if not chunk:
                            continue
                        f.write(chunk)
                        seg.downloaded += len(chunk)
                        self._record_speed(len(chunk))
                        self._maybe_flush(task)
                        if self.pause_event.is_set():
                            return
        except requests.RequestException as e:
            raise DownloadError(f"Segment {seg.index} failed: {e}") from e

    # ------------------------------------------------------------- progress
    def _record_speed(self, nbytes: int):
        now = time.monotonic()
        with self._lock:
            self._speed_samples.append((now, nbytes))
            cutoff = now - 3.0
            self._speed_samples = [(t, n) for t, n in self._speed_samples if t >= cutoff]

    def current_speed(self) -> float:
        with self._lock:
            if len(self._speed_samples) < 2:
                return 0.0
            span = self._speed_samples[-1][0] - self._speed_samples[0][0]
            total = sum(n for _, n in self._speed_samples)
            return total / span if span > 0 else 0.0

    def _maybe_flush(self, task: DownloadTask):
        now = time.monotonic()
        if now - self._last_flush >= META_FLUSH_INTERVAL:
            self._last_flush = now
            task.speed_bps = self.current_speed()
            remaining = task.total_size - task.downloaded_bytes if task.total_size > 0 else None
            task.eta_seconds = (remaining / task.speed_bps) if remaining and task.speed_bps > 0 else None
            self._save_meta(task)
            self.on_update(task)

    # ---------------------------------------------------------------- meta
    def _save_meta(self, task: DownloadTask):
        try:
            with open(task.part_meta_path, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f)
        except OSError:
            pass

    def _remove_meta(self, task: DownloadTask):
        try:
            if os.path.exists(task.part_meta_path):
                os.remove(task.part_meta_path)
        except OSError:
            pass

    def _cleanup_files(self, task: DownloadTask):
        for path in (task.dest_path, task.part_meta_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


_PROGRESS_TIME_RE = re.compile(r"out_time_ms=(\d+)")
_PROGRESS_SPEED_RE = re.compile(r"speed=\s*([\d.]+)x")
_PROGRESS_END_RE = re.compile(r"progress=end")


class StreamWorker(threading.Thread):
    """Grabs an HLS (.m3u8) / DASH (.mpd) source by shelling out to ffmpeg.

    ffmpeg already knows how to fetch and demux adaptive streams over HTTP,
    so rather than re-implementing a segment downloader we drive it as a
    subprocess and translate its `-progress` output into task updates.
    Streams can't be byte-resumed the way plain HTTP downloads can: pausing
    one is equivalent to cancelling it.
    """

    def __init__(self, task: DownloadTask, on_update: Callable[[DownloadTask], None],
                 on_finished: Callable[[DownloadTask], None]):
        super().__init__(daemon=True)
        self.task = task
        self.on_update = on_update
        self.on_finished = on_finished
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def request_pause(self):
        # No mid-mux resume support; pausing a stream just stops it cleanly.
        self.request_cancel()

    def request_cancel(self):
        self.cancel_event.set()
        self._stop_process()

    def current_speed(self) -> float:
        return 0.0  # not a meaningful byte-rate for a remux; see extra_info

    def _stop_process(self):
        proc = self._proc
        if not proc or proc.poll() is not None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write(b"q")
                proc.stdin.flush()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except OSError:
                pass

    def run(self):
        task = self.task
        stderr_tail: list[str] = []
        try:
            task.status = Status.CONNECTING
            task.extra_info = "Setting up ffmpeg…"
            self.on_update(task)

            ffmpeg_path, ffprobe_path = ffmpeg_util.ensure_ffmpeg(
                on_progress=lambda msg: self._report(task, msg))

            if self.cancel_event.is_set():
                raise DownloadError("Cancelled")

            os.makedirs(task.dest_folder, exist_ok=True)
            if not task.filename.lower().endswith((".mp4", ".mkv", ".ts")):
                base = os.path.splitext(task.filename)[0] or "video"
                _, task.filename = unique_path(task.dest_folder, base + ".mp4")

            task.extra_info = "Reading stream info…"
            self.on_update(task)
            task.stream_duration = ffmpeg_util.probe_duration(
                ffprobe_path, task.url, task.stream_headers)

            cmd = [ffmpeg_path, "-y"]
            if task.stream_headers:
                cmd += ["-headers", ffmpeg_util.headers_block(task.stream_headers)]
            cmd += ["-i", task.url, "-c", "copy", "-bsf:a", "aac_adtstoasc",
                    task.dest_path, "-progress", "pipe:1", "-nostats", "-loglevel", "error"]

            task.status = Status.DOWNLOADING
            self.on_update(task)

            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0,
            )

            stderr_thread = threading.Thread(
                target=self._drain_stderr, args=(self._proc, stderr_tail), daemon=True)
            stderr_thread.start()

            last_update = 0.0
            for raw_line in self._proc.stdout:
                line = raw_line.decode(errors="ignore").strip()
                m = _PROGRESS_TIME_RE.search(line)
                if m and task.stream_duration > 0:
                    elapsed = int(m.group(1)) / 1_000_000
                    task.stream_progress = min(1.0, elapsed / task.stream_duration)
                m = _PROGRESS_SPEED_RE.search(line)
                if m:
                    task.extra_info = f"{m.group(1)}x realtime"
                now = time.monotonic()
                if now - last_update > 0.5:
                    last_update = now
                    self.on_update(task)
                if _PROGRESS_END_RE.search(line) or self.cancel_event.is_set():
                    break

            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
            stderr_thread.join(timeout=2)

            if self.cancel_event.is_set():
                self._cleanup_output(task)
                task.status = Status.CANCELLED
                task.extra_info = ""
            elif self._proc.returncode == 0:
                task.status = Status.COMPLETED
                task.stream_progress = 1.0
                task.completed_at = time.time()
                task.extra_info = ""
            else:
                tail = " ".join(stderr_tail[-3:]) or "unknown error"
                raise DownloadError(f"ffmpeg failed: {tail}")

        except ffmpeg_util.FFmpegFetchError as e:
            task.status = Status.ERROR
            task.error = str(e)
            task.extra_info = ""
        except Exception as e:  # noqa: BLE001
            task.status = Status.ERROR
            task.error = str(e) or " ".join(stderr_tail[-3:]) or "ffmpeg failed"
            task.extra_info = ""

        self.on_update(task)
        self.on_finished(task)

    def _report(self, task: DownloadTask, msg: str):
        task.extra_info = msg
        self.on_update(task)

    @staticmethod
    def _drain_stderr(proc: subprocess.Popen, sink: list[str]):
        try:
            for raw_line in proc.stderr:
                line = raw_line.decode(errors="ignore").strip()
                if line:
                    sink.append(line)
                    del sink[:-20]  # keep only the tail
        except (OSError, ValueError):
            pass

    def _cleanup_output(self, task: DownloadTask):
        try:
            if os.path.exists(task.dest_path):
                os.remove(task.dest_path)
        except OSError:
            pass


class YtDlpWorker(threading.Thread):
    """Grabs YouTube (and other yt-dlp-supported) URLs via the yt-dlp library.

    YouTube serves media through a protocol (SABR) that isn't a plain
    fetchable URL, specifically to defeat generic downloaders/sniffers -
    the same wall that briefly broke yt-dlp itself until its maintainers
    reverse-engineered a workaround. Rather than re-fighting that battle,
    we lean on yt-dlp, which tracks the countermeasures as they evolve.
    """

    def __init__(self, task: DownloadTask, on_update: Callable[[DownloadTask], None],
                 on_finished: Callable[[DownloadTask], None]):
        super().__init__(daemon=True)
        self.task = task
        self.on_update = on_update
        self.on_finished = on_finished
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()
        self._last_update = 0.0

    def request_pause(self):
        # yt-dlp can technically resume partial single-format downloads, but
        # a merge (video+audio) can't safely resume mid-merge, so treat
        # pause as cancel for consistency and predictability.
        self.request_cancel()

    def request_cancel(self):
        self.cancel_event.set()

    def current_speed(self) -> float:
        return self.task.speed_bps

    def run(self):
        task = self.task
        try:
            import yt_dlp
            from yt_dlp.utils import DownloadCancelled, sanitize_filename
        except ImportError as e:
            task.status = Status.ERROR
            task.error = f"yt-dlp is not installed: {e}"
            self.on_update(task)
            self.on_finished(task)
            return

        try:
            task.status = Status.CONNECTING
            task.extra_info = "Fetching video info…"
            self.on_update(task)

            ffmpeg_path, _ = ffmpeg_util.ensure_ffmpeg(
                on_progress=lambda msg: self._report(task, msg))

            if self.cancel_event.is_set():
                raise DownloadError("Cancelled")

            os.makedirs(task.dest_folder, exist_ok=True)

            probe_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            with yt_dlp.YoutubeDL(probe_opts) as probe:
                info = probe.extract_info(task.url, download=False)
            title = sanitize_filename(info.get("title") or "video", restricted=False)
            _, task.filename = unique_path(task.dest_folder, f"{title}.mp4")
            out_path = task.dest_path

            def hook(d: dict):
                if self.cancel_event.is_set():
                    raise DownloadCancelled("Cancelled by user")
                if d.get("status") == "downloading":
                    downloaded = d.get("downloaded_bytes") or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or -1
                    task.ytdlp_downloaded = downloaded
                    task.total_size = total
                    task.speed_bps = d.get("speed") or 0.0
                    task.eta_seconds = d.get("eta")
                    task.status = Status.DOWNLOADING
                    now = time.monotonic()
                    if now - self._last_update > 0.5:
                        self._last_update = now
                        self.on_update(task)

            ydl_opts = {
                "outtmpl": out_path,
                "format": task.format_selector or "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "ffmpeg_location": ffmpeg_path,
                "progress_hooks": [hook],
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([task.url])

            task.status = Status.COMPLETED
            task.completed_at = time.time()
            task.extra_info = ""
            if os.path.exists(out_path):
                task.total_size = os.path.getsize(out_path)
                task.ytdlp_downloaded = task.total_size

        except Exception as e:  # noqa: BLE001 - covers DownloadCancelled + yt-dlp's own errors
            is_cancel = self.cancel_event.is_set()
            try:
                out_path = task.dest_path
                if os.path.exists(out_path) and (is_cancel or task.status != Status.COMPLETED):
                    os.remove(out_path)
            except OSError:
                pass
            if is_cancel:
                task.status = Status.CANCELLED
            else:
                task.status = Status.ERROR
                task.error = str(e) or "yt-dlp failed"
            task.extra_info = ""

        self.on_update(task)
        self.on_finished(task)

    def _report(self, task: DownloadTask, msg: str):
        task.extra_info = msg
        self.on_update(task)


YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com")


def is_youtube_url(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


def make_worker(task: DownloadTask, on_update: Callable[[DownloadTask], None],
                 on_finished: Callable[[DownloadTask], None]):
    if task.kind == "ytdlp":
        return YtDlpWorker(task, on_update, on_finished)
    if task.kind == "stream":
        return StreamWorker(task, on_update, on_finished)
    return DownloadWorker(task, on_update, on_finished)
