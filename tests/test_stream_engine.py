"""Headless smoke test for the ffmpeg-backed HLS/DASH stream engine.

Run with: python tests/test_stream_engine.py
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine import StreamWorker
from app.models import DownloadTask, Status

# Mux's public HLS test asset (well-known, stable, used widely for player testing).
HLS_URL = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"


def wait_for(worker, timeout=300):
    worker.join(timeout=timeout)
    assert not worker.is_alive(), "worker did not finish in time"


def test_hls_download_and_probe(tmp_dir):
    print("== test_hls_download_and_probe ==")
    task = DownloadTask(url=HLS_URL, dest_folder=tmp_dir, filename="test_stream.mp4", kind="stream")
    events = []
    worker = StreamWorker(task, on_update=lambda t: events.append((t.status, t.stream_progress)),
                           on_finished=lambda t: None)
    worker.start()
    wait_for(worker)

    assert task.status == Status.COMPLETED, f"status={task.status} error={task.error}"
    assert os.path.exists(task.dest_path), "output file was not created"
    size = os.path.getsize(task.dest_path)
    assert size > 100_000, f"output file suspiciously small: {size} bytes"
    print(f"PASS: HLS stream muxed to {task.dest_path} ({size} bytes)")
    print(f"progress samples observed: {len(events)}, final={events[-1] if events else None}")

    # Verify the output is actually a playable video file via ffprobe.
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=noprint_wrappers=1", task.dest_path],
        capture_output=True, text=True, timeout=20,
    )
    assert out.returncode == 0, f"ffprobe could not read output file: {out.stderr}"
    print("ffprobe output:", out.stdout.strip())
    assert "duration=" in out.stdout
    print("PASS: output file is a valid, ffprobe-readable video")


def test_cancel_mid_stream(tmp_dir):
    print("== test_cancel_mid_stream ==")
    task = DownloadTask(url=HLS_URL, dest_folder=tmp_dir, filename="cancelled_stream.mp4", kind="stream")
    worker = StreamWorker(task, on_update=lambda t: None, on_finished=lambda t: None)
    worker.start()

    import time
    time.sleep(1.5)
    worker.request_cancel()
    wait_for(worker, timeout=30)

    assert task.status == Status.CANCELLED, f"status={task.status} error={task.error}"
    assert not os.path.exists(task.dest_path), "cancelled stream should clean up its output file"
    print("PASS: cancel mid-stream stopped ffmpeg and cleaned up the partial file")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_hls_download_and_probe(tmp_dir)
        test_cancel_mid_stream(tmp_dir)
    print("\nALL STREAM TESTS PASSED")
