"""X Downloader – a multi-connection, resumable download manager."""
import sys

from PySide6.QtWidgets import QApplication

from app.cloud_sync import CloudSync
from app.local_server import DEFAULT_PORT, LocalServer
from app.manager import DownloadManager
from app.storage import Settings
from ui.main_window import MainWindow


def selftest() -> int:
    """Import everything the app needs at runtime, without opening a window.

    Used to verify that a packaged (PyInstaller) build actually bundled its
    dynamically-loaded dependencies; run as `"X Downloader.exe" --selftest`
    and check the exit code (0 = healthy).
    """
    import requests  # noqa: F401
    import yt_dlp
    from supabase import create_client

    from app.storage import DEFAULT_SUPABASE_KEY, DEFAULT_SUPABASE_URL
    from yt_dlp.extractor import gen_extractor_classes

    if len(list(gen_extractor_classes())) < 500:
        print("yt-dlp extractors missing from build", file=sys.stderr)
        return 1
    create_client(DEFAULT_SUPABASE_URL, DEFAULT_SUPABASE_KEY)
    print(f"selftest ok (yt-dlp {yt_dlp.version.__version__})")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    app = QApplication(sys.argv)
    app.setApplicationName("X Downloader")
    app.setQuitOnLastWindowClosed(True)

    settings = Settings()
    manager = DownloadManager(settings)
    cloud_sync = CloudSync(manager, settings)

    server = None
    try:
        server = LocalServer(manager)
        server.start()
    except OSError as e:
        print(f"Warning: could not start browser-extension bridge on port {DEFAULT_PORT}: {e}",
              file=sys.stderr)

    window = MainWindow(settings, manager, cloud_sync)
    window.show()

    exit_code = app.exec()
    cloud_sync.shutdown()
    if server:
        server.stop()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
