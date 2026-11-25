"""Headless smoke test for the segmented download engine: full download,
plus a pause/resume cycle, against a real HTTP endpoint that supports
Range requests.

Run with: python tests/test_engine.py
"""
import hashlib
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine import DownloadWorker, probe_url
from app.models import DownloadTask, Status

TEST_URL = "https://proof.ovh.net/files/1Mb.dat"


def wait_for(worker, timeout=60):
    worker.join(timeout=timeout)
    assert not worker.is_alive(), "worker did not finish in time"


def test_full_download(tmp_dir):
    print("== test_full_download ==")
    info = probe_url(TEST_URL)
    print("probe:", info)
    assert info["size"] > 0
    assert info["supports_ranges"] is True

    task = DownloadTask(url=TEST_URL, dest_folder=tmp_dir, filename="full.dat", num_connections=4)
    events = []
    worker = DownloadWorker(task, on_update=lambda t: events.append(t.status), on_finished=lambda t: None)
    worker.start()
    wait_for(worker)

    assert task.status == Status.COMPLETED, f"status={task.status} error={task.error}"
    assert os.path.getsize(task.dest_path) == info["size"]
    assert not os.path.exists(task.part_meta_path)
    print("PASS: full download completed, size matches, meta cleaned up")


def test_pause_resume(tmp_dir):
    print("== test_pause_resume ==")
    task = DownloadTask(url=TEST_URL, dest_folder=tmp_dir, filename="resumed.dat", num_connections=4)
    worker = DownloadWorker(task, on_update=lambda t: None, on_finished=lambda t: None)
    worker.start()

    # Let it get going, then pause mid-flight.
    time.sleep(0.15)
    worker.request_pause()
    wait_for(worker, timeout=30)

    assert task.status in (Status.PAUSED, Status.COMPLETED), f"status={task.status} error={task.error}"
    downloaded_at_pause = task.downloaded_bytes
    print(f"paused with {downloaded_at_pause} / {task.total_size} bytes")

    if task.status == Status.COMPLETED:
        print("download finished before pause took effect (too fast); skipping resume assertions")
        return

    assert os.path.exists(task.part_meta_path)

    # Resume: reuse the same task object with its saved segment progress,
    # exactly like the manager does after reloading from downloads.json.
    task.status = Status.QUEUED
    worker2 = DownloadWorker(task, on_update=lambda t: None, on_finished=lambda t: None)
    worker2.start()
    wait_for(worker2, timeout=60)

    assert task.status == Status.COMPLETED, f"status={task.status} error={task.error}"
    assert task.downloaded_bytes >= downloaded_at_pause, "resume should not lose already-downloaded bytes"
    assert os.path.getsize(task.dest_path) == task.total_size
    print("PASS: paused, resumed, and completed with correct final size")


def test_checksum_matches_direct_download(tmp_dir):
    print("== test_checksum_matches_direct_download ==")
    import requests
    direct = requests.get(TEST_URL, timeout=30).content
    direct_hash = hashlib.sha256(direct).hexdigest()

    task = DownloadTask(url=TEST_URL, dest_folder=tmp_dir, filename="checksum.dat", num_connections=6)
    worker = DownloadWorker(task, on_update=lambda t: None, on_finished=lambda t: None)
    worker.start()
    wait_for(worker)
    assert task.status == Status.COMPLETED, f"status={task.status} error={task.error}"

    with open(task.dest_path, "rb") as f:
        segmented_hash = hashlib.sha256(f.read()).hexdigest()

    assert segmented_hash == direct_hash, "segmented download content must match a plain single-shot download"
    print("PASS: segmented multi-connection download byte-for-byte matches direct download")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_full_download(tmp_dir)
        test_pause_resume(tmp_dir)
        test_checksum_matches_direct_download(tmp_dir)
    print("\nALL TESTS PASSED")
