"""Locate ffmpeg/ffprobe, downloading a portable Windows build if neither is
on PATH and nothing was fetched previously. ffmpeg is what lets X Downloader
grab HLS (.m3u8) and DASH (.mpd) streams the same way it handles plain files
- it already knows how to pull segmented video over HTTP and mux it, so we
shell out to it rather than reimplementing an adaptive-streaming client.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from typing import Callable, Optional

import requests

from .storage import app_data_dir

FFMPEG_BUILD_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

ProgressCb = Optional[Callable[[str], None]]


def _local_dir() -> str:
    return os.path.join(app_data_dir(), "ffmpeg")


def _local_bin(name: str) -> str:
    return os.path.join(_local_dir(), "bin", name)


def find_ffmpeg() -> Optional[str]:
    path = shutil.which("ffmpeg")
    if path:
        return path
    local = _local_bin("ffmpeg.exe")
    return local if os.path.exists(local) else None


def find_ffprobe() -> Optional[str]:
    path = shutil.which("ffprobe")
    if path:
        return path
    local = _local_bin("ffprobe.exe")
    return local if os.path.exists(local) else None


class FFmpegFetchError(Exception):
    pass


def ensure_ffmpeg(on_progress: ProgressCb = None) -> tuple[str, str]:
    """Return (ffmpeg_path, ffprobe_path), downloading a static build if needed."""
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe

    def report(msg: str):
        if on_progress:
            on_progress(msg)

    dest_dir = _local_dir()
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, "ffmpeg_download.zip")

    try:
        report("Downloading ffmpeg (one-time, ~100 MB)…")
        with requests.get(FFMPEG_BUILD_URL, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        report(f"Downloading ffmpeg… {done * 100 // total}%")

        report("Extracting ffmpeg…")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            exe_members = [n for n in names if n.endswith(("bin/ffmpeg.exe", "bin/ffprobe.exe"))]
            if not exe_members:
                raise FFmpegFetchError("Downloaded archive did not contain ffmpeg/ffprobe")
            for member in exe_members:
                out_name = "ffmpeg.exe" if member.endswith("ffmpeg.exe") else "ffprobe.exe"
                out_path = _local_bin(out_name)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with zf.open(member) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (requests.RequestException, zipfile.BadZipFile, OSError) as e:
        raise FFmpegFetchError(f"Could not set up ffmpeg: {e}") from e
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass

    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if not ffmpeg or not ffprobe:
        raise FFmpegFetchError("ffmpeg download completed but the executables were not found")
    report("ffmpeg ready.")
    return ffmpeg, ffprobe


def probe_duration(ffprobe_path: str, url: str, headers: dict | None = None) -> float:
    """Return the stream's duration in seconds, or 0.0 if unknown (e.g. a live stream)."""
    cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1"]
    if headers:
        cmd += ["-headers", headers_block(headers)]
    cmd += [url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def headers_block(headers: dict) -> str:
    return "".join(f"{k}: {v}\r\n" for k, v in headers.items())
