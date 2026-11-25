"""Cross-device sync via Supabase.

Mirrors this desktop instance's downloads to a shared `downloads` table so
a signed-in mobile app can see them and their live progress. Also polls for
links the mobile app queued (status "Pending") and feeds them into the
local DownloadManager so this PC actually does the downloading - the
mobile app never downloads video itself, only submits a URL.

Network I/O runs on dedicated background threads, decoupled from the
download engines: engine threads just mark a task "dirty" (a fast,
in-memory set update) and the push thread drains that set on its own
cadence, so a slow or failed network call never blocks a download.

The project URL and anon key are configured per-install in Settings (not
hardcoded), since every user of this app points at their own Supabase
project. The anon/public key is safe to store locally - it only ever acts
within the row-level-security policies defined in supabase_schema.sql.
"""
from __future__ import annotations

import platform
import threading
from typing import Optional

from .manager import DownloadManager
from .models import DownloadTask
from .storage import Settings

PULL_INTERVAL = 4.0
PUSH_INTERVAL = 1.5
TABLE = "downloads"


class CloudSync:
    def __init__(self, manager: DownloadManager, settings: Settings):
        self.manager = manager
        self.settings = settings
        self.client = None
        self.user = None
        self.last_error: str = ""
        self.device_name = platform.node() or "Desktop"

        self._cloud_id_by_task: dict[str, str] = {}
        self._dirty: set[str] = set()
        self._dirty_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

        self.manager.add_listener(self._on_local_update)

        if self.is_configured and settings.supabase_refresh_token:
            threading.Thread(target=self._restore_session, daemon=True).start()

    # ------------------------------------------------------------- status
    @property
    def is_signed_in(self) -> bool:
        return self.client is not None and self.user is not None

    @property
    def email(self) -> str:
        return getattr(self.user, "email", "") if self.user else ""

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_anon_key)

    def _new_client(self):
        from supabase import create_client
        return create_client(self.settings.supabase_url, self.settings.supabase_anon_key)

    # ------------------------------------------------------------- auth
    def sign_up(self, email: str, password: str) -> Optional[str]:
        return self._auth_call(lambda c: c.auth.sign_up({"email": email, "password": password}))

    def sign_in(self, email: str, password: str) -> Optional[str]:
        return self._auth_call(
            lambda c: c.auth.sign_in_with_password({"email": email, "password": password}))

    def _auth_call(self, fn) -> Optional[str]:
        if not self.is_configured:
            return "Cloud sync is not configured (add your Supabase URL/key in Settings)."
        try:
            client = self._new_client()
            resp = fn(client)
            if not resp.user:
                return "Sign-in failed: no user returned."
            self.client = client
            self.user = resp.user
            self.last_error = ""
            session = getattr(resp, "session", None)
            if session:
                self.settings.supabase_refresh_token = session.refresh_token
                self.settings.save()
        except Exception as e:  # noqa: BLE001
            return str(e)
        self._start()
        return None

    def _restore_session(self):
        try:
            client = self._new_client()
            resp = client.auth.refresh_session(self.settings.supabase_refresh_token)
            if resp.user and resp.session:
                self.client = client
                self.user = resp.user
                self.settings.supabase_refresh_token = resp.session.refresh_token
                self.settings.save()
                self._start()
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            self.settings.supabase_refresh_token = ""
            self.settings.save()

    def sign_out(self):
        self._stop_threads()
        if self.client:
            try:
                self.client.auth.sign_out()
            except Exception:
                pass
        self.client = None
        self.user = None
        self._cloud_id_by_task.clear()
        self.settings.supabase_refresh_token = ""
        self.settings.save()

    # ------------------------------------------------------------- lifecycle
    def _start(self):
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._pull_loop, daemon=True),
            threading.Thread(target=self._push_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def _stop_threads(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads = []

    def shutdown(self):
        self._stop_threads()

    # ------------------------------------------------------- pull (mobile -> pc)
    def _pull_loop(self):
        while not self._stop.is_set():
            try:
                self._claim_pending()
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
            self._stop.wait(PULL_INTERVAL)

    def _claim_pending(self):
        if not self.is_signed_in:
            return
        rows = (
            self.client.table(TABLE)
            .select("*")
            .eq("user_id", self.user.id)
            .eq("status", "Pending")
            .execute()
        ).data or []
        for row in rows:
            self.client.table(TABLE).update(
                {"status": "Queued", "claimed_by": self.device_name}
            ).eq("id", row["id"]).execute()
            task = self.manager.add(row["url"], filename=row.get("filename") or None, start=True)
            self._cloud_id_by_task[task.id] = row["id"]

    # ------------------------------------------------------- push (pc -> cloud)
    def _on_local_update(self):
        if not self.is_signed_in:
            return
        with self._dirty_lock:
            for t in self.manager.tasks:
                self._dirty.add(t.id)

    def _push_loop(self):
        while not self._stop.is_set():
            with self._dirty_lock:
                ids = list(self._dirty)
                self._dirty.clear()
            for tid in ids:
                task = self.manager.get(tid)
                if task:
                    self._push_task(task)
            self._stop.wait(PUSH_INTERVAL)

    def _push_task(self, task: DownloadTask):
        payload = {
            "user_id": self.user.id,
            "source": "desktop",
            "device_name": self.device_name,
            "url": task.url,
            "filename": task.filename,
            "kind": task.kind,
            "status": task.status.value,
            "progress": task.progress,
            "total_size": task.total_size,
            "downloaded_bytes": task.downloaded_bytes,
            "speed_bps": task.speed_bps,
            "error": task.error,
        }
        try:
            cloud_id = self._cloud_id_by_task.get(task.id)
            if cloud_id:
                self.client.table(TABLE).update(payload).eq("id", cloud_id).execute()
            else:
                resp = self.client.table(TABLE).insert(payload).execute()
                if resp.data:
                    self._cloud_id_by_task[task.id] = resp.data[0]["id"]
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
