"""Data models for download tasks."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    SELECT_QUALITY = "Select Quality"
    QUEUED = "Queued"
    CONNECTING = "Connecting"
    DOWNLOADING = "Downloading"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    ERROR = "Error"
    CANCELLED = "Cancelled"


@dataclass
class Segment:
    index: int
    start: int
    end: int
    downloaded: int = 0

    @property
    def remaining(self) -> int:
        return (self.end - self.start + 1) - self.downloaded

    def to_dict(self) -> dict:
        return {"index": self.index, "start": self.start, "end": self.end, "downloaded": self.downloaded}

    @staticmethod
    def from_dict(d: dict) -> "Segment":
        return Segment(index=d["index"], start=d["start"], end=d["end"], downloaded=d.get("downloaded", 0))


@dataclass
class DownloadTask:
    url: str
    dest_folder: str
    filename: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    total_size: int = -1              # -1 = unknown
    supports_ranges: bool = False
    num_connections: int = 8
    status: Status = Status.QUEUED
    segments: list[Segment] = field(default_factory=list)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    # kind == "stream" covers HLS (.m3u8) / DASH (.mpd) sources, muxed via
    # ffmpeg instead of the segmented HTTP engine. kind == "ytdlp" covers
    # sites (currently YouTube) that need yt-dlp's site-specific extraction
    # rather than a raw manifest URL. Neither can be byte-resumed the way
    # plain HTTP downloads can.
    kind: str = "http"                # "http" | "stream" | "ytdlp"
    stream_headers: dict = field(default_factory=dict)
    stream_duration: float = 0.0      # seconds; 0 = unknown (e.g. live)
    stream_progress: float = 0.0      # 0..1
    ytdlp_downloaded: int = 0         # bytes; total_size doubles as the total

    # yt-dlp format selector string (e.g. "bestvideo[height<=720]+bestaudio/best").
    # None means "not chosen yet" - the manager holds the task instead of
    # starting it until the GUI's quality dialog sets this.
    format_selector: str | None = None

    # runtime-only (not persisted)
    speed_bps: float = field(default=0.0, repr=False, compare=False)
    eta_seconds: float | None = field(default=None, repr=False, compare=False)
    extra_info: str = field(default="", repr=False, compare=False)

    @property
    def dest_path(self) -> str:
        import os
        return os.path.join(self.dest_folder, self.filename)

    @property
    def part_meta_path(self) -> str:
        return self.dest_path + ".idmpart"

    @property
    def downloaded_bytes(self) -> int:
        if self.kind == "ytdlp":
            return self.ytdlp_downloaded
        if self.segments:
            return sum(s.downloaded for s in self.segments)
        return 0

    @property
    def progress(self) -> float:
        if self.kind == "stream":
            return min(1.0, max(0.0, self.stream_progress))
        if self.total_size <= 0:
            return 0.0
        return min(1.0, self.downloaded_bytes / self.total_size)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "dest_folder": self.dest_folder,
            "filename": self.filename,
            "total_size": self.total_size,
            "supports_ranges": self.supports_ranges,
            "num_connections": self.num_connections,
            "status": self.status.value,
            "segments": [s.to_dict() for s in self.segments],
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "kind": self.kind,
            "stream_headers": self.stream_headers,
            "stream_duration": self.stream_duration,
            "stream_progress": self.stream_progress,
            "ytdlp_downloaded": self.ytdlp_downloaded,
            "format_selector": self.format_selector,
        }

    @staticmethod
    def from_dict(d: dict) -> "DownloadTask":
        t = DownloadTask(
            url=d["url"],
            dest_folder=d["dest_folder"],
            filename=d["filename"],
            id=d["id"],
            total_size=d.get("total_size", -1),
            supports_ranges=d.get("supports_ranges", False),
            num_connections=d.get("num_connections", 8),
            status=Status(d.get("status", Status.QUEUED.value)),
            error=d.get("error", ""),
            created_at=d.get("created_at", time.time()),
            completed_at=d.get("completed_at"),
            kind=d.get("kind", "http"),
            stream_headers=d.get("stream_headers", {}),
            stream_duration=d.get("stream_duration", 0.0),
            stream_progress=d.get("stream_progress", 0.0),
            ytdlp_downloaded=d.get("ytdlp_downloaded", 0),
            format_selector=d.get("format_selector"),
        )
        t.segments = [Segment.from_dict(s) for s in d.get("segments", [])]
        # Any task that wasn't cleanly finished should re-queue rather than
        # silently claim to still be "downloading" on load. Streams/yt-dlp
        # can't resume mid-mux, so they go back to the start of the queue.
        if t.status in (Status.DOWNLOADING, Status.CONNECTING):
            t.status = Status.PAUSED if t.kind == "http" else Status.QUEUED
        return t
