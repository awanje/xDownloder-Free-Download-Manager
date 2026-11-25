"""Small formatting / URL helpers."""
from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse


def filename_from_url(url: str, content_disposition: str | None = None) -> str:
    if content_disposition:
        m = re.search(r'filename\*=UTF-8\'\'([^;]+)', content_disposition)
        if m:
            return unquote(m.group(1)).strip().strip('"')
        m = re.search(r'filename="?([^";]+)"?', content_disposition)
        if m:
            return m.group(1).strip().strip('"')

    path = urlparse(url).path
    name = unquote(os.path.basename(path))
    return name or "download"


def unique_path(folder: str, filename: str) -> tuple[str, str]:
    """Return (folder, filename) guaranteed not to collide with an existing file."""
    base, ext = os.path.splitext(filename)
    candidate = filename
    n = 1
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{base} ({n}){ext}"
        n += 1
    return folder, candidate


def format_size(num_bytes: float) -> str:
    if num_bytes < 0:
        return "Unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_speed(bps: float) -> str:
    if bps <= 0:
        return "-"
    return f"{format_size(bps)}/s"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "-"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
