"""Local loopback HTTP bridge that the browser extension talks to.

Bound to 127.0.0.1 only, so it is reachable from processes on this machine
(the browser) but never from the network. No auth token is used because the
loopback interface is itself the trust boundary: anything that can reach it
already runs as the same local user as this app.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .manager import DownloadManager

DEFAULT_PORT = 38019
APP_NAME = "X Downloader"


def _make_handler(manager: DownloadManager):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XDownloaderBridge/1.0"

        def log_message(self, fmt, *args):
            pass  # keep stdout quiet; errors still bubble up via responses

        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path == "/ping":
                self._send_json(200, {"app": APP_NAME, "status": "ok"})
            else:
                self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if self.path != "/add":
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b"{}"
                data = json.loads(body or b"{}")
                url = str(data.get("url") or "").strip()
                if not url.lower().startswith(("http://", "https://")):
                    raise ValueError("Missing or invalid 'url'")
                filename = str(data.get("filename") or "").strip() or None

                raw_kind = str(data.get("kind") or "").strip().lower()
                if raw_kind in ("hls", "dash", "stream"):
                    kind = "stream"
                elif raw_kind == "ytdlp":
                    kind = "ytdlp"
                else:
                    kind = None  # let the manager infer it from the URL

                referrer = str(data.get("referrer") or "").strip()
                stream_headers = {"Referer": referrer} if (kind == "stream" and referrer) else None

                task = manager.add(url, filename=filename, start=True,
                                    kind=kind, stream_headers=stream_headers)
                self._send_json(200, {"ok": True, "id": task.id, "filename": task.filename})
            except Exception as e:  # noqa: BLE001
                self._send_json(400, {"ok": False, "error": str(e)})

    return Handler


class LocalServer:
    """Runs the loopback bridge on a background thread for the app's lifetime."""

    def __init__(self, manager: DownloadManager, port: int = DEFAULT_PORT):
        self.port = port
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(manager))
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
