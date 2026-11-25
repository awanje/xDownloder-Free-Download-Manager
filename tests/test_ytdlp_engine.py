"""Headless smoke test for the yt-dlp-backed YouTube engine.

Run with: python tests/test_ytdlp_engine.py
"""
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine import YtDlpWorker, is_youtube_url
from app.models import DownloadTask, Status

# "Me at the zoo" - the first video ever uploaded to YouTube, 19s long.
YT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def wait_for(worker, timeout=90):
    worker.join(timeout=timeout)
    assert not worker.is_alive(), "worker did not finish in time"


def test_is_youtube_url():
    print("== test_is_youtube_url ==")
    assert is_youtube_url("https://www.youtube.com/watch?v=abc123")
    assert is_youtube_url("https://youtu.be/abc123")
    assert is_youtube_url("https://m.youtube.com/watch?v=abc123")
    assert not is_youtube_url("https://example.com/video.mp4")
    print("PASS: YouTube URL detection")


def test_download_and_probe(tmp_dir):
    print("== test_download_and_probe ==")
    task = DownloadTask(url=YT_URL, dest_folder=tmp_dir, filename="", kind="ytdlp")
    events = []
    worker = YtDlpWorker(task, on_update=lambda t: events.append((t.status, t.downloaded_bytes, t.total_size)),
                          on_finished=lambda t: None)
    worker.start()
    wait_for(worker)

    assert task.status == Status.COMPLETED, f"status={task.status} error={task.error}"
    assert task.filename, "worker should have resolved a real filename from the video title"
    assert "zoo" in task.filename.lower(), f"expected title-derived filename, got {task.filename!r}"
    assert os.path.exists(task.dest_path)
    size = os.path.getsize(task.dest_path)
    assert size > 50_000, f"output suspiciously small: {size} bytes"
    print(f"PASS: downloaded '{task.filename}' ({size} bytes), {len(events)} progress updates")

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", task.dest_path],
        capture_output=True, text=True, timeout=20,
    )
    assert out.returncode == 0, f"ffprobe could not read output: {out.stderr}"
    duration = float(out.stdout.strip())
    assert 15 < duration < 25, f"unexpected duration: {duration}"
    print(f"PASS: output is a valid video, duration={duration:.1f}s (matches the ~19s source)")


def test_cancel(tmp_dir):
    print("== test_cancel ==")
    task = DownloadTask(url=YT_URL, dest_folder=tmp_dir, filename="", kind="ytdlp")
    worker = YtDlpWorker(task, on_update=lambda t: None, on_finished=lambda t: None)
    worker.start()
    time.sleep(0.3)
    worker.request_cancel()
    wait_for(worker, timeout=30)

    assert task.status == Status.CANCELLED, f"status={task.status} error={task.error}"
    if task.filename:
        assert not os.path.exists(task.dest_path), "cancelled download should not leave a file behind"
    print("PASS: cancel stopped the download and cleaned up")


if __name__ == "__main__":
    test_is_youtube_url()
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_download_and_probe(tmp_dir)
        test_cancel(tmp_dir)
    print("\nALL YT-DLP TESTS PASSED")
