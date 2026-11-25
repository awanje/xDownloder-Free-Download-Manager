"""Persistence of the download list (not the file bytes themselves)."""
from __future__ import annotations

import json
import os

from .models import DownloadTask

APP_DIR_NAME = "X Downloader"

DEFAULT_SUPABASE_URL = "https://kxadbtptfkfsiaxtiovc.supabase.co"
DEFAULT_SUPABASE_KEY = "sb_publishable_hWdxtZFbMkIyWwUMIq2Hbg_TRc33rRo"


def app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def state_file_path() -> str:
    return os.path.join(app_data_dir(), "downloads.json")


def default_download_dir() -> str:
    path = os.path.join(os.path.expanduser("~"), "Downloads", "X Downloader")
    os.makedirs(path, exist_ok=True)
    return path


def load_tasks() -> list[DownloadTask]:
    path = state_file_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [DownloadTask.from_dict(d) for d in raw]
    except (OSError, json.JSONDecodeError, KeyError):
        return []


def save_tasks(tasks: list[DownloadTask]) -> None:
    path = state_file_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)
    os.replace(tmp, path)


class Settings:
    def __init__(self):
        self.download_dir = default_download_dir()
        self.max_connections_per_download = 8
        self.max_concurrent_downloads = 3
        self.clipboard_monitor = True
        # Cross-device sync (Supabase). Ships pointing at the app's own
        # backend; the publishable key is safe to embed (row-level security
        # in supabase_schema.sql is what protects data). Users can override
        # both in Settings -> Cloud Sync.
        self.supabase_url = DEFAULT_SUPABASE_URL
        self.supabase_anon_key = DEFAULT_SUPABASE_KEY
        self.supabase_refresh_token = ""
        self._path = os.path.join(app_data_dir(), "settings.json")
        self.load()

    def load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.download_dir = d.get("download_dir", self.download_dir)
                self.max_connections_per_download = d.get("max_connections_per_download", 8)
                self.max_concurrent_downloads = d.get("max_concurrent_downloads", 3)
                self.clipboard_monitor = d.get("clipboard_monitor", True)
                self.supabase_url = d.get("supabase_url") or DEFAULT_SUPABASE_URL
                self.supabase_anon_key = d.get("supabase_anon_key") or DEFAULT_SUPABASE_KEY
                self.supabase_refresh_token = d.get("supabase_refresh_token", "")
            except (OSError, json.JSONDecodeError):
                pass
        os.makedirs(self.download_dir, exist_ok=True)

    def save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({
                "download_dir": self.download_dir,
                "max_connections_per_download": self.max_connections_per_download,
                "max_concurrent_downloads": self.max_concurrent_downloads,
                "clipboard_monitor": self.clipboard_monitor,
                "supabase_url": self.supabase_url,
                "supabase_anon_key": self.supabase_anon_key,
                "supabase_refresh_token": self.supabase_refresh_token,
            }, f, indent=2)
